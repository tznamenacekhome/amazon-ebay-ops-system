"""Import Amazon FBA return recovery reports into MBOP.

Supported report types:
- GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA
- GET_FBA_REIMBURSEMENTS_DATA
- GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA
- GET_FBA_FULFILLMENT_REMOVAL_SHIPMENT_DETAIL_DATA

This is a read-only Amazon Reports API integration. It stores report evidence in
Amazon-specific return recovery row tables only. It does not create recovery
cases yet, infer reimbursement/customer-return matches, or write to purchases,
purchase_items, receiving, Order Problems, FBA shipment prep, dashboard, or UI
tables.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_return_recovery_report_sync")
BATCH_SIZE = 500
TERMINAL_STATUSES = {"DONE", "CANCELLED", "FATAL"}

CUSTOMER_RETURNS = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"
REIMBURSEMENTS = "GET_FBA_REIMBURSEMENTS_DATA"
REMOVAL_ORDERS = "GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA"
REMOVAL_SHIPMENTS = "GET_FBA_FULFILLMENT_REMOVAL_SHIPMENT_DETAIL_DATA"


@dataclass(frozen=True)
class ReportSpec:
    report_type: str
    table_name: str
    row_builder: Callable[[dict[str, str], int, str, str], dict[str, Any] | None]


REPORT_SPECS: dict[str, ReportSpec] = {
    CUSTOMER_RETURNS: ReportSpec(
        report_type=CUSTOMER_RETURNS,
        table_name="amazon_fba_customer_return_rows",
        row_builder=lambda row, row_number, marketplace_id, report_run_id: build_customer_return_row(
            row,
            row_number=row_number,
            marketplace_id=marketplace_id,
            report_run_id=report_run_id,
        ),
    ),
    REIMBURSEMENTS: ReportSpec(
        report_type=REIMBURSEMENTS,
        table_name="amazon_fba_reimbursement_rows",
        row_builder=lambda row, row_number, marketplace_id, report_run_id: build_reimbursement_row(
            row,
            row_number=row_number,
            marketplace_id=marketplace_id,
            report_run_id=report_run_id,
        ),
    ),
    REMOVAL_ORDERS: ReportSpec(
        report_type=REMOVAL_ORDERS,
        table_name="amazon_fba_removal_order_detail_rows",
        row_builder=lambda row, row_number, marketplace_id, report_run_id: build_removal_order_row(
            row,
            row_number=row_number,
            marketplace_id=marketplace_id,
            report_run_id=report_run_id,
        ),
    ),
    REMOVAL_SHIPMENTS: ReportSpec(
        report_type=REMOVAL_SHIPMENTS,
        table_name="amazon_fba_removal_shipment_detail_rows",
        row_builder=lambda row, row_number, marketplace_id, report_run_id: build_removal_shipment_row(
            row,
            row_number=row_number,
            marketplace_id=marketplace_id,
            report_run_id=report_run_id,
        ),
    ),
}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("amazon_spapi").setLevel(logging.WARNING)
    load_dotenv()

    try:
        selected_report_types = select_report_types(args)
        data_start_time, data_end_time = report_window(args)
        client = AmazonSPAPIClient.from_env()
        supabase = get_supabase_client()

        exit_code = 0
        for report_type in selected_report_types:
            spec = REPORT_SPECS[report_type]
            try:
                summary = sync_report_type(
                    client=client,
                    supabase=supabase,
                    spec=spec,
                    report_id=args.report_id,
                    create_only=args.create_only,
                    dry_run=args.dry_run,
                    data_start_time=data_start_time,
                    data_end_time=data_end_time,
                    poll_seconds=args.poll_seconds,
                    timeout_seconds=args.timeout_seconds,
                )
            except AmazonSPAPIError as error:
                LOGGER.error("%s failed safely: %s", report_type, error)
                summary = error_summary(spec, str(error), report_id=args.report_id)
            print_summary(summary)
            if summary["errors"] > 0:
                exit_code = 1

        return exit_code
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon return recovery report sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - integration guard
        LOGGER.exception("Unexpected Amazon return recovery report sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Amazon FBA return recovery reports into MBOP."
    )
    parser.add_argument(
        "--report-type",
        choices=sorted(REPORT_SPECS),
        help="One Amazon report type to request/import. Omit only when using --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Request/import all supported Amazon Return Recovery reports.",
    )
    parser.add_argument(
        "--report-id",
        default=None,
        help="Resume/import an existing Amazon report ID. Requires --report-type.",
    )
    parser.add_argument(
        "--create-only",
        action="store_true",
        help="Create report request(s) and exit after logging report IDs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and parse report rows but do not write row tables.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Report data start date/time. Accepts YYYY-MM-DD or an ISO timestamp.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Report data end date/time. Accepts YYYY-MM-DD or an ISO timestamp. Defaults to now.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Default report window when --start-date is omitted. Default: 30.",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def select_report_types(args: argparse.Namespace) -> list[str]:
    if args.all and args.report_id:
        raise AmazonSPAPIError("--report-id can only be used with one --report-type")
    if args.all:
        return sorted(REPORT_SPECS)
    if args.report_type:
        return [args.report_type]
    raise AmazonSPAPIError("Choose --report-type <type> or --all")


def report_window(args: argparse.Namespace) -> tuple[str, str]:
    if args.report_id:
        return "", ""

    end_time = parse_report_time(args.end_date) if args.end_date else datetime.now(timezone.utc)
    if args.start_date:
        start_time = parse_report_time(args.start_date)
    else:
        start_time = end_time - timedelta(days=max(args.lookback_days, 1))

    if start_time >= end_time:
        raise AmazonSPAPIError("Report --start-date must be before --end-date")

    return format_report_time(start_time), format_report_time(end_time)


def parse_report_time(value: str) -> datetime:
    text = value.strip()
    if len(text) == 10:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_report_time(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sync_report_type(
    *,
    client: AmazonSPAPIClient,
    supabase,
    spec: ReportSpec,
    report_id: str | None,
    create_only: bool,
    dry_run: bool,
    data_start_time: str,
    data_end_time: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    marketplace_id = client.config.marketplace_id
    run = get_or_create_report_run(
        supabase,
        report_type=spec.report_type,
        marketplace_id=marketplace_id,
        report_id=report_id,
    )

    if not report_id:
        response = client.create_report(
            spec.report_type,
            data_start_time=data_start_time,
            data_end_time=data_end_time,
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
                "data_start_time": data_start_time,
                "data_end_time": data_end_time,
                "raw_report_json": response,
                "updated_at": utc_now_iso(),
            },
        )
        run["amazon_report_id"] = report_id
        LOGGER.info("%s report requested: %s", spec.report_type, report_id)

    if create_only:
        LOGGER.info("Create-only mode complete for %s. Report ID: %s", spec.report_type, report_id)
        return empty_summary(spec, report_id, created_only=True)

    report = wait_for_report(
        client,
        report_id,
        poll_seconds=poll_seconds,
        timeout_seconds=timeout_seconds,
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
        return error_summary(
            spec,
            f"Amazon report {report_id} did not complete successfully: {status}",
            report_id=report_id,
        )

    document_id = report.get("reportDocumentId")
    if not document_id:
        return error_summary(
            spec,
            f"Completed report {report_id} missing reportDocumentId",
            report_id=report_id,
        )

    document = client.get_report_document(document_id)
    text = download_report_document(document)
    rows = parse_flat_file_report(text)
    normalized_rows, skipped, errors = normalize_rows(
        rows=rows,
        spec=spec,
        marketplace_id=marketplace_id,
        report_run_id=run["amazon_report_run_id"],
    )

    inserted_or_updated = 0
    if not dry_run:
        inserted_or_updated = upsert_rows(supabase, spec.table_name, normalized_rows)
        update_report_run(
            supabase,
            run["amazon_report_run_id"],
            {
                "rows_imported": inserted_or_updated,
                "processing_status": "IMPORTED",
                "updated_at": utc_now_iso(),
            },
        )

    return {
        "report_type": spec.report_type,
        "report_id": report_id,
        "table_name": spec.table_name,
        "rows_read": len(rows),
        "rows_prepared": len(normalized_rows),
        "rows_inserted_or_updated": inserted_or_updated,
        "rows_skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "created_only": False,
    }


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )
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


def normalize_rows(
    *,
    rows: list[dict[str, str]],
    spec: ReportSpec,
    marketplace_id: str,
    report_run_id: str,
) -> tuple[list[dict[str, Any]], int, int]:
    normalized_rows: list[dict[str, Any]] = []
    skipped = 0
    errors = 0

    for index, row in enumerate(rows, start=2):
        try:
            normalized = spec.row_builder(row, index, marketplace_id, report_run_id)
            if normalized is None:
                skipped += 1
                continue
            normalized_rows.append(normalized)
        except Exception as error:  # noqa: BLE001 - row-level guard
            errors += 1
            LOGGER.warning(
                "Skipping %s row %s due to parse error: %s",
                spec.report_type,
                index,
                error,
            )

    return normalized_rows, skipped, errors


def build_customer_return_row(
    row: dict[str, str],
    *,
    row_number: int,
    marketplace_id: str,
    report_run_id: str,
) -> dict[str, Any]:
    seller_sku = first_value(row, "seller-sku", "sku", "merchant-sku", "msku")
    return {
        "amazon_report_run_id": report_run_id,
        "source_row_number": row_number,
        "marketplace_id": marketplace_id,
        "amazon_order_id": first_value(row, "amazon-order-id", "order-id"),
        "merchant_order_id": first_value(row, "merchant-order-id", "merchant-order-number"),
        "return_date": parse_date(first_value(row, "return-date", "returned-date", "date")),
        "seller_sku": seller_sku,
        "sku": first_value(row, "sku", "merchant-sku", "seller-sku", "msku"),
        "fnsku": first_value(row, "fnsku", "fba-fnsku"),
        "asin": clean_asin(first_value(row, "asin")),
        "product_name": first_value(row, "product-name", "product-name/title", "title"),
        "title": first_value(row, "title", "product-name", "product-name/title"),
        "quantity": to_int_or_none(first_value(row, "quantity", "qty")),
        "fulfillment_center_id": first_value(row, "fulfillment-center-id", "fc", "fc-id"),
        "detailed_disposition": first_value(
            row,
            "detailed-disposition",
            "disposition",
            "detailed-disposition-code",
        ),
        "reason": first_value(row, "reason", "return-reason", "customer-return-reason"),
        "status": first_value(row, "status", "return-status"),
        "license_plate_number": first_value(
            row,
            "license-plate-number",
            "lpn",
            "lpn-number",
            "license-plate",
        ),
        "customer_comments": first_value(
            row,
            "customer-comments",
            "customer-comment",
            "comments",
            "buyer-comments",
        ),
        "raw_row_json": row,
        "updated_at": utc_now_iso(),
    }


def build_reimbursement_row(
    row: dict[str, str],
    *,
    row_number: int,
    marketplace_id: str,
    report_run_id: str,
) -> dict[str, Any]:
    amount_total = first_money(
        row,
        "amount-total",
        "amount",
        "total-amount",
        "reimbursement-amount",
        "reimbursed-amount",
        "currency-amount",
    )
    amount_per_unit = first_money(row, "amount-per-unit", "per-unit-amount")
    quantity = to_int_or_none(
        first_value(
            row,
            "quantity-reimbursed-total",
            "quantity-reimbursed",
            "quantity-reimbursed-cash",
            "quantity-reimbursed-inventory",
            "quantity",
            "qty",
            "reimbursed-quantity",
            "amount-quantity",
        )
    )
    return {
        "amazon_report_run_id": report_run_id,
        "source_row_number": row_number,
        "marketplace_id": marketplace_id,
        "approval_date": parse_date(
            first_value(row, "approval-date", "approved-date", "reimbursement-date", "date")
        ),
        "reimbursement_id": first_value(
            row,
            "reimbursement-id",
            "reimbursement-id-key",
            "reimbursement-event-id",
        ),
        "case_id": first_value(row, "case-id", "amazon-case-id"),
        "amazon_order_id": first_value(row, "amazon-order-id", "order-id"),
        "reason": first_value(row, "reason", "reimbursement-reason", "reason-code"),
        "seller_sku": first_value(row, "seller-sku", "sku", "merchant-sku", "msku"),
        "sku": first_value(row, "sku", "merchant-sku", "seller-sku", "msku"),
        "fnsku": first_value(row, "fnsku", "fba-fnsku"),
        "asin": clean_asin(first_value(row, "asin")),
        "product_name": first_value(row, "product-name", "title", "product-name/title"),
        "title": first_value(row, "title", "product-name", "product-name/title"),
        "quantity_reimbursed": quantity,
        "amount_total": amount_total,
        "amount_per_unit": amount_per_unit or per_unit_amount(amount_total, quantity),
        "currency": first_value(row, "currency", "currency-unit", "currency-code") or infer_currency(row),
        "raw_row_json": row,
        "updated_at": utc_now_iso(),
    }


def build_removal_order_row(
    row: dict[str, str],
    *,
    row_number: int,
    marketplace_id: str,
    report_run_id: str,
) -> dict[str, Any]:
    return {
        "amazon_report_run_id": report_run_id,
        "source_row_number": row_number,
        "marketplace_id": marketplace_id,
        "removal_order_id": first_value(row, "removal-order-id", "order-id"),
        "order_type": first_value(row, "order-type", "removal-order-type"),
        "order_status": first_value(row, "order-status", "status"),
        "requested_quantity": to_int_or_none(first_value(row, "requested-quantity", "request-quantity")),
        "cancelled_quantity": to_int_or_none(first_value(row, "cancelled-quantity", "canceled-quantity")),
        "disposed_quantity": to_int_or_none(first_value(row, "disposed-quantity")),
        "shipped_quantity": to_int_or_none(first_value(row, "shipped-quantity")),
        "in_process_quantity": to_int_or_none(first_value(row, "in-process-quantity")),
        "removal_fee": first_money(row, "removal-fee", "fee", "estimated-fee"),
        "currency": first_value(row, "currency", "currency-code") or infer_currency(row),
        "request_date": parse_date(first_value(row, "request-date", "requested-date", "date")),
        "last_updated_date": parse_date(first_value(row, "last-updated-date", "updated-date")),
        "seller_sku": first_value(row, "seller-sku", "sku", "merchant-sku", "msku"),
        "sku": first_value(row, "sku", "merchant-sku", "seller-sku", "msku"),
        "fnsku": first_value(row, "fnsku", "fba-fnsku"),
        "asin": clean_asin(first_value(row, "asin")),
        "product_name": first_value(row, "product-name", "title", "product-name/title"),
        "title": first_value(row, "title", "product-name", "product-name/title"),
        "disposition": first_value(row, "disposition", "detailed-disposition"),
        "raw_row_json": row,
        "updated_at": utc_now_iso(),
    }


def build_removal_shipment_row(
    row: dict[str, str],
    *,
    row_number: int,
    marketplace_id: str,
    report_run_id: str,
) -> dict[str, Any]:
    return {
        "amazon_report_run_id": report_run_id,
        "source_row_number": row_number,
        "marketplace_id": marketplace_id,
        "removal_order_id": first_value(row, "removal-order-id", "order-id"),
        "removal_shipment_id": first_value(row, "removal-shipment-id", "shipment-id"),
        "shipment_date": parse_date(first_value(row, "shipment-date", "shipped-date", "date")),
        "carrier": first_value(row, "carrier", "carrier-name"),
        "tracking_number": first_value(row, "tracking-number", "tracking-id"),
        "shipped_quantity": to_int_or_none(first_value(row, "shipped-quantity", "quantity", "qty")),
        "seller_sku": first_value(row, "seller-sku", "sku", "merchant-sku", "msku"),
        "sku": first_value(row, "sku", "merchant-sku", "seller-sku", "msku"),
        "fnsku": first_value(row, "fnsku", "fba-fnsku"),
        "asin": clean_asin(first_value(row, "asin")),
        "product_name": first_value(row, "product-name", "title", "product-name/title"),
        "title": first_value(row, "title", "product-name", "product-name/title"),
        "disposition": first_value(row, "disposition", "detailed-disposition"),
        "fulfillment_center_id": first_value(row, "fulfillment-center-id", "fc", "fc-id"),
        "license_plate_number": first_value(
            row,
            "license-plate-number",
            "lpn",
            "lpn-number",
            "license-plate",
        ),
        "vret_id": first_value(row, "vret-id", "vret"),
        "ra_number": first_value(row, "ra-number", "rma", "return-authorization-number"),
        "raw_row_json": row,
        "updated_at": utc_now_iso(),
    }


def upsert_rows(supabase, table_name: str, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table(table_name).upsert(
            chunk,
            on_conflict="amazon_report_run_id,source_row_number",
        ).execute()
        count += len(chunk)
    return count


def first_value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(normalize_header(key))
        if clean_text(value):
            return clean_text(value)
    return None


def first_money(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        value = to_money(first_value(row, key))
        if value is not None:
            return value
    return None


def normalize_header(value: str | None) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("\ufeff", "")
        .replace("_", "-")
        .replace(" ", "-")
    )


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.upper()
    return text if len(text) == 10 else None


def to_int_or_none(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def per_unit_amount(amount_total: float | None, quantity: int | None) -> float | None:
    if amount_total is None or not quantity:
        return None
    return round(amount_total / quantity, 4)


def parse_date(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def infer_currency(row: dict[str, str]) -> str | None:
    for value in row.values():
        text = clean_text(value)
        if text and text.startswith("$"):
            return "USD"
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


def empty_summary(
    spec: ReportSpec,
    report_id: str | None,
    *,
    created_only: bool,
) -> dict[str, Any]:
    return {
        "report_type": spec.report_type,
        "report_id": report_id,
        "table_name": spec.table_name,
        "rows_read": 0,
        "rows_prepared": 0,
        "rows_inserted_or_updated": 0,
        "rows_skipped": 0,
        "errors": 0,
        "dry_run": False,
        "created_only": created_only,
    }


def error_summary(
    spec: ReportSpec,
    error_message: str,
    *,
    report_id: str | None,
) -> dict[str, Any]:
    return {
        "report_type": spec.report_type,
        "report_id": report_id,
        "table_name": spec.table_name,
        "rows_read": 0,
        "rows_prepared": 0,
        "rows_inserted_or_updated": 0,
        "rows_skipped": 0,
        "errors": 1,
        "dry_run": False,
        "created_only": False,
        "error_message": error_message,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("Amazon return recovery report")
    print("-----------------------------")
    print(f"Report type: {summary['report_type']}")
    print(f"Report ID: {summary.get('report_id') or '--'}")
    print(f"Target table: {summary['table_name']}")
    print(f"Rows read: {summary['rows_read']}")
    print(f"Rows prepared: {summary['rows_prepared']}")
    print(f"Rows inserted/updated: {summary['rows_inserted_or_updated']}")
    print(f"Rows skipped: {summary['rows_skipped']}")
    print(f"Errors: {summary['errors']}")
    if summary.get("error_message"):
        print(f"Error: {summary['error_message']}")
    if summary.get("dry_run"):
        print("Mode: dry run; no row-table writes")
    if summary.get("created_only"):
        print("Mode: create only")


# Future matching should remain explicit workflow logic, not import-time inference.
# Candidate match keys: amazon_order_id, reimbursement_id context, sku/fnsku/asin,
# reason, quantity, and nearby return/approval/removal dates.


if __name__ == "__main__":
    raise SystemExit(main())
