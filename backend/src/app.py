"""Lambda entry point for the GovVue Light HTTP API."""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

import storage
import user_admin
from sam_entity_client import (
    build_entity_search_parameters,
    sanitize_entity_criteria,
    search_entities,
)
from notification_filters import sanitize_criteria
from runtime_config import get_runtime_config
from sam_client import (
    SamApiError,
    build_search_parameters,
    expand_search_parameters,
    load_opportunity_detail,
    search_opportunities,
)


LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

OPPORTUNITY_SORTS = {
    "posted_desc",
    "posted_asc",
    "response_deadline_asc",
    "response_deadline_desc",
}


def _queue_daily_notification_run() -> None:
    boto3.client("sqs").send_message(
        QueueUrl=os.environ["FEED_QUEUE_URL"],
        MessageBody=json.dumps(
            {
                "action": "start",
                "force": True,
                "request_id": uuid.uuid4().hex,
            },
            separators=(",", ":"),
        ),
        MessageGroupId="daily-feed",
    )


class ForbiddenError(RuntimeError):
    pass


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body, default=_json_default, separators=(",", ":")),
    }


def _body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _claims(event: dict[str, Any]) -> dict[str, Any]:
    return (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )


def _user_id(event: dict[str, Any]) -> str:
    user_id = str(_claims(event).get("sub") or "")
    if not user_id:
        raise PermissionError("Authenticated user identity is missing")
    return user_id


def _groups(event: dict[str, Any]) -> list[str]:
    raw = _claims(event).get("cognito:groups") or []
    if isinstance(raw, list):
        return [str(value) for value in raw]
    value = str(raw).strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [part.strip().strip('"\'') for part in value.split(",") if part.strip()]


def _require_admin(event: dict[str, Any]) -> None:
    if "admin" not in _groups(event):
        raise ForbiddenError("Administrator role is required")


def _query(event: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in (event.get("queryStringParameters") or {}).items()}


def _notification_schedule_time(payload: dict[str, Any]) -> str:
    value = str(
        payload.get("schedule_time")
        or get_runtime_config().daily_notification_default_time
    ).strip()
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if not match:
        raise ValueError("schedule_time must use HH:MM in 24-hour time")
    if int(match.group(2)) % 5:
        raise ValueError("schedule_time must use a five-minute increment")
    return value


def _load_search_pages(
    tasks: list[tuple[int, dict[str, Any], int]], config: Any
) -> tuple[dict[tuple[int, int], dict[str, Any]], bool]:
    results: dict[tuple[int, int], dict[str, Any]] = {}
    misses: list[tuple[int, dict[str, Any], int, str]] = []
    for request_index, params, page_index in tasks:
        key = storage.cache_key(
            "search-cache", {"params": params, "page": page_index}
        )
        cached = storage.get_cached(key, config.search_cache_ttl_seconds)
        if cached is None:
            misses.append((request_index, params, page_index, key))
        else:
            results[(request_index, page_index)] = cached

    if misses:
        workers = min(4, len(misses))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(search_opportunities, params, page_index, config): (
                    request_index,
                    page_index,
                    key,
                )
                for request_index, params, page_index, key in misses
            }
            for future in as_completed(futures):
                request_index, page_index, key = futures[future]
                upstream = future.result()
                storage.put_cached(key, upstream)
                results[(request_index, page_index)] = upstream
    return results, not misses


