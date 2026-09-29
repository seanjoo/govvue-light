"""Build and publish the public active-opportunity index.

Example (batch worker):
  python -m ingest_opportunities --download --bucket BUCKET --source-date 2026-09-28
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import boto3

from local_index import MANIFEST_KEY
from local_index_builder import apply_delta, build_from_csv
from sam_client import search_opportunities
from types import SimpleNamespace


PUBLIC_CSV_URL = (
    "https://sam.gov/api/prod/fileextractservices/v1/api/download/"
    "Contract%20Opportunities/datagov/ContractOpportunitiesFullCSV.csv"
)


def _download(path: str) -> None:
    request = Request(PUBLIC_CSV_URL, headers={"User-Agent": "GovVue-Light/2.0"})
    with urlopen(request, timeout=120) as source, open(path, "wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)


def _hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _upload_index(s3, bucket: str, index_path: str, version: str) -> dict[str, str]:
    compressed = f"{index_path}.gz"
    with open(index_path, "rb") as source, gzip.open(compressed, "wb", compresslevel=1) as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
    key = f"indexes/opportunities/versions/{version}/opportunities.sqlite.gz"
    s3.upload_file(compressed, bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    return {"key": key, "sha256": _hash(index_path), "compression": "gzip"}


def _download_index(s3, bucket: str, manifest: dict, output_path: str) -> None:
    if manifest.get("compression") == "gzip":
        compressed = f"{output_path}.gz"
        s3.download_file(bucket, manifest["key"], compressed)
        with gzip.open(compressed, "rb") as source, open(output_path, "wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
    else:
        s3.download_file(bucket, manifest["key"], output_path)


def _source_row_count(index_path: str) -> int:
    with sqlite3.connect(f"file:{index_path}?mode=ro", uri=True) as db:
        return int(db.execute("SELECT COUNT(*) FROM opportunities WHERE active = 1").fetchone()[0])


def publish(csv_path: str, bucket: str, source_date: str, *, min_records: int = 1000) -> dict:
    source_date = date.fromisoformat(source_date).isoformat()
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    s3 = boto3.client("s3")
    previous_count = 0
    try:
        previous = json.loads(s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())
        previous_count = int(previous.get("raw_record_count") or previous.get("record_count") or 0)
    except s3.exceptions.NoSuchKey:
        pass
    required_count = max(min_records, int(previous_count * 0.7))
    with tempfile.TemporaryDirectory(prefix="govvue-opp-index-") as work:
        index_path = os.path.join(work, "opportunities.sqlite")
        count = build_from_csv(csv_path, index_path, min_records=required_count)
        raw_count = _source_row_count(index_path)
        artifact = _upload_index(s3, bucket, index_path, version)
        manifest = {
            "version": version,
            **artifact,
            "source_date": source_date,
            "snapshot_source_date": source_date,
            "record_count": count,
            "raw_record_count": raw_count,
            "superseded_record_count": raw_count - count,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        # S3 object PUT is atomic; the old manifest remains live until this succeeds.
        s3.put_object(
            Bucket=bucket,
            Key=MANIFEST_KEY,
            Body=json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
    return manifest


def publish_poll(bucket: str, sam_key_parameter: str, sam_api: str,
                 *, site_url: str = "https://sam.gov", min_records: int = 1000) -> dict:
    """Overlay active notices posted yesterday/today onto the current index."""
    s3 = boto3.client("s3")
    try:
        previous = json.loads(s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey as exc:
        raise ValueError("Run the active-opportunity full-file backfill first") from exc
    api_key = boto3.client("ssm").get_parameter(
        Name=sam_key_parameter, WithDecryption=True
    )["Parameter"]["Value"]
    config = SimpleNamespace(
        sam_api_key=api_key, sam_opportunities_api=sam_api,
        sam_site_base_url=site_url, sam_request_timeout_seconds=60,
    )
    now = datetime.now(timezone.utc)
    end = now.date()
    start = end - timedelta(days=1)
    params = {
        "postedFrom": start.strftime("%m/%d/%Y"),
        "postedTo": end.strftime("%m/%d/%Y"),
        "status": "active",
    }
    records: list[dict] = []
    page = 0
    while True:
        result = search_opportunities(params, page, config, 1000)
        records.extend(result["records"])
        page += 1
        if page * 1000 >= int(result["total_records"]):
            break
        if page >= 100:
            raise ValueError("Intraday opportunity poll exceeded 100 pages")
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="govvue-opp-poll-") as work:
        base = os.path.join(work, "base.sqlite")
        updated = os.path.join(work, "updated.sqlite")
        _download_index(s3, bucket, previous, base)
        if _hash(base) != previous["sha256"]:
            raise ValueError("Published opportunity index checksum mismatch")
        count = apply_delta(
            base, updated, records,
            min_records=max(min_records, int((previous.get("raw_record_count") or previous.get("record_count") or 0) * 0.7)),
        )
        raw_count = _source_row_count(updated)
        raw_key = f"raw/opportunities/polls/{stamp}.json.gz"
        s3.put_object(
            Bucket=bucket, Key=raw_key,
            Body=gzip.compress(json.dumps({"records": records}, separators=(",", ":")).encode("utf-8")),
            ContentType="application/json", ContentEncoding="gzip", ServerSideEncryption="AES256",
        )
        artifact = _upload_index(s3, bucket, updated, stamp)
        manifest = {
            "version": stamp, **artifact,
            "source_date": end.isoformat(), "record_count": count,
            "raw_record_count": raw_count,
            "superseded_record_count": raw_count - count,
            "snapshot_source_date": previous.get("snapshot_source_date") or previous["source_date"],
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source": "intraday_api",
        }
        s3.put_object(
            Bucket=bucket, Key=MANIFEST_KEY,
            Body=json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
            ContentType="application/json", ServerSideEncryption="AES256",
        )
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="Existing SAM public CSV file")
    source.add_argument("--download", action="store_true", help="Download current public CSV")
    parser.add_argument("--bucket", required=True, help="Private index bucket")
    parser.add_argument("--source-date", default=date.today().isoformat())
    parser.add_argument("--min-records", type=int, default=1000)
    args = parser.parse_args()
    if args.min_records < 1:
        parser.error("--min-records must be positive")
    if args.download:
        with tempfile.TemporaryDirectory(prefix="govvue-opp-source-") as work:
            csv_path = str(Path(work) / "ContractOpportunitiesFullCSV.csv")
            _download(csv_path)
            manifest = publish(csv_path, args.bucket, args.source_date, min_records=args.min_records)
    else:
        manifest = publish(args.csv, args.bucket, args.source_date, min_records=args.min_records)
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
