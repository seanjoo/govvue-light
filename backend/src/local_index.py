"""Read-only, versioned SQLite opportunity search indexes staged in S3.

The index is immutable once published. A small manifest is switched only after
the builder validates and uploads the complete database, so concurrent Lambda
readers never see a partially written file.
"""

from __future__ import annotations

import hashlib
import gzip
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import boto3


MANIFEST_KEY = "indexes/opportunities/current.json"
_MANIFEST_TTL_SECONDS = 60
_lock = threading.Lock()
_last_check: dict[str, float] = {}
_cached_manifest: dict[str, dict[str, Any]] = {}
_cached_path: dict[str, str] = {}
_pinned_paths: dict[str, str] = {}
_s3 = None


class LocalIndexUnavailable(RuntimeError):
    """No validated local index is ready; direct SAM search may be used."""


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _read_manifest(bucket: str, kind: str) -> dict[str, Any]:
    payload = _client().get_object(Bucket=bucket, Key=f"indexes/{kind}/current.json")["Body"].read()
    manifest = json.loads(payload)
    if not isinstance(manifest, dict) or not all(
        isinstance(manifest.get(name), str) and manifest[name]
        for name in ("key", "sha256", "version", "source_date")
    ):
        raise LocalIndexUnavailable("Opportunity index manifest is invalid")
    if not re.fullmatch(r"[a-f0-9]{64}", manifest["sha256"]):
        raise LocalIndexUnavailable("Opportunity index checksum is invalid")
    if not manifest["key"].startswith(f"indexes/{kind}/versions/"):
        raise LocalIndexUnavailable("Opportunity index key is invalid")
    if manifest.get("compression") not in (None, "gzip"):
        raise LocalIndexUnavailable("Index compression is unsupported")
    if manifest.get("compression") == "gzip" and not manifest["key"].endswith(".sqlite.gz"):
        raise LocalIndexUnavailable("Compressed index key is invalid")
    return manifest


def current_manifest(kind: str = "opportunities") -> dict[str, Any]:
    """Read publication metadata without downloading the large SQLite artifact."""
    bucket = os.environ.get("LOCAL_INDEX_BUCKET", "")
    if not bucket:
        raise LocalIndexUnavailable("Local search is not configured")
    try:
        return _read_manifest(bucket, kind)
    except Exception as exc:
        raise LocalIndexUnavailable(f"{kind.capitalize()} index is not published") from exc


