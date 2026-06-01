"""Sync Amazon order-specific financial events for sales profitability.

Stores raw and normalized financial-event rows in Amazon-specific sales tables.
FBA fulfillment fees are preserved with their fee_type so profitability can keep
Amazon fees separate from fulfillment cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_sales_finance_sync")
BATCH_SIZE = 200
DEFAULT_ORDER_FINANCE_DELAY_SECONDS = 0.75
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
        client = AmazonSPAPIClient.from_env()
        order_ids = (
            [args.order_id]
            if args.order_id
            else fetch_order_ids(
                limit=args.limit,
                purchase_date_start=args.purchase_date_start,
                purchase_date_end=args.purchase_date_end,
            )
        )
        rows: list[dict[str, Any]] = []
        failures: list[str] = []
        for order_id in order_ids:
            try:
                payload = client.get_order_financial_events(order_id)
            except AmazonSPAPIError as error:
                failures.append(order_id)
                LOGGER.warning(
                    "Skipping financial events for %s after Amazon error: %s",
                    order_id,
                    error,
                )
                continue
            rows.extend(build_financial_event_rows(order_id, payload))
            if args.order_finance_delay_seconds > 0:
                time.sleep(args.order_finance_delay_seconds)

        print_summary(order_ids, rows, apply=args.apply, failures=failures)

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        replace_rows(
            supabase,
            "amazon_sales_financial_events",
            rows,
        )
        LOGGER.info("Amazon sales finance sync complete. rows=%s", len(rows))
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon SP-API sales finance sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001
        LOGGER.exception("Unexpected Amazon sales finance sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Amazon financial events for one sales order."
    )
    parser.add_argument("--order-id", help="Amazon order ID.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum stored orders to process. Defaults to 100 for recent-order mode.",
    )
    parser.add_argument(
        "--purchase-date-start",
        help="Stored order purchase_date lower bound as ISO timestamp.",
    )
    parser.add_argument(
        "--purchase-date-end",
        help="Stored order purchase_date upper bound as ISO timestamp.",
    )
    parser.add_argument(
        "--order-finance-delay-seconds",
        type=float,
        default=DEFAULT_ORDER_FINANCE_DELAY_SECONDS,
        help="Delay between order-specific finances calls to stay under Amazon quotas.",
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


def fetch_order_ids(
    *,
    limit: int | None,
    purchase_date_start: str | None,
    purchase_date_end: str | None,
) -> list[str]:
    supabase = get_supabase_client()
    request = supabase.table("amazon_sales_orders").select("amazon_order_id")
    effective_start = max_iso(purchase_date_start, MIN_PURCHASE_DATE)
    if effective_start:
        request = request.gte("purchase_date", effective_start)
    if purchase_date_end:
        request = request.lt("purchase_date", purchase_date_end)
    if purchase_date_start or purchase_date_end:
        request = request.order("purchase_date", desc=False)
        if limit:
            request = request.limit(max(limit, 1))
    else:
        request = request.order("purchase_date", desc=True).limit(max(limit or 100, 1))
    result = request.execute()
    return [row["amazon_order_id"] for row in result.data or [] if row.get("amazon_order_id")]


def build_financial_event_rows(
    amazon_order_id: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    container = payload.get("payload") or payload
    events = container.get("FinancialEvents") or container
    rows: list[dict[str, Any]] = []

    for event_type, event_list in events.items():
        if not isinstance(event_list, list):
            continue
        for event in event_list:
            if not isinstance(event, dict):
                continue
            rows.extend(extract_event_rows(amazon_order_id, event_type, event))

    return rows


def extract_event_rows(
    amazon_order_id: str,
    event_type: str,
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    posted_date = first_text(
        event,
        "PostedDate",
        "ShipmentPostedDate",
        "AdjustmentEventDate",
        "RefundEventDate",
    )
    rows: list[dict[str, Any]] = []

    def visit(value: Any, path: list[str], context: dict[str, Any]) -> None:
        if isinstance(value, dict):
            next_context = {
                **context,
                "amazon_order_item_id": first_text(
                    value,
                    "OrderItemId",
                    "AmazonOrderItemCode",
                )
                or context.get("amazon_order_item_id"),
                "fee_type": first_text(value, "FeeType") or context.get("fee_type"),
                "charge_type": first_text(value, "ChargeType")
                or context.get("charge_type"),
                "promotion_type": first_text(value, "PromotionType")
                or context.get("promotion_type"),
            }
            amount = money_amount(value)
            currency = money_currency(value)
            if amount is not None and currency:
                raw_event = {
                    "event_type": event_type,
                    "path": path,
                    "event": event,
                    "money_node": value,
                }
                row = {
                    "financial_event_id": deterministic_event_id(
                        amazon_order_id,
                        event_type,
                        path,
                        next_context,
                        amount,
                        currency,
                    ),
                    "amazon_order_id": amazon_order_id,
                    "amazon_order_item_id": next_context.get("amazon_order_item_id"),
                    "event_type": event_type,
                    "posted_date": posted_date,
                    "amount": amount,
                    "currency": currency,
                    "fee_type": next_context.get("fee_type"),
                    "charge_type": next_context.get("charge_type"),
                    "promotion_type": next_context.get("promotion_type"),
                    "source": "amazon_spapi_finances",
                    "raw_financial_event_json": raw_event,
                }
                rows.append(row)

            for key, child in value.items():
                visit(child, [*path, key], next_context)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, [*path, str(index)], context)

    visit(event, [event_type], {})
    return rows


def deterministic_event_id(
    amazon_order_id: str,
    event_type: str,
    path: list[str],
    context: dict[str, Any],
    amount: float,
    currency: str,
) -> str:
    seed = json.dumps(
        {
            "amazon_order_id": amazon_order_id,
            "event_type": event_type,
            "path": path,
            "context": context,
            "amount": amount,
            "currency": currency,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def replace_rows(supabase, table: str, rows: list[dict[str, Any]]) -> None:
    rows = dedupe_rows(rows)
    for chunk in chunks(rows, BATCH_SIZE):
        event_ids = [row["financial_event_id"] for row in chunk]
        supabase.table(table).delete().in_("financial_event_id", event_ids).execute()
        supabase.table(table).insert(chunk).execute()


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        event_id = row.get("financial_event_id")
        if not event_id or event_id in seen:
            continue
        seen.add(event_id)
        deduped.append(row)
    return deduped


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def max_iso(left: str | None, right: str | None) -> str | None:
    values = [value for value in (left, right) if value]
    return max(values) if values else None


def money_amount(value: dict[str, Any]) -> float | None:
    amount = value.get("CurrencyAmount") or value.get("Amount") or value.get("amount")
    if amount in (None, ""):
        return None
    try:
        return round(float(amount), 2)
    except (TypeError, ValueError):
        return None


def money_currency(value: dict[str, Any]) -> str | None:
    currency = value.get("CurrencyCode") or value.get("currencyCode")
    return str(currency).strip() if currency else None


def print_summary(
    amazon_order_ids: list[str],
    rows: list[dict[str, Any]],
    *,
    apply: bool,
    failures: list[str],
) -> None:
    mode = "write" if apply else "dry run"
    print(f"Amazon sales finance {mode}")
    print("-------------------------")
    print(f"Orders: {len(amazon_order_ids)}")
    print(f"Financial rows: {len(rows)}")
    print(f"Order finance failures: {len(failures)}")
    for row in rows[:10]:
        label = row.get("fee_type") or row.get("charge_type") or row.get("promotion_type")
        print(
            f"- {row['event_type']} {label or '--'} "
            f"{row['amount']} {row['currency']} item={row.get('amazon_order_item_id') or '--'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
