from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import local_index
import ingest_opportunities
from opportunity_versions import collapse_versions
from local_index_builder import apply_delta, build_from_csv


class LocalIndexTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        source = Path(self.work.name) / "source.csv"
        with source.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=[
                "NoticeId", "Title", "PostedDate", "Active", "Description",
                "Type", "ResponseDeadLine", "NaicsCode", "SetASideCode",
                "Department/Ind.Agency", "Office", "PopState", "Link",
            ])
            writer.writeheader()
            writer.writerow({
                "NoticeId": "CIV-1", "Title": "Cloud hosting support",
                "PostedDate": date.today().isoformat(), "Active": "Yes",
                "Description": "Cloud operations and migration services",
                "Type": "Solicitation", "ResponseDeadLine": "12/31/2099",
                "NaicsCode": "541512", "SetASideCode": "SBA",
                "Department/Ind.Agency": "Department of Energy", "Office": "Energy Office",
                "PopState": "VA", "Link": "https://sam.gov/opp/CIV-1/view",
            })
            writer.writerow({
                "NoticeId": "DOD-1", "Title": "Cloud hosting support",
                "PostedDate": date.today().isoformat(), "Active": "Yes",
                "Description": "Cloud operations services",
                "Type": "Solicitation", "ResponseDeadLine": "12/31/2099",
                "NaicsCode": "541511", "SetASideCode": "SBP",
                "Department/Ind.Agency": "DEFENSE, DEPARTMENT OF", "Office": "Army",
                "PopState": "MD", "Link": "https://sam.gov/opp/DOD-1/view",
            })
            writer.writerow({
                "NoticeId": "OLD-1", "Title": "Inactive cloud notice",
                "PostedDate": date.today().isoformat(), "Active": "No",
            })
        self.path = str(Path(self.work.name) / "index.sqlite")
        self.assertEqual(build_from_csv(str(source), self.path), 2)
        self.manifest = {"version": "test", "source_date": date.today().isoformat()}

    def _search(self, criteria):
        with patch.object(local_index, "current_index", return_value=(self.path, self.manifest)):
            return local_index.search(criteria, 1, 25)

    def test_full_text_filters_sort_and_civilian_exclusion(self):
        result = self._search({
            "title": "cloud support", "naics_code": "541511,541512",
            "set_aside": "SBA,SBP", "exclude_organization_name": "Defense, Department of",
            "sort": "response_deadline_desc",
        })
        self.assertEqual(result["total_records"], 1)
        self.assertEqual(result["items"][0]["notice_id"], "CIV-1")
        self.assertEqual(result["source"], "local")
        self.assertIn("description", result["items"][0])

    def test_no_sam_fanout_limit_or_page_sort_limit(self):
        values = ",".join(["541512"] + [str(100000 + number) for number in range(40)])
        result = self._search({"naics_code": values, "sort": "posted_asc"})
        self.assertEqual(result["total_records"], 1)

    def test_daily_delta_is_copy_on_write(self):
        output = str(Path(self.work.name) / "updated.sqlite")
        count = apply_delta(self.path, output, [{
            "notice_id": "CIV-2", "title": "Web application operations",
            "description": "civilian software support", "posted_date": date.today().isoformat(),
            "response_deadline": "2099-12-31", "active": True,
            "naics_code": "541511", "type_code": "o", "place_of_performance": {"state": "VA"},
        }])
        self.assertEqual(count, 3)
        with patch.object(local_index, "current_index", return_value=(output, self.manifest)):
            result = local_index.search({"title": "web application"}, 1, 25)
        self.assertEqual(result["items"][0]["notice_id"], "CIV-2")
        self.assertEqual(self._search({})["total_records"], 2)

    def test_daily_feed_uses_pinned_index_and_date_window(self):
        checksum = hashlib.sha256(Path(self.path).read_bytes()).hexdigest()
        key = "indexes/opportunities/versions/test/opportunities.sqlite"
        with patch.object(local_index, "pinned_opportunity_index", return_value=self.path):
            result = local_index.feed_page(
                key, checksum, date.today().isoformat(), date.today().isoformat(), 0, 1
            )
        self.assertEqual(result["total_records"], 2)
        self.assertEqual(len(result["records"]), 1)

    def test_revised_csv_postings_keep_latest_but_preserve_older_detail(self):
        source = Path(self.work.name) / "versions.csv"
        rows = [
            ("IRS-OLD", "IRS27-220503", "2032H5", "Sources Sought", "SAP Software Subscription", "2026-09-28 10:19:12"),
            ("IRS-NEW", "IRS27-220503", "2032H5", "Sources Sought", "SAP Software Subscription", "2026-09-28 10:25:17"),
            ("FA-OLD", "FA940126Mishap", "FA9401", "Sources Sought", "Requesting infomation for MISHAP ANALYSIS & ANIMATION FACILITY", "2026-09-28 12:47:09"),
            ("FA-NEW", "FA940126Mishap", "FA9401", "Sources Sought", "Requesting information for MISHAP ANALYSIS & ANIMATION FACILITY", "2026-09-28 12:50:49"),
            # Same solicitation but clearly different title must remain visible.
            ("FA-OTHER", "FA940126Mishap", "FA9401", "Sources Sought", "Unrelated replacement equipment notice", "2026-09-28 13:00:00"),
            # Same number issued by a different office is a separate notice.
            ("IRS-OTHER-OFFICE", "IRS27-220503", "OTHER", "Sources Sought", "SAP Software Subscription", "2026-09-28 11:00:00"),
        ]
        with source.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=[
                "NoticeId", "Sol#", "AAC Code", "Type", "Title", "PostedDate", "Active",
            ])
            writer.writeheader()
            for notice_id, sol, office, kind, title, posted in rows:
                writer.writerow({"NoticeId": notice_id, "Sol#": sol, "AAC Code": office,
                                 "Type": kind, "Title": title, "PostedDate": posted, "Active": "Yes"})
        index = str(Path(self.work.name) / "versions.sqlite")
        # Six valid source rows pass the source-size guard even though only
        # four latest logical opportunities should be searchable.
        self.assertEqual(build_from_csv(str(source), index, min_records=6), 4)
        with patch.object(local_index, "current_index", return_value=(index, self.manifest)):
            self.assertEqual(local_index.search({"posted_from": "2026-09-28", "posted_to": "2026-09-28"}, 1, 25)["total_records"], 4)
            self.assertIsNotNone(local_index.detail("IRS-OLD"))
            self.assertIsNotNone(local_index.detail("FA-OLD"))
        with patch.object(local_index, "pinned_opportunity_index", return_value=index):
            feed = local_index.feed_page("unused", "unused", "2026-09-28", "2026-09-28", 0, 25)
        self.assertEqual({item["notice_id"] for item in feed["records"]},
                         {"IRS-NEW", "FA-NEW", "FA-OTHER", "IRS-OTHER-OFFICE"})

    def test_api_delta_selects_latest_record_when_api_lacks_time(self):
        source = Path(self.work.name) / "poll-versions.csv"
        with source.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=[
                "NoticeId", "Sol#", "AAC Code", "Type", "Title", "PostedDate", "Active",
            ])
            writer.writeheader()
            writer.writerow({"NoticeId": "OLD", "Sol#": "A-1", "AAC Code": "FA9401",
                             "Type": "Sources Sought", "Title": "Cloud support",
                             "PostedDate": "2026-09-28 12:00:00", "Active": "Yes"})
        original = str(Path(self.work.name) / "poll-base.sqlite")
        updated = str(Path(self.work.name) / "poll-updated.sqlite")
        build_from_csv(str(source), original)
        count = apply_delta(original, updated, [{
            "notice_id": "NEW", "solicitation_number": "A-1",
            "organization_code": "057.5700.AFGSC.FA9401", "type": "Sources Sought",
            "type_code": "r", "title": "Cloud support", "posted_date": "2026-09-28",
            "active": True,
        }])
        self.assertEqual(count, 1)
        with patch.object(local_index, "pinned_opportunity_index", return_value=updated):
            feed = local_index.feed_page("unused", "unused", "2026-09-28", "2026-09-28", 0, 25)
        self.assertEqual([item["notice_id"] for item in feed["records"]], ["NEW"])

    def test_missing_office_code_does_not_collapse_agency_wide_notices(self):
        source = Path(self.work.name) / "no-office.csv"
        with source.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=[
                "NoticeId", "Sol#", "CGAC", "Type", "Title", "PostedDate", "Active",
            ])
            writer.writeheader()
            for notice_id, posted in (("FIRST", "2026-09-28 12:00:00"),
                                      ("SECOND", "2026-09-28 12:05:00")):
                writer.writerow({"NoticeId": notice_id, "Sol#": "A-1", "CGAC": "057",
                                 "Type": "Sources Sought", "Title": "Cloud support",
                                 "PostedDate": posted, "Active": "Yes"})
        index = str(Path(self.work.name) / "no-office.sqlite")
        self.assertEqual(build_from_csv(str(source), index), 2)

    def test_notification_safety_collapses_versions_across_pages(self):
        older = {"notice_id": "OLD", "solicitation_number": "A-1", "organization_code": "FA9401",
                 "type_code": "r", "title": "Cloud support", "posted_at": "2026-09-28T12:00:00"}
        newer = {**older, "notice_id": "NEW", "posted_at": "2026-09-28T12:05:00"}
        self.assertEqual([item["notice_id"] for item in collapse_versions([older, newer])], ["NEW"])

    def test_compressed_entity_index_loads_and_verifies_raw_checksum(self):
        body = Path(self.path).read_bytes()
        manifest = {
            "version": "compressed-test", "source_date": date.today().isoformat(),
            "key": "indexes/entities/versions/compressed-test/entities.sqlite.gz",
            "sha256": hashlib.sha256(body).hexdigest(), "compression": "gzip",
        }

        class FakeS3:
            def get_object(self, *, Bucket, Key):
                value = json.dumps(manifest).encode() if Key.endswith("current.json") else gzip.compress(body)
                return {"Body": io.BytesIO(value)}

        with patch.dict(os.environ, {"LOCAL_INDEX_BUCKET": "test-bucket"}), \
             patch.object(local_index, "_s3", FakeS3()), \
             patch.dict(local_index._cached_manifest, {}, clear=True), \
             patch.dict(local_index._cached_path, {}, clear=True), \
             patch.dict(local_index._last_check, {}, clear=True):
            loaded_path, loaded_manifest = local_index.current_index("entities")
            self.addCleanup(lambda: Path(loaded_path).unlink(missing_ok=True))
            self.assertEqual(Path(loaded_path).read_bytes(), body)
            self.assertEqual(loaded_manifest["compression"], "gzip")

    def test_compressed_opportunity_index_supports_pinned_feed(self):
        source = Path(self.path).read_bytes()
        s3 = Mock()
        artifact = ingest_opportunities._upload_index(s3, "test-bucket", self.path, "test")
        compressed = Path(s3.upload_file.call_args.args[0]).read_bytes()

        class FakeS3:
            def get_object(self, *, Bucket, Key):
                return {"Body": io.BytesIO(compressed)}

        with patch.dict(os.environ, {"LOCAL_INDEX_BUCKET": "test-bucket"}), \
             patch.object(local_index, "_s3", FakeS3()), \
             patch.dict(local_index._pinned_paths, {}, clear=True):
            loaded_path = local_index.pinned_opportunity_index(artifact["key"], artifact["sha256"])
            self.addCleanup(lambda: Path(loaded_path).unlink(missing_ok=True))
            self.assertEqual(Path(loaded_path).read_bytes(), source)
        self.assertEqual(artifact["compression"], "gzip")


if __name__ == "__main__":
    unittest.main()
