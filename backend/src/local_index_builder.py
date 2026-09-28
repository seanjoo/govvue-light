"""Build an immutable SQLite search index from SAM's public active CSV.

This module intentionally has no AWS dependency. Batch jobs can stream the
public extract to a local file, build and validate the index, then publish it
with ``local_index_publisher``. The extract's CSV header is validated rather
than relying on column position.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sam_client import NOTICE_TYPE_CODES, _plain_text


REQUIRED_COLUMNS = {"NoticeId", "Title", "PostedDate", "Active"}
UPSERT = """
INSERT INTO opportunities (
  notice_id, title, solicitation_number, type_code, naics_code,
  classification_code, set_aside_code, state, zip, organization_code,
  organization_name, agency_path, posted_date, response_deadline, active,
  payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(notice_id) DO UPDATE SET
  title=excluded.title, solicitation_number=excluded.solicitation_number,
  type_code=excluded.type_code, naics_code=excluded.naics_code,
  classification_code=excluded.classification_code,
  set_aside_code=excluded.set_aside_code, state=excluded.state,
  zip=excluded.zip, organization_code=excluded.organization_code,
  organization_name=excluded.organization_name, agency_path=excluded.agency_path,
  posted_date=excluded.posted_date, response_deadline=excluded.response_deadline,
  active=excluded.active, payload=excluded.payload
"""


def _iso(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d", "%b %d, %Y"):
        try:
            return datetime.strptime(value[:20], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _field(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_csv_row(row: dict[str, Any], site_url: str = "https://sam.gov") -> dict[str, Any] | None:
    notice_id = _field(row, "NoticeId")
    if not notice_id:
        return None
    active = _field(row, "Active").casefold() == "yes"
    if not active:
        return None
    type_name = _field(row, "Type", "BaseType")
    description = _plain_text(_field(row, "Description"))[:100_000]
    state = _field(row, "PopState", "PopStateCode", "PlaceOfPerformanceState")
    zip_code = _field(row, "PopZip", "PlaceOfPerformanceZip")
    organization_name = _field(row, "Office", "Department/Ind.Agency")
    agency_path = " / ".join(filter(None, (
        _field(row, "Department/Ind.Agency"), _field(row, "Sub-Tier"), _field(row, "Office")
    )))
    link = _field(row, "Link")
    if not link.startswith("https://sam.gov/"):
        link = f"{site_url.rstrip('/')}/opp/{notice_id}/view"
    return {
        "notice_id": notice_id,
        "title": _field(row, "Title") or "Untitled opportunity",
        "solicitation_number": _field(row, "Sol#"),
        "type": type_name,
        "type_code": NOTICE_TYPE_CODES.get(type_name.casefold(), ""),
        "posted_date": _iso(_field(row, "PostedDate")),
        "response_deadline": _iso(_field(row, "ResponseDeadLine")),
        "archive_date": _iso(_field(row, "ArchiveDate")),
        "active": True,
        "naics_code": _field(row, "NaicsCode"),
        "classification_code": _field(row, "ClassificationCode"),
        "set_aside": _field(row, "SetASide"),
        "set_aside_code": _field(row, "SetASideCode"),
        "organization_name": organization_name,
        "organization_code": _field(row, "AAC Code", "CGAC"),
        "agency_path": agency_path,
        "place_of_performance": {
            "city": _field(row, "PopCity", "PlaceOfPerformanceCity"),
            "state": state,
            "zip": zip_code,
            "country": _field(row, "PopCountry", "PlaceOfPerformanceCountry"),
        },
        "contact": {"name": "", "email": "", "phone": ""},
        "description": description,
        "sam_url": link,
    }


def _schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    PRAGMA journal_mode=DELETE;
    PRAGMA synchronous=NORMAL;
    CREATE TABLE opportunities (
      notice_id TEXT PRIMARY KEY, title TEXT NOT NULL, solicitation_number TEXT NOT NULL,
      type_code TEXT NOT NULL, naics_code TEXT NOT NULL, classification_code TEXT NOT NULL,
      set_aside_code TEXT NOT NULL, state TEXT NOT NULL, zip TEXT NOT NULL,
      organization_code TEXT NOT NULL, organization_name TEXT NOT NULL,
      agency_path TEXT NOT NULL, posted_date TEXT NOT NULL,
      response_deadline TEXT NOT NULL, active INTEGER NOT NULL, payload TEXT NOT NULL
    );
    CREATE VIRTUAL TABLE opportunity_fts USING fts5(
      notice_id UNINDEXED, title, description, organization_name, agency_path
    );
    CREATE INDEX opp_posted ON opportunities(active, posted_date);
    CREATE INDEX opp_deadline ON opportunities(active, response_deadline);
    CREATE INDEX opp_naics ON opportunities(naics_code);
    CREATE INDEX opp_type ON opportunities(type_code);
    CREATE INDEX opp_state ON opportunities(state);
    CREATE INDEX opp_set_aside ON opportunities(set_aside_code);
    """)


