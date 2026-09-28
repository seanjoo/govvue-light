"""Monthly public entity index with daily API-export overlays."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import local_index


def _col(cols: list[str], index: int) -> str:
    return cols[index].strip() if index < len(cols) and cols[index] else ""


def _iso(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _codes(value: str, *, naics: bool = False) -> list[str]:
    result: list[str] = []
    for raw in str(value or "").split("~"):
        code = raw.strip()[:6] if naics else raw.strip()
        if code and code not in result:
            result.append(code)
    return result


def _exclusion(value: str) -> str:
    # The public V2 extract uses D/null while the v4 search UI uses Y/N.
    flag = str(value or "").strip().upper()
    return "Y" if flag in {"D", "Y"} else "N" if flag in {"", "N"} else flag


def normalize_monthly_row(cols: list[str]) -> dict[str, Any] | None:
    """Map zero-based positions from GSA's Public File V2 layout v6.0.

    Important: position 6 is *purpose of registration*, not entity structure;
    entity structure is position 27. Old GovVue had this mislabeled.
    """
    uei = _col(cols, 0)
    if not uei or _col(cols, 5) != "A":
        return None
    business_codes = _codes(_col(cols, 31))
    sba_codes = _codes(_col(cols, 117))
    primary = _col(cols, 32)
    naics_codes = _codes(_col(cols, 34), naics=True)
    if primary and primary not in naics_codes:
        naics_codes.insert(0, primary)
    psc_codes = _codes(_col(cols, 36))
    address = {
        "line1": _col(cols, 15), "line2": _col(cols, 16),
        "city": _col(cols, 17), "state": _col(cols, 18),
        "zip": _col(cols, 19), "country": _col(cols, 21),
    }
    return {
        "uei": uei,
        "legal_business_name": _col(cols, 11) or "Unnamed entity",
        "dba_name": _col(cols, 12),
        "cage_code": _col(cols, 3),
        "dodaac": _col(cols, 4),
        "sam_registered": "Yes",
        "registration_status": "Active",
        "purpose_of_registration": _col(cols, 6),
        "purpose_registration_code": _col(cols, 6),
        "registration_date": _iso(_col(cols, 7)),
        "activation_date": _iso(_col(cols, 10)),
        "last_update_date": _iso(_col(cols, 9)),
        "expiration_date": _iso(_col(cols, 8)),
        "uei_status": "Active",
        "exclusion_status": _exclusion(_col(cols, 115)),
        "debt_subject_to_offset": _col(cols, 114),
        "address": address,
        "mailing_address": {
            "city": _col(cols, 41), "state": _col(cols, 45),
            "zip": _col(cols, 42), "country": _col(cols, 44),
        },
        "website": _col(cols, 26),
        "entity_structure": _col(cols, 27),
        "entity_structure_code": _col(cols, 27),
        "organization_structure": "Manufacturer of Goods" if "MF" in business_codes else "",
        "organization_structure_code": "MF" if "MF" in business_codes else "",
        "business_types": [{"code": code, "description": ""} for code in business_codes],
        "sba_business_types": [{"code": code, "description": ""} for code in sba_codes],
        "primary_naics": primary,
        "naics": [{"code": code, "description": ""} for code in naics_codes],
        "psc": [{"code": code, "description": ""} for code in psc_codes],
        "disaster_response_participant": "Yes" if _col(cols, 119).strip("0") else "No",
        "sam_url": f"https://sam.gov/entity/{uei}/coreData?status=Active",
        "incorporation_state_code": _col(cols, 28),
        "incorporation_country_code": _col(cols, 29),
        "congressional_district": _col(cols, 22),
    }


def _schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    PRAGMA journal_mode=DELETE;
    PRAGMA synchronous=NORMAL;
    CREATE TABLE entities (
      uei TEXT PRIMARY KEY, legal_business_name TEXT NOT NULL, dba_name TEXT NOT NULL,
      cage_code TEXT NOT NULL, dodaac TEXT NOT NULL, registration_status TEXT NOT NULL,
      purpose_registration_code TEXT NOT NULL, exclusion_status TEXT NOT NULL,
      debt_subject_to_offset TEXT NOT NULL, country_code TEXT NOT NULL,
      state TEXT NOT NULL, city TEXT NOT NULL, zip TEXT NOT NULL,
      entity_structure_code TEXT NOT NULL, organization_structure_code TEXT NOT NULL,
      primary_naics TEXT NOT NULL, registration_date TEXT NOT NULL,
      activation_date TEXT NOT NULL, update_date TEXT NOT NULL,
      expiration_date TEXT NOT NULL, incorporation_state_code TEXT NOT NULL,
      incorporation_country_code TEXT NOT NULL, congressional_district TEXT NOT NULL,
      payload TEXT NOT NULL
    );
    CREATE TABLE entity_naics (uei TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(uei, code));
    CREATE TABLE entity_psc (uei TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(uei, code));
    CREATE TABLE entity_business (uei TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(uei, code));
    CREATE TABLE entity_sba (uei TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(uei, code));
    CREATE INDEX entity_naics_code ON entity_naics(code);
    CREATE INDEX entity_psc_code ON entity_psc(code);
    CREATE INDEX entity_business_code ON entity_business(code);
    CREATE INDEX entity_sba_code ON entity_sba(code);
    CREATE INDEX entity_primary_naics ON entities(primary_naics);
    CREATE INDEX entity_country ON entities(country_code);
    CREATE INDEX entity_state ON entities(state);
    CREATE INDEX entity_purpose ON entities(purpose_registration_code);
    CREATE INDEX entity_expiration ON entities(expiration_date);
    CREATE INDEX entity_org_structure ON entities(organization_structure_code);
    CREATE VIRTUAL TABLE entity_fts USING fts5(uei UNINDEXED, legal_business_name, dba_name);
    """)


