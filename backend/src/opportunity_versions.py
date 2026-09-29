"""Conservative identity and ordering for SAM opportunity posting versions.

SAM's CSV can mark multiple actions for one solicitation as active. Its API
returns the latest active version, but the local index must choose one without
making a request for every CSV row.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable


def posted_timestamp(value: Any) -> str:
    """Return a lexically sortable timestamp; a date-only value sorts first."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ""


def logical_key(record: dict[str, Any]) -> str:
    """Group likely revisions, while leaving ambiguous notices independent.

    The key deliberately does not decide whether two records are versions by
    itself. Titles must also be very similar; offices can reuse a solicitation
    number for related but distinct notices.
    """
    solicitation = re.sub(r"\s+", "", str(record.get("solicitation_number") or "")).casefold()
    # CSV's AAC Code is an office identifier. Its CGAC fallback is only an
    # agency identifier and must not be used to collapse postings.
    office_value = (record["version_office_code"] if "version_office_code" in record
                    else record.get("organization_code"))
    office = str(office_value or "").strip().rsplit(".", 1)[-1].casefold()
    if "version_office_code" not in record and re.fullmatch(r"\d{3}", office):
        return ""
    notice_type = str(record.get("type_code") or record.get("type") or "").strip().casefold()
    if not all((solicitation, office, notice_type)):
        return ""
    return json.dumps([office, notice_type, solicitation], separators=(",", ":"))


def similar_title(left: Any, right: Any) -> bool:
    first = " ".join(str(left or "").split()).casefold()
    second = " ".join(str(right or "").split()).casefold()
    if not first or not second:
        return False
    return first == second or SequenceMatcher(None, first, second).ratio() >= 0.94


def collapse_versions(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use the latest posting for a logical notice, including across pages."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        notice_id = str(record.get("notice_id") or "")
        if not notice_id:
            continue
        key = logical_key(record) or f"id:{notice_id}"
        group = by_key.setdefault(key, [])
        position = next((index for index, item in enumerate(group)
                         if similar_title(item.get("title"), record.get("title"))), None)
        if position is None:
            group.append(record)
            continue
        previous = group[position]
        rank = (posted_timestamp(record.get("posted_at") or record.get("posted_date")), notice_id)
        old_rank = (posted_timestamp(previous.get("posted_at") or previous.get("posted_date")),
                    str(previous.get("notice_id") or ""))
        if rank > old_rank:
            group[position] = record
    return [record for group in by_key.values() for record in group]
