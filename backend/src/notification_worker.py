"""Materialize daily notification results and deliver SES summaries."""

from __future__ import annotations

import gzip
import html
import json
import logging
import os
from typing import Any
from urllib.parse import quote

import boto3

import storage
from notification_filters import matches, sanitize_criteria
from runtime_config import get_runtime_config


_s3 = boto3.client("s3")
_ses = boto3.client("sesv2")
LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def _load_feed(run_date: str, total_pages: int) -> list[dict[str, Any]]:
    opportunities: dict[str, dict[str, Any]] = {}
    for page_index in range(total_pages):
        key = f"daily-feed/{run_date}/pages/{page_index:06d}.json.gz"
        response = _s3.get_object(Bucket=os.environ["DAILY_FEED_BUCKET"], Key=key)
        payload = json.loads(gzip.decompress(response["Body"].read()).decode("utf-8"))
        for opportunity in payload.get("records") or []:
            notice_id = str(opportunity.get("notice_id") or "")
            if notice_id:
                opportunities[notice_id] = opportunity
    return list(opportunities.values())


def _email_bodies(name: str, run_date: str, matches_for_run: list[dict[str, Any]], url: str) -> tuple[str, str]:
    count = len(matches_for_run)
    text_lines = [
        f"GovVue Light daily notification: {name}",
        f"{count} matching active opportunities for {run_date}.",
        "",
    ]
    html_items = []
    for opportunity in matches_for_run[:10]:
        title = str(opportunity.get("title") or "Untitled opportunity")
        notice_id = str(opportunity.get("notice_id") or "")
        text_lines.append(f"- {title} ({notice_id})")
        html_items.append(f"<li><strong>{html.escape(title)}</strong><br>Notice ID: {html.escape(notice_id)}</li>")
    text_lines.extend(["", f"View this notification: {url}"])
    html_body = (
        f"<h1>{html.escape(name)}</h1>"
        f"<p>{count} matching active opportunities for {html.escape(run_date)}.</p>"
        f"<ul>{''.join(html_items)}</ul>"
        f'<p><a href="{html.escape(url)}">View this notification in GovVue Light</a></p>'
    )
    return "\n".join(text_lines), html_body


def _process(message: dict[str, Any]) -> None:
    config = get_runtime_config()
    user_id = str(message["user_id"])
    notification_id = str(message["notification_id"])
    run_date = str(message["run_date"])
    name = str(message["name"])
    recipient = str(message["recipient_email"])
    criteria = sanitize_criteria(message.get("criteria") or {})

    feed = _load_feed(run_date, max(1, int(message.get("total_pages") or 1)))
    matched = [opportunity for opportunity in feed if matches(opportunity, criteria)]
    matched.sort(
        key=lambda opportunity: (
            str(opportunity.get("posted_date") or ""),
            str(opportunity.get("notice_id") or ""),
        ),
        reverse=True,
    )
    storage.put_notification_results(
        user_id,
        notification_id,
        run_date,
        matched,
        config.notification_run_retention_days,
    )
    storage.put_notification_run_summary(
        user_id,
        notification_id,
        run_date,
        criteria,
        len(matched),
        config.notification_run_retention_days,
    )
    if not storage.claim_notification_email(user_id, notification_id, run_date):
        return

    app_url = f"https://{os.environ['APP_DOMAIN_NAME'].strip('/')}"
    result_url = f"{app_url}/notifications/{quote(notification_id)}/runs/{quote(run_date)}"
    text_body, html_body = _email_bodies(name, run_date, matched, result_url)
    try:
        response = _ses.send_email(
            FromEmailAddress=os.environ["NOTIFICATION_FROM_EMAIL"],
            Destination={"ToAddresses": [recipient]},
            Content={
                "Simple": {
                    "Subject": {"Data": f"GovVue Light — {name}: {len(matched)} matches", "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                }
            },
        )
        storage.finish_notification_email(
            user_id,
            notification_id,
            run_date,
            "SENT",
            str(response.get("MessageId") or ""),
        )
    except Exception as exc:
        storage.finish_notification_email(
            user_id, notification_id, run_date, "FAILED", error=str(exc)
        )
        raise


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures = []
    for record in event.get("Records") or []:
        try:
            _process(json.loads(record.get("body") or "{}"))
        except Exception:
            LOGGER.exception("Daily notification message failed")
            failures.append({"itemIdentifier": record.get("messageId") or "unknown"})
    return {"batchItemFailures": failures}
