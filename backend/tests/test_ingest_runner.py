from __future__ import annotations

import io
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ingest_runner


class IngestRunnerTests(unittest.TestCase):
    def test_forced_opportunity_rebuild_reuses_staged_snapshot(self):
        s3 = Mock()
        with patch.dict(os.environ, {
            "DATASET": "opportunity-daily", "LOCAL_INDEX_BUCKET": "test-bucket",
            "PROJECT_NAME": "govvue-light", "APP_ENV": "dev",
            "SOURCE_DATE": "2026-09-28", "FORCE_BUILD": "true",
        }), patch.object(ingest_runner.boto3, "client", return_value=s3), \
             patch.object(ingest_runner, "_download") as download, \
             patch.object(ingest_runner, "publish", return_value={"ok": True}) as publish:
            result = ingest_runner.run()
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            s3.download_file.call_args.args[:2],
            ("test-bucket", "raw/opportunities/daily/2026-09-28/active.csv"),
        )
        download.assert_not_called()
        publish.assert_called_once()

    def test_forced_monthly_rebuild_reuses_staged_public_extract(self):
        s3 = Mock()
        s3.get_object.return_value = {
            "Body": io.BytesIO(json.dumps({"monthly_source_date": "2026-09-06"}).encode())
        }
        with patch.dict(os.environ, {
            "DATASET": "entity-monthly", "LOCAL_INDEX_BUCKET": "test-bucket",
            "PROJECT_NAME": "govvue-light", "APP_ENV": "dev",
            "SOURCE_DATE": "2026-09-28", "FORCE_BUILD": "true",
        }), patch.object(ingest_runner.boto3, "client", return_value=s3), \
             patch.object(ingest_runner, "_download_monthly") as download, \
             patch.object(ingest_runner, "publish_monthly", return_value={"ok": True}) as publish:
            result = ingest_runner.run()
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            s3.download_file.call_args.args[:2],
            ("test-bucket", "raw/entities/monthly/2026-09-06/public.zip"),
        )
        download.assert_not_called()
        publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
