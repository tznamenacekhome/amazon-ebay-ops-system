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

SCHEMA_VERSION = "2026-06-29"
PAYLOAD_VERSION = "business_finance_replacement_v2"
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
STALE_SOURCE_HOURS = 36


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
    all_sales_orders = fetch_sales_orders_since(supabase, dt.date(2025, 1, 1))
    profitability = fetch_sales_profitability(supabase)
    purchases = fetch_purchase_rows(supabase, start, end)
    all_purchases = fetch_purchase_rows(supabase, dt.date(2025, 1, 1), end)
    inventory_positions = fetch_all(
        supabase,
        "inventory_positions",
        "inventory_position_id,asin,seller_sku,title,system,inventory_state,marketplace_intent,quantity,total_cost,unit_cost,effective_at,updated_at",
    )
    latest_finance = fetch_latest_row(
        supabase,
        "vw_latest_amazon_finance_balance_snapshot",
        "captured_at,total_amazon_cash,available_to_withdraw,in_transit_to_bank,deferred_or_reserved_cash,raw_financial_event_groups_json",
    )
    order_problem_cases = fetch_order_problem_cases(supabase)
    order_problem_events = fetch_order_problem_events(supabase)
    reimbursement_rows = fetch_reimbursement_rows(supabase, start, end)
    return_recovery_cases = fetch_return_recovery_cases(supabase)

    profit_rows = rows_for_period(profitability, sales_orders, start, end)
    profit_rows_with_dates = attach_sold_dates(profitability, all_sales_orders)
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
    source_timestamps = build_source_timestamps(
        finance=latest_finance,
        profitability=profitability,
        inventory_positions=inventory_positions,
        order_problem_cases=order_problem_cases,
        reimbursement_rows=reimbursement_rows,
    )

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
    windows = build_profitability_windows(profit_rows_with_dates, end, source_timestamps)
    cash_position = build_cash_position(latest_finance, source_timestamps)
    payout_reconciliation = build_payout_reconciliation(latest_finance)
    inventory_capital = build_inventory_capital(inventory_positions, source_timestamps)
    loss_prevention = build_loss_prevention(
        order_problem_cases,
        order_problem_events,
        purchases=all_purchases,
        reimbursements=reimbursement_rows,
        return_recovery_cases=return_recovery_cases,
    )
    top_sellers = build_top_sellers(profit_rows_with_dates, end)
    growth_summary = build_growth_summary(
        profit_rows_with_dates,
        all_purchases,
    )
    sourcing_summary = build_sourcing_summary(
        profit_rows_with_dates,
        inventory_positions,
        all_purchases,
        source_timestamps,
    )
    financial_readiness = build_financial_readiness(
        profit_rows_with_dates,
        source_timestamps,
    )

    return {
        "source": "mbop",
        "schema_version": SCHEMA_VERSION,
        "payload_version": PAYLOAD_VERSION,
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
        "profitability_windows": windows,
        "cash_position": cash_position,
        "payout_reconciliation": payout_reconciliation,
        "inventory_capital": inventory_capital,
        "loss_prevention": loss_prevention,
        "top_sellers": top_sellers,
        "growth_summary": growth_summary,
        "sourcing_summary": sourcing_summary,
        "financial_readiness": financial_readiness,
        "alerts": alerts,
        "source_timestamps": source_timestamps,
        "source_summary": {
            "sales_order_rows": len(sales_orders),
            "all_sales_order_rows": len(all_sales_orders),
            "sales_profitability_rows": len(profitability),
            "period_sales_profitability_rows": len(profit_rows),
            "purchase_rows": len(purchase_rows),
            "all_purchase_rows": len(all_purchases),
            "inventory_position_rows": len(inventory_positions),
            "order_problem_case_rows": len(order_problem_cases),
            "order_problem_event_rows": len(order_problem_events),
            "reimbursement_rows": len(reimbursement_rows),
            "return_recovery_case_rows": len(return_recovery_cases),
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


def fetch_sales_orders_since(supabase, start: dt.date) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "amazon_sales_orders",
        "amazon_order_id,purchase_date,order_status,order_total_amount,updated_at",
        filters=lambda query: query.gte("purchase_date", f"{start.isoformat()}T00:00:00Z"),
    )


def fetch_sales_profitability(supabase) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "amazon_sales_profitability",
        "amazon_order_id,asin,seller_sku,title,quantity,sale_price,amazon_fees_excluding_fulfillment,fulfillment_cost,cogs,net_profit,roi,data_status,calculated_at,updated_at",
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


def fetch_order_problem_cases(supabase) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "order_problem_cases",
        "problem_case_id,purchase_item_id,problem_type,workflow_state,is_open,expected_refund_amount,actual_refund_amount,partial_refund_amount,first_detected_at,updated_at,created_at,closed_at",
    )