def _converged_search(
    parameter_sets: list[dict[str, Any]],
    page: int,
    per_page: int,
    config: Any,
    sort_order: str = "posted_desc",
) -> dict[str, Any]:
    absolute_start = (page - 1) * per_page
    absolute_end = absolute_start + per_page
    first_tasks = [
        (request_index, params, 0)
        for request_index, params in enumerate(parameter_sets)
    ]
    pages, first_cache_hit = _load_search_pages(first_tasks, config)

    branch_totals: dict[int, int] = {}
    branch_records: dict[int, list[dict[str, Any]]] = {}
    additional_tasks: list[tuple[int, dict[str, Any], int]] = []
    exact_sort = sort_order != "posted_desc"
    target_page_count = max(1, math.ceil(absolute_end / config.sam_page_size))
    available_page_counts: dict[int, int] = {}
    for request_index, params in enumerate(parameter_sets):
        first_page = pages[(request_index, 0)]
        total = int(first_page["total_records"])
        branch_totals[request_index] = total
        branch_records[request_index] = list(first_page["records"])
        available_page_count = max(1, math.ceil(total / config.sam_page_size))
        available_page_counts[request_index] = available_page_count

    if exact_sort:
        required_upstream_pages = sum(available_page_counts.values())
        if required_upstream_pages > config.search_max_sort_pages:
            raise ValueError(
                f"Exact {sort_order.replace('_', ' ')} sorting requires "
                f"{required_upstream_pages} SAM.gov page requests; the configured "
                f"maximum is {config.search_max_sort_pages}. Narrow the filters and try again."
            )

    for request_index, params in enumerate(parameter_sets):
        available_page_count = available_page_counts[request_index]
        pages_to_load = available_page_count if exact_sort else min(
            target_page_count, available_page_count
        )
        for page_index in range(1, pages_to_load):
            additional_tasks.append((request_index, params, page_index))

    additional_cache_hit = True
    if additional_tasks:
        additional_pages, additional_cache_hit = _load_search_pages(
            additional_tasks, config
        )
        pages.update(additional_pages)
        for request_index, _, page_index in additional_tasks:
            branch_records[request_index].extend(
                pages[(request_index, page_index)]["records"]
            )

    unique: dict[str, dict[str, Any]] = {}
    for request_index, records in branch_records.items():
        for record_index, record in enumerate(records):
            clean = dict(record)
            clean.pop("_description_url", None)
            notice_id = str(clean.get("notice_id") or "")
            identity = notice_id or f"anonymous-{request_index}-{record_index}"
            unique[identity] = clean
    merged = _sort_opportunities(list(unique.values()), sort_order)

    all_results_loaded = all(
        len(branch_records[index]) >= total
        for index, total in branch_totals.items()
    )
    total_records = (
        len(merged) if all_results_loaded else sum(branch_totals.values())
    )
    return {
        "items": merged[absolute_start:absolute_end],
        "page": page,
        "per_page": per_page,
        "total_records": total_records,
        "has_next": absolute_end < total_records,
        "cache_hit": first_cache_hit and additional_cache_hit,
        "upstream_queries": len(parameter_sets),
        "sort": sort_order,
    }


