from __future__ import annotations

import os
import sys
import unittest
import io
from urllib.error import HTTPError
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import entity_export


class EntityExportDispatchTests(unittest.TestCase):
    def test_daily_request_catches_up_from_last_published_snapshot(self):
        response = MagicMock()
        response.read.return_value = (
            b'Extract file: https://api.sam.gov/entity-information/v4/'
            b'download-entities?api_key=REPLACE_WITH_API_KEY&token=example-token'
        )
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {"SAM_ENTITIES_API": "https://api.sam.gov/entity-information/v4/entities"}), \
             patch.object(entity_export, "_manifest_date", return_value="2026-09-06"), \
             patch.object(entity_export, "_api_key", return_value="test-key"), \
             patch.object(entity_export, "urlopen", return_value=response) as open_url, \
             patch.object(entity_export, "_message") as queue:
            entity_export._request("2026-09-28")
        self.assertIn("09%2F06%2F2026", open_url.call_args.args[0].full_url)
        self.assertIn("09%2F28%2F2026", open_url.call_args.args[0].full_url)
        queue.assert_called_once_with("check", "2026-09-28", token="example-token", attempt=0)

    def test_export_download_uses_post(self):
        error = HTTPError("https://example.test", 429, "busy", {}, io.BytesIO(b"in progress"))
        self.addCleanup(error.close)
        with patch.dict(os.environ, {"SAM_ENTITIES_API": "https://api.sam.gov/entity-information/v4/entities"}), \
             patch.object(entity_export, "_manifest_date", return_value="2026-09-06"), \
             patch.object(entity_export, "_api_key", return_value="test-key"), \
             patch.object(entity_export, "urlopen", side_effect=error) as open_url, \
             patch.object(entity_export, "_message") as queue:
            entity_export._check("2026-09-28", "example-token", 0)
        self.assertEqual(open_url.call_args.args[0].get_method(), "POST")
        queue.assert_called_once()

    def test_busy_build_is_rescheduled_without_failing_the_sqs_message(self):
        codebuild = Mock()
        codebuild.start_build.side_effect = ClientError(
            {"Error": {"Code": "AccountLimitExceededException", "Message": "busy"}},
            "StartBuild",
        )
        sqs = Mock()

        def client(service):
            return {"codebuild": codebuild, "sqs": sqs}[service]

        with patch.dict(os.environ, {
            "INGEST_BUILD_PROJECT": "test-project",
            "ENTITY_EXPORT_QUEUE_URL": "https://example.test/queue",
        }), patch.object(entity_export.boto3, "client", side_effect=client):
            entity_export._start_build("entity-monthly", "2026-09-28")

        sent = sqs.send_message.call_args.kwargs
        self.assertEqual(sent["DelaySeconds"], entity_export.POLL_DELAY_SECONDS)
        self.assertIn('"attempt":1', sent["MessageBody"])


if __name__ == "__main__":
    unittest.main()
