"""Sync read-only Informed Repricer report snapshots into MBOP.

Default behavior is discovery/plan mode. Use --write to import downloaded report
rows. This script only uses Informed's Reports API and intentionally avoids the
Listings Management API feed/upload endpoints.
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import time
import zipfile
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from informed_repricing_client import InformedAPIError, InformedRepricingClient

LOGGER = logging.getLogger("informed_report_sync")
BATCH_SIZE = 500
DEFAULT_LISTING_REPORT_TYPE = "All_Fields_NextGen"
DEFAULT_RULE_REPORT_TYPE = "Set_Strategies"

LISTING_REPORT_TYPES = {
    "All_Fields_NextGen",
    "Featured_Merchant_Status",
    "Listings_At_Max_Price",
    "Listings_At_Min_Price",
    "Listings_With_Manual_Price",
    "Listings_With_No_Cost",
    "Listings_Without_A_Min_Price",
    "Competition_Landscape",
    "Competition_Summary",
    "Listings_In_BuyBox",
    "Listings_That_Do_Not_Have_The_BuyBox",
    "Listings_That_Are_Being_Beaten",
}

RULE_REPORT_TYPES = {
    "Set_Strategies",
}

KNOWN_REPORT_TYPES = sorted(LISTING_REPORT_TYPES | RULE_REPORT_TYPES)
TERMINAL_STATUSES = {"complete", "error"}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = InformedRepricingClient.from_env()
        supabase = get_supabase_client()

        if args.plan_only:
            list_recent_requests(client)
            print_report_type_guidance()
            LOGGER.info("Plan-only mode complete. No report requested or imported.")
            return 0

        report_type = args.report_type
        report_category = classify_report_type(report_type)
        run = create_report_run(supabase, report_type, report_category)

        report_request_id = args.report_request_id
        if not report_request_id:
            request_payload = client.request_report(report_type)
            report_request_id = extract_report_request_id(request_payload)
            if not report_request_id:
                raise InformedAPIError(
                    f"Informed requestReport response missing request ID: {request_payload}"
                )
            update_report_run(
                supabase,
                run["informed_report_run_id"],
                {
                    "report_request_id": report_request_id,
                    "processing_status": "pending",
                    "raw_request_json": scrub_download_links(request_payload),
                    "updated_at": utc_now_iso(),
                },
            )
            LOGGER.info("Informed report requested: %s", report_request_id)

        if args.request_only:
            LOGGER.info("Request-only mode complete. Report Request ID: %s", report_request_id)
            return 0

        status_payload = wait_for_report(
            client,
            report_request_id,
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        status = normalize_status(extract_status(status_payload))
        download_url = extract_download_url(status_payload)
        generated_at = extract_generated_at(status_payload)
        update_report_run(
            supabase,
            run["informed_report_run_id"],
            {
                "report_request_id": report_request_id,
                "processing_status": status,
                "completed_at": utc_now_iso() if status == "complete" else None,
                "report_generated_at": generated_at,
                "raw_status_json": scrub_download_links(status_payload),
                "updated_at": utc_now_iso(),
            },
        )

        if status != "complete":
            raise InformedAPIError(f"Informed report did not complete successfully: {status}")
        if not download_url:
            raise InformedAPIError("Completed Informed report did not include a download URL")

        report_bytes = client.download_report(download_url)
        rows = parse_report_rows(report_bytes)
        summary = normalize_rows(
            rows=rows,
            report_type=report_type,
            report_category=report_category,
            report_run_id=run["informed_report_run_id"],
            report_generated_at=generated_at,
        )
        print_summary(report_type, report_category, summary, write=args.write)

        if not args.write:
            LOGGER.info("Dry run complete. No Informed snapshots inserted.")
            return 0

        inserted = insert_snapshots(supabase, report_category, summary["normalized_rows"])
        update_report_run(
            supabase,
            run["informed_report_run_id"],
            {
                "processing_status": "imported",
                "imported_at": utc_now_iso(),
                "rows_read": summary["rows_read"],
                "rows_inserted": inserted,
                "rows_skipped": summary["rows_skipped"],
                "missing_asin_count": summary["missing_asin_count"],
                "missing_sku_count": summary["missing_sku_count"],
                "parse_error_count": summary["parse_error_count"],
                "updated_at": utc_now_iso(),
            },
        )
        LOGGER.info("Informed report import complete. Rows inserted: %s", inserted)
        return 0
    except InformedAPIError as error:
        LOGGER.error("Informed report sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Informed report sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync read-only Informed Repricer Reports API data into MBOP."
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="List recent report requests and known report types without requesting/downloading a report.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Insert parsed report rows. Default downloads/parses only.",
    )
    parser.add_argument(
        "--report-type",
        default=DEFAULT_LISTING_REPORT_TYPE,
        help=f"Informed report type. Default: {DEFAULT_LISTING_REPORT_TYPE}",
    )
    parser.add_argument(
        "--report-request-id",
        default=None,
        help="Resume/download an existing Informed report request ID.",
    )
    parser.add_argument(
        "--request-only",
        action="store_true",
        help="Request the report and stop after logging the request ID.",
    )
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )
    return create_client(supabase_url, supabase_key)


def list_recent_requests(client: InformedRepricingClient) -> None:
    payload = client.list_report_requests()
    requests = extract_rows_from_payload(payload)
    print("Informed recent report requests")
    print("--------------------------------")
    print(f"Rows returned: {len(requests)}")
    for row in requests[:10]:
        print(
            f"- {row.get('reportType') or row.get('report_type') or '--'} | "
            f"{row.get('reportRequestID') or row.get('reportRequestId') or row.get('reportRequestID'.lower()) or '--'} | "
            f"{row.get('status') or row.get('reportProcessingStatus') or '--'}"
        )


def print_report_type_guidance() -> None:
    print("\nKnown read-only report types for MBOP discovery")
    print("-----------------------------------------------")
    print(f"Preferred listing report: {DEFAULT_LISTING_REPORT_TYPE}")
    print(f"Possible rule/settings template report: {DEFAULT_RULE_REPORT_TYPE}")
    print("MBOP will not use Listings Management API upload/feed endpoints.")


def create_report_run(supabase, report_type: str, report_category: str) -> dict[str, Any]:
    response = (
        supabase.table("informed_report_runs")
        .insert(
            {
                "report_type": report_type,
                "report_category": report_category,
                "processing_status": "created",
            }
        )
        .execute()
    )
    return (response.data or [{}])[0]


def update_report_run(supabase, report_run_id: str, updates: dict[str, Any]) -> None:
    supabase.table("informed_report_runs").update(updates).eq(
        "informed_report_run_id", report_run_id
    ).execute()


def wait_for_report(
    client: InformedRepricingClient,
    report_request_id: str,
    *,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        payload = client.get_report_request_status(report_request_id)
        status = normalize_status(extract_status(payload))
        LOGGER.info("Informed report %s status=%s", report_request_id, status)
        if status in TERMINAL_STATUSES:
            return payload
        if time.monotonic() >= deadline:
            raise InformedAPIError(
                f"Timed out waiting for report {report_request_id}; last status={status}"
            )
        time.sleep(max(poll_seconds, 1))


def parse_report_rows(content: bytes) -> list[dict[str, str]]:
    files = extract_report_files(content)
    rows: list[dict[str, str]] = []
    for filename, text in files:
        parsed = parse_delimited_text(text)
        LOGGER.info("Parsed Informed report file %s rows=%s", filename, len(parsed))
        rows.extend(parsed)
    return rows


def extract_report_files(content: bytes) -> list[tuple[str, str]]:
    if zipfile.is_zipfile(io.BytesIO(content)):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files: list[tuple[str, str]] = []
            for name in archive.namelist():
                if name.endswith("/") or not name.lower().endswith((".csv", ".tsv", ".txt")):
                    continue
                files.append((name, archive.read(name).decode("utf-8-sig")))
            if not files:
                raise InformedAPIError("Informed report ZIP contained no CSV/TSV/TXT files")
            return files
    return [("report", content.decode("utf-8-sig"))]


def parse_delimited_text(text: str) -> list[dict[str, str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [
        {normalize_header(key): clean_text(value) or "" for key, value in row.items()}
        for row in reader
    ]


def normalize_rows(
    *,
    rows: list[dict[str, str]],
    report_type: str,
    report_category: str,
    report_run_id: str,
    report_generated_at: str | None,
) -> dict[str, Any]:
    normalized_rows: list[dict[str, Any]] = []
    missing_asin = 0
    missing_sku = 0
    parse_errors = 0
    rows_skipped = 0

    for index, row in enumerate(rows, start=1):
        try:
            if report_category == "rule":
                normalized_rows.append(
                    normalize_rule_row(
                        row=row,
                        report_type=report_type,
                        row_number=index,
                        report_run_id=report_run_id,
                        report_generated_at=report_generated_at,
                    )
                )
                continue

            normalized = normalize_listing_row(
                row=row,
                report_type=report_type,
                row_number=index,
                report_run_id=report_run_id,
                report_generated_at=report_generated_at,
            )
            if not normalized["asin"]:
                missing_asin += 1
            if not normalized["seller_sku"]:
                missing_sku += 1
            if not normalized["asin"] and not normalized["seller_sku"]:
                rows_skipped += 1
                continue
            normalized_rows.append(normalized)
        except Exception as error:  # noqa: BLE001 - row-level guard
            parse_errors += 1
            LOGGER.warning("Failed to parse Informed row %s: %s", index, error)

    return {
        "rows_read": len(rows),
        "rows_skipped": rows_skipped,
        "missing_asin_count": missing_asin,
        "missing_sku_count": missing_sku,
        "parse_error_count": parse_errors,
        "normalized_rows": normalized_rows,
        "sample_columns": list(rows[0].keys()) if rows else [],
    }


def normalize_listing_row(
    *,
    row: dict[str, str],
    report_type: str,
    row_number: int,
    report_run_id: str,
    report_generated_at: str | None,
) -> dict[str, Any]:
    buy_box_status = first_value(
        row,
        "buy-box-status",
        "buybox-status",
        "buy-box",
        "buybox",
        "featured-merchant-status",
        "featured-merchant",
    )
    return {
        "informed_report_run_id": report_run_id,
        "source_report_type": report_type,
        "source_row_number": row_number,
        "report_generated_at": report_generated_at,
        "asin": clean_asin(first_value(row, "asin", "item-id", "product-id", "amazon-asin")),
        "seller_sku": first_value(row, "sku", "seller-sku", "msku", "merchant-sku"),
        "marketplace": first_value(row, "marketplace", "channel", "marketplace-name"),
        "fulfillment_channel": first_value(
            row,
            "fulfillment-channel",
            "fulfillment",
            "fulfillment-type",
            "channel-fulfillment",
        ),
        "repricing_enabled": to_bool(
            first_value(
                row,
                "repricing-enabled",
                "managed",
                "managed-status",
                "is-managed",
                "reprice",
            )
        ),
        "assigned_rule_name": first_value(
            row,
            "strategy",
            "strategy-id",
            "strategy-name",
            "rule",
            "rule-name",
            "assigned-rule",
            "assigned-rule-name",
        ),
        "current_price": to_money(first_value(row, "current-price", "price", "my-price")),
        "min_price": to_money(first_value(row, "min-price", "minimum-price", "min")),
        "max_price": to_money(first_value(row, "max-price", "maximum-price", "max")),
        "cost": to_money(first_value(row, "cost", "item-cost", "unit-cost")),
        "buy_box_price": to_money(
            first_value(row, "buy-box-price", "buybox-price", "featured-offer-price")
        ),
        "buy_box_status": buy_box_status,
        "buy_box_winner": to_buy_box_winner(
            first_value(row, "buybox-winner", "buy-box-winner") or buy_box_status
        ),
        "competition_offer_count": to_int(
            first_value(row, "offer-count", "competition-count", "competitor-count"),
            default=None,
        ),
        "quantity": to_int(first_value(row, "quantity", "qty", "stock"), default=None),
        "listing_status": first_value(row, "status", "listing-status", "item-status"),
        "raw_row_json": row,
    }


def normalize_rule_row(
    *,
    row: dict[str, str],
    report_type: str,
    row_number: int,
    report_run_id: str,
    report_generated_at: str | None,
) -> dict[str, Any]:
    return {
        "informed_report_run_id": report_run_id,
        "source_report_type": report_type,
        "source_row_number": row_number,
        "report_generated_at": report_generated_at,
        "rule_name": first_value(row, "strategy", "strategy-name", "rule", "rule-name"),
        "strategy_type": first_value(row, "strategy-type", "type", "repricing-strategy"),
        "marketplace": first_value(row, "marketplace", "channel", "marketplace-name"),
        "fulfillment_channel": first_value(row, "fulfillment-channel", "fulfillment"),
        "rule_status": first_value(row, "status", "rule-status", "strategy-status"),
        "min_price_behavior": first_value(row, "min-price-behavior", "minimum-price-behavior"),
        "max_price_behavior": first_value(row, "max-price-behavior", "maximum-price-behavior"),
        "buy_box_behavior": first_value(row, "buy-box-behavior", "buybox-behavior"),
        "competition_filters": filtered_json(row, "competition", "competitor", "filter"),
        "repricing_safeguards": filtered_json(row, "safeguard", "floor", "ceiling"),
        "raw_row_json": row,
    }


def insert_snapshots(
    supabase,
    report_category: str,
    rows: list[dict[str, Any]],
) -> int:
    table = "informed_rule_snapshots" if report_category == "rule" else "informed_listing_snapshots"
    inserted = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table(table).insert(chunk).execute()
        inserted += len(chunk)
    return inserted


def print_summary(
    report_type: str,
    report_category: str,
    summary: dict[str, Any],
    *,
    write: bool,
) -> None:
    print("Informed report sync write" if write else "Informed report sync dry run")
    print("--------------------------")
    print(f"Report type: {report_type}")
    print(f"Report category: {report_category}")
    print(f"Rows read: {summary['rows_read']}")
    print(f"Rows prepared: {len(summary['normalized_rows'])}")
    print(f"Rows skipped: {summary['rows_skipped']}")
    print(f"Missing ASIN: {summary['missing_asin_count']}")
    print(f"Missing SKU: {summary['missing_sku_count']}")
    print(f"Parse errors: {summary['parse_error_count']}")
    if summary["sample_columns"]:
        print("Sample columns:")
        for column in summary["sample_columns"][:30]:
            print(f"- {column}")


def classify_report_type(report_type: str) -> str:
    if report_type in RULE_REPORT_TYPES:
        return "rule"
    if report_type in LISTING_REPORT_TYPES:
        return "listing"
    return "unknown"


def extract_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "reports", "reportRequests", "items", "payload"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def extract_report_request_id(payload: Any) -> str | None:
    value = find_first_key(payload, {"reportrequestid", "reportrequestid", "requestid"})
    return clean_text(value)


def extract_status(payload: Any) -> str | None:
    return clean_text(
        find_first_key(
            payload,
            {"status", "reportprocessingstatus", "processingstatus"},
        )
    )


def extract_generated_at(payload: Any) -> str | None:
    value = clean_text(
        find_first_key(
            payload,
            {"availabledate", "completeddate", "completedat", "generatedat", "reportgeneratedat"},
        )
    )
    return parse_datetime(value)


def extract_download_url(payload: Any) -> str | None:
    value = clean_text(
        find_first_key(
            payload,
            {"downloadlink", "downloadurl", "url", "signedurl", "reporturl"},
        )
    )
    if value and value.startswith(("http://", "https://")):
        return value
    return None


def find_first_key(value: Any, normalized_names: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if normalize_header(key).replace("-", "") in normalized_names:
                return item
        for item in value.values():
            nested = find_first_key(item, normalized_names)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = find_first_key(item, normalized_names)
            if nested is not None:
                return nested
    return None


def scrub_download_links(payload: Any) -> Any:
    if isinstance(payload, dict):
        scrubbed = {}
        for key, value in payload.items():
            normalized = normalize_header(key).replace("-", "")
            if normalized in {"downloadlink", "downloadurl", "signedurl", "reporturl", "url"}:
                scrubbed[key] = "<signed-url-redacted>"
            else:
                scrubbed[key] = scrub_download_links(value)
        return scrubbed
    if isinstance(payload, list):
        return [scrub_download_links(item) for item in payload]
    return payload


def first_value(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(normalize_header(name))
        if clean_text(value):
            return clean_text(value)
    return None


def normalize_header(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("_", "-")
        .replace(" ", "-")
        .replace("/", "-")
    )


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
        return float(text.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def to_int(value: Any, default: int | None = 0) -> int | None:
    text = clean_text(value)
    if not text:
        return default
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return default


def to_bool(value: Any) -> bool | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized in {"y", "yes", "true", "1", "enabled", "managed", "active"}:
        return True
    if normalized in {"n", "no", "false", "0", "disabled", "unmanaged", "inactive"}:
        return False
    return None


def to_buy_box_winner(value: Any) -> bool | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized in {"y", "yes", "true", "1", "winner", "winning", "in buy box"}:
        return True
    if normalized in {"n", "no", "false", "0", "not in buy box", "losing"}:
        return False
    return None


def normalize_status(value: str | None) -> str:
    text = (value or "").strip().lower().replace("_", "").replace("-", "")
    if text in {"complete", "completed", "done"}:
        return "complete"
    if text in {"inprogress", "processing"}:
        return "in_progress"
    if text in {"error", "failed", "fatal"}:
        return "error"
    return "pending"


def parse_datetime(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def filtered_json(row: dict[str, str], *needles: str) -> dict[str, str] | None:
    filtered = {
        key: value
        for key, value in row.items()
        if any(needle in key for needle in needles)
    }
    return filtered or None


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
