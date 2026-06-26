"""Push an MBOP business finance summary into ZFI Supabase.

This is a service-to-service outbound integration. MBOP reads its operational
Supabase data, builds a business summary payload, and writes that payload to a
ZFI-owned Supabase table only when --apply is passed. Dry run is the default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("push_zfi_business_summary")

SCHEMA_VERSION = "2026-06-26"
DEFAULT_TARGET_TABLE = "mbop_business_summaries"
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_SECONDS = 2.0

AMAZON_FBA_STATES = {
    "amazon_fba_sellable",
    "amazon_fba_reserved",
    "amazon_fba_unsellable_damaged",
    "amazon_fba_stranded",
}
AMAZON_OUTBOUND_STATES = {
    "outbound_to_amazon",
    "amazon_fba_inbound_receiving",
}
PURCHASED_NOT_RECEIVED_STATES = {
    "purchased_not_shipped",
    "shipped_not_delivered",
    "delivered_not_received",
}
REPORTING_EXCLUDED_STATUSES = {"cancelled", "return_opened"}


class ZFIPushError(RuntimeError):
    """Raised when the ZFI business summary push cannot safely continue."""


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
        payload = build_payload(
            mbop,
            start_date=args.start_date,
            end_date=args.end_date,
            generated_by=args.generated_by,
        )
        print_summary(payload, write=args.apply)

        if not args.apply:
            print(json.dumps(payload, indent=2, sort_keys=True))
            LOGGER.info("Dry run complete. No ZFI Supabase writes performed.")
            return 0

        zfi = get_zfi_supabase_client()
        pushed_at = now_iso()
        row = {
            "source": payload["source"],
            "schema_version": payload["schema_version"],
            "period_start": payload["period"]["start_date"],
            "period_end": payload["period"]["end_date"],
            "generated_at": payload["generated_at"],
            "payload": payload,
            "source_summary": payload["source_summary"],
            "updated_at": pushed_at,
        }
        push_with_retry(
            zfi,
            table=args.target_table,
            row=row,
            attempts=args.retry_attempts,
            delay_seconds=args.retry_delay_seconds,
        )
        LOGGER.info(
            "ZFI business summary pushed: table=%s period=%s..%s",
            args.target_table,
            payload["period"]["start_date"],
            payload["period"]["end_date"],
        )
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely.
        LOGGER.exception("ZFI business summary push failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    today = dt.date.today()
    default_start = (today - dt.timedelta(days=30)).isoformat()
    parser = argparse.ArgumentParser(
        description="Build and optionally push an MBOP business summary to ZFI Supabase."
    )
    parser.add_argument(
        "--start-date",
        default=default_start,
        help="Reporting period start date, inclusive, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        default=today.isoformat(),
        help="Reporting period end date, inclusive, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--target-table",
        default=os.getenv("ZFI_BUSINESS_SUMMARY_TABLE", DEFAULT_TARGET_TABLE),
        help="ZFI Supabase table to upsert into.",
    )
    parser.add_argument(
        "--generated-by",
        default=os.getenv("ZFI_PUSH_GENERATED_BY", "manual"),
        help="Operator/source label stored in payload metadata.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=int(os.getenv("ZFI_PUSH_RETRY_ATTEMPTS", DEFAULT_RETRY_ATTEMPTS)),
        help="Number of live-push attempts before failing.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=float(os.getenv("ZFI_PUSH_RETRY_DELAY_SECONDS", DEFAULT_RETRY_DELAY_SECONDS)),
        help="Base delay between live-push retries.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the payload to ZFI Supabase. Omit for dry run.",
    )
    return parser.parse_args()


def get_mbop_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise ZFIPushError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def get_zfi_supabase_client():
    supabase_url = os.getenv("ZFI_SUPABASE_URL")
    supabase_key = os.getenv("ZFI_SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise ZFIPushError(
            "Missing ZFI_SUPABASE_URL or ZFI_SUPABASE_SERVICE_ROLE_KEY."
        )
    return create_client(supabase_url, supabase_key)


def build_payload(
    supabase,
    *,
    start_date: str,
    end_date: str,
    generated_by: str,
) -> dict[str, Any]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if start > end:
        raise ZFIPushError("start-date must be on or before end-date.")

    sales_orders = fetch_sales_orders(supabase, start, end)
    profitability = fetch_sales_profitability(supabase)
    purchases = fetch_purchase_rows(supabase, start, end)
    inventory_positions = fetch_all(
        supabase,
        "inventory_positions",
        "inventory_state,marketplace_intent,quantity,total_cost,unit_cost,effective_at,updated_at",
    )
    latest_finance = fetch_latest_row(
        supabase,
        "vw_latest_amazon_finance_balance_snapshot",
        "captured_at,total_amazon_cash,available_to_withdraw,in_transit_to_bank,deferred_or_reserved_cash",
    )
    latest_business_value = fetch_latest_business_value(supabase)

    profit_rows = rows_for_period(profitability, sales_orders, start, end)
    complete_profit_rows = [
        row for row in profit_rows if normalize(row.get("data_status")) == "complete"
    ]
    refunded_rows = [
        row for row in profit_rows if normalize(row.get("data_status")) == "refunded"
    ]
    non_cancelled_rows = [
        row for row in profit_rows if normalize(row.get("data_status")) != "cancelled"
    ]
    purchase_rows = reportable_purchase_rows(purchases)
    inventory_summary = summarize_inventory(inventory_positions)
    finance_captured_at = latest_finance.get("captured_at") if latest_finance else None

    gross_sales = money(sum_number(non_cancelled_rows, "sale_price"))
    marketplace_fees = money(abs(sum_number(complete_profit_rows, "amazon_fees_excluding_fulfillment")))
    fulfillment_costs = money(abs(sum_number(complete_profit_rows, "fulfillment_cost")))
    cogs = money(sum_number(complete_profit_rows, "cogs"))
    net_profit = money(sum_number(complete_profit_rows, "net_profit"))
    inventory_purchases = money(
        sum(
            to_number(row.get("quantity")) * to_number(row.get("unit_cost"))
            for row in purchase_rows
        )
    )

    confidence_notes = [
        "MBOP pushes business-operational summaries only; ZFI owns personal finance, tax classification, and household planning.",
        "Amazon sales are sourced from amazon_sales_profitability joined to amazon_sales_orders by order id.",
        "eBay seller revenue is not included because MBOP does not yet own eBay seller-order ingestion.",
        "Software/tool expenses and owner draws are intentionally not pulled from MBOP; ZFI should own those finance categories.",
    ]
    if any(normalize(row.get("data_status")) != "complete" for row in profit_rows):
        confidence_notes.append(
            "Some period sales rows are incomplete, refunded, cancelled, or missing COGS/fees/fulfillment cost; complete rows drive net-profit totals."
        )

    alerts = build_alerts(profit_rows, inventory_summary)
    generated_at = now_iso()

    return {
        "source": "mbop",
        "schema_version": SCHEMA_VERSION,
        "summary_id": str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"mbop-zfi-business-summary:{start.isoformat()}:{end.isoformat()}",
        )),
        "generated_at": generated_at,
        "generated_by": generated_by,
        "period": {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        "sales": {
            "gross_sales": gross_sales,
            "marketplace_sales_by_channel": {
                "amazon": gross_sales,
                "ebay": 0.0,
                "other": 0.0,
            },
            "refunds_returns": money(sum_number(refunded_rows, "sale_price")),
            "units_sold": int(sum_number(non_cancelled_rows, "quantity")),
            "complete_sales_rows": len(complete_profit_rows),
            "total_sales_rows": len(profit_rows),
        },
        "costs": {
            "marketplace_fees": marketplace_fees,
            "shipping_label_costs": fulfillment_costs,
            "inbound_shipping_prep_costs": None,
            "cogs": cogs,
            "inventory_purchases": inventory_purchases,
            "software_tool_expenses": None,
        },
        "inventory": inventory_summary,
        "profitability": {
            "gross_profit": money(gross_sales - marketplace_fees - cogs),
            "estimated_net_profit": net_profit,
            "roi": round(net_profit / cogs, 4) if cogs else None,
        },
        "cash_operational": {
            "amazon_cash": money((latest_finance or {}).get("total_amazon_cash")),
            "amazon_available_to_withdraw": money((latest_finance or {}).get("available_to_withdraw")),
            "amazon_to_bank_in_transit": money((latest_finance or {}).get("in_transit_to_bank")),
            "amazon_deferred_or_reserved_cash": money((latest_finance or {}).get("deferred_or_reserved_cash")),
        },
        "alerts": alerts,
        "source_timestamps": {
            "amazon_finance_captured_at": finance_captured_at,
            "business_value_snapshot_date": (latest_business_value or {}).get("snapshot_date"),
            "business_value_captured_at": (latest_business_value or {}).get("captured_at"),
            "sales_profitability_updated_at": latest_value(
                row.get("updated_at") or row.get("calculated_at")
                for row in profitability
            ),
            "inventory_positions_updated_at": latest_value(
                row.get("updated_at") for row in inventory_positions
            ),
        },
        "source_summary": {
            "sales_order_rows": len(sales_orders),
            "sales_profitability_rows": len(profitability),
            "period_sales_profitability_rows": len(profit_rows),
            "purchase_rows": len(purchase_rows),
            "inventory_position_rows": len(inventory_positions),
        },
        "reconciliation_confidence_notes": confidence_notes,
    }


def fetch_sales_orders(supabase, start: dt.date, end: dt.date) -> dict[str, str]:
    rows = fetch_all(
        supabase,
        "amazon_sales_orders",
        "amazon_order_id,purchase_date",
        filters=lambda query: query
        .gte("purchase_date", f"{start.isoformat()}T00:00:00Z")
        .lte("purchase_date", f"{end.isoformat()}T23:59:59Z"),
    )
    return {
        str(row.get("amazon_order_id")): str(row.get("purchase_date") or "")
        for row in rows
        if row.get("amazon_order_id")
    }


def fetch_sales_profitability(supabase) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "amazon_sales_profitability",
        "amazon_order_id,quantity,sale_price,amazon_fees_excluding_fulfillment,fulfillment_cost,cogs,net_profit,roi,data_status,calculated_at,updated_at",
    )


def fetch_purchase_rows(supabase, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    rows = fetch_all(
        supabase,
        "vw_purchases_dashboard",
        "item_id,order_date,quantity,unit_cost,current_status",
        filters=lambda query: query
        .gte("order_date", start.isoformat())
        .lte("order_date", end.isoformat()),
    )
    exclusions = fetch_reporting_exclusions(
        supabase,
        [
            str(row.get("item_id"))
            for row in rows
            if row.get("item_id")
        ],
    )
    for row in rows:
        item_id = str(row.get("item_id") or "")
        row["exclude_from_purchase_reporting"] = item_id in exclusions
    return rows


def fetch_reporting_exclusions(supabase, item_ids: list[str]) -> set[str]:
    if not item_ids:
        return set()

    excluded: set[str] = set()
    for chunk in chunks(item_ids, 500):
        response = (
            supabase.table("purchase_items")
            .select("item_id,exclude_from_purchase_reporting")
            .in_("item_id", chunk)
            .eq("exclude_from_purchase_reporting", True)
            .execute()
        )
        for row in response.data or []:
            if row.get("item_id"):
                excluded.add(str(row["item_id"]))
    return excluded


def fetch_latest_business_value(supabase) -> dict[str, Any] | None:
    response = (
        supabase.table("business_value_snapshots")
        .select("snapshot_date,captured_at,total_business_value")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def fetch_latest_row(supabase, table: str, columns: str) -> dict[str, Any] | None:
    response = supabase.table(table).select(columns).limit(1).execute()
    return (response.data or [None])[0]


def fetch_all(
    supabase,
    table: str,
    columns: str,
    *,
    filters=None,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = supabase.table(table).select(columns)
        if filters:
            query = filters(query)
        response = query.range(offset, offset + page_size - 1).execute()
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def rows_for_period(
    rows: list[dict[str, Any]],
    order_date_by_id: dict[str, str],
    start: dt.date,
    end: dt.date,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        order_id = str(row.get("amazon_order_id") or "")
        order_date = date_from_text(order_date_by_id.get(order_id))
        if order_date and start <= order_date <= end:
            selected.append(row)
    return selected


def reportable_purchase_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if not row.get("exclude_from_purchase_reporting")
        and normalize(row.get("current_status")) not in REPORTING_EXCLUDED_STATUSES
    ]


def summarize_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count_by_state: dict[str, int] = {}
    value_by_state: dict[str, float] = {}
    total_value = 0.0
    aged_value = 0.0
    fba_value = 0.0
    merchant_fulfilled_value = 0.0
    purchased_not_received_value = 0.0
    today = dt.date.today()

    for row in rows:
        state = normalize(row.get("inventory_state")) or "unknown"
        quantity = to_number(row.get("quantity"))
        value = row_value(row)
        count_by_state[state] = count_by_state.get(state, 0) + int(quantity)
        value_by_state[state] = money(value_by_state.get(state, 0.0) + value)
        total_value += value

        if state in AMAZON_FBA_STATES or state in AMAZON_OUTBOUND_STATES:
            fba_value += value
        if state in PURCHASED_NOT_RECEIVED_STATES:
            purchased_not_received_value += value
        if normalize(row.get("marketplace_intent")) == "ebay":
            merchant_fulfilled_value += value

        effective_date = date_from_text(row.get("effective_at") or row.get("updated_at"))
        if effective_date and (today - effective_date).days >= 180:
            aged_value += value

    return {
        "current_inventory_value": money(total_value),
        "aged_inventory_value": money(aged_value),
        "inventory_count_by_state": count_by_state,
        "inventory_value_by_state": value_by_state,
        "fba_inventory_value": money(fba_value),
        "merchant_fulfilled_inventory_value": money(merchant_fulfilled_value),
        "purchased_not_received_value": money(purchased_not_received_value),
    }


def build_alerts(
    profit_rows: list[dict[str, Any]],
    inventory_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    missing_cogs = [
        row for row in profit_rows if normalize(row.get("data_status")) == "missing_cogs"
    ]
    missing_fees = [
        row for row in profit_rows if normalize(row.get("data_status")) == "missing_fees"
    ]
    if missing_cogs:
        alerts.append(
            {
                "severity": "medium",
                "code": "missing_cogs",
                "message": f"{len(missing_cogs)} period sales row(s) are missing COGS.",
            }
        )
    if missing_fees:
        alerts.append(
            {
                "severity": "medium",
                "code": "missing_fees",
                "message": f"{len(missing_fees)} period sales row(s) are missing marketplace fees.",
            }
        )
    if to_number(inventory_summary.get("aged_inventory_value")) > 0:
        alerts.append(
            {
                "severity": "low",
                "code": "aged_inventory",
                "message": "Some current inventory is aged 180+ days by MBOP operational dates.",
            }
        )
    return alerts


def push_with_retry(
    supabase,
    *,
    table: str,
    row: dict[str, Any],
    attempts: int,
    delay_seconds: float,
) -> None:
    attempts = max(attempts, 1)
    for attempt in range(1, attempts + 1):
        try:
            supabase.table(table).upsert(
                row,
                on_conflict="source,period_start,period_end",
            ).execute()
            return
        except Exception:
            if attempt == attempts:
                raise
            sleep_for = delay_seconds * attempt
            LOGGER.warning(
                "ZFI Supabase push attempt %s/%s failed; retrying in %.1fs",
                attempt,
                attempts,
                sleep_for,
            )
            time.sleep(sleep_for)


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise ZFIPushError(f"Invalid date {value!r}; use YYYY-MM-DD.") from error


def date_from_text(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def row_value(row: dict[str, Any]) -> float:
    total_cost = to_number(row.get("total_cost"))
    if total_cost:
        return total_cost
    return to_number(row.get("unit_cost")) * to_number(row.get("quantity"))


def sum_number(rows: list[dict[str, Any]], field: str) -> float:
    return sum(to_number(row.get(field)) for row in rows)


def to_number(value: Any) -> float:
    try:
        output = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return output if output == output else 0.0


def money(value: Any) -> float:
    return round(to_number(value), 2)


def normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def latest_value(values) -> str | None:
    filtered = [str(value) for value in values if value]
    return sorted(filtered)[-1] if filtered else None


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def print_summary(payload: dict[str, Any], *, write: bool) -> None:
    mode = "write" if write else "dry run"
    print(f"ZFI business summary {mode}")
    print("------------------------")
    print(
        f"Period: {payload['period']['start_date']} to {payload['period']['end_date']}"
    )
    print(f"Gross sales: ${payload['sales']['gross_sales']:,.2f}")
    print(f"Marketplace fees: ${payload['costs']['marketplace_fees']:,.2f}")
    print(f"Shipping/fulfillment costs: ${payload['costs']['shipping_label_costs']:,.2f}")
    print(f"COGS: ${payload['costs']['cogs']:,.2f}")
    print(f"Estimated net profit: ${payload['profitability']['estimated_net_profit']:,.2f}")
    print(f"Inventory value: ${payload['inventory']['current_inventory_value']:,.2f}")
    print(f"Alerts: {len(payload['alerts'])}")


if __name__ == "__main__":
    raise SystemExit(main())
