"""Cognito pre-sign-up trigger that links Google to an invited local user."""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3


LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_cognito = None


def cognito_client():
    global _cognito
    if _cognito is None:
        _cognito = boto3.client("cognito-idp")
    return _cognito


def _filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _attribute_map(user: dict[str, Any]) -> dict[str, str]:
    return {
        str(attribute.get("Name") or ""): str(attribute.get("Value") or "")
        for attribute in user.get("Attributes", [])
    }


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if event.get("triggerSource") != "PreSignUp_ExternalProvider":
        return event

    username = str(event.get("userName") or "")
    provider_name, separator, provider_subject = username.partition("_")
    attributes = event.get("request", {}).get("userAttributes", {})
    email = str(attributes.get("email") or "").strip().lower()
    email_verified = str(attributes.get("email_verified") or "").lower() == "true"
    user_pool_id = str(event.get("userPoolId") or "")
    if provider_name != "Google" or not separator or not provider_subject:
        raise ValueError("Only Google identities can use this sign-in flow")
    if not user_pool_id or not email or not email_verified:
        raise ValueError("Google must provide a verified email address")

    client = cognito_client()
    response = client.list_users(
        UserPoolId=user_pool_id,
        Filter=f'email = "{_filter_value(email)}"',
        Limit=10,
    )
    candidates = [
        user
        for user in response.get("Users", [])
        if not str(user.get("Username") or "").startswith("Google_")
        and _attribute_map(user).get("email", "").lower() == email
    ]
    if not candidates:
        raise ValueError(
            "No invited GovVue Light account matches this Google email address"
        )
    if len(candidates) > 1:
        raise RuntimeError("Multiple GovVue Light accounts use this email address")

    destination_username = str(candidates[0].get("Username") or "")
    destination_attributes = _attribute_map(candidates[0])
    if destination_attributes.get("email_verified", "false").lower() != "true":
        client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=destination_username,
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )
    client.admin_link_provider_for_user(
        UserPoolId=user_pool_id,
        DestinationUser={
            "ProviderName": "Cognito",
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": destination_username,
        },
        SourceUser={
            "ProviderName": "Google",
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": provider_subject,
        },
    )
    LOGGER.info("Linked a verified Google identity to an invited Cognito user")
    return event
