from __future__ import annotations

import os
import io
import json
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ingest_health


class IngestHealthTests(unittest.TestCase):
    def test_stale_full_snapshot_alerts_even_after_recent_poll(self):
        today = date.today()
        s3 = Mock()
        s3.get_object.side_effect = lambda **kwargs: {"Body": io.BytesIO(json.dumps(
            {"source_date": today.isoformat(),
             "snapshot_source_date": (today - timedelta(days=3)).isoformat()}
            if "opportunities" in kwargs["Key"] else
            {"source_date": today.isoformat(), "monthly_source_date": today.isoformat()}
        ).encode())}
        sqs = Mock()
        sqs.get_queue_attributes.return_value = {"Attributes": {"ApproximateNumberOfMessages": "0"}}
        codebuild = Mock()
        codebuild.list_builds_for_project.return_value = {"ids": []}
        clients = {"s3": s3, "sqs": sqs, "codebuild": codebuild}
        with patch.dict(os.environ, {
            "LOCAL_INDEX_BUCKET": "test-bucket", "INGEST_DLQ_URL": "test-queue",
            "INGEST_BUILD_PROJECT": "test-project",
        }), patch.object(ingest_health.boto3, "client", side_effect=lambda name: clients[name]):
            problems = ingest_health.issues()
        self.assertTrue(any("full snapshot is stale" in item for item in problems))

    def test_no_email_when_healthy(self):
        with patch.object(ingest_health, "issues", return_value=[]), \
             patch.object(ingest_health.boto3, "client") as client:
            result = ingest_health.lambda_handler({}, None)
        self.assertEqual(result["status"], "healthy")
        client.assert_not_called()

    def test_alert_includes_admin_url_and_issue(self):
        ses = Mock()
        with patch.dict(os.environ, {
            "ADMIN_URL": "https://admin.govvue.com",
            "OPS_ALERT_EMAIL": "ops@example.com",
            "NOTIFICATION_FROM_EMAIL": "notifications@govvue.com",
        }), patch.object(ingest_health, "issues", return_value=["Entity index is stale"]), \
             patch.object(ingest_health.boto3, "client", return_value=ses):
            result = ingest_health.lambda_handler({}, None)
        self.assertEqual(result["status"], "alerted")
        email = ses.send_email.call_args.kwargs
        self.assertIn("https://admin.govvue.com/", email["Content"]["Simple"]["Body"]["Text"]["Data"])
        self.assertEqual(email["Destination"]["ToAddresses"], ["ops@example.com"])


if __name__ == "__main__":
    unittest.main()