def fetch_order_problem_events(supabase) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "order_problem_events",
        "problem_event_id,problem_case_id,event_type,amount,currency,event_at,created_at",
    )


def fetch_reimbursement_rows(supabase, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "amazon_fba_reimbursement_rows",
        "amazon_fba_reimbursement_row_id,approval_date,reimbursement_id,case_id,amazon_order_id,reason,seller_sku,sku,fnsku,asin,quantity_reimbursed,amount_total,amount_per_unit,currency,imported_at,updated_at",
        filters=lambda query: query
        .gte("approval_date", start.isoformat())
        .lte("approval_date", end.isoformat()),
    )


def fetch_return_recovery_cases(supabase) -> list[dict[str, Any]]:
    return fetch_all(
        supabase,
        "amazon_return_recovery_cases",
        "amazon_return_recovery_case_id,workflow_state,decision,reimbursement_review_status,reimbursement_likelihood,asin,seller_sku,fnsku,quantity,updated_at",
    )


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


def attach_sold_dates(
    profit_rows: list[dict[str, Any]],
    sales_orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    order_dates = {
        str(row.get("amazon_order_id")): row.get("purchase_date")
        for row in sales_orders
        if row.get("amazon_order_id")
    }
    return [
        {
            **row,
            "sold_at": order_dates.get(str(row.get("amazon_order_id") or "")),
        }
        for row in profit_rows
    ]


def build_profitability_windows(
    rows: list[dict[str, Any]],
    end: dt.date,
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    windows = {
        "30d": end - dt.timedelta(days=29),
        "90d": end - dt.timedelta(days=89),
        "ytd": dt.date(end.year, 1, 1),
    }
    return {
        key: summarize_profit_window(key, rows, start, end, source_timestamps)
        for key, start in windows.items()
    }


def summarize_profit_window(
    key: str,
    rows: list[dict[str, Any]],
    start: dt.date,
    end: dt.date,
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    period_rows = [
        row for row in rows
        if (sold_date := date_from_text(row.get("sold_at"))) and start <= sold_date <= end
    ]
    complete = [
        row for row in period_rows if normalize(row.get("data_status")) == "complete"
    ]
    non_cancelled = [
        row for row in period_rows if normalize(row.get("data_status")) != "cancelled"
    ]
    units = sum_number(complete, "quantity")
    gross_sales = money(sum_number(non_cancelled, "sale_price"))
    revenue = money(sum_number(complete, "sale_price"))
    amazon_fees = money(abs(sum_number(complete, "amazon_fees_excluding_fulfillment")))
    fulfillment_costs = money(abs(sum_number(complete, "fulfillment_cost")))
    cogs = money(sum_number(complete, "cogs"))
    net_profit = money(sum_number(complete, "net_profit"))
    warnings = completeness_warnings(period_rows)
    if not complete:
        warnings.append("No complete profitability rows were available for this window.")
    return {
        "window": key,
        "gross_sales": gross_sales,
        "revenue": revenue,
        "amazon_fees": amazon_fees,
        "marketplace_fees": amazon_fees,
        "fulfillment_costs": fulfillment_costs,
        "shipping_label_costs": fulfillment_costs,
        "cogs": cogs,
        "gross_profit": money(revenue - amazon_fees - cogs),
        "net_profit": net_profit,
        "roi": round(net_profit / cogs, 4) if cogs else None,
        "average_profit_per_unit": money(net_profit / units) if units else None,
        "units_sold": int(units),
        "source_start_date": start.isoformat(),
        "source_end_date": end.isoformat(),
        "source_timestamps": source_timestamps_for(
            source_timestamps,
            ["sales_profitability_updated_at"],
        ),
        "complete_rows": len(complete),
        "total_rows": len(period_rows),
        "completeness_warnings": warnings,
    }


def build_cash_position(
    finance: dict[str, Any] | None,
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    amazon_total = nullable_money((finance or {}).get("total_amazon_cash"))
    amazon_available = nullable_money((finance or {}).get("available_to_withdraw"))
    amazon_in_transit = nullable_money((finance or {}).get("in_transit_to_bank"))
    amazon_deferred = nullable_money((finance or {}).get("deferred_or_reserved_cash"))
    warnings = []
    if finance is None:
        warnings.append("Amazon Finance snapshot is missing.")
    return {
        "amazon_cash_total": amazon_total,
        "amazon_available_to_withdraw": amazon_available,
        "amazon_to_bank_in_transit": amazon_in_transit,
        "amazon_deferred_reserved_cash": amazon_deferred,
        "payout_status_summary": payout_status_summary(finance),
        "source_timestamps": source_timestamps_for(
            source_timestamps,
            ["amazon_finance_captured_at"],
        ),
        "freshness_status": freshness_status(source_timestamps),
        "completeness_warnings": warnings,
    }


def build_payout_reconciliation(finance: dict[str, Any] | None) -> dict[str, Any]:
    breakdown = nested_dict(finance, "raw_financial_event_groups_json", "inTransitBreakdown")
    completed_ids = list_value(breakdown.get("recentCompletedTransferGroupIds"))
    processing_amount = nullable_money(breakdown.get("processingTransferCash"))
    completed_amount = nullable_money(breakdown.get("recentCompletedTransferCash"))
    warnings = []
    if finance is None:
        warnings.append("Amazon Finance snapshot is missing.")
    return {
        "payouts_in_transit_count": None,
        "payouts_in_transit_amount": processing_amount,
        "recent_completed_payout_count": len(completed_ids),
        "recent_completed_payout_amount": completed_amount,
        "latest_payout_date": latest_payout_date(finance),
        "reconciliation_status": "amazon_only",
        "warnings": warnings,
    }


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


def build_inventory_capital(
    rows: list[dict[str, Any]],
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    total_value = sum(row_value(row) for row in rows)
    by_location = inventory_value_by_location(rows, total_value)
    age_buckets = inventory_age_buckets(rows, total_value)
    amazon_value = sum(
        row_value(row)
        for row in rows
        if normalize(row.get("inventory_state")) in AMAZON_FBA_STATES
    )
    pre_amazon_value = max(total_value - amazon_value, 0.0)
    warnings = []
    if age_buckets["unknown_age"]["value"] > 0:
        warnings.append("Some inventory positions are missing usable age/effective-date context.")
    return {
        "total_inventory_value": money(total_value),
        "amazon_inventory_value": money(amazon_value),
        "pre_amazon_inventory_value": money(pre_amazon_value),
        "inventory_value_by_location": by_location,
        "inventory_value_by_age_bucket": age_buckets,
        "capital_at_risk": {
            "over_90_days_value": money(
                age_buckets["91_180"]["value"]
                + age_buckets["181_365"]["value"]
                + age_buckets["365_plus"]["value"]
            ),
            "over_180_days_value": money(
                age_buckets["181_365"]["value"] + age_buckets["365_plus"]["value"]
            ),
            "over_365_days_value": money(age_buckets["365_plus"]["value"]),
            "unknown_age_value": money(age_buckets["unknown_age"]["value"]),
        },
        "listing_health_value": None,
        "source_timestamps": source_timestamps_for(
            source_timestamps,
            ["inventory_positions_updated_at"],
        ),
        "completeness_warnings": warnings
        + ["Listing health value is not safely derivable as a dollar value from current MBOP listing-health rows."],
    }


def inventory_value_by_location(rows: list[dict[str, Any]], total_value: float) -> list[dict[str, Any]]:
    groups = [
        ("amazon_fba", "Amazon FBA", AMAZON_FBA_STATES),
        ("outbound_to_amazon", "Outbound to Amazon", AMAZON_OUTBOUND_STATES),
        ("received_ready", "Received / Ready", {"received_unassigned", "received_assigned_amazon_not_sent"}),
        ("ordered_not_received", "Ordered not received", PURCHASED_NOT_RECEIVED_STATES),
        ("return_problem", "Return / problem", {"return_pending", "return_opened", "cancelled_refund_follow_up"}),
    ]
    grouped_states = set().union(*(states for _, _, states in groups))
    output = []
    for key, label, states in groups:
        matching = [row for row in rows if normalize(row.get("inventory_state")) in states]
        value = sum(row_value(row) for row in matching)
        units = sum_number(matching, "quantity")
        output.append({
            "location_key": key,
            "label": label,
            "units": int(units),
            "value": money(value),
            "percent_of_total": round(value / total_value, 4) if total_value else None,
        })
    other = [
        row for row in rows
        if normalize(row.get("inventory_state")) not in grouped_states
    ]
    other_value = sum(row_value(row) for row in other)
    output.append({
        "location_key": "other_unknown",
        "label": "Other / unknown",
        "units": int(sum_number(other, "quantity")),
        "value": money(other_value),
        "percent_of_total": round(other_value / total_value, 4) if total_value else None,
    })
    return output


def inventory_age_buckets(rows: list[dict[str, Any]], total_value: float) -> dict[str, dict[str, Any]]:
    buckets = {
        "0_30": {"units": 0, "value": 0.0},
        "31_60": {"units": 0, "value": 0.0},
        "61_90": {"units": 0, "value": 0.0},
        "91_180": {"units": 0, "value": 0.0},
        "181_365": {"units": 0, "value": 0.0},
        "365_plus": {"units": 0, "value": 0.0},
        "unknown_age": {"units": 0, "value": 0.0},
    }
    today = dt.date.today()
    for row in rows:
        effective = date_from_text(row.get("effective_at") or row.get("updated_at"))
        if not effective:
            key = "unknown_age"
        else:
            age = max(0, (today - effective).days)
            key = (
                "0_30" if age <= 30
                else "31_60" if age <= 60
                else "61_90" if age <= 90
                else "91_180" if age <= 180
                else "181_365" if age <= 365
                else "365_plus"
            )
        buckets[key]["units"] += int(to_number(row.get("quantity")))
        buckets[key]["value"] += row_value(row)
    return {
        key: {
            "units": value["units"],
            "value": money(value["value"]),
            "percent_of_total": round(value["value"] / total_value, 4) if total_value else None,
        }
        for key, value in buckets.items()
    }


def build_loss_prevention(
    cases: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    purchases: list[dict[str, Any]],
    reimbursements: list[dict[str, Any]],
    return_recovery_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    value_by_item = {
        str(row.get("item_id")): to_number(row.get("quantity")) * to_number(row.get("unit_cost"))
        for row in purchases
        if row.get("item_id")
    }
    open_cases = [row for row in cases if bool(row.get("is_open"))]
    enriched_values = [
        to_number(row.get("expected_refund_amount"))
        or value_by_item.get(str(row.get("purchase_item_id") or ""), 0.0)
        for row in open_cases
    ]
    refund_events = [row for row in events if to_number(row.get("amount")) > 0]
    reimbursement_total = sum_number(reimbursements, "amount_total")
    currencies = sorted({str(row.get("currency")) for row in reimbursements if row.get("currency")})
    needs_mapping_count = sum(
        1
        for row in return_recovery_cases
        if normalize(row.get("workflow_state")) in {"reimbursement_review", "reimbursement_pending"}
    )
    expected_refund = sum_number(cases, "expected_refund_amount")
    actual_refund = sum_number(cases, "actual_refund_amount")
    partial_refund = sum_number(cases, "partial_refund_amount")
    return {
        "sales_at_risk_value": money(sum(enriched_values)),
        "refund_pending_value": money(sum(
            enriched_values[index]
            for index, row in enumerate(open_cases)
            if normalize(row.get("workflow_state")) == "refund_pending"
        )),
        "refunds_received_value": money(actual_refund),
        "closed_no_refund_value": None,
        "expected_refund_value": money(expected_refund),
        "received_refund_value": money(actual_refund),
        "partial_refund_value": money(partial_refund),
        "refund_event_amount_total": money(sum_number(refund_events, "amount")),
        "estimated_refund_fallback_total": money(max(sum(enriched_values) - expected_refund, 0)),
        "reimbursement_count": len(reimbursements),
        "reimbursement_amount_total": money(reimbursement_total),
        "reimbursement_currency": currencies[0] if len(currencies) == 1 else ("mixed" if currencies else None),
        "unrecoverable_fees_known_total": None,
        "unrecoverable_fees_needs_mapping_count": needs_mapping_count,
        "warnings": [
            "Closed-no-refund value is not safely modeled yet; MBOP preserves case status and refund fields.",
            "Unrecoverable return fees remain null unless a backend-owned financial mapping exists.",
        ],
    }


def build_top_sellers(rows: list[dict[str, Any]], end: dt.date) -> dict[str, list[dict[str, Any]]]:
    start = end - dt.timedelta(days=89)
    period_rows = [
        row for row in rows
        if normalize(row.get("data_status")) == "complete"
        and (sold_date := date_from_text(row.get("sold_at")))
        and start <= sold_date <= end
    ]
    by_asin: dict[str, dict[str, Any]] = {}
    for row in period_rows:
        asin = str(row.get("asin") or "").upper()
        if not asin:
            continue
        current = by_asin.setdefault(
            asin,
            {
                "asin": asin,
                "title": row.get("title") or "Untitled",
                "units_sold": 0,
                "revenue": 0.0,
                "net_profit": 0.0,
                "cogs": 0.0,
                "source_period": "90d",
            },
        )
        current["units_sold"] += int(to_number(row.get("quantity")))
        current["revenue"] += to_number(row.get("sale_price"))
        current["net_profit"] += to_number(row.get("net_profit"))
        current["cogs"] += to_number(row.get("cogs"))
    sellers = [format_top_seller(row) for row in by_asin.values()]
    return {
        "by_revenue": sorted(sellers, key=lambda row: row["revenue"], reverse=True)[:10],
        "by_profit": sorted(sellers, key=lambda row: row["net_profit"], reverse=True)[:10],
        "by_roi": sorted(
            [row for row in sellers if row["roi"] is not None],
            key=lambda row: row["roi"] or 0,
            reverse=True,
        )[:10],
    }


def format_top_seller(row: dict[str, Any]) -> dict[str, Any]:
    units = to_number(row.get("units_sold"))
    revenue = money(row.get("revenue"))
    net_profit = money(row.get("net_profit"))
    cogs = to_number(row.get("cogs"))
    return {
        "asin": row.get("asin"),
        "title": row.get("title"),
        "units_sold": int(units),
        "revenue": revenue,
        "net_profit": net_profit,
        "roi": round(net_profit / cogs, 4) if cogs else None,
        "average_profit_per_unit": money(net_profit / units) if units else None,
        "source_period": row.get("source_period"),
    }


def build_growth_summary(
    profit_rows: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
) -> dict[str, Any]:
    months: dict[str, dict[str, Any]] = {}
    for row in profit_rows:
        key = month_key(row.get("sold_at"))
        if not key:
            continue
        current = months.setdefault(key, base_month(key))
        current["revenue"] += to_number(row.get("sale_price"))
        current["profit"] += to_number(row.get("net_profit"))
        current["units_sold"] += int(to_number(row.get("quantity")))
        current["cogs"] += to_number(row.get("cogs"))
    for row in reportable_purchase_rows(purchases):
        key = month_key(row.get("order_date"))
        if not key:
            continue
        current = months.setdefault(key, base_month(key))
        current["inventory_spend"] += to_number(row.get("quantity")) * to_number(row.get("unit_cost"))
    formatted = []
    for row in sorted(months.values(), key=lambda value: value["month"], reverse=True)[:12]:
        units = to_number(row["units_sold"])
        cogs = to_number(row["cogs"])
        profit = to_number(row["profit"])
        formatted.append({
            "month": row["month"],
            "revenue": money(row["revenue"]),
            "profit": money(profit),
            "inventory_spend": money(row["inventory_spend"]),
            "units_sold": int(units),
            "roi": round(profit / cogs, 4) if cogs else None,
            "average_profit_per_unit": money(profit / units) if units else None,
        })
    return {"monthly": list(reversed(formatted))}


def base_month(key: str) -> dict[str, Any]:
    return {
        "month": key,
        "revenue": 0.0,
        "profit": 0.0,
        "inventory_spend": 0.0,
        "units_sold": 0,
        "cogs": 0.0,
    }


def build_sourcing_summary(
    profit_rows: list[dict[str, Any]],
    inventory_positions: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    candidates = sourcing_candidates(profit_rows, inventory_positions, purchases)
    estimated_profits = [to_number(row.get("average_estimated_profit")) for row in candidates if row.get("average_estimated_profit") is not None]
    rois = [to_number(row.get("average_roi")) for row in candidates if row.get("average_roi") is not None]
    max_buys = [to_number(row.get("suggested_max_buy_cost")) for row in candidates if row.get("suggested_max_buy_cost") is not None]
    return {
        "research_queue_count": len(candidates),
        "research_queue_estimated_value": money(sum(max_buys)),
        "total_profit_opportunity": money(sum(to_number(row.get("total_profit_opportunity")) for row in candidates)),
        "average_estimated_profit": money(sum(estimated_profits) / len(estimated_profits)) if estimated_profits else None,
        "average_roi": round(sum(rois) / len(rois), 4) if rois else None,
        "max_buy_total": money(sum(max_buys)),
        "source_timestamps": source_timestamps_for(
            source_timestamps,
            ["sales_profitability_updated_at", "inventory_positions_updated_at"],
        ),
    }


def sourcing_candidates(
    rows: list[dict[str, Any]],
    inventory_positions: list[dict[str, Any]],
    purchases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cutoff = dt.date.today() - dt.timedelta(days=90)
    units_by_asin: dict[str, float] = {}
    for row in inventory_positions:
        asin = str(row.get("asin") or "").upper()
        if asin:
            units_by_asin[asin] = units_by_asin.get(asin, 0.0) + to_number(row.get("quantity"))
    purchase_counts: dict[str, int] = {}
    for row in reportable_purchase_rows(purchases):
        asin = str(row.get("asin") or "").upper()
        if asin:
            purchase_counts[asin] = purchase_counts.get(asin, 0) + 1
    by_asin: dict[str, dict[str, Any]] = {}
    for row in rows:
        asin = str(row.get("asin") or "").upper()
        sold = date_from_text(row.get("sold_at"))
        if not asin or not sold or sold < cutoff:
            continue
        current = by_asin.setdefault(
            asin,
            {"asin": asin, "units_sold": 0, "revenue": 0.0, "profit": 0.0, "cogs": 0.0},
        )
        current["units_sold"] += int(to_number(row.get("quantity")))
        current["revenue"] += to_number(row.get("sale_price"))
        current["profit"] += to_number(row.get("net_profit"))
        current["cogs"] += to_number(row.get("cogs"))
    output = []
    for asin, row in by_asin.items():
        units = to_number(row["units_sold"])
        current_units = units_by_asin.get(asin, 0.0)
        avg_profit = row["profit"] / units if units else None
        avg_sale = row["revenue"] / units if units else None
        roi = row["profit"] / row["cogs"] if row["cogs"] else None
        score = units * 4 + max(0, 6 - current_units) * 8 + to_number(avg_profit) * 2 + to_number(roi) * 20 + min(purchase_counts.get(asin, 0), 5) * 4
        if score <= 25:
            continue
        suggested_max = max(avg_sale - avg_profit * 0.75, 0) if avg_sale is not None and avg_profit is not None else None
        output.append({
            "asin": asin,
            "average_estimated_profit": money(avg_profit),
            "average_roi": round(roi, 4) if roi is not None else None,
            "suggested_max_buy_cost": money(suggested_max),
            "total_profit_opportunity": money(to_number(avg_profit) * max(0, 6 - current_units)),
        })
    return output


def build_financial_readiness(
    rows: list[dict[str, Any]],
    source_timestamps: dict[str, Any],
) -> dict[str, Any]:
    cutoff = dt.date.today() - dt.timedelta(days=90)
    recent = [
        row for row in rows
        if (sold := date_from_text(row.get("sold_at"))) and sold >= cutoff
        and normalize(row.get("data_status")) != "cancelled"
    ]
    missing_cogs = [
        row for row in recent
        if normalize(row.get("data_status")) == "missing_cogs" or to_number(row.get("cogs")) <= 0
    ]
    missing_fees = [
        row for row in recent if normalize(row.get("data_status")) == "missing_fees"
    ]
    pending_fees = [
        row for row in recent if "pending" in normalize(row.get("data_status"))
    ]
    missing_fulfillment = [
        row for row in recent
        if normalize(row.get("data_status")) == "missing_fulfillment_cost"
        or to_number(row.get("fulfillment_cost")) == 0
    ]
    source_freshness = freshness_status(source_timestamps)
    blocking = []
    warnings = []
    if missing_cogs:
        blocking.append(f"{len(missing_cogs)} recent sales rows are missing COGS.")
    if missing_fees:
        warnings.append(f"{len(missing_fees)} recent sales rows are missing Amazon fees.")
    if pending_fees:
        warnings.append(f"{len(pending_fees)} recent sales rows have pending fees.")
    if source_freshness["stale_source_count"]:
        warnings.append(f"{source_freshness['stale_source_count']} source timestamp(s) are stale.")
    return {
        "missing_cogs_units": int(sum_number(missing_cogs, "quantity")),
        "missing_cogs_value": money(sum_number(missing_cogs, "sale_price")),
        "missing_fees_count": len(missing_fees),
        "pending_fees_count": len(pending_fees),
        "missing_fulfillment_cost_count": len(missing_fulfillment),
        "stale_source_count": source_freshness["stale_source_count"],
        "source_freshness_summary": source_freshness,
        "blocking_issues": blocking,
        "warning_issues": warnings,
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


def build_source_timestamps(
    *,
    finance: dict[str, Any] | None,
    profitability: list[dict[str, Any]],
    inventory_positions: list[dict[str, Any]],
    order_problem_cases: list[dict[str, Any]],
    reimbursement_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "amazon_finance_captured_at": (finance or {}).get("captured_at"),
        "sales_profitability_updated_at": latest_value(
            row.get("updated_at") or row.get("calculated_at")
            for row in profitability
        ),
        "inventory_positions_updated_at": latest_value(
            row.get("updated_at") for row in inventory_positions
        ),
        "order_problem_cases_updated_at": latest_value(
            row.get("updated_at") or row.get("created_at") for row in order_problem_cases
        ),
        "amazon_reimbursements_updated_at": latest_value(
            row.get("updated_at") or row.get("imported_at") or row.get("approval_date")
            for row in reimbursement_rows
        ),
    }


def source_timestamps_for(
    timestamps: dict[str, Any],
    keys: list[str],
) -> dict[str, Any]:
    return {key: timestamps.get(key) for key in keys}


def completeness_warnings(rows: list[dict[str, Any]]) -> list[str]:
    warnings = []
    counts: dict[str, int] = {}
    for row in rows:
        status = normalize(row.get("data_status")) or "unknown"
        if status != "complete":
            counts[status] = counts.get(status, 0) + 1
    for status, count in sorted(counts.items()):
        warnings.append(f"{count} row(s) have data_status={status}.")
    return warnings


def nullable_money(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return round(number, 2)


def none_if_any_none(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None
    return money(sum(value or 0 for value in values))


def nested_dict(value: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    current: Any = value or {}
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key) or {}
    return current if isinstance(current, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def payout_status_summary(finance: dict[str, Any] | None) -> dict[str, Any]:
    breakdown = nested_dict(finance, "raw_financial_event_groups_json", "inTransitBreakdown")
    return {
        "processing_transfer_cash": nullable_money(breakdown.get("processingTransferCash")),
        "recent_completed_transfer_cash": nullable_money(breakdown.get("recentCompletedTransferCash")),
        "recent_completed_transfer_count": len(list_value(breakdown.get("recentCompletedTransferGroupIds"))),
    }


def latest_payout_date(finance: dict[str, Any] | None) -> str | None:
    breakdown = nested_dict(finance, "raw_financial_event_groups_json", "inTransitBreakdown")
    values: list[str] = []
    for key in ("processingTransfers", "recentCompletedTransfers"):
        for row in list_value(breakdown.get(key)):
            if isinstance(row, dict):
                values.extend(
                    str(row.get(field))
                    for field in ("fundTransferDate", "postedDate", "date")
                    if row.get(field)
                )
    return latest_value(values)


def freshness_status(timestamps: dict[str, Any]) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    entries = []
    stale = 0
    for key, value in sorted(timestamps.items()):
        parsed = datetime_from_text(value)
        is_stale = parsed is not None and (now - parsed).total_seconds() > STALE_SOURCE_HOURS * 3600
        if is_stale:
            stale += 1
        entries.append({
            "source": key,
            "timestamp": value,
            "is_missing": not bool(value),
            "is_stale": is_stale,
        })
    return {
        "stale_source_count": stale,
        "sources": entries,
    }


def datetime_from_text(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value)
    if len(text) == 10:
        text = f"{text}T00:00:00+00:00"
    text = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def month_key(value: Any) -> str | None:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else None


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
