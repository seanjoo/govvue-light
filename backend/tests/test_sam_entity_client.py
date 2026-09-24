from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_config import RuntimeConfig
from sam_entity_client import (
    build_entity_search_parameters,
    normalize_entity,
    sanitize_entity_criteria,
    search_entities,
)


def config() -> RuntimeConfig:
    return RuntimeConfig(
        sam_api_key="test-key",
        sam_opportunities_api="https://api.sam.gov/opportunities/v2/search",
        sam_entities_api="https://api.sam.gov/entity-information/v4/entities",
        sam_site_base_url="https://sam.gov",
        search_cache_ttl_seconds=900,
        search_default_lookback_days=30,
        search_max_lookback_days=365,
        search_max_fanout=12,
        search_max_sort_pages=24,
        sam_page_size=1000,
        sam_request_timeout_seconds=25,
        history_retention_days=90,
        daily_feed_page_size=1000,
        daily_feed_retention_days=30,
        notification_run_retention_days=90,
    )


class EntitySearchParameterTests(unittest.TestCase):
    def test_allowlists_filters_and_defaults_to_active(self):
        result = build_entity_search_parameters(
            {
                "legal_business_name": "Acme",
                "state": "VA,MD",
                "unsupported": "ignored",
            }
        )
        self.assertEqual(result["legalBusinessName"], "Acme")
        self.assertEqual(result["physicalAddressProvinceOrStateCode"], "[VA~MD]")
        self.assertEqual(result["registrationStatus"], "A")
        self.assertNotIn("unsupported", result)

    def test_builds_native_multi_identifier_and_status_filters(self):
        result = build_entity_search_parameters(
            {
                "uei": "RF4KVSJW26F3,JH9ZARNKWKC7",
                "cage_code": "1AB23,4CD56",
                "registration_status": "A,E",
            }
        )
        self.assertEqual(result["ueiSAM"], "[RF4KVSJW26F3~JH9ZARNKWKC7]")
        self.assertEqual(result["cageCode"], "[1AB23~4CD56]")
        self.assertEqual(result["registrationStatus"], "[A~E]")

    def test_unregistered_search_does_not_force_registration_status(self):
        result = build_entity_search_parameters(
            {"sam_registered": "No", "registration_status": "A"}
        )
        self.assertEqual(result["samRegistered"], "No")
        self.assertNotIn("registrationStatus", result)

    def test_formats_date_ranges(self):
        result = build_entity_search_parameters(
            {"update_date_from": "2026-09-01", "update_date_to": "2026-09-20"}
        )
        self.assertEqual(result["updateDate"], "[09/01/2026,09/20/2026]")

    def test_rejects_reversed_date_ranges(self):
        with self.assertRaisesRegex(ValueError, "cannot be later"):
            build_entity_search_parameters(
                {"activation_date_from": "2026-09-20", "activation_date_to": "2026-09-01"}
            )

    def test_rejects_sam_disallowed_characters(self):
        with self.assertRaisesRegex(ValueError, "does not allow"):
            build_entity_search_parameters({"legal_business_name": "Acme & Sons"})

    def test_sanitize_removes_control_parameters(self):
        result = sanitize_entity_criteria(
            {"legal_business_name": "Acme", "page": "12", "api_key": "secret"}
        )
        self.assertEqual(result, {"legal_business_name": "Acme"})


class EntityResponseTests(unittest.TestCase):
    def test_normalizes_public_summary(self):
        entity = normalize_entity(
            {
                "entityRegistration": {
                    "ueiSAM": "RF4KVSJW26F3",
                    "legalBusinessName": "Example LLC",
                    "cageCode": "1AB23",
                    "registrationStatus": "Active",
                    "registrationExpirationDate": "2027-01-01",
                },
                "coreData": {
                    "physicalAddress": {"city": "Herndon", "stateOrProvinceCode": "VA"},
                    "businessTypes": {
                        "businessTypeList": [
                            {"businessTypeCode": "2X", "businessTypeDesc": "For Profit Organization"}
                        ]
                    },
                },
                "assertions": {
                    "goodsAndServices": {
                        "primaryNaics": "541512",
                        "naicsList": [
                            {"naicsCode": "541512", "naicsDescription": "Computer Systems Design Services"}
                        ],
                    }
                },
            },
            config(),
        )
        self.assertEqual(entity["uei"], "RF4KVSJW26F3")
        self.assertEqual(entity["address"]["state"], "VA")
        self.assertEqual(entity["primary_naics"], "541512")
        self.assertEqual(entity["business_types"][0]["code"], "2X")
        self.assertIn("/entity/RF4KVSJW26F3/coreData", entity["sam_url"])

    @patch("sam_entity_client._request_json")
    def test_search_uses_fixed_sam_page_size_and_caps_total(self, request_json):
        request_json.return_value = {"totalRecords": 25000, "entityData": []}
        result = search_entities({"registrationStatus": "A"}, 3, config())
        params = request_json.call_args.args[1]
        self.assertEqual(params["page"], "3")
        self.assertEqual(params["size"], "10")
        self.assertEqual(params["includeSections"], "entityRegistration,coreData,assertions")
        self.assertEqual(result["total_records"], 10000)


if __name__ == "__main__":
    unittest.main()
