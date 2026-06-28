"""Backfill historical MBOP business value snapshots into ZFI Supabase.

This is a one-time migration helper. Dry run is the default. Live writes only
run when --apply is passed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import uuid
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("backfill_zfi_business_value_history")

DEFAULT_TARGET_TABLE = "business_value_snapshots"
DEFAULT_SOURCE_SYSTEM = "mbop"
DEFAULT_SOURCE_TYPE = "migrated_mbop_history"
SCHEMA_VERSION = "2026-06-27"
DETERMINISTIC_ID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "mbop-zfi-business-value-history",
)


class ZFIBusinessValueBackfillError(RuntimeError):
    """Raised when the ZFI business value backfill cannot safely continue."""


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        mbop = get_mbop_supabase_client()
        source_rows = fetch_mbop_business_value_snapshots(mbop)
        mapped_rows = [
            map_business_value_snapshot(row, source_system=args.source_system, source_type=args.source_type)
            for row in source_rows
        ]

        if args.limit is not None:
            mapped_rows = mapped_rows[: args.limit]

        zfi = get_zfi_supabase_client()
        before_count = safe_count_rows(zfi, args.target_table)

        print_summary(
            source_count=len(source_rows),
            mapped_rows=mapped_rows,
            before_count=before_count,
            target_table=args.target_table,
            write=args.apply,
        )
        print_preview(mapped_rows, args.preview_rows)

        if not args.apply:
            LOGGER.info("Dry run complete. No ZFI Supabase writes performed.")
            return 0

        if not mapped_rows:
            LOGGER.info("No rows to write.")
            return 0

        upsert_rows(zfi, args.target_table, mapped_rows, args.page_size)
        after_count = safe_count_rows(zfi, args.target_table)
        LOGGER.info(
            "ZFI business value history backfill complete: target=%s rows_written=%s before=%s after=%s",
            args.target_table,
            len(mapped_rows),
            display_count(before_count),
            display_count(after_count),
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely.
        LOGGER.exception("ZFI business value history backfill failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply a one-time MBOP business value history backfill to ZFI Supabase."
    )
    parser.add_argument(
        "--target-table",
        default=os.getenv("ZFI_BUSINESS_VALUE_HISTORY_TABLE", DEFAULT_TARGET_TABLE),
        help="ZFI Supabase table to upsert into.",
    )
    parser.add_argument(
        "--source-system",
        default=DEFAULT_SOURCE_SYSTEM,
        help="Value to store in source_system.",
    )
    parser.add_argument(
        "--source-type",
        default=DEFAULT_SOURCE_TYPE,
        help="Value to store in source_type.",
    )
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=5,
        help="Number of mapped rows to print in dry-run/apply preview.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=500,
        help="Read/write page size.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for testing the mapping.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write mapped rows to ZFI Supabase. Omit for dry run.",
    )
    return parser.parse_args()


def get_mbop_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise ZFIBusinessValueBackfillError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def get_zfi_supabase_client():
    supabase_url = os.getenv("ZFI_SUPABASE_URL")
    supabase_key = os.getenv("ZFI_SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise ZFIBusinessValueBackfillError(
            "Missing ZFI_SUPABASE_URL or ZFI_SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(supabase_url, supabase_key)


def fetch_mbop_business_value_snapshots(supabase) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table("business_value_snapshots")
            .select(
                "business_value_snapshot_id,snapshot_date,captured_at,"
                "amazon_inventory_value,pre_amazon_inventory_value,"
                "amazon_cash_balance,amazon_cash_in_transit,cash_on_hand,"
                "total_business_value,source,raw_rollup_json,created_at,updated_at"
            )
            .order("snapshot_date", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def map_business_value_snapshot(
    row: dict[str, Any],
    *,
    source_system: str,
    source_type: str,
) -> dict[str, Any]:
    snapshot_date = str(row.get("snapshot_date") or "")
    source_snapshot_id = str(row.get("business_value_snapshot_id") or snapshot_date)
    if not snapshot_date:
        raise ZFIBusinessValueBackfillError(
            f"MBOP business_value_snapshots row is missing snapshot_date: {source_snapshot_id}"
        )

    deterministic_id = uuid.uuid5(
        DETERMINISTIC_ID_NAMESPACE,
        f"{source_system}:{source_type}:{source_snapshot_id}:{snapshot_date}",
    )
    raw_rollup = row.get("raw_rollup_json") or {}
    amazon_inventory_value = money(row.get("amazon_inventory_value"))
    pre_amazon_inventory_value = money(row.get("pre_amazon_inventory_value"))
    amazon_cash_balance = money(row.get("amazon_cash_balance"))
    amazon_cash_in_transit = money(row.get("amazon_cash_in_transit"))
    cash_on_hand = money(row.get("cash_on_hand"))
    total_business_value = money(row.get("total_business_value"))
    source_payload = {
        "mbop_business_value_snapshot_id": source_snapshot_id,
        "snapshot_date": snapshot_date,
        "captured_at": row.get("captured_at"),
        "amazon_inventory_value": amazon_inventory_value,
        "pre_amazon_inventory_value": pre_amazon_inventory_value,
        "amazon_cash_balance": amazon_cash_balance,
        "amazon_cash_in_transit": amazon_cash_in_transit,
        "cash_on_hand": cash_on_hand,
        "total_business_value": total_business_value,
        "source": row.get("source") or "mbop_dashboard_rollup",
        "raw_rollup_json": raw_rollup,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
    raw_component_context = {
        "component_values": {
            "amazon_inventory_value": amazon_inventory_value,
            "pre_amazon_inventory_value": pre_amazon_inventory_value,
            "amazon_cash_balance": amazon_cash_balance,
            "amazon_cash_in_transit": amazon_cash_in_transit,
            "cash_on_hand": cash_on_hand,
            "total_business_value": total_business_value,
        },
        "raw_rollup_json": raw_rollup,
        "migration": {
            "source_system": source_system,
            "source_type": source_type,
            "script": "integrations/backfill_zfi_business_value_history.py",
            "schema_version": SCHEMA_VERSION,
        },
    }

    return {
        "business_value_snapshot_id": str(deterministic_id),
        "snapshot_date": snapshot_date,
        "snapshot_timestamp": row.get("captured_at"),
        "total_business_value": total_business_value,
        "inventory_value": money(amazon_inventory_value + pre_amazon_inventory_value),
        "business_cash": cash_on_hand,
        "amazon_available_balance": None,
        "amazon_funds_in_transit": amazon_cash_in_transit,
        "amazon_deferred_or_reserved_cash": amazon_cash_balance,
        "other_assets_value": 0.0,
        "other_liabilities_value": 0.0,
        "calculation_version": f"mbop_migration_{SCHEMA_VERSION}",
        "source_system": source_system,
        "source_type": source_type,
        "source_payload": source_payload,
        "raw_component_context": raw_component_context,
        "confidence_score": 0.75,
        "review_status": "pending",
        "confidence_notes": (
            "Migrated from MBOP business_value_snapshots. MBOP component values are preserved "
            "in source_payload and raw_component_context. ZFI owns ongoing business value history "
            "after this one-time backfill is verified."
        ),
        "review_notes": None,
        "created_at": row.get("created_at"),
        "updated_at": now_iso(),
    }


def safe_count_rows(supabase, table: str) -> int | None:
    try:
        return supabase.table(table).select("*", count="exact").limit(0).execute().count
    except Exception as error:  # noqa: BLE001 - permission checks should not block dry-run previews.
        LOGGER.warning(
            "Could not read ZFI %s row count. This usually means ZFI needs SELECT privileges for service_role. Error: %s",
            table,
            error,
        )
        return None


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], page_size: int) -> None:
    for chunk in chunks(rows, max(1, page_size)):
        supabase.table(table).upsert(
            chunk,
            on_conflict="business_value_snapshot_id",
        ).execute()


def print_summary(
    *,
    source_count: int,
    mapped_rows: list[dict[str, Any]],
    before_count: int | None,
    target_table: str,
    write: bool,
) -> None:
    action = "LIVE WRITE" if write else "DRY RUN"
    print("ZFI business value history backfill")
    print("-----------------------------------")
    print(f"Mode: {action}")
    print(f"Target table: public.{target_table}")
    print(f"MBOP source rows: {source_count}")
    print(f"Mapped rows: {len(mapped_rows)}")
    print(f"ZFI rows before: {display_count(before_count)}")
    if mapped_rows:
        dates = [row["snapshot_date"] for row in mapped_rows]
        print(f"Date range: {min(dates)} to {max(dates)}")


def print_preview(rows: list[dict[str, Any]], preview_rows: int) -> None:
    preview = rows[: max(0, preview_rows)]
    print("\nPreview rows:")
    print(json.dumps(preview, indent=2, sort_keys=True, default=str))


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def display_count(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


if __name__ == "__main__":
    sys.exit(main())
