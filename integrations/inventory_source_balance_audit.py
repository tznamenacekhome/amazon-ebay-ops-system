"""Audit whether purchase source units explain sales, inventory, and adjustments.

This is a secondary control, not a sync. It compares MBOP source lots against
COGS consumption, active inventory cost layers, and explicit adjustment
movements so unexplained source-unit balances can be reviewed.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


LOGGER = logging.getLogger("inventory_source_balance_audit")
BATCH_SIZE = 1000
DEFAULT_CSV_EXPORT = Path("exports/inventory_source_balance_audit.csv")
DEFAULT_JSON_EXPORT = Path("logs/inventory_source_balance_audit_latest.json")
EXCLUDED_PURCHASE_STATUSES = {"cancelled", "return_opened", "return_pending"}
SOURCE_REFERENCE_TYPES = {"purchase_item", "non_ebay_purchase_cogs_source"}


@dataclass
class AuditRow:
    asin: str
    title: str | None
    source_units: int
    ebay_source_units: int
    non_ebay_source_units: int
    sales_units: int
    current_inventory_units: int
    opening_history_boundary_units: int
    other_adjustment_units: int
    unexplained_units: int
    missing_cogs_units: int
    missing_cogs_rows: int
    status: str


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        supabase = get_supabase_client()
        rows = build_audit_rows(supabase)
        if args.asin:
            selected_asins = {asin.strip().upper() for asin in args.asin}
            rows = [row for row in rows if row.asin in selected_asins]

        rows.sort(key=lambda row: (row.status, -abs(row.unexplained_units), row.asin))
        print_summary(rows)
        write_csv(rows, args.csv_export)
        write_json(rows, args.json_export)
        LOGGER.info("CSV export written: %s", args.csv_export)
        LOGGER.info("JSON export written: %s", args.json_export)
        return 0
    except Exception as error:  # noqa: BLE001 - audit should fail safely
        LOGGER.exception("Inventory Source Balance Audit failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Inventory Source Balance Audit.")
    parser.add_argument(
        "--asin",
        action="append",
        help="Optional ASIN filter. Can be passed multiple times.",
    )
    parser.add_argument(
        "--csv-export",
        type=Path,
        default=DEFAULT_CSV_EXPORT,
        help="CSV export path.",
    )
    parser.add_argument(
        "--json-export",
        type=Path,
        default=DEFAULT_JSON_EXPORT,
        help="Latest JSON summary path.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def build_audit_rows(supabase) -> list[AuditRow]:
    ebay_units, titles = fetch_ebay_source_units(supabase)
    non_ebay_units, non_ebay_titles = fetch_non_ebay_source_units(supabase)
    titles.update({asin: title for asin, title in non_ebay_titles.items() if asin not in titles})
    sales_units = fetch_sales_consumption_units(supabase)
    inventory_units = fetch_active_inventory_layer_units(supabase)
    opening_adjustments, other_adjustments = fetch_adjustment_units(supabase)
    missing_cogs_units, missing_cogs_rows, missing_titles = fetch_missing_cogs_units(supabase)
    titles.update({asin: title for asin, title in missing_titles.items() if asin not in titles})

    all_asins = set().union(
        ebay_units,
        non_ebay_units,
        sales_units,
        inventory_units,
        opening_adjustments,
        other_adjustments,
        missing_cogs_units,
    )

    rows: list[AuditRow] = []
    for asin in all_asins:
        source_units = ebay_units[asin] + non_ebay_units[asin]
        explained_units = (
            sales_units[asin]
            + inventory_units[asin]
            + opening_adjustments[asin]
            + other_adjustments[asin]
        )
        unexplained = source_units - explained_units
        status = row_status(unexplained, missing_cogs_units[asin])
        rows.append(
            AuditRow(
                asin=asin,
                title=titles.get(asin),
                source_units=source_units,
                ebay_source_units=ebay_units[asin],
                non_ebay_source_units=non_ebay_units[asin],
                sales_units=sales_units[asin],
                current_inventory_units=inventory_units[asin],
                opening_history_boundary_units=opening_adjustments[asin],
                other_adjustment_units=other_adjustments[asin],
                unexplained_units=unexplained,
                missing_cogs_units=missing_cogs_units[asin],
                missing_cogs_rows=missing_cogs_rows[asin],
                status=status,
            )
        )
    return rows


def fetch_ebay_source_units(supabase) -> tuple[defaultdict[str, int], dict[str, str]]:
    excluded_item_ids = {
        row["item_id"]
        for row in fetch_all(
            supabase,
            "purchase_items",
            "item_id,exclude_from_purchase_reporting",
        )
        if row.get("exclude_from_purchase_reporting") is True
    }
    units: defaultdict[str, int] = defaultdict(int)
    titles: dict[str, str] = {}
    rows = fetch_all(
        supabase,
        "vw_purchases_dashboard",
        "item_id,asin,title,supplier,quantity,current_status,unit_cost",
    )
    for row in rows:
        item_id = row.get("item_id")
        asin = clean_asin(row.get("asin"))
        supplier = clean_text(row.get("supplier")).lower()
        status = clean_text(row.get("current_status")).lower()
        if item_id in excluded_item_ids:
            continue
        if supplier != "ebay" or not asin or asin == "N/A":
            continue
        if status in EXCLUDED_PURCHASE_STATUSES:
            continue
        if to_decimal(row.get("unit_cost")) is None:
            continue
        quantity = to_int(row.get("quantity")) or 0
        if quantity <= 0:
            continue
        units[asin] += quantity
        titles.setdefault(asin, row.get("title") or "")
    return units, titles


def fetch_non_ebay_source_units(supabase) -> tuple[defaultdict[str, int], dict[str, str]]:
    units: defaultdict[str, int] = defaultdict(int)
    titles: dict[str, str] = {}
    rows = fetch_all(
        supabase,
        "non_ebay_purchase_cogs_sources",
        "asin,description,quantity,received_by_prep_center_quantity,damaged_quantity,unit_cost",
    )
    for row in rows:
        asin = clean_asin(row.get("asin"))
        unit_cost = to_decimal(row.get("unit_cost"))
        if not asin or unit_cost is None:
            continue
        quantity = source_available_quantity(row)
        if quantity <= 0:
            continue
        units[asin] += quantity
        titles.setdefault(asin, row.get("description") or "")
    return units, titles


def fetch_sales_consumption_units(supabase) -> defaultdict[str, int]:
    units: defaultdict[str, int] = defaultdict(int)
    rows = fetch_all(
        supabase,
        "amazon_sales_cogs_consumption",
        "asin,quantity_consumed,source_reference_type",
    )
    for row in rows:
        asin = clean_asin(row.get("asin"))
        if not asin or row.get("source_reference_type") not in SOURCE_REFERENCE_TYPES:
            continue
        units[asin] += to_int(row.get("quantity_consumed")) or 0
    return units


def fetch_active_inventory_layer_units(supabase) -> defaultdict[str, int]:
    units: defaultdict[str, int] = defaultdict(int)
    rows = fetch_all(
        supabase,
        "amazon_inventory_cogs_layers",
        "asin,quantity_assigned,active,source_reference_type",
    )
    for row in rows:
        asin = clean_asin(row.get("asin"))
        if not asin or row.get("active") is not True:
            continue
        if row.get("source_reference_type") not in SOURCE_REFERENCE_TYPES:
            continue
        units[asin] += to_int(row.get("quantity_assigned")) or 0
    return units


def fetch_adjustment_units(supabase) -> tuple[defaultdict[str, int], defaultdict[str, int]]:
    opening: defaultdict[str, int] = defaultdict(int)
    other: defaultdict[str, int] = defaultdict(int)
    rows = fetch_all(
        supabase,
        "inventory_movements",
        "quantity,source_table,source_id,external_reference_type,raw_context_json",
    )
    for row in rows:
        asin = clean_asin((row.get("raw_context_json") or {}).get("asin"))
        if not asin:
            continue
        quantity = to_int(row.get("quantity")) or 0
        if row.get("external_reference_type") == "opening_history_boundary":
            opening[asin] += quantity
        else:
            other[asin] += quantity
    return opening, other


def fetch_missing_cogs_units(
    supabase,
) -> tuple[defaultdict[str, int], defaultdict[str, int], dict[str, str]]:
    units: defaultdict[str, int] = defaultdict(int)
    rows_by_asin: defaultdict[str, int] = defaultdict(int)
    titles: dict[str, str] = {}
    rows = fetch_all(
        supabase,
        "amazon_sales_profitability",
        "asin,title,quantity,data_status",
    )
    for row in rows:
        if row.get("data_status") != "missing_cogs":
            continue
        asin = clean_asin(row.get("asin"))
        if not asin:
            continue
        units[asin] += to_int(row.get("quantity")) or 0
        rows_by_asin[asin] += 1
        titles.setdefault(asin, row.get("title") or "")
    return units, rows_by_asin, titles


def source_available_quantity(row: dict[str, Any]) -> int:
    received = to_int(row.get("received_by_prep_center_quantity"))
    if received is not None:
        return max(received, 0)
    quantity = to_int(row.get("quantity")) or 0
    damaged = to_int(row.get("damaged_quantity")) or 0
    return max(quantity - damaged, 0)


def row_status(unexplained_units: int, missing_cogs_units: int) -> str:
    if unexplained_units == 0 and missing_cogs_units == 0:
        return "balanced"
    if unexplained_units < 0:
        return "source_short"
    if missing_cogs_units > 0:
        return "missing_cogs"
    return "unexplained_positive"


def print_summary(rows: list[AuditRow]) -> None:
    status_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        status_counts[row.status] += 1

    print("Inventory Source Balance Audit")
    print("------------------------------")
    print(f"ASINs audited: {len(rows)}")
    for status in sorted(status_counts):
        print(f"{status}: {status_counts[status]}")
    print(
        "Unexplained units: "
        f"{sum(row.unexplained_units for row in rows if row.unexplained_units != 0)}"
    )
    print(f"Missing COGS units: {sum(row.missing_cogs_units for row in rows)}")


def write_csv(rows: list[AuditRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(rows[0]).keys()) if rows else [field.name for field in AuditRow.__dataclass_fields__.values()]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_json(rows: list[AuditRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "asin_count": len(rows),
        "status_counts": count_statuses(rows),
        "unexplained_units": sum(
            row.unexplained_units for row in rows if row.unexplained_units != 0
        ),
        "missing_cogs_units": sum(row.missing_cogs_units for row in rows),
        "problem_rows": [
            asdict(row)
            for row in rows
            if row.status != "balanced"
        ][:200],
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def count_statuses(rows: list[AuditRow]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.status] += 1
    return dict(sorted(counts.items()))


def fetch_all(supabase, table: str, select: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            supabase.table(table)
            .select(select)
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def clean_asin(value: Any) -> str:
    return str(value or "").strip().upper()


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(Decimal(str(value)))


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