def _write_row(db: sqlite3.Connection, record: dict[str, Any]) -> None:
    place = record.get("place_of_performance") or {}
    db.execute(UPSERT, (
        str(record["notice_id"]), str(record.get("title") or ""),
        str(record.get("solicitation_number") or ""), str(record.get("type_code") or ""),
        str(record.get("naics_code") or ""), str(record.get("classification_code") or ""),
        str(record.get("set_aside_code") or ""), str(place.get("state") or ""),
        str(place.get("zip") or ""), str(record.get("organization_code") or ""),
        str(record.get("organization_name") or ""), str(record.get("agency_path") or ""),
        _iso(record.get("posted_date")), _iso(record.get("response_deadline")),
        int(bool(record.get("active"))), json.dumps(record, separators=(",", ":")),
    ))


def _rebuild_fts(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM opportunity_fts")
    for (payload,) in db.execute("SELECT payload FROM opportunities WHERE active = 1"):
        record = json.loads(payload)
        db.execute(
            "INSERT INTO opportunity_fts VALUES (?, ?, ?, ?, ?)",
            (
                record["notice_id"], record.get("title") or "",
                record.get("description") or "", record.get("organization_name") or "",
                record.get("agency_path") or "",
            ),
        )


def _validate(db: sqlite3.Connection, min_records: int) -> int:
    count = int(db.execute("SELECT COUNT(*) FROM opportunities WHERE active = 1").fetchone()[0])
    if count < min_records:
        raise ValueError(f"Index has only {count} active records; expected at least {min_records}")
    fts_count = int(db.execute("SELECT COUNT(*) FROM opportunity_fts").fetchone()[0])
    if count != fts_count:
        raise ValueError(f"FTS count {fts_count} does not match opportunity count {count}")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    return count


def build_from_csv(csv_path: str, output_path: str, *, min_records: int = 1) -> int:
    if Path(output_path).exists():
        raise FileExistsError(output_path)
    with open(csv_path, "r", encoding="utf-8-sig", errors="replace", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Opportunity CSV missing required columns: {', '.join(sorted(missing))}")
        with closing(sqlite3.connect(output_path)) as db:
            _schema(db)
            for number, row in enumerate(reader, start=1):
                record = normalize_csv_row(row)
                if record:
                    _write_row(db, record)
                if number % 10_000 == 0:
                    db.commit()
            _rebuild_fts(db)
            count = _validate(db, min_records)
            db.commit()
            db.execute("VACUUM")
            return count


def apply_delta(base_path: str, output_path: str, records: Iterable[dict[str, Any]], *, min_records: int = 1) -> int:
    """Apply normalized API results to a copy, never to a published index."""
    import shutil

    if Path(output_path).exists():
        raise FileExistsError(output_path)
    shutil.copyfile(base_path, output_path)
    with closing(sqlite3.connect(output_path)) as db:
        for record in records:
            if not record.get("notice_id"):
                continue
            if not record.get("description"):
                previous = db.execute(
                    "SELECT payload FROM opportunities WHERE notice_id = ?", (record["notice_id"],)
                ).fetchone()
                if previous:
                    record = {**record, "description": json.loads(previous[0]).get("description") or ""}
            _write_row(db, record)
        _rebuild_fts(db)
        count = _validate(db, min_records)
        db.commit()
        db.execute("VACUUM")
        return count
