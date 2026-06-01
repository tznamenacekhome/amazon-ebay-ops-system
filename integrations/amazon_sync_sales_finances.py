"""Sync Amazon order-specific financial events for sales profitability.

Stores raw and normalized financial-event rows in Amazon-specific sales tables.
FBA fulfillment fees are preserved with their fee_type so profitability can keep
Amazon fees separate from fulfillment cost.
"""

from __future__ import annotations

import argparse
import datetime as dt
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
DEFAULT_TRANSACTION_LOOKBACK_DAYS = 180
MAX_TRANSACTION_PAGES = 50


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
            else fetch_missing_fee_order_ids(
                limit=args.limit,
                purchase_date_start=args.purchase_date_start,
                purchase_date_end=args.purchase_date_end,
            )
            if args.missing_fees_only
            else fetch_order_ids(
                limit=args.limit,
                purchase_date_start=args.purchase_date_start,
                purchase_date_end=args.purchase_date_end,
            )
        )
        rows: list[dict[str, Any]] = []
        rows_by_order_id: dict[str, list[dict[str, Any]]] = {}
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
            order_rows = build_financial_event_rows(order_id, payload)
            rows_by_order_id[order_id] = order_rows
            rows.extend(order_rows)
            if args.order_finance_delay_seconds > 0:
                time.sleep(args.order_finance_delay_seconds)

        transaction_rows, transaction_event_rows = fetch_transaction_fallback_rows(
            client,
            order_ids,
            rows_by_order_id,
            transaction_posted_after=transaction_posted_after(args),
        )
        rows.extend(transaction_event_rows)

        print_summary(
            order_ids,
            rows,
            transaction_rows=transaction_rows,
            transaction_event_rows=transaction_event_rows,
            apply=args.apply,
            failures=failures,
        )

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        upsert_rows(
            supabase,
            "amazon_sales_finance_transactions",
            transaction_rows,
            "transaction_id",
        )
        replace_rows(
            supabase,
            "amazon_sales_financial_events",
            rows,
        )
        LOGGER.info(
            "Amazon sales finance sync complete. financial_rows=%s transaction_rows=%s",
            len(rows),
            len(transaction_rows),
        )
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
    parser.add_argument(
        "--transaction-lookback-days",
        type=int,
        default=DEFAULT_TRANSACTION_LOOKBACK_DAYS,
        help="Transactions API postedAfter lookback for deferred-order fallback rows.",
    )
    parser.add_argument(
        "--transaction-posted-after",
        help="Override Transactions API postedAfter as an ISO timestamp.",
    )
    parser.add_argument(
        "--missing-fees-only",
        action="store_true",
        help="Only process orders currently shown with missing fee data.",
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


def fetch_missing_fee_order_ids(
    *,
    limit: int | None,
    purchase_date_start: str | None,
    purchase_date_end: str | None,
) -> list[str]:
    supabase = get_supabase_client()
    request = (
        supabase.table("vw_amazon_sales_orders_recent")
        .select("amazon_order_id,purchase_date")
        .eq("data_status", "missing_fees")
    )
    effective_start = max_iso(purchase_date_start, MIN_PURCHASE_DATE)
    if effective_start:
        request = request.gte("purchase_date", effective_start)
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


def fetch_transaction_fallback_rows(
    client: AmazonSPAPIClient,
    order_ids: list[str],
    legacy_rows_by_order_id: dict[str, list[dict[str, Any]]],
    *,
    transaction_posted_after: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    order_id_set = set(order_ids)
    if not order_id_set:
        return [], []

    transaction_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []

    for transaction in iter_transactions(client, posted_after=transaction_posted_after):
        amazon_order_id = transaction_order_id(transaction)
        if amazon_order_id not in order_id_set:
            continue

        transaction_rows.append(build_transaction_row(transaction, amazon_order_id))
        if legacy_rows_by_order_id.get(amazon_order_id):
            continue
        event_rows.extend(build_transaction_financial_event_rows(transaction, amazon_order_id))

    return dedupe_transaction_rows(transaction_rows), dedupe_rows(event_rows)


def iter_transactions(client: AmazonSPAPIClient, *, posted_after: str):
    next_token: str | None = None
    pages_seen = 0
    while True:
        params = (
            {"nextToken": next_token}
            if next_token
            else {
                "postedAfter": posted_after,
                "marketplaceId": client.config.marketplace_id,
            }
        )
        payload = client.request(
            "GET",
            "/finances/2024-06-19/transactions",
            params=params,
        )
        container = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        for transaction in container.get("transactions") or []:
            if isinstance(transaction, dict):
                yield transaction

        next_token = container.get("nextToken")
        pages_seen += 1
        if not next_token:
            return
        if pages_seen >= MAX_TRANSACTION_PAGES:
            LOGGER.warning("Stopping Amazon transactions pagination at max pages=%s", MAX_TRANSACTION_PAGES)
            return


def build_transaction_row(
    transaction: dict[str, Any],
    amazon_order_id: str,
) -> dict[str, Any]:
    marketplace = transaction.get("marketplaceDetails") or {}
    return {
        "transaction_id": clean_text(transaction.get("transactionId")),
        "amazon_order_id": amazon_order_id,
        "transaction_type": clean_text(transaction.get("transactionType")),
        "transaction_status": clean_text(transaction.get("transactionStatus")),
        "posted_date": clean_text(transaction.get("postedDate")),
        "marketplace_id": clean_text(marketplace.get("marketplaceId")),
        "marketplace_name": clean_text(marketplace.get("marketplaceName")),
        "financial_event_group_id": related_identifier(
            transaction,
            "FINANCIAL_EVENT_GROUP_ID",
        ),
        "shipment_id": related_identifier(transaction, "SHIPMENT_ID"),
        "settlement_id": related_identifier(transaction, "SETTLEMENT_ID"),
        "total_amount": transaction_amount(transaction),
        "currency": transaction_currency(transaction),
        "description": clean_text(transaction.get("description")),
        "source": "amazon_spapi_transactions",
        "raw_transaction_json": transaction,
        "updated_at": utc_now(),
    }


def build_transaction_financial_event_rows(
    transaction: dict[str, Any],
    amazon_order_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    transaction_id = clean_text(transaction.get("transactionId"))
    posted_date = clean_text(transaction.get("postedDate"))
    transaction_status = clean_text(transaction.get("transactionStatus"))

    for item_index, item in enumerate(transaction.get("items") or []):
        if not isinstance(item, dict):
            continue
        amazon_order_item_id = item_order_item_id(item)
        for fee in amazon_fee_breakdowns(item):
            fee_type = clean_text(fee.get("breakdownType"))
            amount = breakdown_amount(fee)
            currency = breakdown_currency(fee)
            if not fee_type or amount is None or not currency:
                continue
            path = ["transactions", transaction_id or "unknown", "items", str(item_index), "AmazonFees", fee_type]
            rows.append(
                {
                    "financial_event_id": deterministic_event_id(
                        amazon_order_id,
                        "TransactionEventList",
                        path,
                        {
                            "amazon_order_item_id": amazon_order_item_id,
                            "fee_type": fee_type,
                            "transaction_id": transaction_id,
                        },
                        amount,
                        currency,
                    ),
                    "amazon_order_id": amazon_order_id,
                    "amazon_order_item_id": amazon_order_item_id,
                    "event_type": "TransactionEventList",
                    "posted_date": posted_date,
                    "amount": amount,
                    "currency": currency,
                    "fee_type": fee_type,
                    "charge_type": None,
                    "promotion_type": None,
                    "source": "amazon_spapi_transactions",
                    "raw_financial_event_json": {
                        "event_type": "TransactionEventList",
                        "transaction_id": transaction_id,
                        "transaction_status": transaction_status,
                        "fee": fee,
                        "item": item,
                        "transaction": transaction,
                    },
                }
            )

    return rows


def amazon_fee_breakdowns(item: dict[str, Any]) -> list[dict[str, Any]]:
    for breakdown in item.get("breakdowns") or []:
        if not isinstance(breakdown, dict):
            continue
        if breakdown.get("breakdownType") == "AmazonFees":
            return [
                row
                for row in breakdown.get("breakdowns") or []
                if isinstance(row, dict)
            ]
    return []


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


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    usable_rows = [row for row in rows if row.get(on_conflict)]
    for chunk in chunks(usable_rows, BATCH_SIZE):
        supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()


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


def dedupe_transaction_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        transaction_id = row.get("transaction_id")
        if not transaction_id or transaction_id in seen:
            continue
        seen.add(transaction_id)
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


def transaction_posted_after(args: argparse.Namespace) -> str:
    if args.transaction_posted_after:
        return args.transaction_posted_after
    if args.purchase_date_start:
        return args.purchase_date_start
    lookback_days = max(args.transaction_lookback_days, 1)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    return iso_z(cutoff)


def money_amount(value: dict[str, Any]) -> float | None:
    amount = (
        value.get("CurrencyAmount")
        or value.get("currencyAmount")
        or value.get("Amount")
        or value.get("amount")
    )
    if amount in (None, ""):
        return None
    try:
        return round(float(amount), 2)
    except (TypeError, ValueError):
        return None


def money_currency(value: dict[str, Any]) -> str | None:
    currency = value.get("CurrencyCode") or value.get("currencyCode")
    return str(currency).strip() if currency else None


def related_identifier(transaction: dict[str, Any], name: str) -> str | None:
    for row in transaction.get("relatedIdentifiers") or []:
        if not isinstance(row, dict):
            continue
        if row.get("relatedIdentifierName") == name:
            return clean_text(row.get("relatedIdentifierValue"))
    return None


def transaction_order_id(transaction: dict[str, Any]) -> str | None:
    return related_identifier(transaction, "ORDER_ID")


def item_order_item_id(item: dict[str, Any]) -> str | None:
    for row in item.get("relatedIdentifiers") or []:
        if not isinstance(row, dict):
            continue
        if row.get("itemRelatedIdentifierName") in {
            "ORDER_ITEM_ID",
            "ORDER_ADJUSTMENT_ITEM_ID",
        }:
            return clean_text(row.get("itemRelatedIdentifierValue"))
    return None


def transaction_amount(transaction: dict[str, Any]) -> float | None:
    return money_amount(transaction.get("totalAmount") or {})


def transaction_currency(transaction: dict[str, Any]) -> str | None:
    return money_currency(transaction.get("totalAmount") or {})


def breakdown_amount(row: dict[str, Any]) -> float | None:
    return money_amount(row.get("breakdownAmount") or {})


def breakdown_currency(row: dict[str, Any]) -> str | None:
    return money_currency(row.get("breakdownAmount") or {})


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def iso_z(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def utc_now() -> str:
    return iso_z(dt.datetime.now(dt.timezone.utc))


def print_summary(
    amazon_order_ids: list[str],
    rows: list[dict[str, Any]],
    *,
    transaction_rows: list[dict[str, Any]],
    transaction_event_rows: list[dict[str, Any]],
    apply: bool,
    failures: list[str],
) -> None:
    mode = "write" if apply else "dry run"
    print(f"Amazon sales finance {mode}")
    print("-------------------------")
    print(f"Orders: {len(amazon_order_ids)}")
    print(f"Financial rows: {len(rows)}")
    print(f"Transaction rows: {len(transaction_rows)}")
    print(f"Transaction-derived financial rows: {len(transaction_event_rows)}")
    print(f"Order finance failures: {len(failures)}")
    for row in rows[:10]:
        label = row.get("fee_type") or row.get("charge_type") or row.get("promotion_type")
        print(
            f"- {row['event_type']} {label or '--'} "
            f"{row['amount']} {row['currency']} item={row.get('amazon_order_item_id') or '--'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
