"""Publish monthly public entity snapshots and daily JSON-export updates.

The monthly build replays every daily file newer than the SAM snapshot before
publishing. S3 keeps the previous immutable index and versioned manifest for
rollback. Run in a batch worker, not a Lambda invocation.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import boto3

from local_entity_index import apply_daily, build_monthly
from sam_entity_client import normalize_entity


MANIFEST_KEY = "indexes/entities/current.json"
EXTRACTS_API = "https://api.sam.gov/data-services/v1/extracts"


def _first_sunday(month: date) -> date:
    first = month.replace(day=1)
    return first + timedelta(days=(6 - first.weekday()) % 7)


def _hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _records(path: str):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    if isinstance(payload, dict):
        items = payload.get("entityData") or payload.get("entities") or []
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("Unexpected entity export JSON structure")
    if not isinstance(items, list):
        raise ValueError("Entity export records must be a list")
    site = SimpleNamespace(sam_site_base_url="https://sam.gov")
    for raw in items:
        if isinstance(raw, dict):
            yield normalize_entity(raw, site)


def _daily_keys(s3, bucket: str, after_date: str) -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="raw/entities/daily/"):
        for item in page.get("Contents") or []:
            key = str(item["Key"])
            name = key.rsplit("/", 1)[-1]
            file_date = name.split(".", 1)[0]
            if file_date > after_date and name.endswith(".json.gz"):
                keys.append(key)
    return sorted(keys)


def _download_monthly(path: str, source_date: str, ssm_parameter: str) -> None:
    api_key = boto3.client("ssm").get_parameter(
        Name=ssm_parameter, WithDecryption=True
    )["Parameter"]["Value"]
    filename = f"SAM_PUBLIC_UTF-8_MONTHLY_V2_{source_date.replace('-', '')}.ZIP"
    request = Request(
        f"{EXTRACTS_API}?{urlencode({'fileName': filename, 'api_key': api_key})}",
        headers={"User-Agent": "GovVue-Light/2.0"},
    )
    with urlopen(request, timeout=120) as source, open(path, "wb") as target:
        while chunk := source.read(1024 * 1024):
            target.write(chunk)


def _manifest(s3, bucket: str) -> dict:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=MANIFEST_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {}


def _download_index(s3, bucket: str, manifest: dict, output_path: str) -> None:
    if manifest.get("compression") == "gzip":
        compressed = f"{output_path}.gz"
        s3.download_file(bucket, manifest["key"], compressed)
        with gzip.open(compressed, "rb") as source, open(output_path, "wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
    else:
        s3.download_file(bucket, manifest["key"], output_path)


def _publish(s3, bucket: str, index_path: str, source_date: str,
             monthly_source_date: str, count: int) -> dict:
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"indexes/entities/versions/{version}/entities.sqlite.gz"
    compressed_path = f"{index_path}.gz"
    with open(index_path, "rb") as source, gzip.open(compressed_path, "wb", compresslevel=1) as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
    s3.upload_file(compressed_path, bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    manifest = {
        "version": version, "key": key, "sha256": _hash(index_path),
        "compression": "gzip",
        "source_date": source_date, "monthly_source_date": monthly_source_date,
        "record_count": count,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    s3.put_object(
        Bucket=bucket, Key=MANIFEST_KEY,
        Body=json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
        ContentType="application/json", ServerSideEncryption="AES256",
    )
    return manifest


def publish_monthly(bucket: str, source_date: str, zip_path: str,
                    *, min_records: int = 1000) -> dict:
    source_date = date.fromisoformat(source_date).isoformat()
    s3 = boto3.client("s3")
    old = _manifest(s3, bucket)
    required = max(min_records, int(old.get("record_count", 0) * 0.7))
    with tempfile.TemporaryDirectory(prefix="govvue-entity-monthly-") as work:
        baseline = os.path.join(work, "monthly.sqlite")
        count = build_monthly(zip_path, baseline, min_records=required)
        latest_path = baseline
        latest_date = source_date
        for number, key in enumerate(_daily_keys(s3, bucket, source_date), 1):
            day = key.rsplit("/", 1)[-1].split(".", 1)[0]
            raw_path = os.path.join(work, f"delta-{number}.json.gz")
            output_path = os.path.join(work, f"replay-{number}.sqlite")
            s3.download_file(bucket, key, raw_path)
            count = apply_daily(latest_path, output_path, _records(raw_path), min_records=required)
            if latest_path != baseline:
                Path(latest_path).unlink(missing_ok=True)
            latest_path = output_path
            latest_date = day
        return _publish(s3, bucket, latest_path, latest_date, source_date, count)


def publish_daily(bucket: str, source_date: str, json_path: str,
                  *, min_records: int = 1000) -> dict:
    source_date = date.fromisoformat(source_date).isoformat()
    s3 = boto3.client("s3")
    previous = _manifest(s3, bucket)
    if not previous:
        raise ValueError("Run the monthly entity backfill before daily updates")
    if source_date <= str(previous.get("source_date") or ""):
        raise ValueError("Daily entity update is not newer than the published index")
    required = max(min_records, int(previous.get("record_count", 0) * 0.7))
    with tempfile.TemporaryDirectory(prefix="govvue-entity-daily-") as work:
        base = os.path.join(work, "base.sqlite")
        output = os.path.join(work, "updated.sqlite")
        _download_index(s3, bucket, previous, base)
        if _hash(base) != previous["sha256"]:
            raise ValueError("Published entity index checksum mismatch")
        count = apply_daily(base, output, _records(json_path), min_records=required)
        # The raw file is durable before publishing, so a concurrent monthly
        # replacement can replay it rather than losing this update.
        raw_key = f"raw/entities/daily/{source_date}.json.gz"
        if json_path.endswith(".gz"):
            s3.upload_file(json_path, bucket, raw_key, ExtraArgs={"ServerSideEncryption": "AES256"})
        else:
            with open(json_path, "rb") as source:
                body = gzip.compress(source.read())
            s3.put_object(Bucket=bucket, Key=raw_key, Body=body, ServerSideEncryption="AES256")
        return _publish(
            s3, bucket, output, source_date,
            str(previous.get("monthly_source_date") or previous["source_date"]), count,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--monthly-zip")
    mode.add_argument("--download-monthly", action="store_true")
    mode.add_argument("--daily-json")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--source-date")
    parser.add_argument("--sam-key-parameter")
    parser.add_argument("--min-records", type=int, default=1000)
    args = parser.parse_args()
    s3 = boto3.client("s3")
    if args.daily_json:
        source_date = args.source_date or date.today().isoformat()
        result = publish_daily(args.bucket, source_date, args.daily_json, min_records=args.min_records)
    else:
        source_date = args.source_date or _first_sunday(date.today()).isoformat()
        if args.download_monthly:
            if not args.sam_key_parameter:
                parser.error("--sam-key-parameter is required with --download-monthly")
            with tempfile.TemporaryDirectory(prefix="govvue-entity-zip-") as work:
                path = os.path.join(work, "monthly.zip")
                _download_monthly(path, source_date, args.sam_key_parameter)
                s3.upload_file(
                    path, args.bucket,
                    f"raw/entities/monthly/{source_date}/public.zip",
                    ExtraArgs={"ServerSideEncryption": "AES256"},
                )
                result = publish_monthly(args.bucket, source_date, path, min_records=args.min_records)
        else:
            result = publish_monthly(args.bucket, source_date, args.monthly_zip, min_records=args.min_records)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
