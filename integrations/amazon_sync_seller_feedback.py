"""Sync Amazon Seller Feedback report into MBOP.

Report type: GET_SELLER_FEEDBACK_DATA

This is a read-only Amazon Reports API integration. It imports seller feedback
rows into Amazon-specific dashboard tables and does not write to purchases,
purchase_items, receiving, FBA shipment workflow rows, or buyer/customer tables.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import logging
import os
import time
from datetime import date, datetime, timezone
from io import StringIO
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_seller_feedback_sync")
REPORT_TYPE = "GET_SELLER_FEEDBACK_DATA"
TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = AmazonSPAPIClient.from_env()
        supabase = get_supabase_client()
        run = create_report_run(supabase, client.config.marketplace_id, args.report_id)

        report_id = args.report_id
        if not report_id:
            response = client.create_report(REPORT_TYPE)
            report_id = response.get("reportId")
            if not report_id:
                raise AmazonSPAPIError(f"Create report response missing reportId: {response}")
            update_report_run(
                supabase,
                run["amazon_report_run_id"],
                {
                    "amazon_report_id": report_id,
                    "processing_status": "IN_QUEUE",
                    "raw_report_json": response,
                    "updated_at": utc_now_iso(),
                },
            )
            LOGGER.info("Amazon seller feedback report requested: %s", report_id)

        if args.create_only:
            LOGGER.info("Create-only mode complete. Report ID: %s", report_id)
            return 0

        report = wait_for_report(
            client,
            report_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        status = report.get("processingStatus")
        update_report_run(
            supabase,
            run["amazon_report_run_id"],
            {
                "processing_status": status,
                "amazon_report_id": report_id,
                "amazon_document_id": report.get("reportDocumentId"),
                "started_at": report.get("processingStartTime"),
                "completed_at": report.get("processingEndTime"),
                "data_start_time": report.get("dataStartTime"),
                "data_end_time": report.get("dataEndTime"),
                "raw_report_json": report,
                "updated_at": utc_now_iso(),
            },
        )

        if status != "DONE":
            raise AmazonSPAPIError(f"Amazon report did not complete successfully: {status}")

        document_id = report.get("reportDocumentId")
        if not document_id:
            raise AmazonSPAPIError(f"Completed report missing reportDocumentId: {report}")

        document = client.get_report_document(document_id)
        text = download_report_document(document)
        rows = parse_feedback_report(text)
        feedback_rows = [build_feedback_row(row) for row in rows]
        feedback_rows = [row for row in feedback_rows if row["rating"] is not None or row["comment"]]

        LOGGER.info("Amazon seller feedback report rows parsed: %s", len(rows))
        LOGGER.info("Amazon seller feedback rows prepared: %s", len(feedback_rows))

        if args.dry_run:
            print_summary(feedback_rows)
            LOGGER.info("Dry run complete. No feedback rows inserted.")
            return 0

        inserted = insert_feedback_items(supabase, feedback_rows)
        update_report_run(
            supabase,
            run["amazon_report_run_id"],
            {
                "rows_imported": inserted,
                "processing_status": "IMPORTED",
                "updated_at": utc_now_iso(),
            },
        )

        LOGGER.info("Amazon seller feedback sync complete. Rows inserted: %s", inserted)
        print_summary(feedback_rows)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon seller feedback sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - integration guard
        LOGGER.exception("Unexpected Amazon seller feedback sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Amazon Seller Feedback report into MBOP.")
    parser.add_argument("--report-id", default=None, help="Resume/import an existing Amazon report ID instead of creating a new one.")
    parser.add_argument("--create-only", action="store_true", help="Create a report request and exit after logging the report ID.")
    parser.add_argument("--dry-run", action="store_true", help="Download and parse the report but do not insert feedback rows.")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable.")
    return create_client(supabase_url, supabase_key)


def create_report_run(supabase, marketplace_id: str, report_id: str | None) -> dict[str, Any]:
    response = (
        supabase.table("amazon_report_runs")
        .insert(
            {
                "report_type": REPORT_TYPE,
                "marketplace_id": marketplace_id,
                "processing_status": "RESUME" if report_id else "CREATED",
                "amazon_report_id": report_id,
            }
        )
        .execute()
    )
    return (response.data or [{}])[0]


def update_report_run(supabase, report_run_id: str, updates: dict[str, Any]) -> None:
    supabase.table("amazon_report_runs").update(updates).eq(
        "amazon_report_run_id", report_run_id
    ).execute()


def wait_for_report(
    client: AmazonSPAPIClient,
    report_id: str,
    *,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds

    while True:
        report = client.get_report(report_id)
        status = report.get("processingStatus")
        LOGGER.info("Amazon report %s status=%s", report_id, status)

        if status in TERMINAL_STATUSES:
            return report
        if time.monotonic() >= deadline:
            raise AmazonSPAPIError(
                f"Timed out waiting for report {report_id}; last status={status}"
            )
        time.sleep(max(poll_seconds, 1))


def download_report_document(document: dict[str, Any]) -> str:
    url = document.get("url")
    if not url:
        raise AmazonSPAPIError(f"Report document response missing url: {document}")

    response = requests.get(url, timeout=120)
    if not response.ok:
        raise AmazonSPAPIError(
            f"Report document download failed with HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    content = response.content
    if document.get("compressionAlgorithm") == "GZIP":
        content = gzip.decompress(content)
    return content.decode("utf-8-sig")


def parse_feedback_report(text: str) -> list[dict[str, str]]:
    delimiter = "\t" if "\t" in text.splitlines()[0] else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    return [{normalize_header(key): value for key, value in row.items()} for row in reader]


def build_feedback_row(row: dict[str, str]) -> dict[str, Any]:
    feedback_date = parse_date(
        get_value(row, "date", "feedback-date", "feedback_date", "rating-date", "posted-date")
    )
    rating = to_int(get_value(row, "rating", "feedback-rating", "feedback_rating", "stars"))
    order_id = clean_text(get_value(row, "order-id", "order_id", "amazon-order-id", "amazon_order_id"))
    comment = clean_text(get_value(row, "comments", "comment", "feedback", "buyer-feedback"))
    return {
        "feedback_date": feedback_date,
        "rating": rating,
        "amazon_order_id": order_id,
        "comment": comment,
        "source": f"amazon_spapi_report_{REPORT_TYPE}",
        "raw_json": row,
    }


def insert_feedback_items(supabase, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for row in rows:
        if feedback_exists(supabase, row):
            continue
        supabase.table("amazon_seller_feedback_items").insert(row).execute()
        inserted += 1
    return inserted


def feedback_exists(supabase, row: dict[str, Any]) -> bool:
    query = supabase.table("amazon_seller_feedback_items").select("feedback_id").limit(1)
    for column in ("feedback_date", "rating", "amazon_order_id", "comment"):
        value = row.get(column)
        if value is None:
            query = query.is_(column, "null")
        else:
            query = query.eq(column, value)
    return bool(query.execute().data or [])


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("Amazon seller feedback report")
    print("-----------------------------")
    print(f"Rows prepared: {len(rows)}")
    for row in sorted(rows, key=lambda item: str(item.get("feedback_date") or ""), reverse=True)[:3]:
        print(
            f"- {row.get('feedback_date') or '--'} | "
            f"{row.get('rating') or '--'} stars | "
            f"{row.get('amazon_order_id') or '--'} | "
            f"{row.get('comment') or '--'}"
        )


def get_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        normalized = normalize_header(key)
        if normalized in row and clean_text(row[normalized]):
            return row[normalized]
    return ""


def normalize_header(value: str | None) -> str:
    return clean_text(value).lower().replace(" ", "-").replace("_", "-")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: str) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_date(value: str) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
