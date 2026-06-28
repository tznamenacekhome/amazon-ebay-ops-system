"""Import Amazon merchant listing reports into MBOP.

Supported report types:
- GET_MERCHANT_LISTINGS_ALL_DATA
- GET_MERCHANT_LISTINGS_DATA
- GET_MERCHANT_LISTINGS_INACTIVE_DATA

This read-only Reports API integration discovers Seller Central MSKUs even when
they are out of stock and therefore absent from FBA inventory summaries. It
writes only Amazon-specific listing/SKU tables.
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

LOGGER = logging.getLogger("amazon_merchant_listings_sync")
BATCH_SIZE = 500
TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL", "DONE_NO_DATA"}
DEFAULT_REPORT_TYPE = "GET_MERCHANT_LISTINGS_ALL_DATA"
REPORT_TYPES = {
    DEFAULT_REPORT_TYPE,
    "GET_MERCHANT_LISTINGS_DATA",
    "GET_MERCHANT_LISTINGS_INACTIVE_DATA",
}


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
        run = get_or_create_report_run(
            supabase,
            report_type=args.report_type,
            marketplace_id=marketplace_id,
            report_id=args.report_id,
        )

        report_id = args.report_id
        if not report_id:
            payload = client.create_report_payload(args.report_type)
            LOGGER.info("Sanitized createReport payload: %s", payload)
            response = client.create_report(args.report_type)
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
            LOGGER.info("%s report requested: %s", args.report_type, report_id)

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
            raise AmazonSPAPIError(f"Amazon report {report_id} did not complete successfully: {status}")

        document_id = report.get("reportDocumentId")
        if not document_id:
            raise AmazonSPAPIError(f"Completed report {report_id} missing reportDocumentId")

        document = client.get_report_document(document_id)
        rows = parse_flat_file_report(download_report_document(document))
        existing_skus = fetch_existing_skus(
            supabase,
            marketplace_id,
            [first_value(row, "seller-sku", "sku", "merchant-sku", "msku") for row in rows],
        )

        captured_at = utc_now_iso()
        sku_rows: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []
        skipped = 0
        for row in rows:
            seller_sku = first_value(row, "seller-sku", "sku", "merchant-sku", "msku")
            asin = clean_asin(first_value(row, "asin1", "asin", "product-id"))
            if not seller_sku:
                skipped += 1
                continue
            existing = existing_skus.get(seller_sku) or {}
            sku_row = build_sku_row(
                row=row,
                existing=existing,
                seller_sku=seller_sku,
                asin=asin,
                marketplace_id=marketplace_id,
                report_type=args.report_type,
                captured_at=captured_at,
            )
            sku_rows.append(sku_row)
            snapshot_rows.append(
                build_snapshot_row(
                    sku_row=sku_row,
                    existing=existing,
                    row=row,
                    marketplace_id=marketplace_id,
                    report_type=args.report_type,
                    captured_at=captured_at,
                )
            )

        LOGGER.info("Merchant listing report rows read: %s", len(rows))
        LOGGER.info("Merchant listing SKU rows prepared: %s", len(sku_rows))
        LOGGER.info("Merchant listing rows skipped: %s", skipped)

        if args.dry_run:
            print_summary(rows_read=len(rows), sku_rows=sku_rows, snapshots=snapshot_rows, skipped=skipped)
            LOGGER.info("Dry run complete. No Amazon SKU/listing rows written.")
            return 0

        upserted = upsert_amazon_skus(supabase, sku_rows)
        inserted = insert_listing_snapshots(supabase, snapshot_rows)
        update_report_run(
            supabase,
            run["amazon_report_run_id"],
            {
                "rows_imported": upserted,
                "processing_status": "IMPORTED",
                "updated_at": utc_now_iso(),
            },
        )

        print_summary(rows_read=len(rows), sku_rows=sku_rows, snapshots=snapshot_rows, skipped=skipped)
        LOGGER.info("Amazon merchant listing sync complete.")
        LOGGER.info("SKU rows inserted/updated: %s", upserted)
        LOGGER.info("Listing snapshots inserted: %s", inserted)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon merchant listing sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Amazon merchant listing sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Amazon merchant listings into MBOP amazon_skus."
    )
    parser.add_argument("--report-type", choices=sorted(REPORT_TYPES), default=DEFAULT_REPORT_TYPE)
    parser.add_argument("--report-id", default=None, help="Resume/import an existing report ID.")
    parser.add_argument("--create-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable.")
    return create_client(supabase_url, supabase_key)


def get_or_create_report_run(
    supabase,
    *,
    report_type: str,
    marketplace_id: str,
    report_id: str | None,
) -> dict[str, Any]:
    if report_id:
        existing = (
            supabase.table("amazon_report_runs")
            .select("*")
            .eq("report_type", report_type)
            .eq("amazon_report_id", report_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

    response = (
        supabase.table("amazon_report_runs")
        .insert(
            {
                "report_type": report_type,
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
            if status != "DONE":
                LOGGER.warning("Amazon report %s terminal payload: %s", report_id, report)
            return report
        if time.monotonic() >= deadline:
            raise AmazonSPAPIError(f"Timed out waiting for report {report_id}; last status={status}")
        time.sleep(max(poll_seconds, 1))


def download_report_document(document: dict[str, Any]) -> str:
    url = document.get("url")
    if not url:
        raise AmazonSPAPIError(f"Report document response missing url: {document}")
    response = requests.get(url, timeout=120)
    if not response.ok:
        raise AmazonSPAPIError(
            f"Report document download failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    content = response.content
    if document.get("compressionAlgorithm") == "GZIP":
        content = gzip.decompress(content)
    return decode_report_bytes(content)


def decode_report_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            LOGGER.debug("Report document did not decode as %s", encoding)
    return content.decode("utf-8-sig", errors="replace")


def parse_flat_file_report(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    if not lines:
        return []
    delimiter = "\t" if "\t" in lines[0] else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    return [
        {normalize_header(key): clean_text(value) or "" for key, value in row.items()}
        for row in reader
    ]


def fetch_existing_skus(
    supabase,
    marketplace_id: str,
    seller_skus: list[str | None],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    unique_skus = sorted({sku for sku in seller_skus if sku})
    for chunk in chunks(unique_skus, 100):
        response = (
            supabase.table("amazon_skus")
            .select(
                "amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name,condition,"
                "fulfillment_channel,listing_status,item_status,currency,listing_price,landed_price"
            )
            .eq("marketplace_id", marketplace_id)
            .in_("seller_sku", chunk)
            .execute()
        )
        for row in response.data or []:
            seller_sku = clean_text(row.get("seller_sku"))
            if seller_sku:
                result[seller_sku] = row
    return result


def build_sku_row(
    *,
    row: dict[str, str],
    existing: dict[str, Any],
    seller_sku: str,
    asin: str | None,
    marketplace_id: str,
    report_type: str,
    captured_at: str,
) -> dict[str, Any]:
    fulfillment_channel = normalize_fulfillment_channel(
        first_value(row, "fulfillment-channel", "fulfillment-channel-code", "fulfillment")
    )
    status = first_value(row, "status", "item-status", "listing-status")
    price = to_money(first_value(row, "price", "standard-price", "item-price"))
    return {
        "seller_sku": seller_sku,
        "marketplace_id": marketplace_id,
        "asin": asin or clean_text(existing.get("asin")),
        "fnsku": clean_text(existing.get("fnsku")),
        "product_name": first_value(row, "item-name", "product-name", "title") or clean_text(existing.get("product_name")),
        "condition": first_value(row, "item-condition", "condition") or clean_text(existing.get("condition")),
        "fulfillment_channel": fulfillment_channel or clean_text(existing.get("fulfillment_channel")),
        "listing_status": normalize_status(status) or clean_text(existing.get("listing_status")),
        "item_status": normalize_status(status) or clean_text(existing.get("item_status")),
        "currency": first_value(row, "currency") or clean_text(existing.get("currency")),
        "listing_price": price if price is not None else existing.get("listing_price"),
        "landed_price": existing.get("landed_price"),
        "last_listing_sync_at": captured_at,
        "raw_listing_json": {"source": f"amazon_report_{report_type}", "row": row},
        "updated_at": captured_at,
    }


def build_snapshot_row(
    *,
    sku_row: dict[str, Any],
    existing: dict[str, Any],
    row: dict[str, str],
    marketplace_id: str,
    report_type: str,
    captured_at: str,
) -> dict[str, Any]:
    return {
        "captured_at": captured_at,
        "amazon_sku_id": existing.get("amazon_sku_id"),
        "marketplace_id": marketplace_id,
        "seller_sku": sku_row["seller_sku"],
        "asin": sku_row.get("asin"),
        "product_name": sku_row.get("product_name"),
        "condition": sku_row.get("condition"),
        "listing_status": sku_row.get("listing_status"),
        "item_status": sku_row.get("item_status"),
        "fulfillment_channel": sku_row.get("fulfillment_channel"),
        "fulfillment_availability": None,
        "issue_count": 0,
        "issue_severity": None,
        "issues_json": [],
        "raw_listing_json": {"source": f"amazon_report_{report_type}", "row": row},
        "source": f"amazon_report_{report_type}",
    }


def upsert_amazon_skus(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_skus").upsert(
            chunk,
            on_conflict="seller_sku,marketplace_id",
        ).execute()
        count += len(chunk)
    return count


def insert_listing_snapshots(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_listing_snapshots").insert(chunk).execute()
        count += len(chunk)
    return count


def print_summary(
    *,
    rows_read: int,
    sku_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    skipped: int,
) -> None:
    fba_like = sum(1 for row in sku_rows if is_fba_fulfillment(row.get("fulfillment_channel")))
    with_asin = sum(1 for row in sku_rows if row.get("asin"))
    print("Amazon merchant listings report")
    print("--------------------------------")
    print(f"Rows read: {rows_read}")
    print(f"SKU rows prepared: {len(sku_rows)}")
    print(f"Listing snapshots prepared: {len(snapshots)}")
    print(f"Rows skipped: {skipped}")
    print(f"Rows with ASIN: {with_asin}")
    print(f"FBA-like rows: {fba_like}")


def first_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = clean_text(row.get(normalize_header(name)))
        if value:
            return value
    return None


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def normalize_status(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return " ".join(text.split())


def normalize_fulfillment_channel(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.upper()
    if normalized in {"AMAZON_NA", "DEFAULT"} or "AMAZON" in normalized:
        return "AMAZON_NA" if normalized == "AMAZON_NA" else "Amazon"
    return text


def is_fba_fulfillment(value: Any) -> bool:
    text = (clean_text(value) or "").upper()
    return text in {"AMAZON", "AMAZON_NA"} or "AMAZON" in text


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


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def chunks(rows: list[Any], size: int):
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
