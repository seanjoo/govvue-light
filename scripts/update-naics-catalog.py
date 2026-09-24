#!/usr/bin/env python3
"""Generate the frontend NAICS hierarchy from the official Census XLSX file."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


DEFAULT_SOURCE = "https://www.census.gov/naics/2022NAICS/2022_NAICS_Structure.xlsx"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "frontend/src/data/naics-2022.json"
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
VALID_CODE = re.compile(r"(?:\d{2}(?:-\d{2})?|\d{3,6})\Z")


def _download(source: str) -> bytes:
    local = Path(source)
    if local.is_file():
        return local.read_bytes()
    request = urllib.request.Request(source, headers={"User-Agent": "GovVue-Light/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(f"{XML_NS}si"):
        runs = item.findall(f"{XML_NS}r")
        if not runs:
            values.append("".join(text.text or "" for text in item.iter(f"{XML_NS}t")))
            continue
        parts: list[str] = []
        for run in runs:
            vertical_alignment = run.find(
                f"{XML_NS}rPr/{XML_NS}vertAlign"
            )
            if vertical_alignment is not None and vertical_alignment.get("val") == "superscript":
                continue
            parts.extend(text.text or "" for text in run.iter(f"{XML_NS}t"))
        values.append("".join(parts))
    return values


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    value = cell.find(f"{XML_NS}v")
    if value is None or value.text is None:
        return ""
    if cell.get("t") == "s":
        return shared[int(value.text)]
    return value.text


def _records(workbook: bytes) -> list[dict[str, str | None]]:
    with zipfile.ZipFile(io.BytesIO(workbook)) as archive:
        shared = _shared_strings(archive)
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    records: list[dict[str, str | None]] = []
    last_by_level: dict[int, str] = {}
    for row in sheet.iter(f"{XML_NS}row"):
        cells = {
            re.match(r"[A-Z]+", cell.get("r", "")).group(0): _cell_value(cell, shared)
            for cell in row.findall(f"{XML_NS}c")
            if re.match(r"[A-Z]+", cell.get("r", ""))
        }
        code = cells.get("B", "").strip()
        title = re.sub(r"\s+", " ", cells.get("C", "")).strip()
        if not title or not VALID_CODE.fullmatch(code):
            continue

        level = 2 if "-" in code else len(code)
        parent = None if level == 2 else last_by_level.get(level - 1)
        if level > 2 and not parent:
            raise RuntimeError(f"Could not resolve parent for NAICS {code}")
        records.append({"code": code, "title": title, "parent": parent})
        for deeper_level in [value for value in last_by_level if value >= level]:
            del last_by_level[deeper_level]
        last_by_level[level] = code

    if len(records) < 2_000 or sum(len(item["code"]) == 6 for item in records) < 1_000:
        raise RuntimeError("Generated NAICS catalog is unexpectedly incomplete")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    workbook = _download(args.source)
    records = _records(workbook)
    payload = {
        "version": "2022",
        "source": DEFAULT_SOURCE,
        "sourceSha256": hashlib.sha256(workbook).hexdigest(),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    leaf_count = sum(len(item["code"]) == 6 for item in records)
    print(f"Wrote {len(records)} NAICS nodes ({leaf_count} selectable leaves) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
