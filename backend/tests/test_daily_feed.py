from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

with patch("boto3.client"):
    import daily_feed


class DailyFeedStartTests(unittest.TestCase):
    @patch("daily_feed._send_page")
    @patch("daily_feed.get_runtime_config")
    @patch("daily_feed._run_dates", return_value=("2026-09-22", "2026-09-21"))
    @patch("daily_feed._meta")
    def test_manual_run_refreshes_a_completed_feed(
        self, meta, _dates, get_config, send_page
    ):
        meta.return_value = {"status": "COMPLETE", "trigger": "scheduled"}
        get_config.return_value = SimpleNamespace(daily_feed_retention_days=30)
        table = MagicMock()

        with patch("daily_feed.storage.table", return_value=table):
            daily_feed._start(
                {"force": True, "request_id": "manual-123"}
            )

        table.update_item.assert_called_once()
        send_page.assert_called_once_with(
            "2026-09-22", 0, "manual-123", "manual", None
        )
        values = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(values[":trigger"], "manual")

    @patch("daily_feed._send_page")
    @patch("daily_feed.get_runtime_config")
    @patch("daily_feed._run_dates", return_value=("2026-09-22", "2026-09-21"))
    @patch("daily_feed._meta", return_value={"status": "COMPLETE", "trigger": "scheduled"})
    def test_completed_scheduled_feed_is_not_downloaded_twice(
        self, _meta, _dates, get_config, send_page
    ):
        get_config.return_value = SimpleNamespace(daily_feed_retention_days=30)

        daily_feed._start({})

        send_page.assert_not_called()

    @patch("daily_feed._send_page")
    @patch("daily_feed.get_runtime_config")
    @patch("daily_feed._run_dates", return_value=("2026-09-22", "2026-09-21"))
    @patch("daily_feed._meta", return_value={"status": "COMPLETE", "trigger": "manual"})
    def test_schedule_refreshes_an_early_manual_feed(
        self, _meta, _dates, get_config, send_page
    ):
        get_config.return_value = SimpleNamespace(daily_feed_retention_days=30)
        table = MagicMock()

        with patch("daily_feed.storage.table", return_value=table):
            daily_feed._start({})

        table.update_item.assert_called_once()
        send_page.assert_called_once()
        values = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(values[":trigger"], "scheduled")


class DailyFeedTickTests(unittest.TestCase):
    @patch("daily_feed._start")
    @patch("daily_feed.storage.list_enabled_daily_notifications")
    @patch("daily_feed.get_runtime_config")
    def test_tick_starts_only_due_notifications(
        self, get_config, list_notifications, start
    ):
        get_config.return_value = SimpleNamespace(
            daily_notification_default_time="06:15"
        )
        list_notifications.return_value = [
            {"userId": "u1", "notificationId": "n1", "scheduleTime": "06:15"},
            {"userId": "u2", "notificationId": "n2", "scheduleTime": "06:30"},
            {
                "userId": "u3",
                "notificationId": "n3",
                "scheduleTime": "06:15",
                "lastScheduledRunDate": "2026-09-22",
            },
            {"userId": "u4", "notificationId": "n4"},
        ]
        fake_datetime = MagicMock(wraps=datetime)
        fake_datetime.now.return_value = datetime(
            2026, 9, 22, 6, 20, tzinfo=ZoneInfo("America/New_York")
        )

        with patch("daily_feed.datetime", fake_datetime):
            daily_feed._tick({"request_id": "tick-123"})

        payload = start.call_args.args[0]
        self.assertEqual(payload["run_date"], "2026-09-22")
        self.assertEqual(payload["request_id"], "tick-123")
        self.assertEqual(
            payload["targets"],
            [
                {"user_id": "u1", "notification_id": "n1"},
                {"user_id": "u4", "notification_id": "n4"},
            ],
        )

    @patch("daily_feed._start")
    @patch("daily_feed.storage.list_enabled_daily_notifications", return_value=[])
    @patch("daily_feed.get_runtime_config")
    def test_tick_does_not_fetch_when_nothing_is_due(
        self, get_config, _list_notifications, start
    ):
        get_config.return_value = SimpleNamespace(
            daily_notification_default_time="06:15"
        )

        daily_feed._tick({})

        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
