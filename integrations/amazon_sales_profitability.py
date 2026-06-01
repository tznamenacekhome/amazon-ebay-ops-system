"""Calculate Amazon sales profitability rollups.

Profitability is backend-owned. This script reads Amazon sales order/item rows,
financial events, optional Veeqo label data, and legacy InventoryLab valuation
cost basis, then writes amazon_sales_profitability rows.
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("amazon_sales_profitability")
BATCH_SIZE = 200
FBA_FULFILLMENT_FEE_KEYWORDS = ("fba", "fulfillment")
MIN_PURCHASE_DATE = "2025-01-01T00:00:00Z"


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
        orders = fetch_orders(
            supabase,
            order_id=args.order_id,
            missing_fees_only=args.missing_fees_only,
            purchase_date_start=args.purchase_date_start,
            purchase_date_end=args.purchase_date_end,
            limit=args.limit,
        )
        if not orders:
            LOGGER.warning("No Amazon sales orders found for profitability calculation.")
            return 0

        rows: list[dict[str, Any]] = []
        consumption_rows: list[dict[str, Any]] = []
        for order in orders:
            order_rows, order_consumption = build_order_profitability(supabase, order)
            rows.extend(order_rows)
            consumption_rows.extend(order_consumption)

        print_summary(rows, apply=args.apply)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        upsert_rows(
            supabase,
            "amazon_sales_profitability",
            rows,
            "amazon_order_id,amazon_order_item_id",
        )
        refresh_consumption_rows(supabase, args.order_id, orders, consumption_rows)
        LOGGER.info("Amazon sales profitability complete. rows=%s", len(rows))
        return 0
    except Exception as error:  # noqa: BLE001
        LOGGER.exception("Amazon sales profitability failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calculate Amazon sales profitability rollups."
    )
    parser.add_argument("--order-id", help="Target one Amazon order ID.")
    parser.add_argument(
        "--purchase-date-start",
        help="Stored order purchase_date lower bound as ISO timestamp.",
    )
    parser.add_argument(
        "--purchase-date-end",
        help="Stored order purchase_date upper bound as ISO timestamp.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum stored orders to process. Defaults to 500 for recent-order mode.",
    )
    parser.add_argument(
        "--missing-fees-only",
        action="store_true",
        help="Only recalculate orders currently stored with missing fee data.",
    )
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run; default mode.")
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def fetch_orders(
    supabase,
    *,
    order_id: str | None,
    missing_fees_only: bool,
    purchase_date_start: str | None,
    purchase_date_end: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    request = supabase.table("amazon_sales_orders").select("*")
    if order_id:
        request = request.eq("amazon_order_id", order_id)
    effective_start = max_iso(purchase_date_start, MIN_PURCHASE_DATE)
    if effective_start:
        request = request.gte("purchase_date", effective_start)
    if purchase_date_end:
        request = request.lt("purchase_date", purchase_date_end)
    if missing_fees_only and not order_id:
        order_ids = fetch_missing_fee_order_ids(
            supabase,
            purchase_date_start=effective_start,
            purchase_date_end=purchase_date_end,
            limit=limit,
        )
        if not order_ids:
            return []
        request = request.in_("amazon_order_id", order_ids)
    if purchase_date_start or purchase_date_end:
        request = request.order("purchase_date", desc=False)
        if limit:
            request = request.limit(max(limit, 1))
    else:
        request = request.order("purchase_date", desc=True).limit(max(limit or 500, 1))

    result = request.execute()
    return result.data or []


def fetch_missing_fee_order_ids(
    supabase,
    *,
    purchase_date_start: str | None,
    purchase_date_end: str | None,
    limit: int | None,
) -> list[str]:
    request = (
        supabase.table("vw_amazon_sales_orders_recent")
        .select("amazon_order_id,purchase_date")
        .eq("data_status", "missing_fees")
    )
    if purchase_date_start:
        request = request.gte("purchase_date", purchase_date_start)
    if purchase_date_end:
        request = request.lt("purchase_date", purchase_date_end)
    request = request.order("purchase_date", desc=False)
    if limit:
        request = request.limit(max(limit, 1))
    result = request.execute()
    seen: set[str] = set()
    order_ids: list[str] = []
    for row in result.data or []:
        order_id = row.get("amazon_order_id")
        if order_id and order_id not in seen:
            seen.add(order_id)
            order_ids.append(order_id)
    return order_ids


def build_order_profitability(
    supabase,
    order: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    amazon_order_id = order["amazon_order_id"]
    items = fetch_order_items(supabase, amazon_order_id)
    financial_events = fetch_financial_events(supabase, amazon_order_id)
    label_cost = fetch_veeqo_label_cost(supabase, amazon_order_id)
    rows: list[dict[str, Any]] = []
    consumption_rows: list[dict[str, Any]] = []

    for item in items:
        item_id = item["amazon_order_item_id"]
        quantity = int(item.get("quantity_ordered") or item.get("quantity_shipped") or 0)
        sale_price = item_sale_price(item)
        item_events = [
            event
            for event in financial_events
            if not event.get("amazon_order_item_id")
            or event.get("amazon_order_item_id") == item_id
        ]
        fee_totals = split_fee_totals(item_events)
        fulfillment_cost, fulfillment_source = fulfillment_cost_for_order(
            order,
            fee_totals["fba_fulfillment_fee"],
            label_cost,
        )
        existing_fifo_consumption = fetch_existing_mbop_fifo_consumption(supabase, item_id)
        if existing_fifo_consumption:
            cogs = round(
                sum(to_float(row.get("total_cogs")) or 0 for row in existing_fifo_consumption),
                2,
            )
            cogs_source = "mbop_fifo"
            cogs_reference = None
        else:
            cogs, cogs_source, cogs_reference = lookup_cogs(supabase, item, quantity)
        amazon_fees = fee_totals["amazon_fees_excluding_fulfillment"]

        net_profit = None
        roi = None
        if sale_price is not None and amazon_fees is not None and fulfillment_cost is not None and cogs is not None:
            net_profit = round(sale_price - amazon_fees - fulfillment_cost - cogs, 2)
            denominator = cogs + fulfillment_cost
            roi = round(net_profit / denominator, 4) if denominator > 0 else None

        data_status = data_status_for_row(
            order,
            amazon_fees=amazon_fees,
            fees_present=fee_totals["fees_present"],
            fulfillment_cost=fulfillment_cost,
            cogs=cogs,
        )
        row = {
            "amazon_order_id": amazon_order_id,
            "amazon_order_item_id": item_id,
            "asin": item.get("asin"),
            "seller_sku": item.get("seller_sku"),
            "title": item.get("title"),
            "quantity": quantity,
            "sale_price": sale_price,
            "amazon_fees_excluding_fulfillment": amazon_fees,
            "fulfillment_cost": fulfillment_cost,
            "fulfillment_cost_source": fulfillment_source,
            "cogs": cogs,
            "cogs_source": cogs_source,
            "net_profit": net_profit,
            "roi": roi,
            "data_status": data_status,
        }
        rows.append(row)

        if existing_fifo_consumption:
            consumption_rows.extend(
                {
                    "amazon_order_id": amazon_order_id,
                    "amazon_order_item_id": item_id,
                    "asin": row.get("asin"),
                    "seller_sku": row.get("seller_sku"),
                    "quantity_consumed": row.get("quantity_consumed"),
                    "unit_cogs": row.get("unit_cogs"),
                    "total_cogs": row.get("total_cogs"),
                    "cost_source": row.get("cost_source"),
                    "source_reference_type": row.get("source_reference_type"),
                    "source_reference_id": row.get("source_reference_id"),
                }
                for row in existing_fifo_consumption
            )
        elif cogs is not None and quantity > 0 and cogs_reference:
            consumption_rows.append(
                {
                    "amazon_order_id": amazon_order_id,
                    "amazon_order_item_id": item_id,
                    "asin": item.get("asin"),
                    "seller_sku": item.get("seller_sku"),
                    "quantity_consumed": quantity,
                    "unit_cogs": round(cogs / quantity, 4),
                    "total_cogs": round(cogs, 4),
                    "cost_source": cogs_source,
                    "source_reference_type": cogs_reference["type"],
                    "source_reference_id": cogs_reference["id"],
                }
            )

    return rows, consumption_rows


def fetch_order_items(supabase, amazon_order_id: str) -> list[dict[str, Any]]:
    result = (
        supabase.table("amazon_sales_order_items")
        .select("*")
        .eq("amazon_order_id", amazon_order_id)
        .execute()
    )
    return result.data or []


def fetch_financial_events(supabase, amazon_order_id: str) -> list[dict[str, Any]]:
    result = (
        supabase.table("amazon_sales_financial_events")
        .select("*")
        .eq("amazon_order_id", amazon_order_id)
        .execute()
    )
    return result.data or []


def fetch_veeqo_label_cost(supabase, amazon_order_id: str) -> float | None:
    result = (
        supabase.table("veeqo_sales_shipments")
        .select("label_cost_amount")
        .eq("amazon_order_id", amazon_order_id)
        .execute()
    )
    amounts = [to_float(row.get("label_cost_amount")) for row in result.data or []]
    amounts = [amount for amount in amounts if amount is not None]
    return round(sum(amounts), 2) if amounts else None


def fetch_existing_mbop_fifo_consumption(
    supabase,
    amazon_order_item_id: str,
) -> list[dict[str, Any]]:
    result = (
        supabase.table("amazon_sales_cogs_consumption")
        .select(
            "asin,seller_sku,quantity_consumed,unit_cogs,total_cogs,cost_source,"
            "source_reference_type,source_reference_id"
        )
        .eq("amazon_order_item_id", amazon_order_item_id)
        .eq("cost_source", "mbop_fifo")
        .execute()
    )
    return result.data or []


def item_sale_price(item: dict[str, Any]) -> float | None:
    values = [
        to_float(item.get("item_price_amount")),
        to_float(item.get("shipping_price_amount")),
        to_float(item.get("gift_wrap_price_amount")),
    ]
    discounts = [
        to_float(item.get("item_promotion_discount_amount")),
        to_float(item.get("ship_promotion_discount_amount")),
    ]
    if all(value is None for value in values):
        return None
    return round(sum(value or 0 for value in values) - sum(discount or 0 for discount in discounts), 2)


def split_fee_totals(events: list[dict[str, Any]]) -> dict[str, Any]:
    amazon_fees = 0.0
    fba_fee = 0.0
    fees_present = False

    for event in events:
        fee_type = (event.get("fee_type") or "").lower()
        amount = to_float(event.get("amount"))
        if amount is None or not fee_type:
            continue
        fees_present = True
        cost_amount = abs(amount)
        if all(keyword in fee_type for keyword in FBA_FULFILLMENT_FEE_KEYWORDS):
            fba_fee += cost_amount
        else:
            amazon_fees += cost_amount

    return {
        "amazon_fees_excluding_fulfillment": round(amazon_fees, 2),
        "fba_fulfillment_fee": round(fba_fee, 2),
        "fees_present": fees_present,
    }


def fulfillment_cost_for_order(
    order: dict[str, Any],
    fba_fee: float,
    label_cost: float | None,
) -> tuple[float | None, str]:
    fulfillment_channel = (order.get("fulfillment_channel") or "").lower()
    if fulfillment_channel in {"afn", "amazon", "amazonfulfilled"}:
        return (fba_fee if fba_fee > 0 else None, "amazon_fba_fee" if fba_fee > 0 else "missing")
    if label_cost is not None:
        return label_cost, "veeqo_label"
    return None, "missing"


def lookup_cogs(
    supabase,
    item: dict[str, Any],
    quantity: int,
) -> tuple[float | None, str, dict[str, str] | None]:
    seller_sku = item.get("seller_sku")
    asin = item.get("asin")

    legacy = fetch_inventorylab_valuation(supabase, seller_sku)
    if legacy and to_float(legacy.get("cost_per_unit")) is not None and quantity > 0:
        unit_cost = to_float(legacy.get("cost_per_unit")) or 0
        return (
            round(unit_cost * quantity, 2),
            "inventorylab_legacy",
            {
                "type": "inventorylab_legacy_valuation",
                "id": legacy["inventorylab_inventory_valuation_snapshot_id"],
            },
        )

    backfill = fetch_inventorylab_backfill(supabase, seller_sku, asin)
    if backfill and to_float(backfill.get("active_cost_per_unit")) is not None and quantity > 0:
        unit_cost = to_float(backfill.get("active_cost_per_unit")) or 0
        return (
            round(unit_cost * quantity, 2),
            "inventorylab_legacy",
            {
                "type": "inventorylab_legacy_valuation",
                "id": backfill["inventorylab_active_inventory_backfill_id"],
            },
        )

    return None, "missing", None


def fetch_inventorylab_valuation(supabase, seller_sku: str | None) -> dict[str, Any] | None:
    if not seller_sku:
        return None
    result = (
        supabase.table("vw_latest_inventorylab_inventory_valuation")
        .select("*")
        .eq("seller_sku", seller_sku)
        .limit(1)
        .execute()
    )
    return (result.data or [None])[0]


def fetch_inventorylab_backfill(
    supabase,
    seller_sku: str | None,
    asin: str | None,
) -> dict[str, Any] | None:
    request = (
        supabase.table("inventorylab_active_inventory_backfill")
        .select("*")
        .eq("match_status", "matched")
        .limit(1)
    )
    if seller_sku:
        request = request.eq("seller_sku", seller_sku)
    elif asin:
        request = request.eq("asin", asin)
    else:
        return None
    result = request.execute()
    return (result.data or [None])[0]


def data_status_for_row(
    order: dict[str, Any],
    *,
    amazon_fees: float | None,
    fees_present: bool,
    fulfillment_cost: float | None,
    cogs: float | None,
) -> str:
    order_status = (order.get("order_status") or "").lower()
    if order_status == "canceled":
        return "cancelled"
    if "refund" in order_status:
        return "refunded"
    if not fees_present or amazon_fees is None:
        return "missing_fees"
    if fulfillment_cost is None:
        return "missing_fulfillment_cost"
    if cogs is None:
        return "missing_cogs"
    return "complete"


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()


def refresh_consumption_rows(
    supabase,
    requested_order_id: str | None,
    orders: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    order_ids = [requested_order_id] if requested_order_id else [order["amazon_order_id"] for order in orders]
    for order_id in order_ids:
        supabase.table("amazon_sales_cogs_consumption").delete().eq(
            "amazon_order_id",
            order_id,
        ).execute()
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_sales_cogs_consumption").insert(chunk).execute()


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def max_iso(left: str | None, right: str | None) -> str | None:
    values = [value for value in (left, right) if value]
    return max(values) if values else None


def print_summary(rows: list[dict[str, Any]], *, apply: bool) -> None:
    mode = "write" if apply else "dry run"
    print(f"Amazon sales profitability {mode}")
    print("--------------------------------")
    print(f"Rows: {len(rows)}")
    for row in rows[:10]:
        print(
            f"- {row['amazon_order_id']} {row['asin'] or '--'} "
            f"sale={row['sale_price']} profit={row['net_profit']} "
            f"roi={row['roi']} status={row['data_status']}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
