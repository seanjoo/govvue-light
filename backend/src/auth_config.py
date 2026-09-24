"""CloudFormation custom resource for the Cognito Google identity provider."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

import boto3
from botocore.exceptions import ClientError


LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def _send_response(
    event: dict[str, Any],
    context: Any,
    status: str,
    physical_id: str,
    reason: str = "",
) -> None:
    body = json.dumps(
        {
            "Status": status,
            "Reason": reason or f"See CloudWatch log stream {context.log_stream_name}",
            "PhysicalResourceId": physical_id,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "NoEcho": True,
            "Data": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        event["ResponseURL"],
        data=body,
        method="PUT",
        headers={"content-type": "", "content-length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=10):
        pass


def _parameter(name: str, decrypt: bool = False) -> str:
    result = boto3.client("ssm").get_parameter(Name=name, WithDecryption=decrypt)
    return str(result["Parameter"]["Value"])


def _provider_configuration() -> dict[str, Any]:
    prefix = os.environ["CONFIG_PREFIX"].rstrip("/")
    return {
        "ProviderDetails": {
            "authorize_scopes": "openid email profile",
            "client_id": _parameter(f"{prefix}/GoogleOAuthClientId"),
            "client_secret": _parameter(
                f"{prefix}/GoogleOAuthClientSecret", decrypt=True
            ),
        },
        "AttributeMapping": {
            "email": "email",
            "email_verified": "email_verified",
        },
    }


def lambda_handler(event: dict[str, Any], context: Any) -> None:
    properties = event.get("ResourceProperties", {})
    user_pool_id = str(properties.get("UserPoolId") or "")
    provider_name = str(properties.get("ProviderName") or "Google")
    physical_id = f"{user_pool_id}/{provider_name}"
    try:
        if event.get("RequestType") == "Delete":
            try:
                boto3.client("cognito-idp").delete_identity_provider(
                    UserPoolId=user_pool_id, ProviderName=provider_name
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                    raise
        else:
            client = boto3.client("cognito-idp")
            configuration = _provider_configuration()
            try:
                client.describe_identity_provider(
                    UserPoolId=user_pool_id, ProviderName=provider_name
                )
                client.update_identity_provider(
                    UserPoolId=user_pool_id,
                    ProviderName=provider_name,
                    **configuration,
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                    raise
                client.create_identity_provider(
                    UserPoolId=user_pool_id,
                    ProviderName=provider_name,
                    ProviderType="Google",
                    **configuration,
                )
        _send_response(event, context, "SUCCESS", physical_id)
    except Exception as exc:
        LOGGER.exception("Failed to configure the Cognito Google identity provider")
        _send_response(
            event,
            context,
            "FAILED",
            physical_id or str(getattr(context, "log_stream_name", "failed")),
            f"Google identity provider configuration failed: {type(exc).__name__}",
        )
