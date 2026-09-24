"""Small SAM.gov Opportunities API client with safe normalization and retries."""

from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from itertools import product
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from runtime_config import RuntimeConfig


ALLOWED_FILTERS = {
    "ptype": "ptype",
    "solicitation_number": "solnum",
    "notice_id": "noticeid",
    "title": "title",
    "state": "state",
    "zip": "zip",
    "organization_code": "organizationCode",
    "organization_name": "organizationName",
    "set_aside": "typeOfSetAside",
    "naics_code": "ncode",
    "classification_code": "ccode",
    "response_deadline_from": "rdlfrom",
    "response_deadline_to": "rdlto",
}
MULTI_VALUE_FILTERS = {
    "ptype",
    "state",
    "zip",
    "organization_code",
    "set_aside",
    "naics_code",
    "classification_code",
}
NATIVE_MULTI_VALUE_PARAMETERS = {"ptype"}
MAX_VALUES_PER_FILTER = 20
ROLLING_LOOKBACK_DAYS = {7, 14, 30, 60, 90}
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
NOTICE_TYPE_CODES = {
    "justification": "u",
    "pre solicitation": "p",
    "presolicitation": "p",
    "award notice": "a",
    "sources sought": "r",
    "special notice": "s",
    "solicitation": "o",
    "sale of surplus property": "g",
    "combined synopsis/solicitation": "k",
    "intent to bundle requirements": "i",
}


class SamApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(value)
        text = "\n".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(re.sub(r"[ \t]+", " ", text)).strip()


