"""Daily low-noise alert for failed or stale local ingestion."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

import boto3


def _manifest(s3, bucket: str, kind: str) -> dict:
    try:
        return json.loads(s3.get_object(
            Bucket=bucket, Key=f"indexes/{kind}/current.json",
        )["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {}


def issues() -> list[str]:
    today = date.today()
    s3 = boto3.client("s3")
    bucket = os.environ["LOCAL_INDEX_BUCKET"]
    problems: list[str] = []
    for kind, max_age in (("opportunities", 1), ("entities", 2)):
        manifest = _manifest(s3, bucket, kind)
        try:
            source_date = date.fromisoformat(str(manifest["source_date"]))
        except (KeyError, ValueError):
            problems.append(f"{kind.capitalize()} index is not published")
            continue
        if source_date < today - timedelta(days=max_age):
            problems.append(f"{kind.capitalize()} index is stale (source {source_date})")
        if kind == "opportunities":
            try:
                snapshot_date = date.fromisoformat(str(
                    manifest.get("snapshot_source_date") or manifest["source_date"]
                ))
            except ValueError:
                problems.append("Opportunity full snapshot date is invalid")
            else:
                if snapshot_date < today - timedelta(days=1):
                    problems.append(f"Opportunity full snapshot is stale ({snapshot_date})")
        if kind == "entities":
            try:
                monthly_date = date.fromisoformat(str(manifest["monthly_source_date"]))
            except (KeyError, ValueError):
                problems.append("Entity monthly replacement date is missing")
            else:
                if monthly_date < today - timedelta(days=40):
                    problems.append(f"Entity monthly replacement is stale ({monthly_date})")
    dlq = boto3.client("sqs").get_queue_attributes(
        QueueUrl=os.environ["INGEST_DLQ_URL"],
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]
    dead_letters = int(dlq.get("ApproximateNumberOfMessages", "0"))
    if dead_letters:
        problems.append(f"Ingestion dead-letter queue contains {dead_letters} message(s)")
    codebuild = boto3.client("codebuild")
    ids = codebuild.list_builds_for_project(
        projectName=os.environ["INGEST_BUILD_PROJECT"], sortOrder="DESCENDING",
    ).get("ids", [])[:10]
    if ids:
        recent = codebuild.batch_get_builds(ids=ids).get("builds", [])
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        latest_by_dataset: dict[str, dict] = {}
        for build in sorted(recent, key=lambda item: item.get("startTime") or cutoff, reverse=True):
            variables = build.get("environment", {}).get("environmentVariables", [])
            dataset = next((item.get("value") for item in variables if item.get("name") == "DATASET"), "")
            if dataset and dataset not in latest_by_dataset:
                latest_by_dataset[dataset] = build
        for build in latest_by_dataset.values():
            started = build.get("startTime")
            if started and started >= cutoff and build.get("buildStatus") in {"FAILED", "FAULT", "TIMED_OUT", "STOPPED"}:
                problems.append(
                    f"Ingestion build {build.get('id', '')} ended {build['buildStatus']}"
                )
    return problems


def lambda_handler(event, context):
    problems = issues()
    if not problems:
        return {"status": "healthy", "alerts": 0}
    admin_url = os.environ["ADMIN_URL"].rstrip("/")
    body = (
        "GovVue Light ingestion needs attention:\n\n"
        + "\n".join(f"- {problem}" for problem in problems)
        + f"\n\nReview jobs and retry safely at {admin_url}/\n"
    )
    boto3.client("sesv2").send_email(
        FromEmailAddress=os.environ["NOTIFICATION_FROM_EMAIL"],
        Destination={"ToAddresses": [os.environ["OPS_ALERT_EMAIL"]]},
        Content={"Simple": {
            "Subject": {"Data": "GovVue Light ingestion alert"},
            "Body": {"Text": {"Data": body}},
        }},
    )
    return {"status": "alerted", "alerts": len(problems)}
