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
from opportunity_versions import logical_key, posted_timestamp, similar_title


REQUIRED_COLUMNS = {"NoticeId", "Title", "PostedDate", "Active"}
UPSERT = """
INSERT INTO opportunities (
  notice_id, title, solicitation_number, type_code, naics_code,
  classification_code, set_aside_code, state, zip, organization_code,
  organization_name, agency_path, posted_date, posted_at, response_deadline,
  active, logical_key, is_current, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(notice_id) DO UPDATE SET
  title=excluded.title, solicitation_number=excluded.solicitation_number,
  type_code=excluded.type_code, naics_code=excluded.naics_code,
  classification_code=excluded.classification_code,
  set_aside_code=excluded.set_aside_code, state=excluded.state,
  zip=excluded.zip, organization_code=excluded.organization_code,
  organization_name=excluded.organization_name, agency_path=excluded.agency_path,
  posted_date=excluded.posted_date, posted_at=excluded.posted_at,
  response_deadline=excluded.response_deadline, active=excluded.active,
  logical_key=excluded.logical_key, is_current=excluded.is_current,
  payload=excluded.payload
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
        "posted_at": posted_timestamp(_field(row, "PostedDate")),
        "response_deadline": _iso(_field(row, "ResponseDeadLine")),
        "archive_date": _iso(_field(row, "ArchiveDate")),
        "active": True,
        "naics_code": _field(row, "NaicsCode"),
        "classification_code": _field(row, "ClassificationCode"),
        "set_aside": _field(row, "SetASide"),
        "set_aside_code": _field(row, "SetASideCode"),
        "organization_name": organization_name,
        "organization_code": _field(row, "AAC Code", "CGAC"),
        "version_office_code": _field(row, "AAC Code"),
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
      agency_path TEXT NOT NULL, posted_date TEXT NOT NULL, posted_at TEXT NOT NULL,
      response_deadline TEXT NOT NULL, active INTEGER NOT NULL,
      logical_key TEXT NOT NULL, is_current INTEGER NOT NULL, payload TEXT NOT NULL
    );
    CREATE VIRTUAL TABLE opportunity_fts USING fts5(
      notice_id UNINDEXED, title, description, organization_name, agency_path
    );
    CREATE INDEX opp_posted ON opportunities(active, is_current, posted_date);
    CREATE INDEX opp_deadline ON opportunities(active, response_deadline);
    CREATE INDEX opp_naics ON opportunities(naics_code);
    CREATE INDEX opp_type ON opportunities(type_code);
    CREATE INDEX opp_state ON opportunities(state);
    CREATE INDEX opp_set_aside ON opportunities(set_aside_code);
    CREATE INDEX opp_logical_key ON opportunities(logical_key, posted_at);
    """)


def _ensure_version_columns(db: sqlite3.Connection) -> None:
    """Allow a poll to overlay an index built before version tracking shipped."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(opportunities)")}
    if "posted_at" in columns:
        return
    db.execute("ALTER TABLE opportunities ADD COLUMN posted_at TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE opportunities ADD COLUMN logical_key TEXT NOT NULL DEFAULT ''")
    db.execute("ALTER TABLE opportunities ADD COLUMN is_current INTEGER NOT NULL DEFAULT 1")
    rows = db.execute(
        "SELECT notice_id, solicitation_number, organization_code, type_code, title, posted_date "
        "FROM opportunities"
    )
    db.executemany(
        "UPDATE opportunities SET posted_at = ?, logical_key = ? WHERE notice_id = ?",
        (
            (posted_timestamp(posted_date), logical_key({
                "solicitation_number": solicitation, "organization_code": office,
                "type_code": notice_type, "title": title,
            }), notice_id)
            for notice_id, solicitation, office, notice_type, title, posted_date in rows
        ),
    )
    db.execute("CREATE INDEX opp_logical_key ON opportunities(logical_key, posted_at)")


def _write_row(db: sqlite3.Connection, record: dict[str, Any]) -> None:
    place = record.get("place_of_performance") or {}
    db.execute(UPSERT, (
        str(record["notice_id"]), str(record.get("title") or ""),
        str(record.get("solicitation_number") or ""), str(record.get("type_code") or ""),
        str(record.get("naics_code") or ""), str(record.get("classification_code") or ""),
        str(record.get("set_aside_code") or ""), str(place.get("state") or ""),
        str(place.get("zip") or ""), str(record.get("organization_code") or ""),
        str(record.get("organization_name") or ""), str(record.get("agency_path") or ""),
        _iso(record.get("posted_date")),
        posted_timestamp(record.get("posted_at") or record.get("posted_date")),
        _iso(record.get("response_deadline")), int(bool(record.get("active"))),
        logical_key(record), 1, json.dumps(record, separators=(",", ":")),
    ))


def _mark_current_versions(db: sqlite3.Connection) -> None:
    db.execute("UPDATE opportunities SET is_current = 1 WHERE is_current != 1")
    duplicate_keys = [row[0] for row in db.execute(
        "SELECT logical_key FROM opportunities WHERE active = 1 AND logical_key != '' "
        "GROUP BY logical_key HAVING COUNT(*) > 1"
    )]
    for key in duplicate_keys:
        rows = db.execute(
            "SELECT notice_id, title FROM opportunities WHERE active = 1 AND logical_key = ? "
            "ORDER BY posted_at DESC, notice_id DESC", (key,),
        ).fetchall()
        kept_titles: list[str] = []
        superseded: list[tuple[str]] = []
        for notice_id, title in rows:
            if any(similar_title(title, kept) for kept in kept_titles):
                superseded.append((notice_id,))
            else:
                kept_titles.append(title)
        db.executemany("UPDATE opportunities SET is_current = 0 WHERE notice_id = ?", superseded)


def _rebuild_fts(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM opportunity_fts")
    for (payload,) in db.execute("SELECT payload FROM opportunities WHERE active = 1 AND is_current = 1"):
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
    raw_count = int(db.execute("SELECT COUNT(*) FROM opportunities WHERE active = 1").fetchone()[0])
    if raw_count < min_records:
        raise ValueError(f"Index has only {raw_count} active source rows; expected at least {min_records}")
    count = int(db.execute("SELECT COUNT(*) FROM opportunities WHERE active = 1 AND is_current = 1").fetchone()[0])
    if not count:
        raise ValueError("Index has no current active opportunities")
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
            _mark_current_versions(db)
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
        _ensure_version_columns(db)
        api_current_ids: dict[str, tuple[str, str]] = {}
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
            key = logical_key(record)
            if key and record.get("active"):
                api_current_ids[key] = (str(record["notice_id"]), str(record.get("title") or ""))
        _mark_current_versions(db)
        # The public API is authoritative when its date-only posted value
        # cannot order same-day CSV versions precisely.
        for key, (notice_id, title) in api_current_ids.items():
            for old_id, old_title in db.execute(
                "SELECT notice_id, title FROM opportunities WHERE active = 1 AND logical_key = ?", (key,)
            ).fetchall():
                if similar_title(title, old_title):
                    db.execute(
                        "UPDATE opportunities SET is_current = ? WHERE notice_id = ?",
                        (int(old_id == notice_id), old_id),
                    )
        _rebuild_fts(db)
        count = _validate(db, min_records)
        db.commit()
        db.execute("VACUUM")
        return count
