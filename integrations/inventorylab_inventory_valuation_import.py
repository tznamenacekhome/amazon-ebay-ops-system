"""Import InventoryLab inventory valuation snapshots.

This is a legacy opening-balance valuation layer for Amazon FBA inventory that
already existed before MBOP became the go-forward source of truth. It stores
InventoryLab valuation rows separately and never writes purchase_items.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("inventorylab_inventory_valuation_import")
DEFAULT_INPUT = Path("docs/Inventory Valuation 5-26-26 0_0.csv")
BATCH_SIZE = 500


@dataclass
class ValuationRow:
    row_number: int
    raw: dict[str, str]
    title: str | None
    seller_sku: str | None
    fulfillment: str | None
    inbound_quantity: int | None
    on_hand_quantity: int | None
    unlisted_quantity: int | None
    cost_per_unit: float | None
    total_value: float | None


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        rows = read_valuation_csv(args.input)
        summary = summarize(rows)
        print_summary(summary)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        payload = build_snapshot_rows(rows, args.input)
        for chunk in chunks(payload, BATCH_SIZE):
            supabase.table("inventorylab_inventory_valuation_snapshots").upsert(
                chunk,
                on_conflict="source_file,source_row_number",
            ).execute()

        LOGGER.info("InventoryLab valuation rows upserted: %s", len(payload))
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("InventoryLab valuation import failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze or import InventoryLab inventory valuation CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="InventoryLab inventory valuation CSV path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write rows to inventorylab_inventory_valuation_snapshots.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def read_valuation_csv(path: Path) -> list[ValuationRow]:
    if not path.exists():
        raise FileNotFoundError(path)

    rows: list[ValuationRow] = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row_number, raw in enumerate(reader, start=2):
            rows.append(
                ValuationRow(
                    row_number=row_number,
                    raw={key: value for key, value in raw.items()},
                    title=clean_text(raw.get("Title")),
                    seller_sku=clean_text(raw.get("MSKU")),
                    fulfillment=clean_text(raw.get("Fulfillment")),
                    inbound_quantity=to_int(raw.get("Inbound Qty")),
                    on_hand_quantity=to_int(raw.get("On Hand")),
                    unlisted_quantity=to_int(raw.get("Unlisted Qty")),
                    cost_per_unit=to_money(raw.get("Cost/Unit")),
                    total_value=to_money(raw.get("Total Value")),
                )
            )

    return rows


def summarize(rows: list[ValuationRow]) -> dict[str, Any]:
    missing_sku = [row for row in rows if not row.seller_sku]
    missing_value = [row for row in rows if row.total_value is None]
    duplicate_skus = find_duplicate_skus(rows)

    return {
        "rows_read": len(rows),
        "rows_missing_sku": len(missing_sku),
        "rows_missing_total_value": len(missing_value),
        "duplicate_skus": duplicate_skus,
        "total_on_hand_units": sum(row.on_hand_quantity or 0 for row in rows),
        "total_inbound_units": sum(row.inbound_quantity or 0 for row in rows),
        "total_unlisted_units": sum(row.unlisted_quantity or 0 for row in rows),
        "total_value": round(sum(row.total_value or 0 for row in rows), 2),
    }


def find_duplicate_skus(rows: list[ValuationRow]) -> list[str]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.seller_sku:
            counts[row.seller_sku] = counts.get(row.seller_sku, 0) + 1
    return sorted([sku for sku, count in counts.items() if count > 1])


def build_snapshot_rows(rows: list[ValuationRow], source_file: Path) -> list[dict[str, Any]]:
    source_name = str(source_file.as_posix())
    payload = []

    for row in rows:
        if not row.seller_sku:
            LOGGER.warning("Skipping row %s with missing MSKU.", row.row_number)
            continue

        payload.append(
            {
                "source_file": source_name,
                "source_row_number": row.row_number,
                "title": row.title,
                "seller_sku": row.seller_sku,
                "fulfillment": row.fulfillment,
                "inbound_quantity": row.inbound_quantity,
                "on_hand_quantity": row.on_hand_quantity,
                "unlisted_quantity": row.unlisted_quantity,
                "cost_per_unit": row.cost_per_unit,
                "total_value": row.total_value,
                "raw_inventorylab_json": row.raw,
            }
        )

    return payload


def print_summary(summary: dict[str, Any]) -> None:
    print("InventoryLab inventory valuation dry run")
    print("----------------------------------------")
    print(f"Rows read: {summary['rows_read']}")
    print(f"Rows missing MSKU: {summary['rows_missing_sku']}")
    print(f"Rows missing total value: {summary['rows_missing_total_value']}")
    print(f"Duplicate MSKUs: {len(summary['duplicate_skus'])}")
    print(f"Total on-hand units: {summary['total_on_hand_units']}")
    print(f"Total inbound units: {summary['total_inbound_units']}")
    print(f"Total unlisted units: {summary['total_unlisted_units']}")
    print(f"Total value: ${summary['total_value']:,.2f}")

    if summary["duplicate_skus"]:
        print("\nFirst duplicate MSKUs:")
        for sku in summary["duplicate_skus"][:10]:
            print(f"- {sku}")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def to_money(value: Any) -> float | None:
    text = clean_text(value)
    if text is None:
        return None
    text = text.replace("$", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def chunks(rows: list[Any], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


if __name__ == "__main__":
    raise SystemExit(main())