def _upsert(db: sqlite3.Connection, record: dict[str, Any]) -> None:
    uei = str(record.get("uei") or "").strip().upper()
    if not uei:
        return
    record = {**record, "exclusion_status": _exclusion(record.get("exclusion_status") or "")}
    address = record.get("address") or {}
    business_codes = [str(item.get("code") or "") for item in record.get("business_types") or []]
    org_structure = str(record.get("organization_structure_code") or "")
    if not org_structure and "MF" in business_codes:
        org_structure = "MF"
    db.execute("""
    INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        uei, str(record.get("legal_business_name") or ""), str(record.get("dba_name") or ""),
        str(record.get("cage_code") or ""), str(record.get("dodaac") or ""),
        str(record.get("registration_status") or ""),
        str(record.get("purpose_registration_code") or record.get("purpose_of_registration") or ""),
        str(record.get("exclusion_status") or ""), str(record.get("debt_subject_to_offset") or ""),
        str(address.get("country") or ""), str(address.get("state") or ""),
        str(address.get("city") or ""), str(address.get("zip") or ""),
        str(record.get("entity_structure_code") or record.get("entity_structure") or ""),
        org_structure, str(record.get("primary_naics") or ""),
        _iso(record.get("registration_date")), _iso(record.get("activation_date")),
        _iso(record.get("last_update_date")), _iso(record.get("expiration_date")),
        str(record.get("incorporation_state_code") or ""),
        str(record.get("incorporation_country_code") or ""),
        str(record.get("congressional_district") or ""),
        json.dumps(record, separators=(",", ":")),
    ))
    for table, field in (
        ("entity_naics", "naics"), ("entity_psc", "psc"),
        ("entity_business", "business_types"), ("entity_sba", "sba_business_types"),
    ):
        db.execute(f"DELETE FROM {table} WHERE uei = ?", (uei,))
        db.executemany(
            f"INSERT OR IGNORE INTO {table} VALUES (?, ?)",
            ((uei, str(item.get("code") or "")) for item in record.get(field) or [] if item.get("code")),
        )


def _finish(db: sqlite3.Connection, min_records: int) -> int:
    db.execute("DELETE FROM entity_fts")
    db.execute("INSERT INTO entity_fts SELECT uei, legal_business_name, dba_name FROM entities")
    count = int(db.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
    if count < min_records:
        raise ValueError(f"Entity index has only {count} active records; expected {min_records}")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("Entity SQLite integrity check failed")
    db.commit()
    db.execute("VACUUM")
    return count


def build_monthly(zip_path: str, output_path: str, *, min_records: int = 1) -> int:
    if Path(output_path).exists():
        raise FileExistsError(output_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith((".dat", ".csv"))]
        if len(names) != 1:
            raise ValueError("Entity ZIP must contain one DAT/CSV file")
        with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace") as text:
            with closing(sqlite3.connect(output_path)) as db:
                _schema(db)
                for number, line in enumerate(text, 1):
                    if line.startswith(("BOF", "EOF", "!end")) or not line.strip():
                        continue
                    # GSA's extract has literal pipe separators and stray quote
                    # characters; conventional CSV quote handling is unsafe.
                    record = normalize_monthly_row(line.rstrip("\r\n").split("|"))
                    if record:
                        _upsert(db, record)
                    if number % 5_000 == 0:
                        db.commit()
                return _finish(db, min_records)


def apply_daily(base_path: str, output_path: str, records: Iterable[dict[str, Any]], *, min_records: int = 1) -> int:
    """Copy monthly/current index then apply daily normalized API records."""
    import shutil

    if Path(output_path).exists():
        raise FileExistsError(output_path)
    shutil.copyfile(base_path, output_path)
    with closing(sqlite3.connect(output_path)) as db:
        for record in records:
            if not record.get("uei"):
                continue
            if str(record.get("registration_status") or "").casefold() not in {"active", "a"}:
                db.execute("DELETE FROM entities WHERE uei = ?", (record["uei"],))
                for table in ("entity_naics", "entity_psc", "entity_business", "entity_sba"):
                    db.execute(f"DELETE FROM {table} WHERE uei = ?", (record["uei"],))
            else:
                _upsert(db, record)
        return _finish(db, min_records)


SUPPORTED_FILTERS = {
    "uei", "cage_code", "dodaac", "legal_business_name", "dba_name",
    "sam_registered", "registration_status", "debt_subject_to_offset",
    "exclusion_status", "purpose_registration_code", "city",
    "congressional_district", "country_code", "state", "zip",
    "entity_structure_code", "organization_structure_code",
    "organization_structure_description", "business_type_code",
    "sba_business_type_code", "primary_naics", "naics_code", "psc_code",
    "incorporation_state_code", "incorporation_country_code",
    "registration_date_from", "registration_date_to", "activation_date_from",
    "activation_date_to", "update_date_from", "update_date_to",
    "expiration_date_from", "expiration_date_to",
}


def search(criteria: dict[str, str], page: int, per_page: int = 10) -> dict[str, Any]:
    unsupported = [key for key, value in criteria.items() if value and key not in SUPPORTED_FILTERS]
    if unsupported:
        raise local_index.LocalIndexUnavailable(
            "These entity filters still require a live SAM search: " + ", ".join(sorted(unsupported))
        )
    path, manifest = local_index.current_index("entities")
    clauses = ["(expiration_date = '' OR expiration_date >= ?)"]
    args: list[Any] = [date.today().isoformat()]
    for key, column in (
        ("uei", "uei"), ("cage_code", "cage_code"), ("dodaac", "dodaac"),
        ("purpose_registration_code", "purpose_registration_code"),
        ("exclusion_status", "exclusion_status"),
        ("debt_subject_to_offset", "debt_subject_to_offset"),
        ("country_code", "country_code"), ("state", "state"),
        ("entity_structure_code", "entity_structure_code"),
        ("organization_structure_code", "organization_structure_code"),
        ("primary_naics", "primary_naics"),
        ("incorporation_state_code", "incorporation_state_code"),
        ("incorporation_country_code", "incorporation_country_code"),
        ("congressional_district", "congressional_district"),
    ):
        values = [item.strip() for item in criteria.get(key, "").split(",") if item.strip()]
        if values:
            clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
            args.extend(values)
    if criteria.get("registration_status") and criteria["registration_status"] not in {"A", "Active"}:
        raise local_index.LocalIndexUnavailable("Only active entities are indexed locally")
    if criteria.get("sam_registered") and criteria["sam_registered"] != "Yes":
        raise local_index.LocalIndexUnavailable("Only registered entities are indexed locally")
    if criteria.get("organization_structure_code") and any(
        value.strip() != "MF"
        for value in criteria["organization_structure_code"].split(",")
        if value.strip()
    ):
        raise local_index.LocalIndexUnavailable(
            "Only Manufacturer of Goods organization structure is indexed locally"
        )
    if criteria.get("organization_structure_description"):
        if criteria["organization_structure_description"].casefold() != "manufacturer of goods":
            raise local_index.LocalIndexUnavailable("This organization structure requires a live SAM search")
        clauses.append("organization_structure_code = 'MF'")
    for key, column in (("legal_business_name", "legal_business_name"), ("dba_name", "dba_name"), ("city", "city"), ("zip", "zip")):
        if criteria.get(key):
            clauses.append(f"lower({column}) LIKE ?")
            args.append(f"%{criteria[key].casefold()}%")
    for key, table in (("naics_code", "entity_naics"), ("psc_code", "entity_psc"), ("business_type_code", "entity_business"), ("sba_business_type_code", "entity_sba")):
        values = [item.strip() for item in criteria.get(key, "").split(",") if item.strip()]
        if values:
            clauses.append(f"EXISTS (SELECT 1 FROM {table} x WHERE x.uei = entities.uei AND x.code IN ({','.join('?' for _ in values)}))")
            args.extend(values)
    for key, column in (("registration_date", "registration_date"), ("activation_date", "activation_date"), ("update_date", "update_date"), ("expiration_date", "expiration_date")):
        for suffix, operator in (("from", ">="), ("to", "<=")):
            value = criteria.get(f"{key}_{suffix}")
            if value:
                parsed = date.fromisoformat(value).isoformat()
                clauses.append(f"{column} {operator} ?")
                args.append(parsed)
    where = " AND ".join(clauses)
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        total = int(db.execute(f"SELECT COUNT(*) FROM entities WHERE {where}", args).fetchone()[0])
        rows = db.execute(
            f"SELECT payload FROM entities WHERE {where} ORDER BY legal_business_name, uei LIMIT ? OFFSET ?",
            [*args, per_page, (page - 1) * per_page],
        ).fetchall()
    return {
        "items": [json.loads(row[0]) for row in rows], "page": page,
        "per_page": per_page, "total_records": total,
        "has_next": page * per_page < total, "cache_hit": True,
        "source": "local", "source_date": manifest["source_date"],
        "index_version": manifest["version"],
    }


def detail(uei: str) -> dict[str, Any] | None:
    path, _ = local_index.current_index("entities")
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
        row = db.execute("SELECT payload FROM entities WHERE uei = ?", (uei,)).fetchone()
    return json.loads(row[0]) if row else None
