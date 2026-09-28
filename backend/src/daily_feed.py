"""SQS-driven, one-SAM-page-per-invocation daily feed fetcher."""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError

import storage
import local_index
from runtime_config import get_runtime_config
from sam_client import build_search_parameters, search_opportunities


_s3 = boto3.client("s3")
_sqs = boto3.client("sqs")
LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def _feed_key(run_date: str, page_index: int) -> str:
    return f"daily-feed/{run_date}/pages/{page_index:06d}.json.gz"


def _run_dates(message: dict[str, Any]) -> tuple[str, str]:
    timezone = ZoneInfo(os.environ.get("FEED_TIMEZONE", "America/New_York"))
    today = datetime.now(timezone).date()
    run_date = str(message.get("run_date") or today.isoformat())
    end = datetime.strptime(run_date, "%Y-%m-%d").date()
    return run_date, (end - timedelta(days=1)).isoformat()


def _meta(run_date: str) -> dict[str, Any] | None:
    return storage.table().get_item(
        Key={"PK": f"DAILY_FEED#{run_date}", "SK": "META"}
    ).get("Item")


def _ensure_run(
    run_date: str,
    posted_from: str,
    retention_days: int,
    run_id: str,
    trigger: str,
    pinned_index: dict[str, Any] | None = None,
) -> None:
    now = int(time.time())
    try:
        storage.table().put_item(
            Item={
                "PK": f"DAILY_FEED#{run_date}",
                "SK": "META",
                "entityType": "dailyFeed",
                "runDate": run_date,
                "postedFrom": posted_from,
                "postedTo": run_date,
                "status": "FETCHING",
                "runId": run_id,
                "trigger": trigger,
                "indexKey": str((pinned_index or {}).get("key") or ""),
                "indexSha256": str((pinned_index or {}).get("sha256") or ""),
                "createdAt": now,
                "expiresAt": now + retention_days * 86400,
            },
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise


def _send_page(
    run_date: str,
    page_index: int,
    run_id: str,
    trigger: str,
    targets: list[dict[str, str]] | None = None,
) -> None:
    body: dict[str, Any] = {
        "action": "page",
        "run_date": run_date,
        "page_index": page_index,
        "run_id": run_id,
        "trigger": trigger,
    }
    if targets is not None:
        body["targets"] = targets
    _sqs.send_message(
        QueueUrl=os.environ["FEED_QUEUE_URL"],
        MessageBody=json.dumps(body, separators=(",", ":")),
        MessageGroupId="daily-feed",
    )


def _start(message: dict[str, Any]) -> None:
    config = get_runtime_config()
    run_date, posted_from = _run_dates(message)
    force = message.get("force") is True
    trigger = str(message.get("trigger") or ("manual" if force else "scheduled"))
    raw_targets = message.get("targets")
    targets = [
        {
            "user_id": str(item.get("user_id") or ""),
            "notification_id": str(item.get("notification_id") or ""),
        }
        for item in raw_targets
        if isinstance(item, dict)
        and item.get("user_id")
        and item.get("notification_id")
    ] if isinstance(raw_targets, list) else None
    run_id = str(message.get("request_id") or f"{run_date}-{time.time_ns()}")
    pinned_index = None
    if os.environ.get("LOCAL_SEARCH_ENABLED") == "true":
        try:
            _, pinned_index = local_index.current_index()
        except local_index.LocalIndexUnavailable as exc:
            LOGGER.warning("Local index unavailable for daily feed; using SAM.gov: %s", exc)
    existing = _meta(run_date)
    if existing and existing.get("status") == "FETCHING":
        return
    if existing and existing.get("status") == "COMPLETE" and not force:
        # A scheduled run may follow an early manual run on the same date. In
        # that case refresh at the normal time; otherwise the daily run is done.
        if existing.get("trigger") != "manual":
            return
    if existing:
        storage.table().update_item(
            Key={"PK": f"DAILY_FEED#{run_date}", "SK": "META"},
            UpdateExpression=(
                "SET #status = :fetching, postedFrom = :posted_from, "
                "postedTo = :posted_to, runId = :run_id, #trigger = :trigger, "
                "indexKey = :index_key, indexSha256 = :index_sha, "
                "updatedAt = :now REMOVE completedAt, lastPageCompleted, totalRecords, totalPages"
            ),
            ExpressionAttributeNames={"#status": "status", "#trigger": "trigger"},
            ExpressionAttributeValues={
                ":fetching": "FETCHING",
                ":posted_from": posted_from,
                ":posted_to": run_date,
                ":run_id": run_id,
                ":trigger": trigger,
                ":now": int(time.time()),
                ":index_key": str((pinned_index or {}).get("key") or ""),
                ":index_sha": str((pinned_index or {}).get("sha256") or ""),
            },
        )
    else:
        _ensure_run(
            run_date,
            posted_from,
            config.daily_feed_retention_days,
            run_id,
            trigger,
            pinned_index,
        )
    _send_page(run_date, 0, run_id, trigger, targets)


def _fan_out(
    run_date: str,
    total_records: int,
    total_pages: int,
    targets: list[dict[str, str]] | None = None,
) -> list[tuple[str, str]]:
    target_keys = None if targets is None else {
        (item["user_id"], item["notification_id"])
        for item in targets
    }
    processed: list[tuple[str, str]] = []
    for item in storage.list_enabled_daily_notifications():
        key = (str(item["userId"]), str(item["notificationId"]))
        if target_keys is not None and key not in target_keys:
            continue
        message = {
            "user_id": key[0],
            "notification_id": key[1],
            "name": str(item["name"]),
            "criteria": item.get("criteria") or {},
            "recipient_email": str(item.get("recipientEmail") or ""),
            "run_date": run_date,
            "total_records": total_records,
            "total_pages": total_pages,
        }
        _sqs.send_message(
            QueueUrl=os.environ["NOTIFICATION_QUEUE_URL"],
            MessageBody=json.dumps(message, separators=(",", ":")),
        )
        processed.append(key)
    return processed


def _tick(message: dict[str, Any]) -> None:
    config = get_runtime_config()
    timezone = ZoneInfo(os.environ.get("FEED_TIMEZONE", "America/New_York"))
    now = datetime.now(timezone)
    run_date = now.date().isoformat()
    current_minutes = now.hour * 60 + now.minute
    if os.environ.get("LOCAL_SEARCH_ENABLED") == "true":
        try:
            manifest = local_index.current_manifest()
        except local_index.LocalIndexUnavailable as exc:
            LOGGER.warning("Waiting for the daily opportunity index: %s", exc)
            return
        if str(manifest["source_date"]) < run_date:
            LOGGER.info("Waiting for the %s opportunity snapshot before scheduled notifications", run_date)
            return
    targets: list[dict[str, str]] = []
    for item in storage.list_enabled_daily_notifications():
        if str(item.get("lastScheduledRunDate") or "") == run_date:
            continue
        schedule_time = str(
            item.get("scheduleTime") or config.daily_notification_default_time
        )
        try:
            hour, minute = (int(part) for part in schedule_time.split(":"))
        except (TypeError, ValueError):
            LOGGER.warning(
                "Skipping notification %s with invalid schedule %s",
                item.get("notificationId"),
                schedule_time,
            )
            continue
        scheduled_minutes = hour * 60 + minute
        # Keep due notifications pending until the daily index is published.
        # The lastScheduledRunDate check above prevents repeat sends.
        if current_minutes >= scheduled_minutes:
            targets.append(
                {
                    "user_id": str(item["userId"]),
                    "notification_id": str(item["notificationId"]),
                }
            )
    if not targets:
        return
    _start(
        {
            "force": True,
            "trigger": "scheduled",
            "run_date": run_date,
            "request_id": str(message.get("request_id") or f"tick-{time.time_ns()}"),
            "targets": targets,
        }
    )


def _page(message: dict[str, Any]) -> None:
    config = get_runtime_config()
    run_date = str(message["run_date"])
    page_index = max(0, int(message.get("page_index") or 0))
    meta = _meta(run_date)
    if not meta:
        raise RuntimeError(f"Daily feed run {run_date} does not exist")
    if meta.get("status") == "COMPLETE":
        return
    run_id = str(message.get("run_id") or "")
    if meta.get("runId") and run_id != str(meta["runId"]):
        LOGGER.info("Ignoring stale daily feed page for %s", run_date)
        return

    if meta.get("indexKey"):
        result = local_index.feed_page(
            str(meta["indexKey"]), str(meta["indexSha256"]),
            str(meta["postedFrom"]), str(meta["postedTo"]),
            page_index, config.daily_feed_page_size,
        )
    else:
        params = build_search_parameters(
            {"posted_from": str(meta["postedFrom"]), "posted_to": str(meta["postedTo"])},
            config,
        )
        result = search_opportunities(params, page_index, config, config.daily_feed_page_size)
    records = result["records"]
    total_records = int(result["total_records"])
    total_pages = max(1, math.ceil(total_records / config.daily_feed_page_size))
    payload = {
        "run_date": run_date,
        "page_index": page_index,
        "page_size": config.daily_feed_page_size,
        "total_records": total_records,
        "records": records,
    }
    _s3.put_object(
        Bucket=os.environ["DAILY_FEED_BUCKET"],
        Key=_feed_key(run_date, page_index),
        Body=gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ContentType="application/json",
        ContentEncoding="gzip",
        ServerSideEncryption="AES256",
    )
    now = int(time.time())
    storage.table().put_item(
        Item={
            "PK": f"DAILY_FEED#{run_date}",
            "SK": f"PAGE#{page_index:06d}",
            "entityType": "dailyFeedPage",
            "pageIndex": page_index,
            "recordCount": len(records),
            "s3Key": _feed_key(run_date, page_index),
            "completedAt": now,
            "expiresAt": now + config.daily_feed_retention_days * 86400,
        }
    )
    storage.table().update_item(
        Key={"PK": f"DAILY_FEED#{run_date}", "SK": "META"},
        UpdateExpression="SET totalRecords = :records, totalPages = :pages, lastPageCompleted = :page, updatedAt = :now",
        ExpressionAttributeValues={
            ":records": total_records,
            ":pages": total_pages,
            ":page": page_index,
            ":now": now,
        },
    )

    if page_index + 1 < total_pages:
        _send_page(
            run_date,
            page_index + 1,
            run_id,
            str(message.get("trigger") or "scheduled"),
            message.get("targets") if isinstance(message.get("targets"), list) else None,
        )
        return

    targets = message.get("targets") if isinstance(message.get("targets"), list) else None
    processed = _fan_out(run_date, total_records, total_pages, targets)
    if str(message.get("trigger") or "scheduled") == "scheduled" and targets is not None:
        for user_id, notification_id in processed:
            storage.mark_daily_notification_scheduled(
                user_id, notification_id, run_date
            )
    storage.table().update_item(
        Key={"PK": f"DAILY_FEED#{run_date}", "SK": "META"},
        UpdateExpression="SET #status = :complete, completedAt = :now",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":complete": "COMPLETE", ":now": int(time.time())},
    )


def _process(message: dict[str, Any]) -> None:
    action = str(message.get("action") or "start")
    if action == "start":
        _start(message)
    elif action == "tick":
        _tick(message)
    elif action == "page":
        _page(message)
    else:
        raise ValueError(f"Unsupported daily feed action: {action}")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records") or []:
        try:
            _process(json.loads(record.get("body") or "{}"))
        except Exception:
            LOGGER.exception("Daily feed message failed")
            failures.append({"itemIdentifier": record.get("messageId") or "unknown"})
    return {"batchItemFailures": failures}
