"""Validation and local matching for daily notification filters."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


ALLOWED_NOTIFICATION_FILTERS = {
    "title",
    "notice_id",
    "solicitation_number",
    "ptype",
    "naics_code",
    "classification_code",
    "set_aside",
    "state",
    "zip",
    "organization_code",
    "organization_name",
    "response_deadline_from",
    "response_deadline_to",
    "open_deadlines_only",
}


def sanitize_criteria(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError("criteria must be an object")
    criteria: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ALLOWED_NOTIFICATION_FILTERS:
            continue
        clean = str(value or "").strip()[:200]
        if clean:
            criteria[key] = clean
    for key in ("response_deadline_from", "response_deadline_to"):
        if key in criteria:
            _parse_date(criteria[key])
    if "open_deadlines_only" in criteria:
        if criteria["open_deadlines_only"].casefold() not in {"1", "true", "yes", "on"}:
            raise ValueError("open_deadlines_only must be true when provided")
        criteria["open_deadlines_only"] = "true"
    return criteria


def _text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _parse_date(value: Any):
    raw = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {value}. Use YYYY-MM-DD.")


def _contains(actual: Any, expected: str) -> bool:
    return _text(expected) in _text(actual)


def _one_of(actual_values: list[Any], expected: str) -> bool:
    values = [_text(value) for value in actual_values]
    requested = [_text(value) for value in expected.split(",") if value.strip()]
    return any(
        any(item == actual or item in actual for actual in values)
        for item in requested
    )


def _matches_any_exact(actual: Any, expected: str) -> bool:
    requested = {_text(value) for value in expected.split(",") if value.strip()}
    return _text(actual) in requested


def matches(opportunity: dict[str, Any], criteria: dict[str, str]) -> bool:
    """Return whether a normalized, active opportunity matches every criterion."""
    if not opportunity.get("active"):
        return False

    contains_fields = {
        "title": opportunity.get("title"),
        "notice_id": opportunity.get("notice_id"),
        "solicitation_number": opportunity.get("solicitation_number"),
        "organization_name": " ".join(
            filter(None, [str(opportunity.get("organization_name") or ""), str(opportunity.get("agency_path") or "")])
        ),
    }
    for key, actual in contains_fields.items():
        if key in criteria and not _contains(actual, criteria[key]):
            return False

    exact_fields = {
        "naics_code": opportunity.get("naics_code"),
        "classification_code": opportunity.get("classification_code"),
        "state": (opportunity.get("place_of_performance") or {}).get("state"),
        "zip": (opportunity.get("place_of_performance") or {}).get("zip"),
        "organization_code": opportunity.get("organization_code"),
    }
    for key, actual in exact_fields.items():
        if key in criteria and not _matches_any_exact(actual, criteria[key]):
            return False

    if "ptype" in criteria and not _one_of(
        [opportunity.get("type_code"), opportunity.get("type")], criteria["ptype"]
    ):
        return False
    if "set_aside" in criteria and not _one_of(
        [opportunity.get("set_aside_code"), opportunity.get("set_aside")], criteria["set_aside"]
    ):
        return False

    deadline = opportunity.get("response_deadline")
    if (
        "response_deadline_from" in criteria
        or "response_deadline_to" in criteria
        or criteria.get("open_deadlines_only") == "true"
    ):
        try:
            response_date = _parse_date(deadline)
        except ValueError:
            return False
        if criteria.get("open_deadlines_only") == "true" and response_date < date.today():
            return False
        if "response_deadline_from" in criteria and response_date < _parse_date(criteria["response_deadline_from"]):
            return False
        if "response_deadline_to" in criteria and response_date > _parse_date(criteria["response_deadline_to"]):
            return False

    return True
