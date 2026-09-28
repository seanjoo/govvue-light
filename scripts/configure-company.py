#!/usr/bin/env python3
"""Idempotently create a company workspace, profile, and user assignments."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from config import load, validate


PROFILE_FIELDS = {
    "overview",
    "capabilities",
    "differentiators",
    "past_performance",
    "naics_codes",
    "psc_codes",
    "target_agencies",
    "set_aside_eligibility",
    "positive_keywords",
    "negative_keywords",
}


def stack_output(client: Any, stack_name: str, key: str) -> str:
    outputs = client.describe_stacks(StackName=stack_name)["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output.get("OutputKey") == key:
            return str(output.get("OutputValue") or "")
    raise RuntimeError(f"Stack output {key} was not found")


def cognito_users(client: Any, pool_id: str) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    paginator = client.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=pool_id):
        for user in page.get("Users", []):
            attributes = {
                str(item.get("Name") or ""): str(item.get("Value") or "")
                for item in user.get("Attributes", [])
            }
            email = attributes.get("email", "").casefold()
            if email:
                users[email] = {
                    "username": str(user.get("Username") or ""),
                    "sub": attributes.get("sub", ""),
                    "email": attributes.get("email", ""),
                }
    return users


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--manager", action="append", default=[])
    parser.add_argument("--member", action="append", default=[])
    parser.add_argument("--feature-user", action="append", default=[])
    args = parser.parse_args()

    config = load(args.config)
    errors = validate(config)
    if errors:
        raise ValueError("; ".join(errors))
    profile_path = Path(args.profile_json)
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile_data, dict):
        raise ValueError("Company profile JSON must be an object")
    profile = {
        field: str(profile_data.get(field) or "").strip()[:4000]
        for field in PROFILE_FIELDS
    }

    requested = {
        value.casefold()
        for value in [*args.manager, *args.member, *args.feature_user]
        if value.strip()
    }
    if not args.manager:
        raise ValueError("At least one --manager is required")

    session = boto3.Session(
        profile_name=str(config["aws_profile"]),
        region_name=str(config["aws_region"]),
    )
    cloudformation = session.client("cloudformation")
    stack_name = f"{config['project_name']}-{config['environment']}"
    table_name = stack_output(cloudformation, stack_name, "StateTableName")
    pool_id = stack_output(cloudformation, stack_name, "CognitoUserPoolId")
    table = session.resource("dynamodb").Table(table_name)
    users = cognito_users(session.client("cognito-idp"), pool_id)
    missing = sorted(requested - set(users))
    if missing:
        raise ValueError(f"Cognito users not found: {', '.join(missing)}")

    existing = table.query(
        KeyConditionExpression=Key("PK").eq("SYSTEM#COMPANIES")
        & Key("SK").begins_with("COMPANY#")
    ).get("Items", [])
    company = next(
        (item for item in existing if str(item.get("name") or "").casefold() == args.name.casefold()),
        None,
    )
    now = int(time.time())
    company_id = str(company.get("companyId")) if company else uuid.uuid4().hex
    table.put_item(
        Item={
            "PK": "SYSTEM#COMPANIES",
            "SK": f"COMPANY#{company_id}",
            "entityType": "company",
            "companyId": company_id,
            "name": args.name.strip()[:120],
            "createdAt": int(company.get("createdAt") or now) if company else now,
            "updatedAt": now,
        }
    )
    table.put_item(
        Item={
            "PK": f"COMPANY#{company_id}",
            "SK": "PROFILE",
            "entityType": "companyProfile",
            "profile": profile,
            "updatedAt": now,
        }
    )

    managers = {value.casefold() for value in args.manager}
    feature_users = {value.casefold() for value in args.feature_user}
    for email in sorted(requested):
        user = users[email]
        current = table.get_item(
            Key={"PK": f"USER#{user['sub']}", "SK": "SETTINGS"},
            ConsistentRead=True,
        ).get("Item", {})
        features = {str(value) for value in current.get("features", [])}
        if email in feature_users:
            features.add("natural_language_search")
        else:
            features.discard("natural_language_search")
        table.put_item(
            Item={
                "PK": f"USER#{user['sub']}",
                "SK": "SETTINGS",
                "entityType": "userSettings",
                "companyId": company_id,
                "companyRole": "manager" if email in managers else "member",
                "features": sorted(features),
                "updatedAt": now,
            }
        )
        print(
            f"ASSIGN {user['email']} as "
            f"{'manager' if email in managers else 'member'}"
            + (" with natural_language_search" if email in feature_users else "")
        )

    print(f"CONFIGURED {args.name} ({company_id}) with profile {profile_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
