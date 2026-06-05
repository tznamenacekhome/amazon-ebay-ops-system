"""Apply FIFO COGS from eBay purchase items to Amazon sales.

This is a controlled backfill utility, not a scheduled sync. It uses costed
eBay purchase_items plus explicitly listed legacy purchase_items as ASIN FIFO
source lots and writes sales COGS consumption rows without changing purchases,
purchase_items, or receiving workflow state.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("apply_ebay_purchase_fifo_cogs")
BATCH_SIZE = 500
MIN_SALE_DATE = "2025-01-01T00:00:00Z"
DEFAULT_REVIEW_EXPORT = Path("exports/missing_amazon_cogs_review.csv")
EXCLUDED_PURCHASE_STATUSES = {"cancelled", "return_opened", "return_pending"}


@dataclass
class SourceLot:
    source_id: str
    asin: str
    order_date: date
    supplier_order_id: str | None
    title: str | None
    quantity_available: int
    unit_cost: Decimal
    remaining: int


@dataclass
class Allocation:
    lot: SourceLot
    quantity: int


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
        lots = fetch_source_lots(supabase)
        pools = build_pools(lots)
        deduct_existing_purchase_item_consumption(supabase, pools)
        plan = build_sales_plan(supabase, pools)

        print_summary(lots, plan)
        write_review_export(plan["skipped_rows"], args.review_export)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        apply_sales_plan(supabase, plan)
        LOGGER.info(
            "eBay purchase FIFO COGS applied. sales_rows=%s consumption_rows=%s",
            len(plan["profitability_updates"]),
            len(plan["consumption_rows"]),
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("eBay purchase FIFO COGS allocation failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply FIFO COGS from eBay purchase items to Amazon sales."
    )
    parser.add_argument("--apply", action="store_true", help="Write allocations.")
    parser.add_argument(
        "--review-export",
        type=Path,
        default=DEFAULT_REVIEW_EXPORT,
        help="CSV path for rows still missing COGS after allocation planning.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def fetch_source_lots(supabase) -> list[SourceLot]:
    excluded_item_ids = fetch_excluded_purchase_item_ids(supabase)
    rows = fetch_all(
        supabase,
        "vw_purchases_dashboard",
        "item_id,order_date,supplier,supplier_order_id,title,asin,quantity,unit_cost,current_status",
    )
    lots: list[SourceLot] = []
    for row in rows:
        item_id = row.get("item_id")
        asin = clean_asin(row.get("asin"))
        order_date = parse_optional_date(row.get("order_date"))
        quantity = to_int(row.get("quantity")) or 0
        unit_cost = to_decimal(row.get("unit_cost"))
        status = clean_text(row.get("current_status")).lower()
        supplier = clean_text(row.get("supplier")).lower()

        if item_id in excluded_item_ids:
            continue
        if supplier != "ebay" and status != "listed":
            continue
        if status in EXCLUDED_PURCHASE_STATUSES:
            continue
        if not asin or asin == "N/A" or not order_date or not unit_cost:
            continue
        if quantity <= 0 or unit_cost <= 0:
            continue

        lots.append(
            SourceLot(
                source_id=item_id,
                asin=asin,
                order_date=order_date,
                supplier_order_id=row.get("supplier_order_id"),
                title=row.get("title"),
                quantity_available=quantity,
                unit_cost=unit_cost,
                remaining=quantity,
            )
        )
    return sorted(lots, key=lambda lot: (lot.asin, lot.order_date, lot.source_id))


def fetch_excluded_purchase_item_ids(supabase) -> set[str]:
    return {
        row["item_id"]
        for row in fetch_all(
            supabase,
            "purchase_items",
            "item_id,exclude_from_purchase_reporting",
        )
        if row.get("exclude_from_purchase_reporting") is True
    }


def build_pools(lots: list[SourceLot]) -> dict[str, list[SourceLot]]:
    pools: dict[str, list[SourceLot]] = {}
    for lot in lots:
        pools.setdefault(lot.asin, []).append(lot)
    return pools


def deduct_existing_purchase_item_consumption(
    supabase,
    pools: dict[str, list[SourceLot]],
) -> None:
    consumed_by_source: dict[str, int] = {}
    rows = fetch_all(
        supabase,
        "amazon_sales_cogs_consumption",
        "source_reference_id,quantity_consumed,cost_source,source_reference_type",
    )
    for row in rows:
        if (
            row.get("cost_source") != "mbop_fifo"
            or row.get("source_reference_type") != "purchase_item"
            or not row.get("source_reference_id")
        ):
            continue
        source_id = row["source_reference_id"]
        consumed_by_source[source_id] = consumed_by_source.get(source_id, 0) + int(
            row.get("quantity_consumed") or 0
        )

    if not consumed_by_source:
        return

    lots_by_source = {
        lot.source_id: lot
        for lots in pools.values()
        for lot in lots
    }
    for source_id, quantity in consumed_by_source.items():
        lot = lots_by_source.get(source_id)
        if lot:
            lot.remaining = max(lot.remaining - quantity, 0)


def build_sales_plan(
    supabase,
    pools: dict[str, list[SourceLot]],
) -> dict[str, list[dict[str, Any]]]:
    profit_rows = fetch_all(
        supabase,
        "amazon_sales_profitability",
        "amazon_order_id,amazon_order_item_id,asin,seller_sku,title,quantity,cogs,"
        "cogs_source,data_status,sale_price,amazon_fees_excluding_fulfillment,"
        "fulfillment_cost",
    )
    order_rows = fetch_all(
        supabase,
        "amazon_sales_orders",
        "amazon_order_id,purchase_date,order_status",
    )
    orders_by_id = {row["amazon_order_id"]: row for row in order_rows}
    source_asins = set(pools)
    candidates = [
        row
        for row in profit_rows
        if clean_asin(row.get("asin")) in source_asins
        and int(row.get("quantity") or 0) > 0
        and (row.get("cogs") is None or row.get("cogs_source") == "missing")
        and row.get("data_status") == "missing_cogs"
        and (orders_by_id.get(row["amazon_order_id"], {}).get("purchase_date") or "") >= MIN_SALE_DATE
    ]
    candidates.sort(
        key=lambda row: (
            orders_by_id.get(row["amazon_order_id"], {}).get("purchase_date") or "",
            row["amazon_order_id"],
            row["amazon_order_item_id"],
        )
    )

    profitability_updates: list[dict[str, Any]] = []
    consumption_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for row in candidates:
        asin = clean_asin(row.get("asin"))
        sale_date = parse_optional_datetime(
            orders_by_id.get(row["amazon_order_id"], {}).get("purchase_date")
        )
        quantity = int(row.get("quantity") or 0)
        allocations = allocate(
            pools,
            asin=asin,
            quantity=quantity,
            max_source_date=sale_date.date() if sale_date else None,
        )
        if not allocations:
            skipped_rows.append(
                {
                    **row,
                    "purchase_date": orders_by_id.get(row["amazon_order_id"], {}).get("purchase_date"),
                    "skip_reason": skip_reason(pools, asin, quantity, sale_date.date() if sale_date else None),
                }
            )
            continue

        cogs = sum(Decimal(allocation.quantity) * allocation.lot.unit_cost for allocation in allocations)
        cogs_float = float(cogs.quantize(Decimal("0.01")))
        fulfillment_cost = to_float(row.get("fulfillment_cost"))
        amazon_fees = to_float(row.get("amazon_fees_excluding_fulfillment"))
        sale_price = to_float(row.get("sale_price"))
        net_profit = None
        roi = None
        if sale_price is not None and amazon_fees is not None and fulfillment_cost is not None:
            net_profit = round(sale_price - amazon_fees - fulfillment_cost - cogs_float, 2)
            denominator = cogs_float + fulfillment_cost
            roi = round(net_profit / denominator, 4) if denominator > 0 else None

        profitability_updates.append(
            {
                "amazon_order_id": row["amazon_order_id"],
                "amazon_order_item_id": row["amazon_order_item_id"],
                "cogs": cogs_float,
                "cogs_source": "mbop_fifo",
                "net_profit": net_profit,
                "roi": roi,
                "data_status": status_after_cogs(row),
            }
        )
        for allocation in allocations:
            consumption_rows.append(
                {
                    "amazon_order_id": row["amazon_order_id"],
                    "amazon_order_item_id": row["amazon_order_item_id"],
                    "asin": asin,
                    "seller_sku": row.get("seller_sku"),
                    "quantity_consumed": allocation.quantity,
                    "unit_cogs": str(allocation.lot.unit_cost),
                    "total_cogs": str(
                        (Decimal(allocation.quantity) * allocation.lot.unit_cost).quantize(
                            Decimal("0.0001")
                        )
                    ),
                    "cost_source": "mbop_fifo",
                    "source_reference_type": "purchase_item",
                    "source_reference_id": allocation.lot.source_id,
                }
            )

    return {
        "profitability_updates": profitability_updates,
        "consumption_rows": consumption_rows,
        "skipped_rows": skipped_rows,
    }


def allocate(
    pools: dict[str, list[SourceLot]],
    *,
    asin: str,
    quantity: int,
    max_source_date: date | None,
) -> list[Allocation] | None:
    if quantity <= 0:
        return []
    ordered_lots = [
        lot
        for lot in pools.get(asin, [])
        if lot.remaining > 0 and (max_source_date is None or lot.order_date <= max_source_date)
    ]
    if sum(lot.remaining for lot in ordered_lots) < quantity:
        return None

    needed = quantity
    allocations: list[Allocation] = []
    for lot in ordered_lots:
        consumed = min(needed, lot.remaining)
        if consumed <= 0:
            continue
        lot.remaining -= consumed
        needed -= consumed
        allocations.append(Allocation(lot=lot, quantity=consumed))
        if needed == 0:
            return allocations
    return None


def skip_reason(
    pools: dict[str, list[SourceLot]],
    asin: str,
    quantity: int,
    max_source_date: date | None,
) -> str:
    lots = pools.get(asin, [])
    if not lots:
        return "no_purchase_lot_for_asin"
    available_before_sale = sum(
        lot.remaining
        for lot in lots
        if max_source_date is None or lot.order_date <= max_source_date
    )
    if available_before_sale < quantity:
        total_remaining = sum(lot.remaining for lot in lots)
        if total_remaining >= quantity:
            return "purchase_lot_after_sale_date"
        return "insufficient_fifo_quantity"
    return "unallocated"


def apply_sales_plan(supabase, plan: dict[str, list[dict[str, Any]]]) -> None:
    for row in plan["profitability_updates"]:
        supabase.table("amazon_sales_cogs_consumption").delete().eq(
            "amazon_order_item_id",
            row["amazon_order_item_id"],
        ).eq("cost_source", "mbop_fifo").eq("source_reference_type", "purchase_item").execute()

    for chunk in chunks(plan["consumption_rows"], BATCH_SIZE):
        supabase.table("amazon_sales_cogs_consumption").insert(chunk).execute()

    for row in plan["profitability_updates"]:
        supabase.table("amazon_sales_profitability").update(
            {
                "cogs": row["cogs"],
                "cogs_source": row["cogs_source"],
                "net_profit": row["net_profit"],
                "roi": row["roi"],
                "data_status": row["data_status"],
                "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        ).eq("amazon_order_id", row["amazon_order_id"]).eq(
            "amazon_order_item_id",
            row["amazon_order_item_id"],
        ).execute()


def status_after_cogs(row: dict[str, Any]) -> str:
    if row.get("data_status") == "missing_cogs":
        return "complete"
    return row.get("data_status") or "complete"


def write_review_export(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "amazon_order_id",
        "amazon_order_item_id",
        "purchase_date",
        "asin",
        "seller_sku",
        "title",
        "quantity",
        "data_status",
        "skip_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def print_summary(
    lots: list[SourceLot],
    plan: dict[str, list[dict[str, Any]]],
) -> None:
    print("eBay purchase FIFO COGS allocation")
    print("----------------------------------")
    print(f"Source lots: {len(lots)}")
    print(f"Source quantity: {sum(lot.quantity_available for lot in lots)}")
    print(f"Sales rows to update: {len(plan['profitability_updates'])}")
    print(f"Sales consumption rows: {len(plan['consumption_rows'])}")
    print(f"Sales rows skipped: {len(plan['skipped_rows'])}")
    print(
        "Skipped by reason: "
        f"{dict(sorted(count_by(plan['skipped_rows'], 'skip_reason').items()))}"
    )
    print(
        "Remaining source units: "
        f"{sum(lot.remaining for lot in lots)} of {sum(lot.quantity_available for lot in lots)}"
    )


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


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


def parse_optional_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def parse_optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(Decimal(str(value)))


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


if __name__ == "__main__":
    raise SystemExit(main())