def _timestamp(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _sort_opportunities(
    opportunities: list[dict[str, Any]], sort_order: str
) -> list[dict[str, Any]]:
    if sort_order not in OPPORTUNITY_SORTS:
        raise ValueError("Unsupported opportunity sort order")
    field = "response_deadline" if sort_order.startswith("response_deadline") else "posted_date"
    descending = sort_order.endswith("_desc")

    def key(item: dict[str, Any]) -> tuple[Any, ...]:
        timestamp = _timestamp(item.get(field))
        notice_id = str(item.get("notice_id") or "")
        if descending:
            return (timestamp is not None, timestamp or float("-inf"), notice_id)
        return (timestamp is None, timestamp or float("inf"), notice_id)

    return sorted(opportunities, key=key, reverse=descending)


def _search(event: dict[str, Any], user_id: str) -> dict[str, Any]:
    config = get_runtime_config()
    query = _query(event)
    page = max(1, min(int(query.pop("page", "1")), 10_000))
    per_page = max(10, min(int(query.pop("per_page", "25")), 100))
    record_history = query.pop("record_history", "true").lower() in {"true", "1", "yes"}
    sort_order = query.pop("sort", "response_deadline_desc").strip().lower()
    if sort_order not in OPPORTUNITY_SORTS:
        raise ValueError("Unsupported opportunity sort order")
    sam_params = build_search_parameters(query, config)
    parameter_sets = expand_search_parameters(sam_params, config.search_max_fanout)
    converged_key = storage.cache_key(
        "converged-search-cache",
        {"params": sam_params, "page": page, "per_page": per_page, "sort": sort_order},
    )
    result = storage.get_cached(converged_key, config.search_cache_ttl_seconds)
    if result is None:
        result = _converged_search(parameter_sets, page, per_page, config, sort_order)
        storage.put_cached(converged_key, result)
    else:
        result["cache_hit"] = True

    total_records = int(result["total_records"])
    if page == 1 and record_history:
        history_query = dict(query)
        history_query["sort"] = sort_order
        storage.record_search(user_id, history_query, total_records, config.history_retention_days)
    return result


def _detail(notice_id: str) -> dict[str, Any]:
    config = get_runtime_config()
    key = storage.cache_key("detail-cache", notice_id)
    opportunity = storage.get_cached(key, config.search_cache_ttl_seconds)
    if opportunity is None:
        opportunity = load_opportunity_detail(notice_id, config)
        if opportunity:
            storage.put_cached(key, opportunity)
    if not opportunity:
        raise LookupError("Opportunity not found or no longer active")
    return opportunity


def _entity_search(event: dict[str, Any]) -> dict[str, Any]:
    config = get_runtime_config()
    query = _query(event)
    try:
        page = max(1, min(int(query.pop("page", "1")), 1000))
    except ValueError as exc:
        raise ValueError("page must be an integer") from exc
    criteria = sanitize_entity_criteria(query)
    params = build_entity_search_parameters(criteria)
    key = storage.cache_key(
        "entity-search-cache", {"params": params, "page": page}
    )
    result = storage.get_cached(key, config.search_cache_ttl_seconds)
    cache_hit = result is not None
    if result is None:
        result = search_entities(params, page - 1, config)
        storage.put_cached(key, result)
    total_records = int(result["total_records"])
    return {
        "items": result["records"],
        "page": page,
        "per_page": 10,
        "total_records": total_records,
        "has_next": page * 10 < total_records,
        "cache_hit": cache_hit,
    }


def _entity_detail(uei: str) -> dict[str, Any]:
    clean_uei = uei.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{12}", clean_uei):
        raise ValueError("UEI must be 12 letters or numbers")
    config = get_runtime_config()
    key = storage.cache_key("entity-detail-cache", clean_uei)
    entity = storage.get_cached(key, config.search_cache_ttl_seconds)
    if entity is None:
        result = search_entities({"ueiSAM": clean_uei}, 0, config)
        entity = next(
            (
                item
                for item in result["records"]
                if str(item.get("uei") or "").upper() == clean_uei
            ),
            None,
        )
        if entity:
            storage.put_cached(key, entity)
    if not entity:
        raise LookupError("Entity not found")
    return entity


def _route(event: dict[str, Any]) -> dict[str, Any]:
    request_context = event.get("requestContext", {})
    method = request_context.get("http", {}).get("method", "GET").upper()
    path = event.get("rawPath") or "/"

    if method == "OPTIONS":
        return response(200, {})

    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "service": "govvue-light"})

    user_id = _user_id(event)
    if method == "GET" and path == "/me":
        claims = _claims(event)
        groups = _groups(event)
        return response(
            200,
            {
                "sub": user_id,
                "email": claims.get("email", ""),
                "role": "admin" if "admin" in groups else "user",
                "groups": groups,
            },
        )

    if path == "/admin/users":
        _require_admin(event)
        if method == "GET":
            return response(200, {"items": user_admin.list_users()})
        if method == "POST":
            payload = _body(event)
            return response(
                201,
                user_admin.create_user(payload.get("email"), payload.get("role", "user")),
            )

    reset_user_match = re.fullmatch(r"/admin/users/([^/]+)/reset-password", path)
    if method == "POST" and reset_user_match:
        from urllib.parse import unquote

        _require_admin(event)
        username = unquote(reset_user_match.group(1))
        if username == str(_claims(event).get("cognito:username") or ""):
            raise ValueError("Use Account to change your own password")
        return response(200, {"action": user_admin.reset_user_password(username)})

    admin_user_match = re.fullmatch(r"/admin/users/([^/]+)", path)
    if admin_user_match:
        from urllib.parse import unquote

        _require_admin(event)
        username = unquote(admin_user_match.group(1))
        current_username = str(_claims(event).get("cognito:username") or "")
        if username == current_username:
            raise ValueError("Administrators cannot modify or delete their own account here")
        if method == "PUT":
            payload = _body(event)
            return response(
                200,
                user_admin.update_user(
                    username, payload.get("role", "user"), payload.get("enabled", True)
                ),
            )
        if method == "DELETE":
            target = user_admin.disable_user_for_deletion(username)
            target_sub = str(target.get("sub") or "")
            if not target_sub:
                raise ValueError("Target user identity is missing")
            deleted_records = storage.delete_user_data(target_sub)
            user_admin.delete_user(username)
            return response(200, {"deleted": True, "deleted_records": deleted_records})

    if method == "GET" and path == "/opportunities/search":
        return response(200, _search(event, user_id))

    if method == "GET" and path == "/entities/search":
        return response(200, _entity_search(event))

    entity_detail_match = re.fullmatch(r"/entities/([^/]+)", path)
    if method == "GET" and entity_detail_match:
        from urllib.parse import unquote

        return response(200, _entity_detail(unquote(entity_detail_match.group(1))))

    detail_match = re.fullmatch(r"/opportunities/([^/]+)", path)
    if method == "GET" and detail_match:
        from urllib.parse import unquote

        return response(200, _detail(unquote(detail_match.group(1))))

    if path == "/saved-opportunities":
        if method == "GET":
            return response(200, {"items": storage.list_saved_opportunities(user_id)})
        if method == "POST":
            payload = _body(event)
            opportunity = payload.get("opportunity") or payload
            if not isinstance(opportunity, dict):
                raise ValueError("opportunity must be a JSON object")
            storage.save_opportunity(user_id, opportunity)
            return response(201, {"saved": True, "notice_id": opportunity.get("notice_id")})
        if method == "DELETE":
            notice_ids = _body(event).get("notice_ids") or []
            if not isinstance(notice_ids, list):
                raise ValueError("notice_ids must be an array")
            deleted = storage.delete_saved_opportunities(user_id, [str(value) for value in notice_ids])
            return response(200, {"deleted": deleted})

    if path == "/saved-entities":
        if method == "GET":
            return response(200, {"items": storage.list_saved_entities(user_id)})
        if method == "POST":
            payload = _body(event)
            entity = payload.get("entity") or payload
            if not isinstance(entity, dict):
                raise ValueError("entity must be a JSON object")
            storage.save_entity(user_id, entity)
            return response(201, {"saved": True, "uei": entity.get("uei")})
        if method == "DELETE":
            ueis = _body(event).get("ueis") or []
            if not isinstance(ueis, list):
                raise ValueError("ueis must be an array")
            deleted = storage.delete_saved_entities(user_id, [str(value) for value in ueis])
            return response(200, {"deleted": deleted})

    if path == "/saved-searches":
        if method == "GET":
            return response(200, {"items": storage.list_saved_searches(user_id)})
        if method == "POST":
            payload = _body(event)
            name = str(payload.get("name") or "").strip()
            criteria = payload.get("criteria") or {}
            if not name:
                raise ValueError("name is required")
            if not isinstance(criteria, dict):
                raise ValueError("criteria must be an object")
            return response(201, storage.save_search(user_id, name, criteria))

    saved_search_match = re.fullmatch(r"/saved-searches/([A-Za-z0-9-]+)", path)
    if method == "DELETE" and saved_search_match:
        storage.delete_saved_search(user_id, saved_search_match.group(1))
        return response(200, {"deleted": True})

    if path == "/saved-entity-searches":
        if method == "GET":
            return response(200, {"items": storage.list_saved_entity_searches(user_id)})
        if method == "POST":
            payload = _body(event)
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            raw_criteria = payload.get("criteria") or {}
            if not isinstance(raw_criteria, dict):
                raise ValueError("criteria must be an object")
            criteria = sanitize_entity_criteria(raw_criteria)
            build_entity_search_parameters(criteria)
            return response(201, storage.save_entity_search(user_id, name, criteria))

    saved_entity_search_match = re.fullmatch(
        r"/saved-entity-searches/([A-Za-z0-9-]+)", path
    )
    if method == "DELETE" and saved_entity_search_match:
        storage.delete_saved_entity_search(user_id, saved_entity_search_match.group(1))
        return response(200, {"deleted": True})

    if path == "/search-history":
        if method == "GET":
            return response(200, {"items": storage.list_search_history(user_id)})
        if method == "DELETE":
            return response(200, {"deleted": storage.clear_search_history(user_id)})

    if path == "/daily-notifications":
        if method == "GET":
            return response(200, {"items": storage.list_daily_notifications(user_id)})
        if method == "POST":
            payload = _body(event)
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            enabled = payload.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            criteria = sanitize_criteria(payload.get("criteria") or {})
            schedule_time = _notification_schedule_time(payload)
            email = str(_claims(event).get("email") or "").strip()
            if not email:
                raise ValueError("Authenticated user email is missing")
            return response(
                201,
                storage.save_daily_notification(
                    user_id, email, name, criteria, enabled, schedule_time
                ),
            )

    if method == "POST" and path == "/daily-notifications/run":
        if not any(item.get("enabled") for item in storage.list_daily_notifications(user_id)):
            raise ValueError("Enable at least one daily notification before running now")
        _queue_daily_notification_run()
        return response(202, {"queued": True})

    notification_match = re.fullmatch(r"/daily-notifications/([A-Za-z0-9-]+)", path)
    if notification_match:
        notification_id = notification_match.group(1)
        if method == "GET":
            item = storage.get_daily_notification(user_id, notification_id)
            if not item:
                raise LookupError("Daily notification not found")
            return response(200, item)
        if method == "PUT":
            payload = _body(event)
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            enabled = payload.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be a boolean")
            criteria = sanitize_criteria(payload.get("criteria") or {})
            schedule_time = _notification_schedule_time(payload)
            email = str(_claims(event).get("email") or "").strip()
            return response(
                200,
                storage.save_daily_notification(
                    user_id,
                    email,
                    name,
                    criteria,
                    enabled,
                    schedule_time,
                    notification_id,
                ),
            )
        if method == "DELETE":
            if not storage.get_daily_notification(user_id, notification_id):
                raise LookupError("Daily notification not found")
            storage.delete_daily_notification(user_id, notification_id)
            return response(200, {"deleted": True})

    notification_runs_match = re.fullmatch(
        r"/daily-notifications/([A-Za-z0-9-]+)/runs", path
    )
    if method == "GET" and notification_runs_match:
        notification_id = notification_runs_match.group(1)
        notification = storage.get_daily_notification(user_id, notification_id)
        if not notification:
            raise LookupError("Daily notification not found")
        return response(
            200,
            {
                "notification": notification,
                "items": storage.list_notification_runs(user_id, notification_id),
            },
        )

    notification_results_match = re.fullmatch(
        r"/daily-notifications/([A-Za-z0-9-]+)/runs/(\d{4}-\d{2}-\d{2})", path
    )
    if method == "GET" and notification_results_match:
        notification_id, run_date = notification_results_match.groups()
        notification = storage.get_daily_notification(user_id, notification_id)
        if not notification:
            raise LookupError("Daily notification not found")
        run = storage.get_notification_run(user_id, notification_id, run_date)
        if not run:
            raise LookupError("Daily notification run not found")
        query = _query(event)
        results = storage.list_notification_results(
            user_id,
            notification_id,
            run_date,
            int(query.get("limit") or 25),
            query.get("cursor"),
        )
        return response(200, {"notification": notification, "run": run, **results})

    return response(404, {"message": "Not found"})


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request_id = getattr(context, "aws_request_id", "local") if context else "local"
    try:
        return _route(event)
    except PermissionError as exc:
        return response(401, {"message": str(exc), "request_id": request_id})
    except ForbiddenError as exc:
        return response(403, {"message": str(exc), "request_id": request_id})
    except user_admin.UserAdminError as exc:
        return response(exc.status_code, {"message": str(exc), "request_id": request_id})
    except (ValueError, json.JSONDecodeError) as exc:
        return response(400, {"message": str(exc), "request_id": request_id})
    except LookupError as exc:
        return response(404, {"message": str(exc), "request_id": request_id})
    except SamApiError as exc:
        LOGGER.warning("SAM.gov request failed: %s", exc)
        return response(exc.status_code, {"message": str(exc), "request_id": request_id})
    except Exception:
        LOGGER.exception("Unhandled API error request_id=%s", request_id)
        return response(500, {"message": "Unexpected server error", "request_id": request_id})
