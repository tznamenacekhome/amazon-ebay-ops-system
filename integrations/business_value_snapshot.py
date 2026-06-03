"""Capture the daily MBOP total business value snapshot.

The snapshot mirrors the backend dashboard rollup: Amazon inventory value,
pre-Amazon inventory value, Amazon-held cash, Amazon-to-bank in-transit cash,
and YNAB Business category cash on hand.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("business_value_snapshot")

AMAZON_FBA_STATES = [
    "amazon_fba_sellable",
    "amazon_fba_reserved",
    "amazon_fba_unsellable_damaged",
    "amazon_fba_stranded",
]
AMAZON_OUTBOUND_STATES = [
    "outbound_to_amazon",
    "amazon_fba_inbound_receiving",
]
PRE_AMAZON_STATES = [
    "purchased_not_shipped",
    "shipped_not_delivered",
    "delivered_not_received",
    "received_unassigned",
    "received_assigned_amazon_not_sent",
]


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
        snapshot = build_snapshot(supabase, args.snapshot_date)
        print_summary(snapshot, write=args.apply)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase.table("business_value_snapshots").upsert(
            snapshot,
            on_conflict="snapshot_date",
        ).execute()
        LOGGER.info(
            "Business value snapshot upserted: date=%s total=%s",
            snapshot["snapshot_date"],
            snapshot["total_business_value"],
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("Business value snapshot failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture the daily MBOP total business value snapshot."
    )
    parser.add_argument(
        "--snapshot-date",
        default=dt.date.today().isoformat(),
        help="Snapshot date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the daily snapshot to Supabase.",
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


def build_snapshot(supabase, snapshot_date: str) -> dict[str, Any]:
    position_rows = fetch_all(
        supabase,
        "inventory_positions",
        "inventory_state,asin,quantity,total_cost,source_system",
    )
    cost_by_state = cost_by_inventory_state(position_rows)
    inventorylab_value = fetch_inventorylab_valuation(supabase)
    finance = fetch_latest_row(supabase, "vw_latest_amazon_finance_balance_snapshot")
    ynab = fetch_latest_business_ynab_row(supabase)

    amazon_at_fba_value = inventorylab_value or sum_states(cost_by_state, AMAZON_FBA_STATES)
    amazon_outbound_value = calculate_amazon_outbound_value(position_rows)
    amazon_inventory_value = amazon_at_fba_value + amazon_outbound_value
    pre_amazon_inventory_value = sum_states(cost_by_state, PRE_AMAZON_STATES)
    amazon_cash_balance = float((finance or {}).get("total_amazon_cash") or 0)
    amazon_cash_in_transit = float((finance or {}).get("in_transit_to_bank") or 0)
    cash_on_hand = float((ynab or {}).get("balance_currency") or 0)
    total_business_value = (
        amazon_inventory_value
        + pre_amazon_inventory_value
        + amazon_cash_balance
        + amazon_cash_in_transit
        + cash_on_hand
    )

    rollup = {
        "inventorylab_valuation_used": inventorylab_value is not None,
        "amazon_at_fba_value": round(amazon_at_fba_value, 2),
        "amazon_outbound_value": round(amazon_outbound_value, 2),
        "amazon_finance_snapshot_id": (finance or {}).get(
            "amazon_finance_balance_snapshot_id"
        ),
        "amazon_finance_in_transit_breakdown": (
            ((finance or {}).get("raw_financial_event_groups_json") or {})
            .get("inTransitBreakdown")
        ),
        "ynab_category_balance_snapshot_id": (ynab or {}).get(
            "ynab_category_balance_snapshot_id"
        ),
    }

    return {
        "snapshot_date": snapshot_date,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "amazon_inventory_value": round(amazon_inventory_value, 2),
        "pre_amazon_inventory_value": round(pre_amazon_inventory_value, 2),
        "amazon_cash_balance": round(amazon_cash_balance, 2),
        "amazon_cash_in_transit": round(amazon_cash_in_transit, 2),
        "cash_on_hand": round(cash_on_hand, 2),
        "total_business_value": round(total_business_value, 2),
        "raw_rollup_json": rollup,
    }


def cost_by_inventory_state(rows: list[dict[str, Any]]) -> dict[str, float]:
    costs: dict[str, float] = {}
    for row in rows:
        state = str(row.get("inventory_state") or "")
        costs[state] = costs.get(state, 0) + float(row.get("total_cost") or 0)
    return costs


def calculate_amazon_outbound_value(rows: list[dict[str, Any]]) -> float:
    outbound_cost = 0.0
    outbound_asins: set[str] = set()
    amazon_inbound_by_asin: dict[str, float] = {}

    for row in rows:
        state = str(row.get("inventory_state") or "")
        asin = str(row.get("asin") or "").strip().upper()
        cost = float(row.get("total_cost") or 0)

        if state == "outbound_to_amazon":
            outbound_cost += cost
            if asin:
                outbound_asins.add(asin)
        elif state == "amazon_fba_inbound_receiving" and asin:
            amazon_inbound_by_asin[asin] = amazon_inbound_by_asin.get(asin, 0) + cost

    uncovered_amazon_inbound_cost = sum(
        cost for asin, cost in amazon_inbound_by_asin.items() if asin not in outbound_asins
    )
    return outbound_cost + uncovered_amazon_inbound_cost


def fetch_all(supabase, table: str, columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            supabase.table(table)
            .select(columns)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def fetch_inventorylab_valuation(supabase) -> float | None:
    rows = fetch_all(
        supabase,
        "vw_latest_inventorylab_inventory_valuation",
        "total_value",
    )
    total = sum(float(row.get("total_value") or 0) for row in rows)
    return round(total, 2) if total > 0 else None


def fetch_latest_row(supabase, table: str) -> dict[str, Any] | None:
    response = supabase.table(table).select("*").limit(1).execute()
    return (response.data or [None])[0]


def fetch_latest_business_ynab_row(supabase) -> dict[str, Any] | None:
    response = (
        supabase.table("vw_latest_ynab_category_balance_snapshot")
        .select("*")
        .ilike("category_name", "Business")
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def sum_states(cost_by_state: dict[str, float], states: list[str]) -> float:
    return sum(cost_by_state.get(state, 0) for state in states)


def print_summary(snapshot: dict[str, Any], *, write: bool) -> None:
    print("Business value snapshot write" if write else "Business value snapshot dry run")
    print("-----------------------------")
    print(f"Date: {snapshot['snapshot_date']}")
    print(f"Inventory at/on way to Amazon: ${snapshot['amazon_inventory_value']:,.2f}")
    print(f"Purchased not shipped to Amazon: ${snapshot['pre_amazon_inventory_value']:,.2f}")
    print(f"Amazon cash: ${snapshot['amazon_cash_balance']:,.2f}")
    print(f"Amazon cash in transit: ${snapshot['amazon_cash_in_transit']:,.2f}")
    print(f"Cash on hand: ${snapshot['cash_on_hand']:,.2f}")
    print(f"Total business value: ${snapshot['total_business_value']:,.2f}")


if __name__ == "__main__":
    raise SystemExit(main())