def _format_sam_date(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {raw}. Use YYYY-MM-DD.")


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _split_multi_value(raw: str, field_name: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        value = part.strip()[:200]
        normalized = value.casefold()
        if value and normalized not in seen:
            seen.add(normalized)
            values.append(value)
    if len(values) > MAX_VALUES_PER_FILTER:
        raise ValueError(
            f"{field_name} accepts at most {MAX_VALUES_PER_FILTER} selected values"
        )
    return sorted(values, key=str.casefold)


def build_search_parameters(query: dict[str, str], config: RuntimeConfig) -> dict[str, Any]:
    today = date.today()
    default_from = today - timedelta(days=config.search_default_lookback_days)
    posted_within = (query.get("posted_within") or "").strip()
    if posted_within:
        try:
            rolling_days = int(posted_within)
        except ValueError as exc:
            raise ValueError("posted_within must be 7, 14, 30, 60, or 90 days") from exc
        if rolling_days not in ROLLING_LOOKBACK_DAYS:
            raise ValueError("posted_within must be 7, 14, 30, 60, or 90 days")
        posted_from = _format_sam_date(
            (today - timedelta(days=rolling_days - 1)).isoformat()
        )
        posted_to = _format_sam_date(today.isoformat())
    else:
        posted_from = _format_sam_date(query.get("posted_from", default_from.isoformat()))
        posted_to = _format_sam_date(query.get("posted_to", today.isoformat()))

    start = datetime.strptime(posted_from, "%m/%d/%Y").date()
    end = datetime.strptime(posted_to, "%m/%d/%Y").date()
    if start > end:
        raise ValueError("posted_from cannot be later than posted_to")
    if (end - start).days > config.search_max_lookback_days:
        raise ValueError(
            f"Date range cannot exceed {config.search_max_lookback_days} days"
        )

    params: dict[str, Any] = {
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "status": "active",
    }
    for input_name, sam_name in ALLOWED_FILTERS.items():
        value = (query.get(input_name) or "").strip()
        if value:
            if input_name in MULTI_VALUE_FILTERS:
                values = _split_multi_value(value, input_name)
                if values:
                    params[sam_name] = values if len(values) > 1 else values[0]
            elif input_name in {"response_deadline_from", "response_deadline_to"}:
                params[sam_name] = _format_sam_date(value)
            else:
                params[sam_name] = value[:200]

    if _is_truthy(query.get("open_deadlines_only")):
        today_deadline = today.strftime("%m/%d/%Y")
        explicit_from = params.get("rdlfrom")
        if not explicit_from:
            params["rdlfrom"] = today_deadline
        else:
            requested = datetime.strptime(str(explicit_from), "%m/%d/%Y").date()
            if requested < today:
                params["rdlfrom"] = today_deadline
    return params


def expand_search_parameters(
    params: dict[str, Any], max_fanout: int
) -> list[dict[str, Any]]:
    """Expand SAM single-value filters while preserving native ptype arrays."""
    fanout_fields = [
        (name, value)
        for name, value in params.items()
        if isinstance(value, list) and name not in NATIVE_MULTI_VALUE_PARAMETERS
    ]
    fanout_count = 1
    for _, values in fanout_fields:
        fanout_count *= len(values)
    if fanout_count > max_fanout:
        raise ValueError(
            f"Selected filters require {fanout_count} SAM.gov searches; "
            f"the configured maximum is {max_fanout}. Select fewer values."
        )
    if not fanout_fields:
        return [dict(params)]

    expanded: list[dict[str, Any]] = []
    names = [name for name, _ in fanout_fields]
    choices = [values for _, values in fanout_fields]
    for selected_values in product(*choices):
        request = dict(params)
        request.update(zip(names, selected_values, strict=True))
        expanded.append(request)
    return expanded


def _request_json(url: str, params: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    safe_params = dict(params)
    safe_params["api_key"] = config.sam_api_key
    request_url = f"{url}?{urlencode(safe_params, doseq=True)}"
    request = Request(
        request_url,
        headers={"Accept": "application/json", "User-Agent": "GovVue-Light/1.0"},
    )

    for attempt in range(3):
        try:
            with urlopen(request, timeout=config.sam_request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in RETRYABLE_STATUSES and attempt < 2:
                retry_after = exc.headers.get("Retry-After")
                wait = min(float(retry_after), 5.0) if retry_after else 0.5 * (2**attempt)
                time.sleep(wait)
                continue
            if exc.code in {401, 403}:
                raise SamApiError("SAM.gov rejected the configured API key", 502) from exc
            if exc.code == 429:
                raise SamApiError("SAM.gov request limit reached; try again shortly", 429) from exc
            raise SamApiError(f"SAM.gov returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
                continue
            raise SamApiError("SAM.gov is temporarily unavailable") from exc
    raise SamApiError("SAM.gov request failed")


def search_opportunities(
    params: dict[str, Any],
    page_index: int,
    config: RuntimeConfig,
    limit: int | None = None,
) -> dict[str, Any]:
    page_size = max(1, min(int(limit or config.sam_page_size), 1000))
    upstream = dict(params)
    upstream.update(
        {
            "limit": page_size,
            # SAM.gov defines offset as a zero-based page index, not a record offset.
            "offset": max(0, page_index),
        }
    )
    payload = _request_json(config.sam_opportunities_api, upstream, config)
    raw_records = payload.get("opportunitiesData") or []
    active_records = [
        record
        for record in raw_records
        if str(record.get("active", "")).strip().lower() == "yes"
    ]
    return {
        "total_records": int(payload.get("totalRecords") or len(active_records)),
        "records": [normalize_opportunity(record, config) for record in active_records],
    }


def normalize_opportunity(record: dict[str, Any], config: RuntimeConfig) -> dict[str, Any]:
    notice_id = str(record.get("noticeId") or record.get("notice_id") or "")
    ui_link = str(record.get("uiLink") or "")
    if not ui_link and notice_id:
        ui_link = f"{config.sam_site_base_url.rstrip('/')}/opp/{notice_id}/view"

    contacts = record.get("pointOfContact") or []
    contact = contacts[0] if isinstance(contacts, list) and contacts else {}
    place = record.get("placeOfPerformance") or {}
    state = place.get("state") or {}
    country = place.get("country") or {}
    type_name = str(record.get("type") or record.get("baseType") or "")
    type_code = str(record.get("ptype") or NOTICE_TYPE_CODES.get(type_name.strip().lower(), ""))
    set_aside_code = str(record.get("typeOfSetAside") or record.get("setAsideCode") or "")

    return {
        "notice_id": notice_id,
        "title": record.get("title") or "Untitled opportunity",
        "solicitation_number": record.get("solicitationNumber") or "",
        "type": type_name,
        "type_code": type_code,
        "posted_date": record.get("postedDate") or "",
        "response_deadline": record.get("responseDeadLine") or "",
        "archive_date": record.get("archiveDate") or "",
        "active": str(record.get("active") or "").lower() == "yes",
        "naics_code": record.get("naicsCode") or "",
        "classification_code": record.get("classificationCode") or "",
        "set_aside": record.get("typeOfSetAsideDescription") or record.get("setAside") or "",
        "set_aside_code": set_aside_code,
        "organization_name": record.get("organizationName") or "",
        "organization_code": record.get("organizationCode") or record.get("fullParentPathCode") or "",
        "agency_path": record.get("fullParentPathName") or "",
        "place_of_performance": {
            "city": place.get("city", {}).get("name", "") if isinstance(place.get("city"), dict) else place.get("city", ""),
            "state": state.get("name") or state.get("code") or "" if isinstance(state, dict) else state,
            "zip": place.get("zip") or "",
            "country": country.get("name") or country.get("code") or "" if isinstance(country, dict) else country,
        },
        "contact": {
            "name": contact.get("fullName") or "",
            "email": contact.get("email") or "",
            "phone": contact.get("phone") or "",
        },
        "sam_url": ui_link,
        "_description_url": record.get("description") or "",
    }


def _extract_description(payload: Any) -> str:
    if isinstance(payload, str):
        return _plain_text(payload)
    if isinstance(payload, list):
        values = [_extract_description(item) for item in payload]
        return "\n\n".join(value for value in values if value)
    if isinstance(payload, dict):
        for key in ("description", "descriptionText", "body", "text"):
            if key in payload:
                value = _extract_description(payload[key])
                if value:
                    return value
        for value in payload.values():
            extracted = _extract_description(value)
            if extracted:
                return extracted
    return ""


def fetch_description(description_url: str, config: RuntimeConfig) -> str:
    if not description_url:
        return ""
    parsed = urlparse(description_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (hostname == "sam.gov" or hostname.endswith(".sam.gov")):
        return ""
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("api_key", None)
    safe_url = urlunparse(parsed._replace(query=""))
    payload = _request_json(safe_url, query, config)
    return _extract_description(payload)[:100_000]


def load_opportunity_detail(notice_id: str, config: RuntimeConfig) -> dict[str, Any] | None:
    safe_notice_id = notice_id.strip()[:100]
    if not safe_notice_id:
        return None
    result = search_opportunities({"noticeid": safe_notice_id, "status": "active"}, 0, config)
    records = result["records"]
    if not records:
        return None
    opportunity = records[0]
    description_url = str(opportunity.pop("_description_url", ""))
    opportunity["description"] = fetch_description(description_url, config)
    return opportunity
