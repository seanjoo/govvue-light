"""DynamoDB user state and S3 search cache helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
import base64
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


_table = None
_s3 = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["STATE_TABLE"])
    return _table


def s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def cache_key(namespace: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{namespace}/{digest}.json"


def get_cached(key: str, ttl_seconds: int) -> dict[str, Any] | None:
    try:
        response = s3_client().get_object(Bucket=os.environ["SEARCH_CACHE_BUCKET"], Key=key)
        payload = json.loads(response["Body"].read().decode("utf-8"))
        if int(payload.get("cached_at", 0)) + ttl_seconds < int(time.time()):
            return None
        return payload.get("data")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            return None
        raise


def put_cached(key: str, data: dict[str, Any]) -> None:
    payload = json.dumps(
        {"cached_at": int(time.time()), "data": data},
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    s3_client().put_object(
        Bucket=os.environ["SEARCH_CACHE_BUCKET"],
        Key=key,
        Body=payload,
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )


def _query(user_id: str, prefix: str) -> list[dict[str, Any]]:
    response = table().query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with(prefix),
        ScanIndexForward=False,
    )
    return response.get("Items", [])


def list_saved_opportunities(user_id: str) -> list[dict[str, Any]]:
    return [item["opportunity"] | {"saved_at": item["savedAt"]} for item in _query(user_id, "SAVED_OPP#")]


def save_opportunity(user_id: str, opportunity: dict[str, Any]) -> None:
    notice_id = str(opportunity.get("notice_id") or "").strip()
    if not notice_id:
        raise ValueError("notice_id is required")
    compact = {key: value for key, value in opportunity.items() if key not in {"description", "_description_url"}}
    table().put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"SAVED_OPP#{notice_id}",
            "entityType": "savedOpportunity",
            "savedAt": int(time.time()),
            "opportunity": compact,
        }
    )


def delete_saved_opportunities(user_id: str, notice_ids: list[str]) -> int:
    clean_ids = sorted({value.strip() for value in notice_ids if value.strip()})[:100]
    with table().batch_writer() as batch:
        for notice_id in clean_ids:
            batch.delete_item(Key={"PK": f"USER#{user_id}", "SK": f"SAVED_OPP#{notice_id}"})
    return len(clean_ids)


def list_saved_entities(user_id: str) -> list[dict[str, Any]]:
    return [
        item["entity"] | {"saved_at": item["savedAt"]}
        for item in _query(user_id, "SAVED_ENTITY#")
    ]


def save_entity(user_id: str, entity: dict[str, Any]) -> None:
    uei = str(entity.get("uei") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{12}", uei):
        raise ValueError("A valid 12-character UEI is required")
    compact = dict(entity)
    compact["uei"] = uei
    compact.pop("saved_at", None)
    table().put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"SAVED_ENTITY#{uei}",
            "entityType": "savedEntity",
            "savedAt": int(time.time()),
            "entity": compact,
        }
    )


def delete_saved_entities(user_id: str, ueis: list[str]) -> int:
    clean_ueis = sorted(
        {
            value.strip().upper()
            for value in ueis
            if re.fullmatch(r"[A-Za-z0-9]{12}", value.strip())
        }
    )[:100]
    with table().batch_writer() as batch:
        for uei in clean_ueis:
            batch.delete_item(
                Key={"PK": f"USER#{user_id}", "SK": f"SAVED_ENTITY#{uei}"}
            )
    return len(clean_ueis)


def list_saved_searches(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": item["searchId"],
            "name": item["name"],
            "criteria": item["criteria"],
            "created_at": item["createdAt"],
        }
        for item in _query(user_id, "SAVED_SEARCH#")
    ]


def save_search(user_id: str, name: str, criteria: dict[str, Any]) -> dict[str, Any]:
    search_id = uuid.uuid4().hex
    created_at = int(time.time())
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"SAVED_SEARCH#{search_id}",
        "entityType": "savedSearch",
        "searchId": search_id,
        "name": name.strip()[:100],
        "criteria": criteria,
        "createdAt": created_at,
    }
    table().put_item(Item=item)
    return {"id": search_id, "name": item["name"], "criteria": criteria, "created_at": created_at}


def delete_saved_search(user_id: str, search_id: str) -> None:
    table().delete_item(Key={"PK": f"USER#{user_id}", "SK": f"SAVED_SEARCH#{search_id}"})


def list_saved_entity_searches(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": item["searchId"],
            "name": item["name"],
            "criteria": item["criteria"],
            "created_at": item["createdAt"],
        }
        for item in _query(user_id, "SAVED_ENTITY_SEARCH#")
    ]


def save_entity_search(
    user_id: str, name: str, criteria: dict[str, str]
) -> dict[str, Any]:
    search_id = uuid.uuid4().hex
    created_at = int(time.time())
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"SAVED_ENTITY_SEARCH#{search_id}",
        "entityType": "savedEntitySearch",
        "searchId": search_id,
        "name": name.strip()[:100],
        "criteria": criteria,
        "createdAt": created_at,
    }
    table().put_item(Item=item)
    return {
        "id": search_id,
        "name": item["name"],
        "criteria": criteria,
        "created_at": created_at,
    }


def delete_saved_entity_search(user_id: str, search_id: str) -> None:
    table().delete_item(
        Key={"PK": f"USER#{user_id}", "SK": f"SAVED_ENTITY_SEARCH#{search_id}"}
    )


def _notification_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["notificationId"],
        "name": item["name"],
        "criteria": item.get("criteria") or {},
        "enabled": bool(item.get("enabled", True)),
        "schedule_time": str(
            item.get("scheduleTime")
            or os.environ.get("DEFAULT_NOTIFICATION_TIME", "06:15")
        ),
        "recipient_email": item.get("recipientEmail") or "",
        "created_at": int(item.get("createdAt") or 0),
        "updated_at": int(item.get("updatedAt") or 0),
    }


def list_daily_notifications(user_id: str) -> list[dict[str, Any]]:
    return [_notification_from_item(item) for item in _query(user_id, "DAILY_NOTIFICATION#")]


def get_daily_notification(user_id: str, notification_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"PK": f"USER#{user_id}", "SK": f"DAILY_NOTIFICATION#{notification_id}"}
    )
    item = response.get("Item")
    return _notification_from_item(item) if item else None


def save_daily_notification(
    user_id: str,
    email: str,
    name: str,
    criteria: dict[str, str],
    enabled: bool,
    schedule_time: str,
    notification_id: str | None = None,
) -> dict[str, Any]:
    now = int(time.time())
    existing: dict[str, Any] | None = None
    if notification_id:
        response = table().get_item(
            Key={"PK": f"USER#{user_id}", "SK": f"DAILY_NOTIFICATION#{notification_id}"}
        )
        existing = response.get("Item")
        if not existing:
            raise LookupError("Daily notification not found")
    else:
        notification_id = uuid.uuid4().hex

    item: dict[str, Any] = {
        "PK": f"USER#{user_id}",
        "SK": f"DAILY_NOTIFICATION#{notification_id}",
        "entityType": "dailyNotification",
        "notificationId": notification_id,
        "userId": user_id,
        "name": name.strip()[:100],
        "criteria": criteria,
        "enabled": enabled,
        "scheduleTime": schedule_time,
        "recipientEmail": email.strip().lower(),
        "createdAt": int((existing or {}).get("createdAt") or now),
        "updatedAt": now,
    }
    if enabled:
        item["GSI1PK"] = "DAILY_NOTIFICATION#ENABLED"
        item["GSI1SK"] = f"USER#{user_id}#NOTIFICATION#{notification_id}"
    if (existing or {}).get("lastScheduledRunDate"):
        item["lastScheduledRunDate"] = existing["lastScheduledRunDate"]
    table().put_item(Item=item)
    return _notification_from_item(item)


def delete_daily_notification(user_id: str, notification_id: str) -> None:
    table().delete_item(
        Key={"PK": f"USER#{user_id}", "SK": f"DAILY_NOTIFICATION#{notification_id}"}
    )


def list_enabled_daily_notifications() -> list[dict[str, Any]]:
    response = table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq("DAILY_NOTIFICATION#ENABLED"),
    )
    return response.get("Items", [])


def mark_daily_notification_scheduled(
    user_id: str, notification_id: str, run_date: str
) -> None:
    table().update_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"DAILY_NOTIFICATION#{notification_id}",
        },
        UpdateExpression="SET lastScheduledRunDate = :run_date, updatedAt = :now",
        ExpressionAttributeValues={
            ":run_date": run_date,
            ":now": int(time.time()),
        },
        ConditionExpression="attribute_exists(PK) AND attribute_exists(SK)",
    )


def put_notification_run_summary(
    user_id: str,
    notification_id: str,
    run_date: str,
    criteria: dict[str, str],
    match_count: int,
    retention_days: int,
) -> dict[str, Any]:
    now = int(time.time())
    key = {
        "PK": f"USER#{user_id}",
        "SK": f"NOTIFICATION_RUN#{notification_id}#{run_date}",
    }
    prior = table().get_item(Key=key).get("Item") or {}
    item = {
        **key,
        "entityType": "notificationRun",
        "notificationId": notification_id,
        "runDate": run_date,
        "criteria": criteria,
        "matchCount": match_count,
        "status": "COMPLETE",
        "emailStatus": prior.get("emailStatus") or "PENDING",
        "createdAt": int(prior.get("createdAt") or now),
        "completedAt": now,
        "expiresAt": now + retention_days * 86400,
    }
    if prior.get("emailMessageId"):
        item["emailMessageId"] = prior["emailMessageId"]
    if prior.get("emailSentAt"):
        item["emailSentAt"] = prior["emailSentAt"]
    table().put_item(Item=item)
    return item


def put_notification_results(
    user_id: str,
    notification_id: str,
    run_date: str,
    opportunities: list[dict[str, Any]],
    retention_days: int,
) -> None:
    now = int(time.time())
    expires_at = now + retention_days * 86400
    partition = f"NOTIFICATION_RESULTS#{user_id}#{notification_id}#{run_date}"
    existing_keys: list[dict[str, str]] = []
    start_key = None
    while True:
        request: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(partition),
            "ProjectionExpression": "PK, SK",
        }
        if start_key:
            request["ExclusiveStartKey"] = start_key
        response = table().query(**request)
        existing_keys.extend(response.get("Items", []))
        start_key = response.get("LastEvaluatedKey")
        if not start_key:
            break
    with table().batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
        for key in existing_keys:
            batch.delete_item(Key={"PK": key["PK"], "SK": key["SK"]})
        for opportunity in opportunities:
            posted = str(opportunity.get("posted_date") or "")[:10]
            notice_id = str(opportunity.get("notice_id") or "")
            batch.put_item(
                Item={
                    "PK": partition,
                    "SK": f"RESULT#{posted}#{notice_id}",
                    "entityType": "notificationResult",
                    "opportunity": opportunity,
                    "expiresAt": expires_at,
                }
            )


def list_notification_runs(user_id: str, notification_id: str) -> list[dict[str, Any]]:
    return [
        {
            "run_date": item["runDate"],
            "criteria": item.get("criteria") or {},
            "match_count": int(item.get("matchCount") or 0),
            "status": item.get("status") or "",
            "email_status": item.get("emailStatus") or "",
            "completed_at": int(item.get("completedAt") or 0),
        }
        for item in _query(user_id, f"NOTIFICATION_RUN#{notification_id}#")[:90]
    ]


def get_notification_run(user_id: str, notification_id: str, run_date: str) -> dict[str, Any] | None:
    item = table().get_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"NOTIFICATION_RUN#{notification_id}#{run_date}",
        }
    ).get("Item")
    if not item:
        return None
    return {
        "run_date": item["runDate"],
        "criteria": item.get("criteria") or {},
        "match_count": int(item.get("matchCount") or 0),
        "status": item.get("status") or "",
        "email_status": item.get("emailStatus") or "",
        "completed_at": int(item.get("completedAt") or 0),
    }


def _encode_cursor(key: dict[str, Any] | None) -> str | None:
    if not key:
        return None
    raw = json.dumps(key, separators=(",", ":"), default=_json_default).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        parsed = json.loads(base64.urlsafe_b64decode(value + padding).decode("utf-8"))
        if not isinstance(parsed, dict) or not {"PK", "SK"}.issubset(parsed):
            raise ValueError
        return {"PK": str(parsed["PK"]), "SK": str(parsed["SK"])}
    except Exception as exc:
        raise ValueError("Invalid pagination cursor") from exc


def list_notification_results(
    user_id: str,
    notification_id: str,
    run_date: str,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    partition = f"NOTIFICATION_RESULTS#{user_id}#{notification_id}#{run_date}"
    start_key = _decode_cursor(cursor)
    if start_key and start_key.get("PK") != partition:
        raise ValueError("Pagination cursor does not belong to this notification run")
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": Key("PK").eq(partition),
        "Limit": max(1, min(limit, 100)),
        "ScanIndexForward": False,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return {
        "items": [item["opportunity"] for item in response.get("Items", [])],
        "next_cursor": _encode_cursor(response.get("LastEvaluatedKey")),
    }


def claim_notification_email(user_id: str, notification_id: str, run_date: str) -> bool:
    try:
        table().update_item(
            Key={
                "PK": f"USER#{user_id}",
                "SK": f"NOTIFICATION_RUN#{notification_id}#{run_date}",
            },
            UpdateExpression="SET emailStatus = :sending, emailAttemptedAt = :now",
            ConditionExpression="emailStatus IN (:pending, :failed)",
            ExpressionAttributeValues={
                ":sending": "SENDING",
                ":pending": "PENDING",
                ":failed": "FAILED",
                ":now": int(time.time()),
            },
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def finish_notification_email(
    user_id: str,
    notification_id: str,
    run_date: str,
    status: str,
    message_id: str = "",
    error: str = "",
) -> None:
    names = {"#status": "emailStatus"}
    values: dict[str, Any] = {":status": status, ":now": int(time.time())}
    expression = "SET #status = :status, emailUpdatedAt = :now"
    if message_id:
        expression += ", emailMessageId = :message_id, emailSentAt = :now"
        values[":message_id"] = message_id
    if error:
        expression += ", emailError = :error"
        values[":error"] = error[:500]
    table().update_item(
        Key={
            "PK": f"USER#{user_id}",
            "SK": f"NOTIFICATION_RUN#{notification_id}#{run_date}",
        },
        UpdateExpression=expression,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def record_search(
    user_id: str,
    criteria: dict[str, Any],
    result_count: int,
    retention_days: int,
) -> None:
    created_at = int(time.time())
    history_id = f"{created_at:010d}#{uuid.uuid4().hex}"
    table().put_item(
        Item={
            "PK": f"USER#{user_id}",
            "SK": f"HISTORY#{history_id}",
            "entityType": "searchHistory",
            "criteria": criteria,
            "resultCount": result_count,
            "createdAt": created_at,
            "expiresAt": created_at + retention_days * 86400,
        }
    )


def list_search_history(user_id: str) -> list[dict[str, Any]]:
    return [
        {
            "criteria": item["criteria"],
            "result_count": int(item["resultCount"]),
            "created_at": int(item["createdAt"]),
        }
        for item in _query(user_id, "HISTORY#")[:50]
    ]


def clear_search_history(user_id: str) -> int:
    items = _query(user_id, "HISTORY#")
    with table().batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    return len(items)


def delete_user_data(user_id: str) -> int:
    """Delete user-owned records; expiring notification result snapshots retain their TTL."""
    partition = f"USER#{user_id}"
    items: list[dict[str, str]] = []
    start_key = None
    while True:
        request: dict[str, Any] = {
            "KeyConditionExpression": Key("PK").eq(partition),
            "ProjectionExpression": "PK, SK",
        }
        if start_key:
            request["ExclusiveStartKey"] = start_key
        result = table().query(**request)
        items.extend(result.get("Items", []))
        start_key = result.get("LastEvaluatedKey")
        if not start_key:
            break
    with table().batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
    return len(items)
