"""CodeBuild batch entry point for local index publishing."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import boto3
from botocore.exceptions import ClientError

from ingest_entities import _download_monthly, _first_sunday, publish_daily, publish_monthly
from ingest_opportunities import _download, publish, publish_poll


def run() -> dict:
    dataset = os.environ["DATASET"]
    bucket = os.environ["LOCAL_INDEX_BUCKET"]
    project = os.environ["PROJECT_NAME"]
    environment = os.environ["APP_ENV"]
    key_parameter = f"/{project}/{environment}/SamApiKey"
    source_day = os.environ.get("SOURCE_DATE") or date.today().isoformat()
    if dataset == "opportunity-daily":
        with tempfile.TemporaryDirectory(prefix="govvue-opp-source-") as work:
            path = str(Path(work) / "ContractOpportunitiesFullCSV.csv")
            s3 = boto3.client("s3")
            raw_key = f"raw/opportunities/daily/{source_day}/active.csv"
            reused = False
            if os.environ.get("FORCE_BUILD") == "true":
                try:
                    s3.download_file(bucket, raw_key, path)
                    reused = True
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
                        raise
            if not reused:
                _download(path)
                s3.upload_file(
                    path, bucket, raw_key,
                    ExtraArgs={"ServerSideEncryption": "AES256"},
                )
            return publish(path, bucket, source_day)
    if dataset == "opportunity-poll":
        return publish_poll(
            bucket, key_parameter, os.environ["SAM_OPPORTUNITIES_API"],
            site_url=os.environ.get("SAM_SITE_BASE_URL", "https://sam.gov"),
        )
    if dataset == "entity-monthly":
        monthly_day = _first_sunday(date.fromisoformat(source_day)).isoformat()
        if source_day < monthly_day:
            return {"status": "not_due", "source_date": monthly_day}
        s3 = boto3.client("s3")
        try:
            current = json.loads(s3.get_object(
                Bucket=bucket, Key="indexes/entities/current.json"
            )["Body"].read())
        except s3.exceptions.NoSuchKey:
            current = {}
        if current.get("monthly_source_date") == monthly_day and os.environ.get("FORCE_BUILD") != "true":
            return {"status": "already_published", "source_date": monthly_day}
        with tempfile.TemporaryDirectory(prefix="govvue-entity-source-") as work:
            path = str(Path(work) / "monthly.zip")
            raw_key = f"raw/entities/monthly/{monthly_day}/public.zip"
            try:
                s3.download_file(bucket, raw_key, path)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
                    raise
                try:
                    _download_monthly(path, monthly_day, key_parameter)
                except HTTPError as http_exc:
                    if http_exc.code in {400, 404}:
                        return {"status": "not_available_yet", "source_date": monthly_day}
                    raise
                s3.upload_file(
                    path, bucket, raw_key,
                    ExtraArgs={"ServerSideEncryption": "AES256"},
                )
            return publish_monthly(bucket, monthly_day, path)
    if dataset == "entity-daily":
        with tempfile.TemporaryDirectory(prefix="govvue-entity-delta-") as work:
            path = str(Path(work) / "entities.json.gz")
            boto3.client("s3").download_file(
                bucket, f"raw/entities/daily/{source_day}.json.gz", path
            )
            return publish_daily(bucket, source_day, path)
    raise ValueError(f"Unsupported ingestion dataset: {dataset}")


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
