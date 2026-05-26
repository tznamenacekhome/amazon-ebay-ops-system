"""Sync Amazon FBA Inventory Planning report into MBOP.

Report type: GET_FBA_INVENTORY_PLANNING_DATA

This is a read-only Amazon Reports API integration. It requests Amazon's native
aged-inventory / inventory-health report, stores report-run audit metadata, and
inserts point-in-time planning snapshot rows. It does not write to purchases,
purchase_items, receiving, FBA shipment workflow rows, or Amazon prices.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import logging
import os
import time
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_inventory_planning_sync")
BATCH_SIZE = 500
REPORT_TYPE = "GET_FBA_INVENTORY_PLANNING_DATA"
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
        marketplace_id = client.config.marketplace_id
        run = create_report_run(supabase, marketplace_id, args.report_id)

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
            LOGGER.info("Amazon inventory planning report requested: %s", report_id)

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
        rows = parse_planning_report(text)
        snapshot_rows = [
            build_snapshot_row(
                row=row,
                marketplace_id=marketplace_id,
                report_run_id=run["amazon_report_run_id"],
            )
            for row in rows
            if clean_text(get_value(row, "sku"))
        ]

        LOGGER.info("Amazon inventory planning report rows parsed: %s", len(rows))
        LOGGER.info("Amazon inventory planning snapshot rows prepared: %s", len(snapshot_rows))

        if args.dry_run:
            print_summary(snapshot_rows)
            LOGGER.info("Dry run complete. No planning snapshots inserted.")
            return 0

        inserted = insert_snapshots(supabase, snapshot_rows)
        update_report_run(
            supabase,
            run["amazon_report_run_id"],
            {
                "rows_imported": inserted,
                "processing_status": "IMPORTED",
                "updated_at": utc_now_iso(),
            },
        )

        LOGGER.info("Amazon inventory planning sync complete. Rows inserted: %s", inserted)
        print_summary(snapshot_rows)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon inventory planning sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - integration guard
        LOGGER.exception("Unexpected Amazon inventory planning sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Amazon FBA Inventory Planning report into MBOP."
    )
    parser.add_argument(
        "--report-id",
        default=None,
        help="Resume/import an existing Amazon report ID instead of creating a new one.",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Create a report request and exit after logging the report ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse the report but do not insert planning snapshot rows.",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )
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


def parse_planning_report(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text), delimiter="\t")
    return [
        {normalize_header(key): value for key, value in row.items()}
        for row in reader
    ]


def build_snapshot_row(
    *,
    row: dict[str, str],
    marketplace_id: str,
    report_run_id: str,
) -> dict[str, Any]:
    return {
        "amazon_report_run_id": report_run_id,
        "snapshot_date": parse_date(get_value(row, "snapshot-date", "snapshot_date")),
        "marketplace_id": marketplace_id,
        "seller_sku": clean_text(get_value(row, "sku")) or "",
        "fnsku": clean_text(get_value(row, "fnsku")),
        "asin": clean_asin(get_value(row, "asin")),
        "product_name": clean_text(get_value(row, "product-name", "product_name")),
        "condition": clean_text(get_value(row, "condition")),
        "available_quantity": to_int(get_value(row, "available")),
        "pending_removal_quantity": to_int(
            get_value(row, "pending-removal-quantity", "pending_removal_quantity")
        ),
        "inv_age_0_to_90_days": to_int(
            get_value(row, "inv-age-0-to-90-days", "inv_age_0_to_90_days")
        ),
        "inv_age_91_to_180_days": to_int(
            get_value(row, "inv-age-91-to-180-days", "inv_age_91_to_180_days")
        ),
        "inv_age_181_to_270_days": to_int(
            get_value(row, "inv-age-181-to-270-days", "inv_age_181_to_270_days")
        ),
        "inv_age_271_to_365_days": to_int(
            get_value(row, "inv-age-271-to-365-days", "inv_age_271_to_365_days")
        ),
        "inv_age_365_plus_days": to_int(
            get_value(row, "inv-age-365-plus-days", "inv_age_365_plus_days")
        ),
        "currency": clean_text(get_value(row, "currency")),
        "estimated_excess_quantity": to_int(
            get_value(row, "estimated-excess-quantity", "estimated_excess_quantity")
        ),
        "estimated_storage_cost_next_month": to_money(
            get_value(
                row,
                "estimated-storage-cost-next-month",
                "estimated_storage_cost_next_month",
            )
        ),
        "estimated_ltsf_next_charge": to_money(
            get_value(row, "estimated-ltsf-next-charge", "estimated_ltsf_next_charge")
        ),
        "recommended_action": clean_text(
            get_value(row, "recommended-action", "recommended_action")
        ),
        "healthy_inventory_level": to_int(
            get_value(row, "healthy-inventory-level", "healthy_inventory_level")
        ),
        "sales_shipped_last_7_days": to_int(
            get_value(row, "sales-shipped-last-7-days", "sales_shipped_last_7_days")
        ),
        "sales_shipped_last_30_days": to_int(
            get_value(row, "sales-shipped-last-30-days", "sales_shipped_last_30_days")
        ),
        "sales_shipped_last_60_days": to_int(
            get_value(row, "sales-shipped-last-60-days", "sales_shipped_last_60_days")
        ),
        "sales_shipped_last_90_days": to_int(
            get_value(row, "sales-shipped-last-90-days", "sales_shipped_last_90_days")
        ),
        "alert": clean_text(get_value(row, "alert")),
        "raw_planning_json": row,
        "source": "amazon_spapi_report_GET_FBA_INVENTORY_PLANNING_DATA",
    }


def insert_snapshots(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_inventory_planning_snapshots").insert(chunk).execute()
        count += len(chunk)
    return count


def print_summary(rows: list[dict[str, Any]]) -> None:
    aged_91_plus = sum(
        to_int(row.get("inv_age_91_to_180_days"))
        + to_int(row.get("inv_age_181_to_270_days"))
        + to_int(row.get("inv_age_271_to_365_days"))
        + to_int(row.get("inv_age_365_plus_days"))
        for row in rows
    )
    print("Amazon inventory planning report")
    print("--------------------------------")
    print(f"Rows prepared: {len(rows)}")
    print(f"Available units: {sum(to_int(row.get('available_quantity')) for row in rows)}")
    print(f"91+ day units: {aged_91_plus}")


def get_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        normalized = normalize_header(name)
        if normalized in row:
            return row[normalized]
    return None


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def parse_date(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text[:10] if len(text) >= 10 else None


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.upper()
    return text if len(text) == 10 else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
