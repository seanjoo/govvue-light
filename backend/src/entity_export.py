"""SQS-driven asynchronous daily SAM entity JSON export downloader."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
from datetime import date
from urllib.error import HTTPError
from urllib.parse import urlencode, unquote
from urllib.request import Request, urlopen

import boto3
from botocore.exceptions import ClientError


LOGGER = logging.getLogger(__name__)
MAX_POLLS = 24
POLL_DELAY_SECONDS = 300
MAX_BUILD_WAIT_ATTEMPTS = 48


def _api_key() -> str:
    return boto3.client("ssm").get_parameter(
        Name=os.environ["SAM_API_KEY_PARAMETER"], WithDecryption=True
    )["Parameter"]["Value"]


def _message(action: str, day: str, **extra: object) -> None:
    payload = {"action": action, "day": day, **extra}
    boto3.client("sqs").send_message(
        QueueUrl=os.environ["ENTITY_EXPORT_QUEUE_URL"],
        MessageBody=json.dumps(payload, separators=(",", ":")),
        DelaySeconds=POLL_DELAY_SECONDS if action == "check" else 0,
    )


def _manifest_date() -> str:
    try:
        body = boto3.client("s3").get_object(
            Bucket=os.environ["LOCAL_INDEX_BUCKET"],
            Key="indexes/entities/current.json",
        )["Body"].read()
        return str(json.loads(body).get("source_date") or "")
    except Exception:
        return ""


def _request(day: str) -> None:
    last_published = _manifest_date()
    if not last_published:
        raise ValueError("Run the public monthly entity backfill before a daily export")
    if last_published >= day:
        return
    end = date.fromisoformat(day)
    start = date.fromisoformat(last_published)
    api = os.environ["SAM_ENTITIES_API"].rstrip("/")
    params = {
        "api_key": _api_key(),
        "updateDate": f"[{start.strftime('%m/%d/%Y')},{end.strftime('%m/%d/%Y')}]",
        "registrationStatus": "A",
        "samRegistered": "Yes",
        "includeSections": "entityRegistration,coreData,assertions",
        "format": "json",
    }
    request = Request(f"{api}?{urlencode(params)}", headers={"Accept": "application/json"})
    with urlopen(request, timeout=60) as response:
        payload = response.read().decode("utf-8")
    match = re.search(r"download-entities\?[^\s\"']*?\btoken=([^&\s\"']+)", payload)
    if not match:
        raise ValueError("SAM did not provide a daily entity export token")
    token = unquote(match.group(1).replace("\\u003d", "="))
    if not token or len(token) > 1024:
        raise ValueError("SAM provided an invalid entity export token")
    _message("check", day, token=token, attempt=0)


def _check(day: str, token: str, attempt: int) -> None:
    if _manifest_date() >= day:
        return
    if attempt >= MAX_POLLS:
        raise TimeoutError(f"SAM entity export for {day} was not ready after {MAX_POLLS} polls")
    api = os.environ["SAM_ENTITIES_API"].rstrip("/")
    endpoint = api.rsplit("/entities", 1)[0] + "/download-entities"
    request = Request(
        f"{endpoint}?{urlencode({'token': token, 'api_key': _api_key()})}",
        data=b"",
        headers={"Accept": "application/zip", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        if exc.code in {400, 404, 429, 503} and (
            "not generated yet" in detail.casefold()
            or "in progress" in detail.casefold()
            or exc.code in {429, 503}
        ):
            _message("check", day, token=token, attempt=attempt + 1)
            return
        raise
    if "json" in content_type and not body.startswith(b"\x1f\x8b"):
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, (dict, list)) or (
            isinstance(payload, dict) and "entityData" not in payload
        ):
            _message("check", day, token=token, attempt=attempt + 1)
            return
        body = gzip.compress(body)
    elif not body.startswith(b"\x1f\x8b"):
        raise ValueError("SAM entity export was neither JSON nor gzipped JSON")
    bucket = os.environ["LOCAL_INDEX_BUCKET"]
    key = f"raw/entities/daily/{day}.json.gz"
    boto3.client("s3").put_object(
        Bucket=bucket, Key=key, Body=body,
        ContentType="application/json", ContentEncoding="gzip",
        ServerSideEncryption="AES256",
    )
    boto3.client("codebuild").start_build(
        projectName=os.environ["INGEST_BUILD_PROJECT"],
        environmentVariablesOverride=[
            {"name": "DATASET", "value": "entity-daily", "type": "PLAINTEXT"},
            {"name": "SOURCE_DATE", "value": day, "type": "PLAINTEXT"},
        ],
    )
    LOGGER.info("Daily entity export staged for %s", day)


def _start_build(dataset: str, day: str, attempt: int = 0, force: bool = False) -> None:
    if dataset not in {"opportunity-daily", "opportunity-poll", "entity-monthly"}:
        raise ValueError("Unsupported ingestion dataset")
    try:
        boto3.client("codebuild").start_build(
            projectName=os.environ["INGEST_BUILD_PROJECT"],
            environmentVariablesOverride=[
                {"name": "DATASET", "value": dataset, "type": "PLAINTEXT"},
                {"name": "SOURCE_DATE", "value": day, "type": "PLAINTEXT"},
                {"name": "FORCE_BUILD", "value": "true" if force else "false", "type": "PLAINTEXT"},
            ],
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "AccountLimitExceededException":
            raise
        if attempt >= MAX_BUILD_WAIT_ATTEMPTS:
            raise TimeoutError(f"Ingest build capacity did not free up for {dataset}") from exc
        boto3.client("sqs").send_message(
            QueueUrl=os.environ["ENTITY_EXPORT_QUEUE_URL"],
            MessageBody=json.dumps({
                "action": "build", "dataset": dataset, "day": day,
                "attempt": attempt + 1, "force": force,
            }, separators=(",", ":")),
            DelaySeconds=POLL_DELAY_SECONDS,
        )
        LOGGER.info("Queued %s for retry after another ingest build completes", dataset)


def lambda_handler(event, context):
    failures = []
    for record in event.get("Records") or []:
        try:
            message = json.loads(record["body"])
            day = str(message.get("day") or date.today().isoformat())
            date.fromisoformat(day)
            if message.get("action") == "check":
                _check(day, str(message["token"]), int(message.get("attempt") or 0))
            elif message.get("action") == "start":
                _request(day)
            elif message.get("action") == "build":
                _start_build(
                    str(message.get("dataset") or ""), day,
                    int(message.get("attempt") or 0),
                    bool(message.get("force")),
                )
            else:
                raise ValueError("Unsupported entity export action")
        except Exception:
            LOGGER.exception("Entity export message failed")
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
