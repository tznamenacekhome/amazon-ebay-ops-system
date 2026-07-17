"""Import Amazon sales order history from the SP-API all-orders report.

Report type: GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL

This importer is for historical order/item coverage. It requests Amazon's
non-PII order tracking report in date chunks, ignores location columns, and
upserts only Amazon-specific sales rows. It must not write to purchases,
purchase_items, receiving, or sourcing business-rule tables.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import logging
import os
import time
import uuid
from io import StringIO
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_sales_order_report_sync")
BATCH_SIZE = 500
MAX_CHUNK_DAYS = 30
REPORT_TYPE = "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"
TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()
    load_dotenv(".env.local")

    try:
        client = AmazonSPAPIClient.from_env()
        supabase = get_supabase_client()
        import_batch_id = str(uuid.uuid4())
        total_orders = 0
        total_items = 0

        for start, end in date_chunks(args.start_date, args.end_date, args.chunk_days):
            LOGGER.info("Importing Amazon order report chunk %s to %s", start, end)
            run = create_report_run(supabase, client.config.marketplace_id, start, end)
            response = client.create_report(
                REPORT_TYPE,
                data_start_time=to_iso_z(start),
                data_end_time=to_iso_z(end),
            )
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

            if args.create_only:
                LOGGER.info("Created report %s for %s to %s", report_id, start, end)
                continue

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
                raise AmazonSPAPIError(f"Amazon order report did not complete: {status}")

            document_id = report.get("reportDocumentId")
            if not document_id:
                raise AmazonSPAPIError(f"Completed report missing reportDocumentId: {report}")
            rows = parse_flat_file_report(
                download_report_document(client.get_report_document(document_id))
            )
            order_rows = build_order_rows(rows, import_batch_id)
            item_rows = build_item_rows(rows)
            LOGGER.info(
                "Prepared order report rows for %s to %s: orders=%s items=%s",
                start,
                end,
                len(order_rows),
                len(item_rows),
            )

            if not args.dry_run:
                upsert_rows(supabase, "amazon_sales_orders", order_rows, "amazon_order_id")
                upsert_rows(
                    supabase,
                    "amazon_sales_order_items",
                    item_rows,
                    "amazon_order_item_id",
                )
                update_report_run(
                    supabase,
                    run["amazon_report_run_id"],
                    {
                        "processing_status": "IMPORTED",
                        "rows_imported": len(item_rows),
                        "updated_at": utc_now_iso(),
                    },
                )
            total_orders += len(order_rows)
            total_items += len(item_rows)

            if args.chunk_delay_seconds > 0:
                time.sleep(args.chunk_delay_seconds)

        print("Amazon sales order report import")
        print("--------------------------------")
        print(f"Order rows prepared: {total_orders}")
        print(f"Item rows prepared: {total_items}")
        print(f"Mode: {'dry run' if args.dry_run else 'write'}")
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon sales order report sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001
        LOGGER.exception("Unexpected Amazon sales order report sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Amazon all-orders report rows into MBOP sales tables."
    )
    parser.add_argument("--start-date", required=True, help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Inclusive YYYY-MM-DD.")
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--chunk-delay-seconds", type=int, default=10)
    parser.add_argument("--create-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    args = parser.parse_args()
    if args.chunk_days < 1 or args.chunk_days > MAX_CHUNK_DAYS:
        parser.error(f"--chunk-days must be between 1 and {MAX_CHUNK_DAYS}")
    if args.dry_run and args.apply:
        parser.error("Use either --dry-run or --apply, not both.")
    if not args.apply and not args.dry_run and not args.create_only:
        args.dry_run = True
    return args


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def create_report_run(
    supabase,
    marketplace_id: str,
    start: dt.datetime,
    end: dt.datetime,
) -> dict[str, Any]:
    response = (
        supabase.table("amazon_report_runs")
        .insert(
            {
                "report_type": REPORT_TYPE,
                "marketplace_id": marketplace_id,
                "processing_status": "CREATED",
                "data_start_time": to_iso_z(start),
                "data_end_time": to_iso_z(end),
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


def build_order_rows(rows: list[dict[str, str]], import_batch_id: str) -> list[dict[str, Any]]:
    by_order_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        order_id = clean_text(get_value(row, "amazon-order-id"))
        if not order_id:
            continue
        by_order_id.setdefault(
            order_id,
            {
                "amazon_order_id": order_id,
                "purchase_date": parse_datetime(get_value(row, "purchase-date")),
                "last_update_date": parse_datetime(get_value(row, "last-updated-date")),
                "order_status": clean_text(get_value(row, "order-status")),
                "fulfillment_channel": clean_text(get_value(row, "fulfillment-channel")),
                "sales_channel": clean_text(get_value(row, "sales-channel")),
                "is_business_order": to_bool(get_value(row, "is-business-order")),
                "shipment_service_level_category": clean_text(
                    get_value(row, "ship-service-level")
                ),
                "raw_order_json": report_order_payload(row),
                "import_batch_id": import_batch_id,
                "source": f"amazon_spapi_report_{REPORT_TYPE}",
                "updated_at": utc_now_iso(),
            },
        )
    return list(by_order_id.values())


def build_item_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    item_rows: list[dict[str, Any]] = []
    for row in rows:
        order_item_id = clean_text(get_value(row, "order-item-id"))
        order_id = clean_text(get_value(row, "amazon-order-id"))
        if not order_item_id or not order_id:
            continue
        item_rows.append(
            {
                "amazon_order_item_id": order_item_id,
                "amazon_order_id": order_id,
                "asin": clean_asin(get_value(row, "asin")),
                "seller_sku": clean_text(get_value(row, "sku")),
                "title": clean_text(get_value(row, "product-name")),
                "quantity_ordered": to_int(get_value(row, "quantity")),
                "quantity_shipped": to_int(get_value(row, "quantity")),
                "item_price_amount": to_money(get_value(row, "item-price")),
                "item_price_currency": clean_text(get_value(row, "currency")),
                "item_tax_amount": to_money(get_value(row, "item-tax")),
                "shipping_price_amount": to_money(get_value(row, "shipping-price")),
                "shipping_tax_amount": to_money(get_value(row, "shipping-tax")),
                "gift_wrap_price_amount": to_money(get_value(row, "gift-wrap-price")),
                "gift_wrap_tax_amount": to_money(get_value(row, "gift-wrap-tax")),
                "item_promotion_discount_amount": to_money(
                    get_value(row, "item-promotion-discount")
                ),
                "ship_promotion_discount_amount": to_money(
                    get_value(row, "ship-promotion-discount")
                ),
                "raw_order_item_json": report_item_payload(row),
                "updated_at": utc_now_iso(),
            }
        )
    return item_rows


def report_order_payload(row: dict[str, str]) -> dict[str, Any]:
    return {
        key: get_value(row, key)
        for key in (
            "amazon-order-id",
            "purchase-date",
            "last-updated-date",
            "order-status",
            "fulfillment-channel",
            "sales-channel",
            "order-channel",
            "ship-service-level",
            "is-business-order",
        )
    }


def report_item_payload(row: dict[str, str]) -> dict[str, Any]:
    return {
        key: get_value(row, key)
        for key in (
            "order-item-id",
            "product-name",
            "sku",
            "asin",
            "item-status",
            "quantity",
            "currency",
            "item-price",
            "item-tax",
            "shipping-price",
            "shipping-tax",
            "gift-wrap-price",
            "gift-wrap-tax",
            "item-promotion-discount",
            "ship-promotion-discount",
            "price-designation",
        )
    }


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    deduped: dict[Any, dict[str, Any]] = {}
    for row in rows:
        key = row.get(on_conflict)
        if key:
            deduped[key] = row
    usable_rows = list(deduped.values())
    for chunk in chunks(usable_rows, BATCH_SIZE):
        supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()


def date_chunks(start_date: str, end_date: str, chunk_days: int):
    start = parse_day(start_date)
    inclusive_end = parse_day(end_date)
    cursor = start
    exclusive_end = inclusive_end + dt.timedelta(days=1)
    while cursor < exclusive_end:
        next_cursor = min(cursor + dt.timedelta(days=chunk_days), exclusive_end)
        yield cursor, next_cursor
        cursor = next_cursor


def get_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        normalized = normalize_header(name)
        if normalized in row:
            return row[normalized]
    return None


def normalize_header(value: str | None) -> str:
    return (value or "").strip().lower().replace("_", "-")


def parse_day(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)


def parse_datetime(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    parsed = text.replace(" UTC", "Z").replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(parsed).astimezone(dt.timezone.utc).isoformat()
    except ValueError:
        return text


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


def to_bool(value: Any) -> bool | None:
    text = clean_text(value)
    if text is None:
        return None
    return text.lower() in {"true", "1", "yes", "y"}


def to_int(value: Any) -> int:
    text = clean_text(value)
    if not text:
        return 0
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return 0


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return round(float(text.replace("$", "").replace(",", "")), 2)
    except ValueError:
        return None


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def to_iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
