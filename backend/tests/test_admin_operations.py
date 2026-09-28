from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import admin_operations
from app import ForbiddenError, _route


class AdminOperationsTests(unittest.TestCase):
    def test_ingestion_route_requires_admin_group(self):
        with self.assertRaises(ForbiddenError):
            _route({
                "rawPath": "/admin/ingestion",
                "requestContext": {
                    "http": {"method": "GET"},
                    "authorizer": {"jwt": {"claims": {"sub": "regular-user"}}},
                },
            })

    def test_index_validation_route_requires_admin_group(self):
        with self.assertRaises(ForbiddenError):
            _route({
                "rawPath": "/admin/ingestion/validate",
                "body": '{"kind":"entities"}',
                "requestContext": {
                    "http": {"method": "POST"},
                    "authorizer": {"jwt": {"claims": {"sub": "regular-user"}}},
                },
            })

    @patch("admin_operations.local_entity_index.search")
    def test_index_validation_uses_published_entity_search(self, search):
        search.return_value = {
            "source": "local", "source_date": "2026-09-28",
            "index_version": "v1", "total_records": 42,
        }
        result = admin_operations.validate_index("entities")
        self.assertEqual(result["total_records"], 42)
        self.assertEqual(result["source"], "local")
        search.assert_called_once()

    @patch.dict(os.environ, {"INGEST_QUEUE_URL": "https://example.invalid/queue"})
    @patch("admin_operations.boto3.client")
    def test_manual_run_accepts_only_named_datasets(self, client):
        queue = MagicMock()
        queue.send_message.return_value = {"MessageId": "m-1"}
        client.return_value = queue
        result = admin_operations.start("entity-daily")
        self.assertTrue(result["queued"])
        self.assertIn('"action":"start"', queue.send_message.call_args.kwargs["MessageBody"])
        with self.assertRaisesRegex(ValueError, "Unknown ingestion job"):
            admin_operations.start("delete-everything")
        queue.send_message.assert_called_once()
