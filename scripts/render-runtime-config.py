#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--aws-region", required=True)
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--user-pool-client-id", required=True)
    parser.add_argument("--app-title", required=True)
    parser.add_argument("--daily-notification-default-time", required=True)
    parser.add_argument("--build-id", required=True)
    args = parser.parse_args()
    config = {
        "apiBaseUrl": args.api_base_url,
        "awsRegion": args.aws_region,
        "userPoolId": args.user_pool_id,
        "userPoolClientId": args.user_pool_client_id,
        "appTitle": args.app_title,
        "dailyNotificationDefaultTime": args.daily_notification_default_time,
        "buildId": args.build_id,
    }
    output = Path(args.output)
    output.write_text(
        "window.GOVVUE_CONFIG = " + json.dumps(config, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
