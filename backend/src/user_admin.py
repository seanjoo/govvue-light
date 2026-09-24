"""Administrative Cognito user management for authorized GovVue admins."""

from __future__ import annotations

import os
import re
from typing import Any

import boto3
from botocore.exceptions import ClientError


VALID_ROLES = {"admin", "user"}
_cognito = None
_ses = None


class UserAdminError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def cognito_client():
    global _cognito
    if _cognito is None:
        _cognito = boto3.client("cognito-idp")
    return _cognito


def ses_client():
    global _ses
    if _ses is None:
        _ses = boto3.client("sesv2")
    return _ses


def user_pool_id() -> str:
    return os.environ["USER_POOL_ID"]


def _role(value: Any) -> str:
    role = str(value or "user").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("role must be admin or user")
    return role


def _email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise ValueError("A valid email address is required")
    return email


def _attributes(values: list[dict[str, str]]) -> dict[str, str]:
    return {str(item.get("Name") or ""): str(item.get("Value") or "") for item in values}


def _groups_for(username: str) -> list[str]:
    response = cognito_client().admin_list_groups_for_user(
        UserPoolId=user_pool_id(), Username=username
    )
    return sorted(str(group.get("GroupName") or "") for group in response.get("Groups", []))


def _normalize_user(user: dict[str, Any], groups: list[str] | None = None) -> dict[str, Any]:
    attributes = _attributes(user.get("Attributes") or user.get("UserAttributes") or [])
    memberships = groups if groups is not None else _groups_for(str(user["Username"]))
    return {
        "username": str(user.get("Username") or ""),
        "sub": attributes.get("sub", ""),
        "email": attributes.get("email", ""),
        "email_verified": attributes.get("email_verified", "false").lower() == "true",
        "role": "admin" if "admin" in memberships else "user",
        "groups": memberships,
        "enabled": bool(user.get("Enabled", True)),
        "status": str(user.get("UserStatus") or ""),
        "created_at": user.get("UserCreateDate").isoformat() if user.get("UserCreateDate") else "",
        "updated_at": user.get("UserLastModifiedDate").isoformat() if user.get("UserLastModifiedDate") else "",
    }


def _translate_error(exc: ClientError) -> UserAdminError:
    code = str(exc.response.get("Error", {}).get("Code") or "")
    message = str(exc.response.get("Error", {}).get("Message") or "Cognito request failed")
    if code in {"UserNotFoundException", "ResourceNotFoundException"}:
        return UserAdminError("User not found", 404)
    if code in {"UsernameExistsException", "AliasExistsException"}:
        return UserAdminError("A user with this email already exists", 409)
    if code in {"TooManyRequestsException", "LimitExceededException"}:
        return UserAdminError("Cognito request limit reached; try again shortly", 429)
    if code in {"InvalidParameterException", "InvalidPasswordException", "NotAuthorizedException"}:
        return UserAdminError(message, 400)
    return UserAdminError("User management request failed", 502)


def _request_ses_verification(email: str) -> str:
    client = ses_client()
    try:
        identity = client.get_email_identity(EmailIdentity=email)
        if identity.get("VerifiedForSendingStatus"):
            return "verified"
        if identity.get("VerificationStatus") in {"PENDING", "NOT_STARTED"}:
            return "pending"
        # SES verification links expire. Recreate failed identities so SES
        # sends the user a fresh verification message.
        client.delete_email_identity(EmailIdentity=email)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "NotFoundException":
            raise
    client.create_email_identity(EmailIdentity=email)
    return "verification_requested"


def list_users() -> list[dict[str, Any]]:
    client = cognito_client()
    users: list[dict[str, Any]] = []
    token: str | None = None
    try:
        while True:
            request: dict[str, Any] = {"UserPoolId": user_pool_id(), "Limit": 60}
            if token:
                request["PaginationToken"] = token
            result = client.list_users(**request)
            users.extend(result.get("Users", []))
            token = result.get("PaginationToken")
            if not token or len(users) >= 500:
                break
        normalized = [_normalize_user(user) for user in users]
        return sorted(normalized, key=lambda item: (item["email"].casefold(), item["username"]))
    except ClientError as exc:
        raise _translate_error(exc) from exc


def create_user(email_value: Any, role_value: Any) -> dict[str, Any]:
    email = _email(email_value)
    role = _role(role_value)
    client = cognito_client()
    created = False
    try:
        ses_status = _request_ses_verification(email)
        result = client.admin_create_user(
            UserPoolId=user_pool_id(),
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        created = True
        username = str(result["User"]["Username"])
        client.admin_add_user_to_group(
            UserPoolId=user_pool_id(), Username=username, GroupName=role
        )
        return {**_normalize_user(result["User"], [role]), "ses_status": ses_status}
    except ClientError as exc:
        if created:
            try:
                client.admin_delete_user(UserPoolId=user_pool_id(), Username=username)
            except Exception:
                pass
        raise _translate_error(exc) from exc


def get_user(username: str) -> dict[str, Any]:
    try:
        result = cognito_client().admin_get_user(
            UserPoolId=user_pool_id(), Username=username
        )
        return _normalize_user(result)
    except ClientError as exc:
        raise _translate_error(exc) from exc


def update_user(username: str, role_value: Any, enabled_value: Any) -> dict[str, Any]:
    role = _role(role_value)
    if not isinstance(enabled_value, bool):
        raise ValueError("enabled must be a boolean")
    client = cognito_client()
    try:
        client.admin_add_user_to_group(
            UserPoolId=user_pool_id(), Username=username, GroupName=role
        )
        for group in VALID_ROLES - {role}:
            try:
                client.admin_remove_user_from_group(
                    UserPoolId=user_pool_id(), Username=username, GroupName=group
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                    raise
        action = client.admin_enable_user if enabled_value else client.admin_disable_user
        action(UserPoolId=user_pool_id(), Username=username)
        return get_user(username)
    except ClientError as exc:
        raise _translate_error(exc) from exc


def reset_user_password(username: str) -> str:
    client = cognito_client()
    try:
        user = client.admin_get_user(UserPoolId=user_pool_id(), Username=username)
        if user.get("UserStatus") == "FORCE_CHANGE_PASSWORD":
            client.admin_create_user(
                UserPoolId=user_pool_id(),
                Username=username,
                MessageAction="RESEND",
                DesiredDeliveryMediums=["EMAIL"],
            )
            return "invitation_resent"
        client.admin_reset_user_password(UserPoolId=user_pool_id(), Username=username)
        return "password_reset_sent"
    except ClientError as exc:
        raise _translate_error(exc) from exc


def disable_user_for_deletion(username: str) -> dict[str, Any]:
    client = cognito_client()
    try:
        user = client.admin_get_user(UserPoolId=user_pool_id(), Username=username)
        client.admin_disable_user(UserPoolId=user_pool_id(), Username=username)
        return _normalize_user(user)
    except ClientError as exc:
        raise _translate_error(exc) from exc


def delete_user(username: str) -> None:
    try:
        cognito_client().admin_delete_user(
            UserPoolId=user_pool_id(), Username=username
        )
    except ClientError as exc:
        raise _translate_error(exc) from exc
