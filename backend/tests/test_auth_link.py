from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import auth_link


def google_event(email: str = "invited@example.com", verified: str = "true"):
    return {
        "triggerSource": "PreSignUp_ExternalProvider",
        "userPoolId": "pool-1",
        "userName": "Google_google-subject-1",
        "request": {
            "userAttributes": {
                "email": email,
                "email_verified": verified,
            }
        },
        "response": {},
    }


class GoogleAccountLinkTests(unittest.TestCase):
    @patch("auth_link.cognito_client")
    def test_links_verified_google_email_to_existing_invited_user(self, factory):
        client = MagicMock()
        factory.return_value = client
        client.list_users.return_value = {
            "Users": [
                {
                    "Username": "cognito-user-id",
                    "Attributes": [
                        {"Name": "email", "Value": "invited@example.com"},
                        {"Name": "email_verified", "Value": "true"},
                    ],
                }
            ]
        }

        event = google_event()
        self.assertIs(auth_link.lambda_handler(event, None), event)
        client.admin_link_provider_for_user.assert_called_once_with(
            UserPoolId="pool-1",
            DestinationUser={
                "ProviderName": "Cognito",
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": "cognito-user-id",
            },
            SourceUser={
                "ProviderName": "Google",
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": "google-subject-1",
            },
        )
        client.admin_update_user_attributes.assert_not_called()

    @patch("auth_link.cognito_client")
    def test_marks_invited_email_verified_before_linking(self, factory):
        client = MagicMock()
        factory.return_value = client
        client.list_users.return_value = {
            "Users": [
                {
                    "Username": "cognito-user-id",
                    "Attributes": [
                        {"Name": "email", "Value": "invited@example.com"}
                    ],
                }
            ]
        }

        auth_link.lambda_handler(google_event(), None)
        client.admin_update_user_attributes.assert_called_once_with(
            UserPoolId="pool-1",
            Username="cognito-user-id",
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )

    @patch("auth_link.cognito_client")
    def test_rejects_google_email_that_was_not_invited(self, factory):
        client = MagicMock()
        factory.return_value = client
        client.list_users.return_value = {"Users": []}

        with self.assertRaisesRegex(ValueError, "No invited GovVue Light account"):
            auth_link.lambda_handler(google_event(), None)
        client.admin_link_provider_for_user.assert_not_called()

    def test_rejects_unverified_google_email(self):
        with self.assertRaisesRegex(ValueError, "verified email"):
            auth_link.lambda_handler(google_event(verified="false"), None)

    @patch("auth_link.cognito_client")
    def test_non_external_trigger_is_unchanged(self, factory):
        event = {"triggerSource": "PreSignUp_AdminCreateUser"}
        self.assertIs(auth_link.lambda_handler(event, None), event)
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
