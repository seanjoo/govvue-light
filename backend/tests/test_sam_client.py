from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runtime_config import RuntimeConfig
from sam_client import (
    build_search_parameters,
    expand_search_parameters,
    normalize_opportunity,
    search_opportunities,
)


def config(**overrides):
    values = {
        "sam_api_key": "test-key",
        "sam_opportunities_api": "https://api.sam.gov/opportunities/v2/search",
        "sam_entities_api": "https://api.sam.gov/entity-information/v4/entities",
        "sam_site_base_url": "https://sam.gov",
        "search_cache_ttl_seconds": 900,
        "search_default_lookback_days": 30,
        "search_max_lookback_days": 365,
        "search_max_fanout": 12,
        "search_max_sort_pages": 24,
        "sam_page_size": 1000,
        "sam_request_timeout_seconds": 25,
        "history_retention_days": 90,
        "daily_feed_page_size": 1000,
        "daily_feed_retention_days": 30,
        "notification_run_retention_days": 90,
    }
    values.update(overrides)
    return RuntimeConfig(**values)


class SearchParameterTests(unittest.TestCase):
    def test_builds_only_allowlisted_filters_and_forces_active(self):
        params = build_search_parameters(
            {
                "posted_from": "2026-01-01",
                "posted_to": "2026-01-31",
                "naics_code": "541512",
                "title": "cloud",
                "unsupported": "ignored",
            },
            config(),
        )
        self.assertEqual(params["postedFrom"], "01/01/2026")
        self.assertEqual(params["postedTo"], "01/31/2026")
        self.assertEqual(params["ncode"], "541512")
        self.assertEqual(params["title"], "cloud")
        self.assertEqual(params["status"], "active")
        self.assertNotIn("unsupported", params)

    def test_rejects_excessive_date_range(self):
        today = date.today()
        with self.assertRaises(ValueError):
            build_search_parameters(
                {
                    "posted_from": (today - timedelta(days=31)).isoformat(),
                    "posted_to": today.isoformat(),
                },
                config(search_max_lookback_days=30),
            )

    def test_builds_rolling_posted_date_range_at_execution_time(self):
        today = date.today()
        params = build_search_parameters(
            {
                "posted_within": "14",
                "posted_from": "2020-01-01",
                "posted_to": "2020-01-02",
            },
            config(),
        )
        self.assertEqual(
            params["postedFrom"],
            (today - timedelta(days=13)).strftime("%m/%d/%Y"),
        )
        self.assertEqual(params["postedTo"], today.strftime("%m/%d/%Y"))

    def test_open_deadlines_only_uses_today_at_execution_time(self):
        today = date.today()
        params = build_search_parameters(
            {
                "posted_within": "30",
                "open_deadlines_only": "true",
            },
            config(),
        )
        self.assertEqual(params["rdlfrom"], today.strftime("%m/%d/%Y"))

    def test_open_deadlines_only_overrides_a_past_explicit_deadline(self):
        today = date.today()
        params = build_search_parameters(
            {
                "posted_within": "30",
                "response_deadline_from": (today - timedelta(days=10)).isoformat(),
                "open_deadlines_only": "yes",
            },
            config(),
        )
        self.assertEqual(params["rdlfrom"], today.strftime("%m/%d/%Y"))

    def test_formats_explicit_response_deadlines_for_sam(self):
        params = build_search_parameters(
            {
                "posted_from": "2026-01-01",
                "posted_to": "2026-01-31",
                "response_deadline_from": "2026-02-01",
                "response_deadline_to": "2026-02-28",
            },
            config(),
        )
        self.assertEqual(params["rdlfrom"], "02/01/2026")
        self.assertEqual(params["rdlto"], "02/28/2026")

    def test_rejects_unsupported_rolling_posted_date_range(self):
        with self.assertRaisesRegex(ValueError, "7, 14, 30, 60, or 90"):
            build_search_parameters({"posted_within": "45"}, config())

    def test_builds_multi_value_filters_and_correct_set_aside_parameter(self):
        params = build_search_parameters(
            {
                "posted_from": "2026-01-01",
                "posted_to": "2026-01-31",
                "ptype": "o, p, o, k",
                "state": "VA, MD",
                "set_aside": "SBA, 8A",
            },
            config(),
        )
        self.assertEqual(params["ptype"], ["k", "o", "p"])
        self.assertEqual(params["state"], ["MD", "VA"])
        self.assertEqual(params["typeOfSetAside"], ["8A", "SBA"])
        self.assertNotIn("setaside", params)

    def test_expands_only_sam_single_value_filters(self):
        params = {
            "postedFrom": "01/01/2026",
            "postedTo": "01/31/2026",
            "ptype": ["o", "p"],
            "state": ["MD", "VA"],
            "ncode": ["541511", "541512"],
        }
        expanded = expand_search_parameters(params, 4)
        self.assertEqual(len(expanded), 4)
        self.assertTrue(all(item["ptype"] == ["o", "p"] for item in expanded))
        self.assertEqual(
            {(item["state"], item["ncode"]) for item in expanded},
            {
                ("MD", "541511"),
                ("MD", "541512"),
                ("VA", "541511"),
                ("VA", "541512"),
            },
        )

    def test_rejects_excessive_search_fanout(self):
        with self.assertRaisesRegex(ValueError, "require 6 SAM.gov searches"):
            expand_search_parameters(
                {"state": ["DC", "MD", "VA"], "ncode": ["1", "2"]},
                5,
            )

    def test_normalizes_result_and_builds_sam_link(self):
        result = normalize_opportunity(
            {
                "noticeId": "abc-123",
                "title": "Cloud support",
                "active": "Yes",
                "naicsCode": "541512",
                "typeOfSetAsideDescription": "Small Business Set-Aside",
            },
            config(),
        )
        self.assertEqual(result["notice_id"], "abc-123")
        self.assertTrue(result["active"])
        self.assertEqual(result["sam_url"], "https://sam.gov/opp/abc-123/view")

    @patch("sam_client._request_json")
    def test_search_uses_zero_based_page_index(self, request_json):
        request_json.return_value = {"totalRecords": 2500, "opportunitiesData": []}
        search_opportunities({"postedFrom": "09/19/2026", "postedTo": "09/20/2026"}, 2, config(), 500)
        params = request_json.call_args.args[1]
        self.assertEqual(params["offset"], 2)
        self.assertEqual(params["limit"], 500)

    @patch("sam_client.urlopen")
    def test_native_multi_value_ptype_uses_repeated_query_parameter(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"totalRecords":0,"opportunitiesData":[]}'
        )
        urlopen.return_value = response
        search_opportunities(
            {
                "postedFrom": "09/19/2026",
                "postedTo": "09/20/2026",
                "ptype": ["o", "p", "k"],
            },
            0,
            config(),
            25,
        )
        request = urlopen.call_args.args[0]
        parsed = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(parsed["ptype"], ["o", "p", "k"])


if __name__ == "__main__":
    unittest.main()
