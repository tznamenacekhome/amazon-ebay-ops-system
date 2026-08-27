"""Trace Amazon FBA Inventory Ledger movements for a SKU/FNSKU/ASIN.

This diagnostic script requests Amazon's read-only Inventory Ledger detailed
view and prints matching movement rows. It does not write to Supabase.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import logging
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import requests
from dotenv import load_dotenv

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_inventory_ledger_trace")
REPORT_TYPE = "GET_LEDGER_DETAIL_VIEW_DATA"
TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv()

    try:
        client = AmazonSPAPIClient.from_env()
        report_options = {
            key: value
            for key, value in {
                "eventType": clean_option(args.event_type),
                "FNSKU": args.fnsku,
            }.items()
            if clean_option(value) is not None
        }
        response = client.create_report(
            REPORT_TYPE,
            report_options=report_options,
            data_start_time=args.start,
            data_end_time=args.end,
        )
        report_id = response.get("reportId")
        if not report_id:
            raise AmazonSPAPIError(f"Create report response missing reportId: {response}")
        LOGGER.info("Amazon inventory ledger report requested: %s", report_id)

        report = wait_for_report(
            client,
            report_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        if report.get("processingStatus") != "DONE":
            raise AmazonSPAPIError(
                f"Amazon report did not complete successfully: {report.get('processingStatus')}"
            )

        document_id = report.get("reportDocumentId")
        if not document_id:
            raise AmazonSPAPIError(f"Completed report missing reportDocumentId: {report}")

        rows = parse_report(download_report_document(client.get_report_document(document_id)))
        matches = filter_rows(
            rows,
            asin=args.asin,
            seller_sku=args.seller_sku,
            fnsku=args.fnsku,
        )
        print_summary(rows, matches)
        print_rows(matches, limit=args.limit)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon inventory ledger trace failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - diagnostic guard
        LOGGER.exception("Unexpected Amazon inventory ledger trace failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trace Amazon FBA Inventory Ledger movements.")
    parser.add_argument("--asin", default=None)
    parser.add_argument("--seller-sku", default=None)
    parser.add_argument("--fnsku", default=None)
    parser.add_argument("--start", required=True, help="ISO-8601 dataStartTime")
    parser.add_argument("--end", required=True, help="ISO-8601 dataEndTime")
    parser.add_argument(
        "--event-type",
        default="",
        help="Inventory Ledger event type. Empty string returns all events.",
    )
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--limit", type=int, default=100)
    return parser.parse_args()


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
        time.sleep(max(1, poll_seconds))


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


def parse_report(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text), delimiter="\t")
    return [
        {normalize_header(key): value for key, value in row.items()}
        for row in reader
    ]


def filter_rows(
    rows: list[dict[str, str]],
    *,
    asin: str | None,
    seller_sku: str | None,
    fnsku: str | None,
) -> list[dict[str, str]]:
    asin = clean_id(asin)
    seller_sku = clean_id(seller_sku)
    fnsku = clean_id(fnsku)
    matches: list[dict[str, str]] = []
    for row in rows:
        row_asin = clean_id(get_value(row, "asin"))
        row_sku = clean_id(get_value(row, "msku", "sku", "seller-sku", "seller sku"))
        row_fnsku = clean_id(get_value(row, "fnsku", "fulfillment-network-sku"))
        if asin and row_asin == asin:
            matches.append(row)
        elif seller_sku and row_sku == seller_sku:
            matches.append(row)
        elif fnsku and row_fnsku == fnsku:
            matches.append(row)
    return matches


def print_summary(rows: list[dict[str, str]], matches: list[dict[str, str]]) -> None:
    print("Amazon Inventory Ledger Trace")
    print("-----------------------------")
    print(f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    print(f"Rows returned: {len(rows)}")
    print(f"Matching rows: {len(matches)}")
    if rows:
        print(f"Columns: {', '.join(rows[0].keys())}")


def print_rows(rows: list[dict[str, str]], *, limit: int) -> None:
    for index, row in enumerate(rows[:limit], start=1):
        print("")
        print(f"Row {index}")
        for key, value in row.items():
            if value not in (None, ""):
                print(f"  {key}: {value}")
    if len(rows) > limit:
        print(f"\n... {len(rows) - limit} more matching rows omitted")


def get_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        normalized = normalize_header(name)
        if normalized in row:
            return row[normalized]
    return None


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def clean_id(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def clean_option(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


if __name__ == "__main__":
    sys.exit(main())
