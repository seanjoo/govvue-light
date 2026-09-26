"""Materialize daily notification results and deliver SES summaries."""

from __future__ import annotations

import gzip
import html
import json
import logging
import os
from typing import Any
from urllib.parse import quote, urlencode

import boto3

import storage
from notification_filters import matches, sanitize_criteria
from runtime_config import get_runtime_config
from sam_client import fetch_description


_s3 = boto3.client("s3")
_ses = boto3.client("sesv2")
LOGGER = logging.getLogger()
LOGGER.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
EMAIL_ITEM_LIMIT = 10
EMAIL_DESCRIPTION_LIMIT = 320
DESCRIPTION_CACHE_LIMIT = 250
_description_cache: dict[str, str] = {}


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


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _description_excerpt(value: Any) -> str:
    text = _compact_text(value)
    if len(text) <= EMAIL_DESCRIPTION_LIMIT:
        return text
    shortened = text[: EMAIL_DESCRIPTION_LIMIT - 1].rsplit(" ", 1)[0]
    if not shortened:
        shortened = text[: EMAIL_DESCRIPTION_LIMIT - 1]
    return f"{shortened}…"


def _email_opportunities(
    matches_for_run: list[dict[str, Any]], config: Any
) -> list[dict[str, Any]]:
    email_opportunities: list[dict[str, Any]] = []
    for opportunity in matches_for_run[:EMAIL_ITEM_LIMIT]:
        email_opportunity = {
            key: value
            for key, value in opportunity.items()
            if key != "_description_url"
        }
        description = str(opportunity.get("description") or "")
        description_url = str(opportunity.get("_description_url") or "")
        if not description and description_url:
            if description_url in _description_cache:
                description = _description_cache[description_url]
            else:
                try:
                    description = _description_excerpt(
                        fetch_description(description_url, config)
                    )
                    if len(_description_cache) >= DESCRIPTION_CACHE_LIMIT:
                        _description_cache.pop(next(iter(_description_cache)))
                    _description_cache[description_url] = description
                except Exception:
                    LOGGER.warning(
                        "Could not load a description for opportunity %s",
                        opportunity.get("notice_id") or "unknown",
                        exc_info=True,
                    )
        email_opportunity["description"] = _description_excerpt(description)
        email_opportunities.append(email_opportunity)
    return email_opportunities


def _detail_url(
    app_url: str, notice_id: str, notification_path: str
) -> str:
    query = urlencode(
        {
            "return_to": notification_path,
            "source_label": "daily notification results",
        }
    )
    return f"{app_url}/opportunities/{quote(notice_id, safe='')}?{query}"


def _email_bodies(
    name: str,
    run_date: str,
    total_count: int,
    email_opportunities: list[dict[str, Any]],
    notification_url: str,
    app_url: str,
    notification_path: str,
) -> tuple[str, str]:
    text_lines = [
        f"GovVue Light daily notification: {name}",
        f"{total_count} matching active opportunities for {run_date}.",
        "",
    ]
    if total_count > len(email_opportunities):
        text_lines.extend(
            [f"Showing the first {len(email_opportunities)} matches.", ""]
        )
    html_items: list[str] = []
    for opportunity in email_opportunities:
        title = _compact_text(opportunity.get("title")) or "Untitled opportunity"
        notice_id = _compact_text(opportunity.get("notice_id"))
        opportunity_type = _compact_text(opportunity.get("type")) or "Opportunity"
        due_date = _compact_text(opportunity.get("response_deadline")) or "Not provided"
        description = _description_excerpt(opportunity.get("description")) or "No description was provided by SAM.gov."
        detail_url = _detail_url(app_url, notice_id, notification_path)
        text_lines.extend(
            [
                f"- {title}",
                f"  Type: {opportunity_type}",
                f"  Response due: {due_date}",
                f"  Notice ID: {notice_id}",
                f"  Description: {description}",
                f"  View details: {detail_url}",
                "",
            ]
        )
        html_items.append(
            '<li style="margin-bottom: 1.25rem;">'
            f'<strong><a href="{html.escape(detail_url)}">{html.escape(title)}</a></strong><br>'
            f"<strong>Type:</strong> {html.escape(opportunity_type)}<br>"
            f"<strong>Response due:</strong> {html.escape(due_date)}<br>"
            f"<strong>Notice ID:</strong> {html.escape(notice_id)}"
            f'<p style="margin: .5rem 0;">{html.escape(description)}</p>'
            f'<a href="{html.escape(detail_url)}">View details in GovVue Light</a>'
            "</li>"
        )
    text_lines.append(f"View all matching opportunities: {notification_url}")
    showing = (
        f" Showing the first {len(email_opportunities)} matches."
        if total_count > len(email_opportunities)
        else ""
    )
    html_body = (
        f"<h1>{html.escape(name)}</h1>"
        f"<p>{total_count} matching active opportunities for {html.escape(run_date)}.{showing}</p>"
        f"<ul>{''.join(html_items)}</ul>"
        f'<p><a href="{html.escape(notification_url)}">View all matching opportunities in GovVue Light</a></p>'
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
        [
            {
                key: value
                for key, value in opportunity.items()
                if key != "_description_url"
            }
            for opportunity in matched
        ],
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
    result_path = f"/notifications/{quote(notification_id, safe='')}/runs/{quote(run_date, safe='')}"
    result_url = f"{app_url}{result_path}"
    email_opportunities = _email_opportunities(matched, config)
    text_body, html_body = _email_bodies(
        name,
        run_date,
        len(matched),
        email_opportunities,
        result_url,
        app_url,
        result_path,
    )
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
