from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app
import user_admin


def event(method: str, path: str, groups=None, body=None):
    claims = {
        "sub": "current-sub",
        "email": "admin@example.com",
        "cognito:username": "current-username",
    }
    if groups is not None:
        claims["cognito:groups"] = groups
    return {
        "rawPath": path,
        "body": json.dumps(body or {}),
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": claims}},
        },
    }


class AdminAuthorizationTests(unittest.TestCase):
    def test_group_claim_accepts_api_gateway_string_and_list_forms(self):
        self.assertEqual(app._groups(event("GET", "/", "[admin,user]")), ["admin", "user"])
        self.assertEqual(app._groups(event("GET", "/", ["admin"])), ["admin"])

    @patch("app.user_admin.list_users")
    def test_regular_user_cannot_list_users(self, list_users):
        result = app.lambda_handler(event("GET", "/admin/users", "[user]"), SimpleNamespace(aws_request_id="test"))
        self.assertEqual(result["statusCode"], 403)
        list_users.assert_not_called()

    @patch("app.user_admin.create_user")
    def test_admin_create_defaults_to_user_role(self, create_user):
        create_user.return_value = {"email": "new@example.com", "role": "user"}
        result = app.lambda_handler(
            event("POST", "/admin/users", "[admin]", {"email": "new@example.com"}),
            SimpleNamespace(aws_request_id="test"),
        )
        self.assertEqual(result["statusCode"], 201)
        create_user.assert_called_once_with("new@example.com", "user")


class CognitoUserAdminTests(unittest.TestCase):
    @patch("user_admin.ses_client")
    def test_failed_ses_identity_is_recreated(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client
        client.get_email_identity.return_value = {
            "VerifiedForSendingStatus": False,
            "VerificationStatus": "FAILED",
        }

        result = user_admin._request_ses_verification("user@example.com")

        self.assertEqual(result, "verification_requested")
        client.delete_email_identity.assert_called_once_with(
            EmailIdentity="user@example.com"
        )
        client.create_email_identity.assert_called_once_with(
            EmailIdentity="user@example.com"
        )

    @patch("user_admin.ses_client")
    def test_pending_ses_identity_is_not_recreated(self, client_factory):
        client = MagicMock()
        client_factory.return_value = client
        client.get_email_identity.return_value = {
            "VerifiedForSendingStatus": False,
            "VerificationStatus": "PENDING",
        }

        result = user_admin._request_ses_verification("user@example.com")

        self.assertEqual(result, "pending")
        client.delete_email_identity.assert_not_called()
        client.create_email_identity.assert_not_called()

    @patch("user_admin._request_ses_verification", return_value="verification_requested")
    @patch("user_admin.cognito_client")
    def test_create_user_uses_generated_password_invitation_and_group(self, client_factory, _ses):
        client = MagicMock()
        client_factory.return_value = client
        client.admin_create_user.return_value = {
            "User": {
                "Username": "generated-id",
                "Enabled": True,
                "UserStatus": "FORCE_CHANGE_PASSWORD",
                "Attributes": [
                    {"Name": "sub", "Value": "sub-1"},
                    {"Name": "email", "Value": "new@example.com"},
                ],
            }
        }
        with patch.dict(os.environ, {"USER_POOL_ID": "pool-1"}):
            result = user_admin.create_user("NEW@example.com", "admin")

        request = client.admin_create_user.call_args.kwargs
        self.assertNotIn("TemporaryPassword", request)
        self.assertEqual(request["DesiredDeliveryMediums"], ["EMAIL"])
        client.admin_add_user_to_group.assert_called_once_with(
            UserPoolId="pool-1", Username="generated-id", GroupName="admin"
        )
        self.assertEqual(result["role"], "admin")


if __name__ == "__main__":
    unittest.main()
