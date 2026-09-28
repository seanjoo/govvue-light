from __future__ import annotations

import os
import gzip
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import local_entity_index
import local_index
import ingest_entities


def row(uei: str, *, status: str = "A", primary: str = "333248", manufacturer: bool = True) -> str:
    cols = [""] * 142
    cols[0] = uei
    cols[3] = "ABC12"
    cols[5] = status
    cols[6] = "Z2"
    cols[8] = "20991231"
    cols[11] = "Example Machine Builders"
    cols[17] = "Richmond"
    cols[18] = "VA"
    cols[21] = "USA"
    cols[27] = "2L"
    cols[31] = "2X~MF" if manufacturer else "2X"
    cols[32] = primary
    cols[34] = primary + "~333517"
    cols[36] = "3110~3040"
    cols[115] = ""
    cols[119] = "0000"
    return "|".join(cols)


class EntityIndexTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        source = Path(self.work.name) / "monthly.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr("public.dat", "BOF\n" + row("TESTENTITY01") + "\n" + row("EXPIREDENT01", status="E") + "\nEOF\n")
        self.index = str(Path(self.work.name) / "entities.sqlite")
        self.assertEqual(local_entity_index.build_monthly(str(source), self.index), 1)
        self.manifest = {"version": "test", "source_date": date.today().isoformat()}

    def _search(self, criteria):
        with patch.object(local_index, "current_index", return_value=(self.index, self.manifest)):
            return local_entity_index.search(criteria, 1)

    def test_won_common_filters_use_correct_public_positions(self):
        result = self._search({
            "sam_registered": "Yes", "registration_status": "A",
            "purpose_registration_code": "Z2", "exclusion_status": "N",
            "country_code": "USA", "primary_naics": "333241,333248",
            "organization_structure_description": "Manufacturer of Goods",
        })
        self.assertEqual(result["total_records"], 1)
        self.assertEqual(result["items"][0]["uei"], "TESTENTITY01")
        self.assertEqual(result["items"][0]["purpose_registration_code"], "Z2")
        self.assertEqual(result["items"][0]["exclusion_status"], "N")
        self.assertEqual(result["items"][0]["disaster_response_participant"], "No")

    def test_secondary_naics_and_psc_are_searchable(self):
        result = self._search({"naics_code": "333517", "psc_code": "3110"})
        self.assertEqual(result["total_records"], 1)

    def test_public_exclusion_flags_map_to_app_filters(self):
        self.assertEqual(local_entity_index._exclusion(""), "N")
        self.assertEqual(local_entity_index._exclusion("D"), "Y")

    def test_detail_uses_the_published_local_index(self):
        with patch.object(local_index, "current_index", return_value=(self.index, self.manifest)):
            result = local_entity_index.detail("TESTENTITY01")
        self.assertEqual(result["legal_business_name"], "Example Machine Builders")

    def test_unsupported_filter_uses_live_fallback(self):
        with self.assertRaises(local_index.LocalIndexUnavailable):
            self._search({"naics_description": "machines"})

    def test_published_entity_index_is_gzip_compressed(self):
        s3 = Mock()
        manifest = ingest_entities._publish(
            s3, "test-bucket", self.index, "2026-09-28", "2026-09-06", 1
        )
        uploaded_path = s3.upload_file.call_args.args[0]
        self.assertEqual(gzip.decompress(Path(uploaded_path).read_bytes()), Path(self.index).read_bytes())
        self.assertEqual(manifest["compression"], "gzip")
        self.assertTrue(manifest["key"].endswith("entities.sqlite.gz"))

    def test_daily_update_expands_compressed_base_index(self):
        source = Path(self.index).read_bytes()
        s3 = Mock()
        s3.download_file.side_effect = lambda _bucket, _key, path: Path(path).write_bytes(gzip.compress(source))
        output = str(Path(self.work.name) / "expanded.sqlite")
        ingest_entities._download_index(
            s3, "test-bucket",
            {"key": "indexes/entities/versions/v1/entities.sqlite.gz", "compression": "gzip"},
            output,
        )
        self.assertEqual(Path(output).read_bytes(), source)


if __name__ == "__main__":
    unittest.main()
