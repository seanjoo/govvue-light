#!/usr/bin/env python3
"""Read and validate local GovVue Light configuration without leaking secrets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


REQUIRED = (
    "project_name",
    "environment",
    "aws_profile",
    "aws_region",
    "app_domain_name",
    "hosted_zone_id",
    "acm_certificate_arn",
    "sam_api_key",
    "sam_opportunities_api",
    "sam_entities_api",
    "sam_site_base_url",
    "notification_from_email",
    "ses_identity_domain",
    "daily_feed_schedule_expression",
    "daily_feed_timezone",
    "daily_notification_default_time",
)


def load(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a YAML mapping")
    return data


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED:
        value = data.get(key)
        if value is None or str(value).strip() in {"", "REPLACE_ME"}:
            errors.append(f"{key} must be set")

    environment = str(data.get("environment", ""))
    if environment not in {"dev", "stg", "prod"}:
        errors.append("environment must be dev, stg, or prod")

    if not str(data.get("app_domain_name", "")).endswith(".govvue.com"):
        errors.append("app_domain_name must be a govvue.com hostname")
    if str(data.get("aws_profile", "")) != "workshop":
        errors.append("aws_profile must be workshop for GovVue Light")
    certificate_arn = str(data.get("acm_certificate_arn", ""))
    if not certificate_arn.startswith("arn:aws:acm:us-east-1:"):
        errors.append("acm_certificate_arn must be an ACM certificate in us-east-1")

    for key in (
        "search_cache_ttl_seconds",
        "search_default_lookback_days",
        "search_max_lookback_days",
        "search_max_fanout",
        "search_max_sort_pages",
        "sam_page_size",
        "sam_request_timeout_seconds",
        "api_throttle_rate",
        "api_throttle_burst",
        "lambda_reserved_concurrency",
        "log_retention_days",
        "history_retention_days",
        "daily_feed_page_size",
        "daily_feed_retention_days",
        "notification_run_retention_days",
    ):
        try:
            if int(data.get(key, 0)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{key} must be a positive integer")

    try:
        page_size = int(data.get("sam_page_size", 0))
        if page_size > 1000:
            errors.append("sam_page_size cannot exceed the SAM.gov maximum of 1000")
    except (TypeError, ValueError):
        pass

    try:
        search_max_fanout = int(data.get("search_max_fanout", 0))
        if search_max_fanout > 50:
            errors.append("search_max_fanout cannot exceed 50")
    except (TypeError, ValueError):
        pass

    try:
        search_max_sort_pages = int(data.get("search_max_sort_pages", 0))
        if search_max_sort_pages > 50:
            errors.append("search_max_sort_pages cannot exceed 50")
    except (TypeError, ValueError):
        pass

    try:
        daily_page_size = int(data.get("daily_feed_page_size", 0))
        if daily_page_size > 1000:
            errors.append("daily_feed_page_size cannot exceed the SAM.gov maximum of 1000")
    except (TypeError, ValueError):
        pass

    sender = str(data.get("notification_from_email", ""))
    identity = str(data.get("ses_identity_domain", ""))
    if "@" not in sender or not sender.lower().endswith(f"@{identity.lower()}"):
        errors.append("notification_from_email must belong to ses_identity_domain")
    if not str(data.get("daily_feed_schedule_expression", "")).startswith(("cron(", "rate(")):
        errors.append("daily_feed_schedule_expression must be an EventBridge cron() or rate() expression")
    default_time = str(data.get("daily_notification_default_time", ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):(?:[0-5]\d)", default_time):
        errors.append("daily_notification_default_time must use HH:MM in 24-hour time")
    elif int(default_time[-2:]) % 5:
        errors.append("daily_notification_default_time must use a five-minute increment")

    return errors


def get_value(data: dict[str, Any], dotted_key: str) -> Any:
    value: Any = data
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted_key)
        value = value[part]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("key")
    subparsers.add_parser("validate")
    subparsers.add_parser("json")

    args = parser.parse_args()
    try:
        data = load(args.file)
        if args.command == "validate":
            errors = validate(data)
            if errors:
                for error in errors:
                    print(f"ERROR: {error}", file=sys.stderr)
                return 1
            print(f"Configuration is valid: {args.file}")
            return 0
        if args.command == "get":
            value = get_value(data, args.key)
            if isinstance(value, (dict, list)):
                print(json.dumps(value, separators=(",", ":")))
            elif isinstance(value, bool):
                print(str(value).lower())
            else:
                print(value)
            return 0
        if args.command == "json":
            redacted = dict(data)
            if "sam_api_key" in redacted:
                redacted["sam_api_key"] = "<redacted>"
            print(json.dumps(redacted, indent=2, sort_keys=True))
            return 0
    except (ValueError, KeyError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
