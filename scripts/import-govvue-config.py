#!/usr/bin/env python3
"""Create a local GovVue Light dev config from the retired GovVue config."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml


DEFAULTS = {
    "project_name": "govvue-light",
    "environment": "dev",
    "aws_profile": "workshop",
    "aws_region": "us-east-1",
    "app_domain_name": "app.govvue.com",
    "hosted_zone_id": "Z04260832ZB8NBYSOXBA7",
    "acm_certificate_arn": "arn:aws:acm:us-east-1:428613119099:certificate/f810f621-f8fb-449e-9f51-a793dcc69904",
    "sam_opportunities_api": "https://api.sam.gov/opportunities/v2/search",
    "sam_entities_api": "https://api.sam.gov/entity-information/v4/entities",
    "sam_site_base_url": "https://sam.gov",
    "frontend_title": "GovVue Light",
    "cors_allowed_origin": "https://app.govvue.com",
    "search_cache_ttl_seconds": 900,
    "search_default_lookback_days": 30,
    "search_max_lookback_days": 365,
    "search_max_fanout": 12,
    "search_max_sort_pages": 24,
    "sam_page_size": 1000,
    "sam_request_timeout_seconds": 25,
    "api_throttle_rate": 2,
    "api_throttle_burst": 5,
    "lambda_reserved_concurrency": 2,
    "log_retention_days": 30,
    "history_retention_days": 90,
    "daily_feed_page_size": 1000,
    "daily_feed_retention_days": 30,
    "notification_run_retention_days": 90,
    "daily_feed_schedule_expression": "cron(0/5 * * * ? *)",
    "daily_feed_timezone": "America/New_York",
    "daily_notification_default_time": "06:15",
    "notification_from_email": "notifications@govvue.com",
    "ses_identity_domain": "govvue.com",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing configuration: {output}")

    with source.open("r", encoding="utf-8") as stream:
        legacy = yaml.safe_load(stream) or {}

    enabled_keys = [
        entry
        for entry in legacy.get("sam_api_keys", [])
        if entry.get("api_key") and entry.get("status", "enabled") == "enabled"
    ]
    if not enabled_keys:
        raise SystemExit("No enabled SAM.gov API key was found in the GovVue configuration")

    config = dict(DEFAULTS)
    config["sam_api_key"] = enabled_keys[0]["api_key"]
    config["sam_opportunities_api"] = legacy.get(
        "sam_opportunities_api", DEFAULTS["sam_opportunities_api"]
    )
    config["sam_site_base_url"] = legacy.get(
        "sam_site_base_url", DEFAULTS["sam_site_base_url"]
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)
    os.chmod(output, 0o600)
    print(f"Created local configuration: {output}")
    print("The SAM.gov API key was copied without being displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
