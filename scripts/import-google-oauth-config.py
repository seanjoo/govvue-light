#!/usr/bin/env python3
"""Import a Google Web OAuth client JSON into the local environment YAML."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--domain-name", required=True)
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    config_path = Path(args.config)
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    web = credentials.get("web")
    if not isinstance(web, dict):
        raise ValueError("Google credentials must be for a Web application")
    client_id = str(web.get("client_id") or "").strip()
    client_secret = str(web.get("client_secret") or "").strip()
    if not client_id.endswith(".apps.googleusercontent.com") or not client_secret:
        raise ValueError("Google credentials are missing a client ID or client secret")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("Configuration root must be a YAML mapping")
    config["cognito_domain_name"] = args.domain_name
    config["google_oauth_client_id"] = client_id
    config["google_oauth_client_secret"] = client_secret
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    os.chmod(config_path, 0o600)
    print(f"Imported Google Web OAuth credentials into {config_path} (secret redacted).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
