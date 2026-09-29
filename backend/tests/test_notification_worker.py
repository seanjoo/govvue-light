from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

with patch("boto3.client"):
    import notification_worker


class NotificationEmailTests(unittest.TestCase):
    def setUp(self) -> None:
        notification_worker._description_cache.clear()

    @patch("notification_worker.fetch_description")
    def test_email_opportunities_loads_and_truncates_descriptions(self, fetch_description):
        fetch_description.return_value = "A detailed description " + ("word " * 100)
        opportunities = [
            {
                "notice_id": "notice-1",
                "title": "Test opportunity",
                "_description_url": "https://api.sam.gov/description/notice-1",
            }
        ]

        result = notification_worker._email_opportunities(
            opportunities, SimpleNamespace()
        )

        self.assertEqual(len(result), 1)
        self.assertNotIn("_description_url", result[0])
        self.assertLessEqual(
            len(result[0]["description"]),
            notification_worker.EMAIL_DESCRIPTION_LIMIT,
        )
        self.assertTrue(result[0]["description"].endswith("…"))
        fetch_description.assert_called_once()

    def test_email_bodies_include_details_and_govvue_link(self):
        text_body, html_body = notification_worker._email_bodies(
            "Machine builders",
            "2026-09-26",
            12,
            [
                {
                    "notice_id": "notice/1",
                    "solicitation_number": "SAM-123",
                    "title": "Tools <and> machinery",
                    "type": "Solicitation",
                    "response_deadline": "2026-10-15T17:00:00-04:00",
                    "description": "Supply precision equipment <quickly>.",
                }
            ],
            "https://app.govvue.com/notifications/notification-1/runs/2026-09-26",
            "https://app.govvue.com",
            "/notifications/notification-1/runs/2026-09-26",
        )

        self.assertIn("Showing the first 1 matches.", text_body)
        self.assertIn("Type: Solicitation", text_body)
        self.assertIn("Notice ID: SAM-123", text_body)
        self.assertNotIn("Notice ID: notice/1", text_body)
        self.assertIn("Response due: 2026-10-15T17:00:00-04:00", text_body)
        self.assertIn("Description: Supply precision equipment <quickly>.", text_body)
        self.assertIn("/opportunities/notice%2F1?", text_body)
        self.assertIn("return_to=%2Fnotifications%2Fnotification-1%2Fruns%2F2026-09-26", text_body)
        self.assertIn("View in GovVue Light", html_body)
        self.assertIn("Tools &lt;and&gt; machinery", html_body)
        self.assertIn("<strong>Tools &lt;and&gt; machinery</strong>", html_body)
        self.assertNotIn(">Tools &lt;and&gt; machinery</a>", html_body)
        self.assertIn("Supply precision equipment &lt;quickly&gt;.", html_body)
        self.assertNotIn("Tools <and> machinery", html_body)

    @patch("notification_worker.fetch_description", side_effect=RuntimeError("SAM unavailable"))
    def test_description_failure_does_not_block_email(self, _fetch_description):
        with self.assertLogs(notification_worker.LOGGER, level="WARNING"):
            result = notification_worker._email_opportunities(
                [
                    {
                        "notice_id": "notice-2",
                        "_description_url": "https://api.sam.gov/description/notice-2",
                    }
                ],
                SimpleNamespace(),
            )

        self.assertEqual(result[0]["description"], "")

    @patch.object(notification_worker._ses, "send_email")
    @patch("notification_worker.storage.claim_notification_email")
    @patch("notification_worker.storage.skip_notification_email")
    @patch("notification_worker.storage.put_notification_run_summary")
    @patch("notification_worker.storage.put_notification_results")
    @patch("notification_worker.get_runtime_config")
    @patch("notification_worker._load_feed", return_value=[])
    def test_no_match_run_is_recorded_without_sending_email(
        self,
        _load_feed,
        get_runtime_config,
        _put_results,
        _put_summary,
        skip_notification_email,
        claim_notification_email,
        send_email,
    ):
        get_runtime_config.return_value = SimpleNamespace(
            notification_run_retention_days=30
        )

        notification_worker._process(
            {
                "user_id": "user-1",
                "notification_id": "notification-1",
                "run_date": "2026-09-27",
                "name": "No matches",
                "recipient_email": "user@example.com",
                "criteria": {},
                "total_pages": 1,
            }
        )

        skip_notification_email.assert_called_once_with(
            "user-1", "notification-1", "2026-09-27"
        )
        claim_notification_email.assert_not_called()
        send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
