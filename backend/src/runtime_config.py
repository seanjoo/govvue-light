"""Runtime configuration loaded from SSM Parameter Store."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import boto3


@dataclass(frozen=True)
class RuntimeConfig:
    sam_api_key: str
    sam_opportunities_api: str
    sam_entities_api: str
    sam_site_base_url: str
    search_cache_ttl_seconds: int
    search_default_lookback_days: int
    search_max_lookback_days: int
    search_max_fanout: int
    search_max_sort_pages: int
    sam_page_size: int
    sam_request_timeout_seconds: int
    history_retention_days: int
    daily_feed_page_size: int
    daily_feed_retention_days: int
    notification_run_retention_days: int
    daily_notification_default_time: str = "06:15"


_PARAMETERS = {
    "SamApiKey": "sam_api_key",
    "SamOpportunitiesApi": "sam_opportunities_api",
    "SamEntitiesApi": "sam_entities_api",
    "SamSiteBaseUrl": "sam_site_base_url",
    "SearchCacheTtlSeconds": "search_cache_ttl_seconds",
    "SearchDefaultLookbackDays": "search_default_lookback_days",
    "SearchMaxLookbackDays": "search_max_lookback_days",
    "SearchMaxFanout": "search_max_fanout",
    "SearchMaxSortPages": "search_max_sort_pages",
    "SamPageSize": "sam_page_size",
    "SamRequestTimeoutSeconds": "sam_request_timeout_seconds",
    "HistoryRetentionDays": "history_retention_days",
    "DailyFeedPageSize": "daily_feed_page_size",
    "DailyFeedRetentionDays": "daily_feed_retention_days",
    "NotificationRunRetentionDays": "notification_run_retention_days",
    "DailyNotificationDefaultTime": "daily_notification_default_time",
}
_INTEGER_FIELDS = {
    "search_cache_ttl_seconds",
    "search_default_lookback_days",
    "search_max_lookback_days",
    "search_max_fanout",
    "search_max_sort_pages",
    "sam_page_size",
    "sam_request_timeout_seconds",
    "history_retention_days",
    "daily_feed_page_size",
    "daily_feed_retention_days",
    "notification_run_retention_days",
}
_lock = threading.Lock()
_cached: RuntimeConfig | None = None
_cached_at = 0.0


def get_runtime_config() -> RuntimeConfig:
    """Load configuration once per warm runtime and refresh it every five minutes."""
    global _cached, _cached_at
    now = time.monotonic()
    if _cached and now - _cached_at < 300:
        return _cached

    with _lock:
        now = time.monotonic()
        if _cached and now - _cached_at < 300:
            return _cached

        prefix = os.environ["CONFIG_PREFIX"].rstrip("/")
        names = [f"{prefix}/{name}" for name in _PARAMETERS]
        client = boto3.client("ssm")
        values: dict[str, str] = {}
        for start in range(0, len(names), 10):
            response = client.get_parameters(Names=names[start : start + 10], WithDecryption=True)
            values.update(
                {
                    parameter["Name"].rsplit("/", 1)[-1]: parameter["Value"]
                    for parameter in response.get("Parameters", [])
                }
            )
        missing = sorted(set(_PARAMETERS) - set(values))
        if missing:
            raise RuntimeError(f"Missing runtime parameters: {', '.join(missing)}")

        kwargs: dict[str, object] = {}
        for parameter_name, field_name in _PARAMETERS.items():
            value: object = values[parameter_name]
            if field_name in _INTEGER_FIELDS:
                value = int(str(value))
            kwargs[field_name] = value

        page_size = int(kwargs["sam_page_size"])
        if page_size < 1 or page_size > 1000:
            raise RuntimeError("SamPageSize must be between 1 and 1000")
        daily_page_size = int(kwargs["daily_feed_page_size"])
        if daily_page_size < 1 or daily_page_size > 1000:
            raise RuntimeError("DailyFeedPageSize must be between 1 and 1000")
        search_max_fanout = int(kwargs["search_max_fanout"])
        if search_max_fanout < 1 or search_max_fanout > 50:
            raise RuntimeError("SearchMaxFanout must be between 1 and 50")
        search_max_sort_pages = int(kwargs["search_max_sort_pages"])
        if search_max_sort_pages < 1 or search_max_sort_pages > 50:
            raise RuntimeError("SearchMaxSortPages must be between 1 and 50")
        default_time = str(kwargs["daily_notification_default_time"])
        try:
            hour, minute = (int(part) for part in default_time.split(":"))
            valid_default_time = len(default_time) == 5 and 0 <= hour <= 23 and 0 <= minute <= 59
        except (TypeError, ValueError):
            valid_default_time = False
        if not valid_default_time or minute % 5:
            raise RuntimeError(
                "DailyNotificationDefaultTime must use HH:MM on a five-minute increment"
            )

        _cached = RuntimeConfig(**kwargs)  # type: ignore[arg-type]
        _cached_at = now
        return _cached
