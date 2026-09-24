from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import (
    _converged_search,
    _entity_detail,
    _notification_schedule_time,
    _route,
    _sort_opportunities,
)


class ConvergedSearchTests(unittest.TestCase):
    @patch("app._load_search_pages")
    def test_merges_sorts_and_deduplicates_fanout_results(self, load_pages):
        load_pages.return_value = (
            {
                (0, 0): {
                    "total_records": 2,
                    "records": [
                        {"notice_id": "a", "posted_date": "2026-09-18", "_description_url": "secret"},
                        {"notice_id": "shared", "posted_date": "2026-09-19"},
                    ],
                },
                (1, 0): {
                    "total_records": 2,
                    "records": [
                        {"notice_id": "b", "posted_date": "2026-09-20"},
                        {"notice_id": "shared", "posted_date": "2026-09-19"},
                    ],
                },
            },
            True,
        )
        result = _converged_search(
            [{"state": "MD"}, {"state": "VA"}],
            page=1,
            per_page=10,
            config=SimpleNamespace(sam_page_size=1000),
        )
        self.assertEqual([item["notice_id"] for item in result["items"]], ["b", "shared", "a"])
        self.assertEqual(result["total_records"], 3)
        self.assertFalse(result["has_next"])
        self.assertTrue(result["cache_hit"])
        self.assertEqual(result["upstream_queries"], 2)
        self.assertNotIn("_description_url", result["items"][-1])

    def test_sorts_response_deadlines_both_directions_with_missing_last(self):
        records = [
            {"notice_id": "oct", "response_deadline": "2026-10-01T12:00:00-04:00"},
            {"notice_id": "missing", "response_deadline": ""},
            {"notice_id": "nov", "response_deadline": "2026-11-01T12:00:00-04:00"},
        ]
        self.assertEqual(
            [item["notice_id"] for item in _sort_opportunities(records, "response_deadline_desc")],
            ["nov", "oct", "missing"],
        )
        self.assertEqual(
            [item["notice_id"] for item in _sort_opportunities(records, "response_deadline_asc")],
            ["oct", "nov", "missing"],
        )

    @patch("app._load_search_pages")
    def test_exact_sort_rejects_searches_over_the_request_cap(self, load_pages):
        load_pages.return_value = (
            {(0, 0): {"total_records": 13_000, "records": []}},
            True,
        )
        with self.assertRaisesRegex(ValueError, "requires 13 SAM.gov page requests"):
            _converged_search(
                [{}],
                page=1,
                per_page=25,
                config=SimpleNamespace(sam_page_size=1000, search_max_sort_pages=12),
                sort_order="response_deadline_desc",
            )


class PreflightRouteTests(unittest.TestCase):
    def test_options_does_not_require_authenticated_claims(self):
        result = _route(
            {
                "rawPath": "/entities/search",
                "requestContext": {"http": {"method": "OPTIONS"}},
            }
        )

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["body"], "{}")


class DailyNotificationRunRouteTests(unittest.TestCase):
    @patch("app._queue_daily_notification_run")
    @patch("app.storage.list_daily_notifications", return_value=[{"enabled": True}])
    def test_authenticated_user_can_queue_enabled_notifications(self, _list, queue_run):
        result = _route(
            {
                "rawPath": "/daily-notifications/run",
                "requestContext": {
                    "http": {"method": "POST"},
                    "authorizer": {"jwt": {"claims": {"sub": "user-1"}}},
                },
            }
        )

        self.assertEqual(result["statusCode"], 202)
        queue_run.assert_called_once_with()

    @patch("app._queue_daily_notification_run")
    @patch("app.storage.list_daily_notifications", return_value=[{"enabled": False}])
    def test_requires_an_enabled_notification(self, _list, queue_run):
        with self.assertRaisesRegex(ValueError, "Enable at least one"):
            _route(
                {
                    "rawPath": "/daily-notifications/run",
                    "requestContext": {
                        "http": {"method": "POST"},
                        "authorizer": {"jwt": {"claims": {"sub": "user-1"}}},
                    },
                }
            )
        queue_run.assert_not_called()


class DailyNotificationScheduleTests(unittest.TestCase):
    def test_accepts_five_minute_schedule(self):
        self.assertEqual(
            _notification_schedule_time({"schedule_time": "14:35"}), "14:35"
        )

    def test_rejects_non_five_minute_schedule(self):
        with self.assertRaisesRegex(ValueError, "five-minute increment"):
            _notification_schedule_time({"schedule_time": "14:37"})

    @patch("app.get_runtime_config")
    def test_uses_configured_default(self, get_config):
        get_config.return_value = SimpleNamespace(
            daily_notification_default_time="06:15"
        )
        self.assertEqual(_notification_schedule_time({}), "06:15")


class EntityDetailTests(unittest.TestCase):
    @patch("app.storage.put_cached")
    @patch("app.storage.get_cached", return_value=None)
    @patch("app.search_entities")
    @patch("app.get_runtime_config")
    def test_loads_entity_by_exact_uei_and_caches_it(
        self, get_config, search_entities, _get_cached, put_cached
    ):
        get_config.return_value = SimpleNamespace(search_cache_ttl_seconds=900)
        entity = {"uei": "REBSNSUL2BM1", "legal_business_name": "LatticeWorks, Inc."}
        search_entities.return_value = {"records": [entity], "total_records": 1}

        self.assertEqual(_entity_detail("rebsnsul2bm1"), entity)
        self.assertEqual(search_entities.call_args.args[0], {"ueiSAM": "REBSNSUL2BM1"})
        put_cached.assert_called_once()

    def test_rejects_invalid_uei(self):
        with self.assertRaisesRegex(ValueError, "12 letters or numbers"):
            _entity_detail("not-a-uei")


if __name__ == "__main__":
    unittest.main()