def current_index(kind: str = "opportunities") -> tuple[str, dict[str, Any]]:
    """Download a changed S3 index once per warm Lambda runtime.

    A missing index is expected before the first backfill. An invalid index is
    never used, and the caller can fall back to direct SAM search.
    """
    if kind not in {"opportunities", "entities"}:
        raise ValueError("Unsupported local index kind")
    bucket = os.environ.get("LOCAL_INDEX_BUCKET", "")
    if not bucket:
        raise LocalIndexUnavailable("Local opportunity search is not configured")
    with _lock:
        now = time.monotonic()
        if (
            kind in _cached_manifest
            and kind in _cached_path
            and Path(_cached_path[kind]).is_file()
            and now - _last_check.get(kind, 0) < _MANIFEST_TTL_SECONDS
        ):
            return _cached_path[kind], _cached_manifest[kind]
        try:
            manifest = _read_manifest(bucket, kind)
        except Exception as exc:
            raise LocalIndexUnavailable("Opportunity index is not published") from exc
        _last_check[kind] = now
        if (
            kind in _cached_manifest
            and _cached_manifest[kind]["version"] == manifest["version"]
            and kind in _cached_path
            and Path(_cached_path[kind]).is_file()
        ):
            return _cached_path[kind], _cached_manifest[kind]

        fd, temp_path = tempfile.mkstemp(prefix=f"govvue-{kind}-", suffix=".sqlite", dir="/tmp")
        os.close(fd)
        try:
            digest = hashlib.sha256()
            body = _client().get_object(Bucket=bucket, Key=manifest["key"])["Body"]
            source = gzip.GzipFile(fileobj=body) if manifest.get("compression") == "gzip" else body
            try:
                with open(temp_path, "wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
            finally:
                source.close()
                body.close()
            if digest.hexdigest() != manifest["sha256"]:
                raise LocalIndexUnavailable("Opportunity index checksum mismatch")
            # The builder runs integrity_check before publishing. Matching its
            # SHA-256 proves this is exactly that artifact; a second full scan
            # here would make cold API requests unnecessarily slow.
            previous_path = _cached_path.get(kind)
            _cached_path[kind] = temp_path
            _cached_manifest[kind] = manifest
            if previous_path and previous_path != temp_path:
                Path(previous_path).unlink(missing_ok=True)
            return temp_path, manifest
        except Exception as exc:
            Path(temp_path).unlink(missing_ok=True)
            raise LocalIndexUnavailable("Opportunity index could not be loaded") from exc


def pinned_opportunity_index(key: str, sha256: str) -> str:
    """Load the exact index version chosen when a daily feed run started."""
    if not re.fullmatch(r"indexes/opportunities/versions/[^/]+/opportunities\.sqlite(?:\.gz)?", key):
        raise LocalIndexUnavailable("Invalid pinned opportunity index key")
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise LocalIndexUnavailable("Invalid pinned opportunity index checksum")
    with _lock:
        cached = _pinned_paths.get(key)
        if cached and Path(cached).is_file():
            return cached
        bucket = os.environ.get("LOCAL_INDEX_BUCKET", "")
        if not bucket:
            raise LocalIndexUnavailable("Local opportunity index is not configured")
        fd, path = tempfile.mkstemp(prefix="govvue-feed-", suffix=".sqlite", dir="/tmp")
        os.close(fd)
        try:
            digest = hashlib.sha256()
            body = _client().get_object(Bucket=bucket, Key=key)["Body"]
            source = gzip.GzipFile(fileobj=body) if key.endswith(".sqlite.gz") else body
            try:
                with open(path, "wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
            finally:
                source.close()
                body.close()
            if digest.hexdigest() != sha256:
                raise LocalIndexUnavailable("Pinned opportunity index checksum mismatch")
            for old in _pinned_paths.values():
                if old != path:
                    Path(old).unlink(missing_ok=True)
            _pinned_paths.clear()
            _pinned_paths[key] = path
            return path
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise


def feed_page(index_key: str, index_sha256: str, posted_from: str,
              posted_to: str, page_index: int, page_size: int) -> dict[str, Any]:
    path = pinned_opportunity_index(index_key, index_sha256)
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        where = "active = 1 AND posted_date >= ? AND posted_date <= ?"
        total = int(db.execute(f"SELECT COUNT(*) FROM opportunities WHERE {where}",
                               (posted_from, posted_to)).fetchone()[0])
        rows = db.execute(
            f"SELECT payload FROM opportunities WHERE {where} ORDER BY posted_date, notice_id LIMIT ? OFFSET ?",
            (posted_from, posted_to, page_size, page_index * page_size),
        ).fetchall()
    return {"records": [json.loads(row[0]) for row in rows], "total_records": total}


def _date(value: str, name: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def _values(value: str, separator: str = ",") -> list[str]:
    return list(dict.fromkeys(part.strip() for part in str(value or "").split(separator) if part.strip()))


def _in_filter(column: str, values: list[str], clauses: list[str], arguments: list[Any]) -> None:
    if values:
        clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
        arguments.extend(values)


def _text_filter(column: str, values: list[str], clauses: list[str], arguments: list[Any]) -> None:
    if values:
        clauses.append("(" + " OR ".join(f"lower({column}) LIKE ?" for _ in values) + ")")
        arguments.extend(f"%{value.casefold()}%" for value in values)


def _terms(value: str) -> list[str]:
    # FTS syntax is constructed from quoted literals, never raw model/user text.
    return [term for term in re.findall(r"[\w-]+", str(value or ""), flags=re.UNICODE) if term]


def search(criteria: dict[str, str], page: int, per_page: int) -> dict[str, Any]:
    path, manifest = current_index()
    today = date.today()
    if criteria.get("posted_within"):
        try:
            days = int(criteria["posted_within"])
        except ValueError as exc:
            raise ValueError("posted_within must be 7, 14, 30, 60, or 90") from exc
        if days not in {7, 14, 30, 60, 90}:
            raise ValueError("posted_within must be 7, 14, 30, 60, or 90")
        posted_from = (today - timedelta(days=days - 1)).isoformat()
        posted_to = today.isoformat()
    else:
        posted_from = _date(criteria.get("posted_from", ""), "posted_from")
        posted_to = _date(criteria.get("posted_to", ""), "posted_to")
        if not posted_from and not posted_to:
            posted_from = (today - timedelta(days=29)).isoformat()
            posted_to = today.isoformat()
    if posted_from and posted_to and posted_from > posted_to:
        raise ValueError("posted_from cannot be later than posted_to")

    clauses = ["active = 1"]
    args: list[Any] = []
    for key, column in (
        ("ptype", "type_code"),
        ("naics_code", "naics_code"),
        ("classification_code", "classification_code"),
        ("set_aside", "set_aside_code"),
        ("state", "state"),
        ("zip", "zip"),
        ("organization_code", "organization_code"),
    ):
        _in_filter(column, _values(criteria.get(key, "")), clauses, args)
    for key, column, separator in (
        ("organization_name", "agency_path || ' ' || organization_name", "|"),
        ("notice_id", "notice_id", ","),
        ("solicitation_number", "solicitation_number", ","),
    ):
        _text_filter(column, _values(criteria.get(key, ""), separator), clauses, args)
    excluded_agencies = _values(criteria.get("exclude_organization_name", ""), "|")
    for value in excluded_agencies:
        clauses.append("lower(agency_path || ' ' || organization_name) NOT LIKE ?")
        args.append(f"%{value.casefold()}%")
    if posted_from:
        clauses.append("posted_date >= ?")
        args.append(posted_from)
    if posted_to:
        clauses.append("posted_date <= ?")
        args.append(posted_to)
    deadline_from = _date(criteria.get("response_deadline_from", ""), "response_deadline_from")
    deadline_to = _date(criteria.get("response_deadline_to", ""), "response_deadline_to")
    if criteria.get("open_deadlines_only") == "true":
        deadline_from = max(deadline_from, today.isoformat())
    if deadline_from:
        clauses.append("response_deadline >= ?")
        args.append(deadline_from)
    if deadline_to:
        clauses.append("response_deadline <= ?")
        args.append(deadline_to)
    if deadline_from and deadline_to and deadline_from > deadline_to:
        raise ValueError("response_deadline_from cannot be later than response_deadline_to")

    title_terms = _terms(criteria.get("title", ""))
    if title_terms:
        clauses.append("notice_id IN (SELECT notice_id FROM opportunity_fts WHERE opportunity_fts MATCH ?)")
        args.append(" AND ".join(f'"{term}"' for term in title_terms))
    any_terms = _terms(criteria.get("include_terms_any", ""))
    if any_terms:
        clauses.append("notice_id IN (SELECT notice_id FROM opportunity_fts WHERE opportunity_fts MATCH ?)")
        args.append(" OR ".join(f'"{term}"' for term in any_terms))
    for term in _terms(criteria.get("exclude_terms", "")):
        clauses.append("notice_id NOT IN (SELECT notice_id FROM opportunity_fts WHERE opportunity_fts MATCH ?)")
        args.append(f'"{term}"')

    sort = criteria.get("sort") or "response_deadline_desc"
    sorts = {
        "posted_desc": "posted_date DESC, notice_id ASC",
        "posted_asc": "posted_date ASC, notice_id ASC",
        "response_deadline_desc": "(response_deadline = '') ASC, response_deadline DESC, notice_id ASC",
        "response_deadline_asc": "(response_deadline = '') ASC, response_deadline ASC, notice_id ASC",
    }
    if sort not in sorts:
        raise ValueError("Unsupported opportunity sort order")
    where = " AND ".join(clauses)
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        total = int(db.execute(f"SELECT COUNT(*) FROM opportunities WHERE {where}", args).fetchone()[0])
        rows = db.execute(
            f"SELECT payload FROM opportunities WHERE {where} ORDER BY {sorts[sort]} LIMIT ? OFFSET ?",
            [*args, per_page, (page - 1) * per_page],
        ).fetchall()
    return {
        "items": [json.loads(row[0]) for row in rows],
        "page": page,
        "per_page": per_page,
        "total_records": total,
        "has_next": page * per_page < total,
        "cache_hit": True,
        "upstream_queries": 0,
        "sort": sort,
        "source": "local",
        "source_date": manifest["source_date"],
        "index_version": manifest["version"],
    }


def detail(notice_id: str) -> dict[str, Any] | None:
    path, _ = current_index()
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        row = db.execute(
            "SELECT payload FROM opportunities WHERE notice_id = ? AND active = 1", (notice_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None
