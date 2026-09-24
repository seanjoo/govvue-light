from __future__ import annotations

import json
import unittest
from pathlib import Path


CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "src"
    / "data"
    / "naics-2022.json"
)


class NaicsCatalogTests(unittest.TestCase):
    def test_catalog_is_complete_and_hierarchical(self):
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(catalog["version"], "2022")
        records = catalog["records"]
        by_code = {record["code"]: record for record in records}
        self.assertGreater(len(records), 2_000)
        self.assertGreater(sum(len(record["code"]) == 6 for record in records), 1_000)
        for record in records:
            self.assertRegex(record["code"], r"^(?:\d{2}(?:-\d{2})?|\d{3,6})$")
            if record["parent"]:
                self.assertIn(record["parent"], by_code)
        self.assertEqual(
            by_code["541512"],
            {
                "code": "541512",
                "title": "Computer Systems Design Services",
                "parent": "54151",
            },
        )


if __name__ == "__main__":
    unittest.main()
