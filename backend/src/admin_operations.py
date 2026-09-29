"""Admin-only ingestion health, controlled job dispatch, and AWS cost summary."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone

import boto3

import local_index
import local_entity_index


DATASETS = {"opportunity-daily", "opportunity-poll", "entity-monthly", "entity-daily"}


def _manifest(s3, bucket: str, kind: str) -> dict:
    try:
        value = json.loads(s3.get_object(
            Bucket=bucket, Key=f"indexes/{kind}/current.json"
        )["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"status": "not_published"}
    return {key: value.get(key) for key in (
        "version", "source_date", "snapshot_source_date", "monthly_source_date", "record_count",
        "published_at", "key", "source",
    ) if key in value} | {"status": "published"}


def overview() -> dict:
    bucket = os.environ["LOCAL_INDEX_BUCKET"]
    project = os.environ["INGEST_BUILD_PROJECT"]
    s3 = boto3.client("s3")
    codebuild = boto3.client("codebuild")
    sqs = boto3.client("sqs")
    scheduler = boto3.client("scheduler")
    build_ids = codebuild.list_builds_for_project(
        projectName=project, sortOrder="DESCENDING"
    ).get("ids", [])[:10]
    builds = codebuild.batch_get_builds(ids=build_ids).get("builds", []) if build_ids else []
    jobs = []
    for item in builds:
        overrides = item.get("environment", {}).get("environmentVariables", [])
        dataset = next((value.get("value") for value in overrides if value.get("name") == "DATASET"), "")
        jobs.append({
            "id": item.get("id"), "dataset": dataset,
            "status": item.get("buildStatus"),
            "started_at": item.get("startTime").isoformat() if item.get("startTime") else "",
            "finished_at": item.get("endTime").isoformat() if item.get("endTime") else "",
            "logs_url": item.get("logs", {}).get("deepLink", ""),
        })
    queue = sqs.get_queue_attributes(
        QueueUrl=os.environ["INGEST_QUEUE_URL"],
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    dead_letters = sqs.get_queue_attributes(
        QueueUrl=os.environ["INGEST_DLQ_URL"],
        AttributeNames=["ApproximateNumberOfMessages"],
    )["Attributes"]
    schedule_names = {
        "opportunity-daily": "opportunity-daily",
        "opportunity-poll": "opportunity-poll",
        "entity-monthly": "entity-monthly",
        "entity-daily": "entity-daily",
        "ingest-health": "ingest-health",
    }
    schedules = {}
    prefix = os.environ["INGEST_SCHEDULE_PREFIX"]
    for dataset, suffix in schedule_names.items():
        item = scheduler.get_schedule(Name=f"{prefix}-{suffix}")
        schedules[dataset] = {
            "state": item.get("State"),
            "expression": item.get("ScheduleExpression"),
            "timezone": item.get("ScheduleExpressionTimezone"),
        }
    return {
        "indexes": {
            "opportunities": _manifest(s3, bucket, "opportunities"),
            "entities": _manifest(s3, bucket, "entities"),
        },
        "jobs": jobs,
        "queue": {
            "waiting": int(queue.get("ApproximateNumberOfMessages", 0)),
            "running": int(queue.get("ApproximateNumberOfMessagesNotVisible", 0)),
            "dead_letters": int(dead_letters.get("ApproximateNumberOfMessages", 0)),
        },
        "schedules": schedules,
        "local_search_enabled": os.environ.get("LOCAL_SEARCH_ENABLED") == "true",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def start(dataset: str) -> dict:
    if dataset not in DATASETS:
        raise ValueError("Unknown ingestion job")
    body = {"action": "start"} if dataset == "entity-daily" else {
        "action": "build", "dataset": dataset,
        "force": dataset == "entity-monthly",
    }
    result = boto3.client("sqs").send_message(
        QueueUrl=os.environ["INGEST_QUEUE_URL"],
        MessageBody=json.dumps(body, separators=(",", ":")),
    )
    return {"queued": True, "dataset": dataset, "message_id": result["MessageId"]}


def validate_index(kind: str) -> dict:
    """Exercise the published search path even before public cutover."""
    started = time.monotonic()
    if kind == "opportunities":
        result = local_index.search({"posted_within": "30"}, 1, 1)
    elif kind == "entities":
        result = local_entity_index.search(
            {"country_code": "USA", "primary_naics": "333248", "exclusion_status": "N"},
            1, 1,
        )
    else:
        raise ValueError("Unknown local index kind")
    return {
        "kind": kind, "source": result["source"],
        "source_date": result["source_date"],
        "index_version": result["index_version"],
        "total_records": result["total_records"],
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def costs() -> dict:
    """Current and preceding month, scoped to this AWS account.

    Cost Explorer is account-level; service totals can include other workloads.
    Its data may lag by a day or more. The UI labels both limitations.
    """
    today = date.today()
    first = today.replace(day=1)
    previous = (first - timedelta(days=1)).replace(day=1)
    result = boto3.client("ce", region_name="us-east-1").get_cost_and_usage(
        TimePeriod={"Start": previous.isoformat(), "End": (today + timedelta(days=1)).isoformat()},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    months = []
    for period in result.get("ResultsByTime", []):
        services = sorted(({
            "name": group["Keys"][0],
            "amount_usd": float(group["Metrics"]["UnblendedCost"]["Amount"]),
        } for group in period.get("Groups", [])), key=lambda item: item["amount_usd"], reverse=True)
        months.append({
            "month": period["TimePeriod"]["Start"][:7],
            "total_usd": round(sum(item["amount_usd"] for item in services), 2),
            "services": services,
            "estimated": period.get("Estimated", False),
        })
    months.sort(key=lambda item: item["month"], reverse=True)
    return {"months": months, "scope": "AWS account (not GovVue-only)", "currency": "USD"}
