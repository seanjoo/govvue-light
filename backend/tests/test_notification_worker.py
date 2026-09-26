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
        self.assertIn("Response due: 2026-10-15T17:00:00-04:00", text_body)
        self.assertIn("Description: Supply precision equipment <quickly>.", text_body)
        self.assertIn("/opportunities/notice%2F1?", text_body)
        self.assertIn("return_to=%2Fnotifications%2Fnotification-1%2Fruns%2F2026-09-26", text_body)
        self.assertIn("View details in GovVue Light", html_body)
        self.assertIn("Tools &lt;and&gt; machinery", html_body)
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


if __name__ == "__main__":
    unittest.main()
