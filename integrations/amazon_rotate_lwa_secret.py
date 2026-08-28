"""Rotate MBOP's Amazon SP-API LWA client secret programmatically.

Prerequisite: in Amazon Developer Console, register the SQS queue in the
application's "Application Client New Secret" notification preference.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_lwa_rotation")
DEFAULT_QUEUE_NAME = "mbop-amazon-lwa-rotation"
DEFAULT_SECRET_ID = "/mbop/prod/amazon-spapi/client-secret"


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv(".env.local")
    load_dotenv()

    try:
        if not args.confirm:
            raise AmazonSPAPIError(
                "Rotation creates a new client secret and starts the seven-day old-secret overlap. "
                "Rerun with --confirm after the SQS queue is registered in Amazon Developer Console."
            )

        sqs = boto3_session(args).client("sqs", region_name=args.region)
        queue_url = queue_url_for_name(sqs, args.queue_name)
        client = AmazonSPAPIClient.from_env()

        LOGGER.info("Calling Amazon Application Management API rotation operation.")
        client.rotate_application_client_secret()
        LOGGER.info("Rotation accepted. Polling SQS queue for the new client secret.")

        message = wait_for_rotation_message(
            sqs,
            queue_url,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        new_secret = extract_client_secret(message)
        if not new_secret:
            raise AmazonSPAPIError("Rotation SQS message did not contain a client secret.")

        if not args.skip_local:
            update_env_file(Path(args.env_file), "AMAZON_SP_API_CLIENT_SECRET", new_secret)
            LOGGER.info("Updated %s.", args.env_file)

        if not args.skip_aws:
            update_aws_secret(args, new_secret)
            LOGGER.info("Updated AWS Secrets Manager secret %s.", args.secret_id)

        if args.delete_message:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
            LOGGER.info("Deleted consumed rotation message from SQS.")

        if not args.skip_smoke_test:
            run_smoke_test()

        LOGGER.info("Amazon LWA client secret rotation complete.")
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon LWA rotation failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - script guard
        LOGGER.exception("Unexpected Amazon LWA rotation failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate Amazon SP-API LWA client secret.")
    parser.add_argument("--profile", default="mbop-admin")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--queue-name", default=DEFAULT_QUEUE_NAME)
    parser.add_argument("--secret-id", default=DEFAULT_SECRET_ID)
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument("--skip-aws", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--delete-message", action="store_true", default=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Confirms the SQS queue is registered in Amazon Developer Console.",
    )
    return parser.parse_args()


def boto3_session(args: argparse.Namespace) -> boto3.Session:
    return boto3.Session(profile_name=args.profile, region_name=args.region)


def queue_url_for_name(sqs, queue_name: str) -> str:
    try:
        return sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    except ClientError as error:
        raise AmazonSPAPIError(f"SQS queue not found: {queue_name}") from error


def wait_for_rotation_message(
    sqs,
    queue_url: str,
    *,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=min(max(poll_seconds, 1), 20),
        )
        messages = response.get("Messages") or []
        for message in messages:
            if extract_client_secret(message):
                return message
            LOGGER.warning("Ignoring SQS message without a client secret payload.")
        time.sleep(1)
    raise AmazonSPAPIError("Timed out waiting for Amazon rotation SQS message.")


def extract_client_secret(message: dict[str, Any]) -> str | None:
    body = parse_json(message.get("Body"))
    payload = body.get("payload") if isinstance(body, dict) else None
    candidates = [body, payload]
    if isinstance(payload, dict):
        candidates.extend(value for value in payload.values() if isinstance(value, dict))

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in (
            "clientSecret",
            "client_secret",
            "applicationClientSecret",
            "newClientSecret",
            "new_client_secret",
        ):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def parse_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def update_env_file(path: Path, name: str, value: str) -> None:
    line = f"{name}={value}"
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    replaced = False
    next_lines = []
    for current in lines:
        if current.startswith(f"{name}="):
            next_lines.append(line)
            replaced = True
        else:
            next_lines.append(current)
    if not replaced:
        next_lines.append(line)
    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def update_aws_secret(args: argparse.Namespace, value: str) -> None:
    client = boto3_session(args).client("secretsmanager", region_name=args.region)
    client.put_secret_value(SecretId=args.secret_id, SecretString=value)


def run_smoke_test() -> None:
    result = subprocess.run(
        [sys.executable, "integrations/amazon_test_connection.py", "--auth-only"],
        check=False,
    )
    if result.returncode != 0:
        raise AmazonSPAPIError("Amazon auth smoke test failed with the rotated secret.")


if __name__ == "__main__":
    sys.exit(main())
