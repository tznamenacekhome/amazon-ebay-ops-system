"""Apply FIFO COGS from non-eBay purchase sources to Amazon sales/inventory.

This is a controlled backfill utility, not a scheduled sync. It matches by ASIN,
allocates sales first by Amazon purchase date, then assigns remaining source
layers to current/inbound Amazon inventory cost layers.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("apply_non_ebay_fifo_cogs")
BATCH_SIZE = 250
DEFAULT_SHIPMENT_SOURCE_DATE = date(2026, 5, 17)
DEFAULT_SHIPMENT_ID = "FBA19F55XZJG"


@dataclass
class SourceLot:
    source_id: str
    asin: str
    order_date: date
    source_row_number: int
    quantity_available: int
    unit_cost: Decimal
    supplier: str | None
    supplier_order_number: str | None
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
        deduct_existing_sales_consumption(supabase, pools)

        sales_plan = build_sales_plan(
            supabase,
            pools,
            reserve_source_date=args.shipment_source_date,
        )
        inventory_plan = build_inventory_plan(
            supabase,
            pools,
            allocation_run_id=str(uuid4()),
            shipment_source_date=args.shipment_source_date,
            shipment_id=args.shipment_id,
        )

        print_summary(lots, sales_plan, inventory_plan)
        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        apply_sales_plan(supabase, sales_plan)
        apply_inventory_plan(supabase, inventory_plan)
        LOGGER.info(
            "FIFO COGS applied. sales_rows=%s inventory_layers=%s",
            len(sales_plan["profitability_updates"]),
            len(inventory_plan),
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("FIFO COGS allocation failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply FIFO COGS from non-eBay purchase source rows."
    )
    parser.add_argument("--apply", action="store_true", help="Write allocations.")
    parser.add_argument(
        "--shipment-source-date",
        type=parse_date,
        default=DEFAULT_SHIPMENT_SOURCE_DATE,
        help="Source order date reserved for the known in-transit FBA shipment.",
    )
    parser.add_argument(
        "--shipment-id",
        default=DEFAULT_SHIPMENT_ID,
        help="FBA shipment ID for the reserved source order date.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def fetch_source_lots(supabase) -> list[SourceLot]:
    rows = fetch_all(
        supabase,
        "non_ebay_purchase_cogs_sources",
        "non_ebay_purchase_cogs_source_id,asin,order_date,source_row_number,"
        "quantity,received_by_prep_center_quantity,damaged_quantity,unit_cost,"
        "supplier,supplier_order_number",
    )
    lots: list[SourceLot] = []
    for row in rows:
        order_date = parse_optional_date(row.get("order_date"))
        unit_cost = to_decimal(row.get("unit_cost"))
        asin = clean_asin(row.get("asin"))
        if not order_date or not unit_cost or not asin:
            continue
        quantity_available = source_available_quantity(row)
        if quantity_available <= 0:
            continue
        lots.append(
            SourceLot(
                source_id=row["non_ebay_purchase_cogs_source_id"],
                asin=asin,
                order_date=order_date,
                source_row_number=int(row["source_row_number"]),
                quantity_available=quantity_available,
                unit_cost=unit_cost,
                supplier=row.get("supplier"),
                supplier_order_number=row.get("supplier_order_number"),
                remaining=quantity_available,
            )
        )
    return sorted(lots, key=lambda lot: (lot.asin, lot.order_date, lot.source_row_number))


def source_available_quantity(row: dict[str, Any]) -> int:
    received = to_int(row.get("received_by_prep_center_quantity"))
    if received is not None:
        return max(received, 0)
    quantity = to_int(row.get("quantity")) or 0
    damaged = to_int(row.get("damaged_quantity")) or 0
    return max(quantity - damaged, 0)


def build_pools(lots: list[SourceLot]) -> dict[str, list[SourceLot]]:
    pools: dict[str, list[SourceLot]] = {}
    for lot in lots:
        pools.setdefault(lot.asin, []).append(lot)
    return pools


def deduct_existing_sales_consumption(
    supabase,
    pools: dict[str, list[SourceLot]],
) -> None:
    consumption_rows = fetch_all(
        supabase,
        "amazon_sales_cogs_consumption",
        "source_reference_id,quantity_consumed,cost_source,source_reference_type",
    )
    consumed_by_source: dict[str, int] = {}
    for row in consumption_rows:
        if (
            row.get("cost_source") != "mbop_fifo"
            or row.get("source_reference_type") != "non_ebay_purchase_cogs_source"
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
        if not lot:
            continue
        lot.remaining = max(lot.remaining - quantity, 0)


def build_sales_plan(
    supabase,
    pools: dict[str, list[SourceLot]],
    *,
    reserve_source_date: date,
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
            excluded_source_dates={reserve_source_date},
        )
        if not allocations:
            skipped_rows.append(row)
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
                    "source_reference_type": "non_ebay_purchase_cogs_source",
                    "source_reference_id": allocation.lot.source_id,
                }
            )

    return {
        "profitability_updates": profitability_updates,
        "consumption_rows": consumption_rows,
        "skipped_rows": skipped_rows,
    }


def build_inventory_plan(
    supabase,
    pools: dict[str, list[SourceLot]],
    *,
    allocation_run_id: str,
    shipment_source_date: date,
    shipment_id: str,
) -> list[dict[str, Any]]:
    latest_snapshots = fetch_latest_fba_snapshots(supabase)
    costed_skus = fetch_costed_skus(supabase)
    amazon_skus = {
        (row.get("seller_sku"), row.get("marketplace_id")): row
        for row in fetch_all(
            supabase,
            "amazon_skus",
            "amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name",
        )
    }

    layers: list[dict[str, Any]] = []
    for snapshot in latest_snapshots:
        seller_sku = snapshot.get("seller_sku")
        asin = clean_asin(snapshot.get("asin"))
        if not seller_sku or not asin or asin not in pools or seller_sku in costed_skus:
            continue

        sku_row = amazon_skus.get((seller_sku, snapshot.get("marketplace_id")), {})
        for inventory_state, quantity in inventory_state_quantities(snapshot):
            allocations = allocate_for_inventory_state(
                pools,
                asin=asin,
                quantity=quantity,
                inventory_state=inventory_state,
                shipment_source_date=shipment_source_date,
            )
            if not allocations:
                LOGGER.warning(
                    "Unable to assign inventory COGS for %s %s quantity=%s",
                    seller_sku,
                    inventory_state,
                    quantity,
                )
                continue
            for allocation in allocations:
                is_known_shipment = (
                    inventory_state == "inbound_shipped"
                    and allocation.lot.order_date == shipment_source_date
                )
                total_cogs = (Decimal(allocation.quantity) * allocation.lot.unit_cost).quantize(
                    Decimal("0.0001")
                )
                layers.append(
                    {
                        "allocation_run_id": allocation_run_id,
                        "amazon_sku_id": sku_row.get("amazon_sku_id"),
                        "marketplace_id": snapshot.get("marketplace_id"),
                        "seller_sku": seller_sku,
                        "asin": asin,
                        "fnsku": snapshot.get("fnsku"),
                        "title": snapshot.get("product_name"),
                        "inventory_state": inventory_state,
                        "fba_shipment_id": shipment_id if is_known_shipment else None,
                        "snapshot_captured_at": snapshot.get("captured_at"),
                        "quantity_assigned": allocation.quantity,
                        "unit_cogs": str(allocation.lot.unit_cost),
                        "total_cogs": str(total_cogs),
                        "cost_source": "mbop_fifo",
                        "source_reference_type": "non_ebay_purchase_cogs_source",
                        "source_reference_id": allocation.lot.source_id,
                        "source_order_date": allocation.lot.order_date.isoformat(),
                        "allocation_method": "fifo_asin",
                        "active": True,
                        "notes": inventory_layer_note(allocation, shipment_id, is_known_shipment),
                        "raw_allocation_json": {
                            "source_supplier": allocation.lot.supplier,
                            "source_supplier_order_number": allocation.lot.supplier_order_number,
                            "source_row_number": allocation.lot.source_row_number,
                            "source_quantity_available": allocation.lot.quantity_available,
                        },
                    }
                )
    return layers


def allocate_for_inventory_state(
    pools: dict[str, list[SourceLot]],
    *,
    asin: str,
    quantity: int,
    inventory_state: str,
    shipment_source_date: date,
) -> list[Allocation]:
    preferred_dates = {shipment_source_date} if inventory_state == "inbound_shipped" else None
    return allocate(pools, asin=asin, quantity=quantity, preferred_source_dates=preferred_dates)


def allocate(
    pools: dict[str, list[SourceLot]],
    *,
    asin: str,
    quantity: int,
    max_source_date: date | None = None,
    excluded_source_dates: set[date] | None = None,
    preferred_source_dates: set[date] | None = None,
) -> list[Allocation] | None:
    if quantity <= 0:
        return []

    candidates = []
    fallback = []
    for lot in pools.get(asin, []):
        if lot.remaining <= 0:
            continue
        if max_source_date and lot.order_date > max_source_date:
            continue
        if excluded_source_dates and lot.order_date in excluded_source_dates:
            continue
        if preferred_source_dates and lot.order_date in preferred_source_dates:
            candidates.append(lot)
        else:
            fallback.append(lot)

    ordered_lots = candidates + ([] if preferred_source_dates else fallback)
    if preferred_source_dates:
        ordered_lots += fallback

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


def apply_sales_plan(supabase, plan: dict[str, list[dict[str, Any]]]) -> None:
    for row in plan["profitability_updates"]:
        supabase.table("amazon_sales_cogs_consumption").delete().eq(
            "amazon_order_item_id",
            row["amazon_order_item_id"],
        ).eq("cost_source", "mbop_fifo").execute()

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


def apply_inventory_plan(supabase, layers: list[dict[str, Any]]) -> None:
    existing_layers = (
        supabase.table("amazon_inventory_cogs_layers")
        .select("amazon_inventory_cogs_layer_id,inventory_state")
        .eq("active", True)
        .eq("cost_source", "mbop_fifo")
        .eq("source_reference_type", "non_ebay_purchase_cogs_source")
        .execute()
        .data
        or []
    )
    merchant_states = {"merchant_available", "merchant_allocated"}
    for layer in existing_layers:
        if layer.get("inventory_state") in merchant_states:
            continue
        supabase.table("amazon_inventory_cogs_layers").update({"active": False}).eq(
            "amazon_inventory_cogs_layer_id",
            layer["amazon_inventory_cogs_layer_id"],
        ).execute()
    for chunk in chunks(layers, BATCH_SIZE):
        supabase.table("amazon_inventory_cogs_layers").insert(chunk).execute()


def fetch_latest_fba_snapshots(supabase) -> list[dict[str, Any]]:
    snapshots = fetch_all(
        supabase,
        "amazon_fba_inventory_snapshots",
        "captured_at,marketplace_id,seller_sku,asin,fnsku,product_name,total_quantity,"
        "fulfillable_quantity,inbound_working_quantity,inbound_shipped_quantity,"
        "inbound_receiving_quantity,reserved_quantity,researching_quantity,"
        "unfulfillable_quantity",
    )
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshots:
        key = (row.get("seller_sku"), row.get("marketplace_id"))
        if key not in latest or (row.get("captured_at") or "") > (latest[key].get("captured_at") or ""):
            latest[key] = row
    return [row for row in latest.values() if int(row.get("total_quantity") or 0) > 0]


def fetch_costed_skus(supabase) -> set[str]:
    costed: set[str] = set()
    for row in fetch_all(supabase, "inventorylab_inventory_valuation_snapshots", "seller_sku,cost_per_unit"):
        if row.get("seller_sku") and row.get("cost_per_unit") is not None:
            costed.add(row["seller_sku"])
    for row in fetch_all(
        supabase,
        "inventorylab_active_inventory_backfill",
        "seller_sku,active_cost_per_unit,match_status",
    ):
        if (
            row.get("seller_sku")
            and row.get("match_status") == "matched"
            and row.get("active_cost_per_unit") is not None
        ):
            costed.add(row["seller_sku"])
    return costed


def inventory_state_quantities(snapshot: dict[str, Any]) -> list[tuple[str, int]]:
    states = [
        ("inbound_shipped", to_int(snapshot.get("inbound_shipped_quantity")) or 0),
        ("inbound_working", to_int(snapshot.get("inbound_working_quantity")) or 0),
        ("inbound_receiving", to_int(snapshot.get("inbound_receiving_quantity")) or 0),
        ("fulfillable", to_int(snapshot.get("fulfillable_quantity")) or 0),
        ("reserved", to_int(snapshot.get("reserved_quantity")) or 0),
        ("unfulfillable", to_int(snapshot.get("unfulfillable_quantity")) or 0),
    ]
    known_quantity = sum(quantity for _, quantity in states)
    total_quantity = to_int(snapshot.get("total_quantity")) or 0
    other = max(total_quantity - known_quantity, 0)
    if other:
        states.append(("other", other))
    return [(state, quantity) for state, quantity in states if quantity > 0]


def status_after_cogs(row: dict[str, Any]) -> str:
    if row.get("data_status") == "missing_cogs":
        return "complete"
    return row.get("data_status") or "complete"


def inventory_layer_note(allocation: Allocation, shipment_id: str, known_shipment: bool) -> str:
    if known_shipment:
        return f"Source lot is in FBA shipment {shipment_id}, still in transit as of allocation."
    return "FIFO ASIN allocation from non-eBay purchase COGS source."


def print_summary(
    lots: list[SourceLot],
    sales_plan: dict[str, list[dict[str, Any]]],
    inventory_plan: list[dict[str, Any]],
) -> None:
    print("Non-eBay FIFO COGS allocation")
    print("-----------------------------")
    print(f"Source lots: {len(lots)}")
    print(f"Sales rows to update: {len(sales_plan['profitability_updates'])}")
    print(f"Sales consumption rows: {len(sales_plan['consumption_rows'])}")
    print(f"Sales rows skipped for insufficient/invalid FIFO pool: {len(sales_plan['skipped_rows'])}")
    print(f"Inventory COGS layers to insert: {len(inventory_plan)}")
    print(
        "Inventory quantity assigned: "
        f"{sum(int(row['quantity_assigned']) for row in inventory_plan)}"
    )
    print(
        "Remaining source units: "
        f"{sum(lot.remaining for lot in lots)} of {sum(lot.quantity_available for lot in lots)}"
    )


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


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


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
