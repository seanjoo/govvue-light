from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app
import storage


def event(method: str, path: str, body=None, groups="[user]"):
    return {
        "rawPath": path,
        "body": json.dumps(body or {}),
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "current-sub",
                        "email": "user@example.com",
                        "cognito:username": "current-username",
                        "cognito:groups": groups,
                    }
                }
            },
        },
    }


class CompanyProfileTests(unittest.TestCase):
    def test_company_member_can_view_profile_but_not_edit_it(self):
        settings = {
            "company_id": "company-1",
            "company_role": "member",
            "features": [],
        }
        company = {"company_id": "company-1", "name": "Acme"}
        with (
            patch("app.storage.get_user_settings", return_value=settings),
            patch("app.storage.get_company", return_value=company),
            patch("app.storage.get_company_profile", return_value={"overview": "Software"}),
            patch("app.storage.put_company_profile") as put_profile,
        ):
            viewed = app.lambda_handler(
                event("GET", "/company-profile"),
                SimpleNamespace(aws_request_id="test"),
            )
            body = json.loads(viewed["body"])
            self.assertEqual(viewed["statusCode"], 200)
            self.assertEqual(body["profile"]["overview"], "Software")
            self.assertFalse(body["can_edit"])
            self.assertFalse(body["can_manage_members"])
            self.assertFalse(body["can_create"])

            updated = app.lambda_handler(
                event("PUT", "/company-profile", {"profile": {"overview": "Changed"}}),
                SimpleNamespace(aws_request_id="test"),
            )
            self.assertEqual(updated["statusCode"], 403)
            put_profile.assert_not_called()

    def test_platform_admin_member_can_edit_profile_but_not_manage_members_here(self):
        settings = {
            "company_id": "company-1",
            "company_role": "member",
            "features": [],
        }
        with (
            patch("app.storage.get_user_settings", return_value=settings),
            patch("app.storage.get_company", return_value={"company_id": "company-1", "name": "Acme"}),
            patch("app.storage.get_company_profile", return_value={"overview": "Software"}),
            patch("app.storage.put_company_profile", return_value={"overview": "Changed"}) as put_profile,
        ):
            viewed = app.lambda_handler(
                event("GET", "/company-profile", groups="[admin]"),
                SimpleNamespace(aws_request_id="test"),
            )
            body = json.loads(viewed["body"])
            self.assertEqual(viewed["statusCode"], 200)
            self.assertTrue(body["can_edit"])
            self.assertFalse(body["can_manage_members"])

            updated = app.lambda_handler(
                event("PUT", "/company-profile", {"profile": {"overview": "Changed"}}, groups="[admin]"),
                SimpleNamespace(aws_request_id="test"),
            )
            self.assertEqual(updated["statusCode"], 200)
            put_profile.assert_called_once_with("company-1", {"overview": "Changed"})

    def test_company_manager_can_view_member_list(self):
        settings = {
            "company_id": "company-1",
            "company_role": "manager",
            "features": [],
        }
        with (
            patch("app.storage.get_user_settings", return_value=settings),
            patch("app.storage.get_company", return_value={"company_id": "company-1", "name": "Acme"}),
            patch("app.storage.get_company_profile", return_value={"overview": "Software"}),
            patch("app.user_admin.list_users", return_value=[]),
        ):
            viewed = app.lambda_handler(
                event("GET", "/company-profile"),
                SimpleNamespace(aws_request_id="test"),
            )
            body = json.loads(viewed["body"])
            self.assertTrue(body["can_edit"])
            self.assertTrue(body["can_manage_members"])

            members = app.lambda_handler(
                event("GET", "/company-members"),
                SimpleNamespace(aws_request_id="test"),
            )
            self.assertEqual(members["statusCode"], 200)
            self.assertEqual(json.loads(members["body"])["items"], [])

    def test_company_member_cannot_view_or_manage_members(self):
        settings = {
            "company_id": "company-1",
            "company_role": "member",
            "features": [],
        }
        with (
            patch("app.storage.get_user_settings", return_value=settings),
            patch("app.storage.get_company", return_value={"company_id": "company-1", "name": "Acme"}),
            patch("app.user_admin.list_users") as list_users,
            patch("app.user_admin.create_user") as create_user,
            patch("app.user_admin.get_user") as get_user,
        ):
            for groups in ("[user]", "[admin]"):
                for method, path, body in (
                    ("GET", "/company-members", None),
                    ("POST", "/company-members", {"email": "new@example.com"}),
                    ("PUT", "/company-members/another-user", {"company_role": "manager"}),
                    ("DELETE", "/company-members/another-user", None),
                ):
                    with self.subTest(groups=groups, method=method, path=path):
                        result = app.lambda_handler(
                            event(method, path, body, groups=groups),
                            SimpleNamespace(aws_request_id="test"),
                        )
                        self.assertEqual(result["statusCode"], 403)
            list_users.assert_not_called()
            create_user.assert_not_called()
            get_user.assert_not_called()

    def test_unassigned_user_receives_self_service_profile_state(self):
        with (
            patch(
                "app.storage.get_user_settings",
                return_value={
                    "company_id": "",
                    "company_role": "member",
                    "features": [],
                },
            ),
            patch("app.storage.get_company", return_value=None),
            patch(
                "app.storage.empty_company_profile",
                return_value={"overview": ""},
            ),
        ):
            result = app.lambda_handler(
                event("GET", "/company-profile"),
                SimpleNamespace(aws_request_id="test"),
            )

        body = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 200)
        self.assertIsNone(body["company"])
        self.assertTrue(body["can_create"])
        self.assertFalse(body["can_edit"])

    def test_unassigned_user_creates_company_profile_as_manager(self):
        settings = {
            "company_id": "",
            "company_role": "member",
            "features": ["natural_language_search"],
        }
        company = {
            "company_id": "company-1",
            "name": "Acme",
            "created_at": 1,
            "updated_at": 1,
        }
        with (
            patch("app.storage.get_user_settings", return_value=settings),
            patch("app.storage.get_company", return_value=None),
            patch("app.storage.create_company", return_value=company) as create_company,
            patch(
                "app.storage.put_company_profile",
                return_value={"overview": "Custom software"},
            ) as put_profile,
            patch("app.storage.assign_company_manager_if_unassigned") as assign,
            patch("app.storage.delete_company") as delete_company,
        ):
            result = app.lambda_handler(
                event(
                    "POST",
                    "/company-profile",
                    {
                        "name": "Acme",
                        "profile": {"overview": "Custom software"},
                    },
                ),
                SimpleNamespace(aws_request_id="test"),
            )

        body = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(body["company"]["company_id"], "company-1")
        self.assertTrue(body["can_edit"])
        self.assertFalse(body["can_create"])
        create_company.assert_called_once_with("Acme")
        put_profile.assert_called_once_with(
            "company-1", {"overview": "Custom software"}
        )
        assign.assert_called_once_with(
            "current-sub", "company-1", ["natural_language_search"]
        )
        delete_company.assert_not_called()

    def test_existing_company_assignment_blocks_self_service_creation(self):
        with (
            patch(
                "app.storage.get_user_settings",
                return_value={
                    "company_id": "company-1",
                    "company_role": "member",
                    "features": [],
                },
            ),
            patch(
                "app.storage.get_company",
                return_value={"company_id": "company-1", "name": "Acme"},
            ),
            patch("app.storage.create_company") as create_company,
        ):
            result = app.lambda_handler(
                event("POST", "/company-profile", {"name": "Another"}),
                SimpleNamespace(aws_request_id="test"),
            )

        self.assertEqual(result["statusCode"], 400)
        create_company.assert_not_called()

    def test_failed_self_service_assignment_removes_new_company(self):
        company = {
            "company_id": "company-1",
            "name": "Acme",
            "created_at": 1,
            "updated_at": 1,
        }
        with (
            patch(
                "app.storage.get_user_settings",
                return_value={
                    "company_id": "",
                    "company_role": "member",
                    "features": [],
                },
            ),
            patch("app.storage.get_company", return_value=None),
            patch("app.storage.create_company", return_value=company),
            patch("app.storage.put_company_profile", return_value={}),
            patch(
                "app.storage.assign_company_manager_if_unassigned",
                side_effect=ValueError("Your account is already assigned to a company"),
            ),
            patch("app.storage.delete_company") as delete_company,
        ):
            result = app.lambda_handler(
                event("POST", "/company-profile", {"name": "Acme"}),
                SimpleNamespace(aws_request_id="test"),
            )

        self.assertEqual(result["statusCode"], 400)
        delete_company.assert_called_once_with("company-1")

    def test_platform_admin_can_read_another_company_profile(self):
        company = {"company_id": "company-1", "name": "Acme"}
        with (
            patch("app.storage.get_company", return_value=company),
            patch(
                "app.storage.get_company_profile",
                return_value={"overview": "Software"},
            ),
        ):
            result = app.lambda_handler(
                event(
                    "GET",
                    "/admin/companies/company-1/profile",
                    groups="[admin]",
                ),
                SimpleNamespace(aws_request_id="test"),
            )

        body = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(body["company"]["name"], "Acme")
        self.assertTrue(body["can_edit"])

    def test_platform_admin_can_update_another_company_profile(self):
        company = {"company_id": "company-1", "name": "Acme"}
        with (
            patch("app.storage.get_company", return_value=company),
            patch(
                "app.storage.put_company_profile",
                return_value={"overview": "Updated"},
            ) as put_profile,
        ):
            result = app.lambda_handler(
                event(
                    "PUT",
                    "/admin/companies/company-1/profile",
                    {"profile": {"overview": "Updated"}},
                    groups="[admin]",
                ),
                SimpleNamespace(aws_request_id="test"),
            )

        self.assertEqual(result["statusCode"], 200)
        put_profile.assert_called_once_with("company-1", {"overview": "Updated"})

    def test_regular_user_cannot_manage_another_company_profile(self):
        result = app.lambda_handler(
            event("GET", "/admin/companies/company-1/profile"),
            SimpleNamespace(aws_request_id="test"),
        )
        self.assertEqual(result["statusCode"], 403)


class CompanyAssignmentTests(unittest.TestCase):
    def test_company_claim_does_not_replace_an_existing_assignment(self):
        conditional_failure = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
        )
        with (
            patch("storage.get_company", return_value={"company_id": "company-1"}),
            patch("storage.table") as table,
        ):
            table.return_value.put_item.side_effect = conditional_failure
            with self.assertRaisesRegex(ValueError, "already assigned"):
                storage.assign_company_manager_if_unassigned(
                    "user-1", "company-1", []
                )


if __name__ == "__main__":
    unittest.main()
