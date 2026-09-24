#!/usr/bin/env python3
"""Synchronize local configuration to SSM Parameter Store."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from config import load, validate


PARAMETERS: dict[str, tuple[str, str, str]] = {
    "SamApiKey": ("sam_api_key", "SecureString", "SAM.gov API key"),
    "SamOpportunitiesApi": ("sam_opportunities_api", "String", "SAM.gov opportunities API URL"),
    "SamEntitiesApi": ("sam_entities_api", "String", "SAM.gov Entity Management API URL"),
    "SamSiteBaseUrl": ("sam_site_base_url", "String", "SAM.gov website base URL"),
    "AppDomainName": ("app_domain_name", "String", "CloudFront application hostname"),
    "HostedZoneId": ("hosted_zone_id", "String", "Route 53 public hosted zone ID"),
    "AcmCertificateArn": ("acm_certificate_arn", "String", "CloudFront ACM certificate ARN"),
    "CognitoDomainName": ("cognito_domain_name", "String", "Cognito custom authentication hostname"),
    "CognitoCertificateArn": ("cognito_certificate_arn", "String", "Cognito custom-domain ACM certificate ARN"),
    "GoogleOAuthClientId": ("google_oauth_client_id", "String", "Google Web OAuth client ID"),
    "GoogleOAuthClientSecret": ("google_oauth_client_secret", "SecureString", "Google Web OAuth client secret"),
    "FrontendTitle": ("frontend_title", "String", "Browser application title"),
    "CorsAllowedOrigin": ("cors_allowed_origin", "String", "Allowed browser origin"),
    "SearchCacheTtlSeconds": ("search_cache_ttl_seconds", "String", "Search cache TTL in seconds"),
    "SearchDefaultLookbackDays": ("search_default_lookback_days", "String", "Default search lookback"),
    "SearchMaxLookbackDays": ("search_max_lookback_days", "String", "Maximum search lookback"),
    "SearchMaxFanout": ("search_max_fanout", "String", "Maximum SAM.gov searches per multi-value query"),
    "SearchMaxSortPages": ("search_max_sort_pages", "String", "Maximum SAM.gov pages loaded for exact result sorting"),
    "SamPageSize": ("sam_page_size", "String", "SAM.gov upstream page size"),
    "SamRequestTimeoutSeconds": ("sam_request_timeout_seconds", "String", "SAM.gov request timeout"),
    "ApiThrottleRate": ("api_throttle_rate", "String", "API Gateway steady request rate"),
    "ApiThrottleBurst": ("api_throttle_burst", "String", "API Gateway request burst"),
    "LambdaReservedConcurrency": ("lambda_reserved_concurrency", "String", "API Lambda concurrency cap"),
    "LogRetentionDays": ("log_retention_days", "String", "CloudWatch log retention"),
    "HistoryRetentionDays": ("history_retention_days", "String", "Search history retention"),
    "DailyFeedPageSize": ("daily_feed_page_size", "String", "SAM.gov records fetched by each daily feed invocation"),
    "DailyFeedRetentionDays": ("daily_feed_retention_days", "String", "Daily feed snapshot retention"),
    "NotificationRunRetentionDays": ("notification_run_retention_days", "String", "Daily notification result retention"),
    "DailyFeedScheduleExpression": ("daily_feed_schedule_expression", "String", "Daily EventBridge schedule expression"),
    "DailyFeedTimezone": ("daily_feed_timezone", "String", "Daily EventBridge schedule time zone"),
    "DailyNotificationDefaultTime": ("daily_notification_default_time", "String", "Default daily notification time"),
    "NotificationFromEmail": ("notification_from_email", "String", "Daily notification sender address"),
    "SesIdentityDomain": ("ses_identity_domain", "String", "SES domain identity"),
}


def run_aws(config: dict[str, Any], arguments: list[str], *, capture: bool = False) -> str:
    command = [
        "aws",
        *arguments,
        "--region",
        str(config["aws_region"]),
        "--profile",
        str(config["aws_profile"]),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    return result.stdout.strip() if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load(Path(args.config))
    errors = validate(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    prefix = f"/{config['project_name']}/{config['environment']}"
    for parameter_key, (config_key, parameter_type, description) in PARAMETERS.items():
        name = f"{prefix}/{parameter_key}"
        secret = parameter_type == "SecureString"
        if args.dry_run:
            display = "<redacted>" if secret else str(config[config_key])
            print(f"WOULD WRITE {name} ({parameter_type}) = {display}")
            continue

        run_aws(
            config,
            [
                "ssm",
                "put-parameter",
                "--name",
                name,
                "--value",
                str(config[config_key]),
                "--type",
                parameter_type,
                "--description",
                description,
                "--tier",
                "Standard",
                "--overwrite",
            ],
        )
        print(f"WRITE {name} ({parameter_type})" + (" = <redacted>" if secret else ""))

    print(f"Configuration synchronized under {prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
