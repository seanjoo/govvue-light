from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auth_config


def event(request_type: str = "Create"):
    return {
        "RequestType": request_type,
        "ResponseURL": "https://cloudformation-response.example.test/",
        "StackId": "stack-1",
        "RequestId": "request-1",
        "LogicalResourceId": "GoogleIdentityProvider",
        "ResourceProperties": {
            "UserPoolId": "pool-1",
            "ProviderName": "Google",
        },
    }


class GoogleIdentityProviderResourceTests(unittest.TestCase):
    @patch("auth_config._send_response")
    @patch("auth_config._provider_configuration")
    @patch("auth_config.boto3.client")
    def test_creates_provider_when_it_does_not_exist(self, client_factory, config, respond):
        client = MagicMock()
        client_factory.return_value = client
        client.describe_identity_provider.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "DescribeIdentityProvider",
        )
        config.return_value = {
            "ProviderDetails": {"client_id": "id", "client_secret": "secret"},
            "AttributeMapping": {"email": "email", "email_verified": "email_verified"},
        }

        auth_config.lambda_handler(event(), SimpleNamespace(log_stream_name="log"))

        client.create_identity_provider.assert_called_once_with(
            UserPoolId="pool-1",
            ProviderName="Google",
            ProviderType="Google",
            **config.return_value,
        )
        respond.assert_called_once_with(event(), ANY, "SUCCESS", "pool-1/Google")

    @patch("auth_config._send_response")
    @patch("auth_config._provider_configuration")
    @patch("auth_config.boto3.client")
    def test_updates_existing_provider(self, client_factory, config, respond):
        client = MagicMock()
        client_factory.return_value = client
        config.return_value = {
            "ProviderDetails": {"client_id": "id", "client_secret": "secret"},
            "AttributeMapping": {"email": "email", "email_verified": "email_verified"},
        }

        current_event = event("Update")
        auth_config.lambda_handler(current_event, SimpleNamespace(log_stream_name="log"))

        client.update_identity_provider.assert_called_once_with(
            UserPoolId="pool-1", ProviderName="Google", **config.return_value
        )
        respond.assert_called_once_with(current_event, ANY, "SUCCESS", "pool-1/Google")

    @patch("auth_config._send_response")
    @patch("auth_config.boto3.client")
    def test_delete_is_idempotent(self, client_factory, respond):
        client = MagicMock()
        client_factory.return_value = client
        client.delete_identity_provider.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "missing"}},
            "DeleteIdentityProvider",
        )

        current_event = event("Delete")
        auth_config.lambda_handler(current_event, SimpleNamespace(log_stream_name="log"))
        respond.assert_called_once_with(current_event, ANY, "SUCCESS", "pool-1/Google")


if __name__ == "__main__":
    unittest.main()
