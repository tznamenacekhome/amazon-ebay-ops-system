"""Sync Amazon seller sales orders into MBOP sales-order tables.

This integration reads Amazon SP-API Orders data and writes only Amazon-specific
sales tables. It does not request restricted buyer PII and must not write to
purchases or purchase_items.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_sales_order_sync")
BATCH_SIZE = 200
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_ORDER_ITEM_DELAY_SECONDS = 2.2
MIN_PURCHASE_DATE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


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
        import_batch_id = str(uuid.uuid4())
        orders = filter_orders_since_cutoff(fetch_orders(client, args))
        order_rows = [build_order_row(order, import_batch_id) for order in orders]
        item_rows: list[dict[str, Any]] = []

        item_fetch_failures: list[str] = []
        for order in orders:
            amazon_order_id = clean_text(order.get("AmazonOrderId"))
            if not amazon_order_id:
                continue
            try:
                items = list(client.iter_order_items(amazon_order_id))
            except AmazonSPAPIError as error:
                item_fetch_failures.append(amazon_order_id)
                LOGGER.warning(
                    "Skipping order items for %s after Amazon error: %s",
                    amazon_order_id,
                    error,
                )
                continue
            item_rows.extend(build_item_row(amazon_order_id, item) for item in items)
            if args.order_item_delay_seconds > 0:
                time.sleep(args.order_item_delay_seconds)

        print_summary(
            order_rows,
            item_rows,
            apply=args.apply,
            item_fetch_failures=item_fetch_failures,
        )

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        supabase = get_supabase_client()
        upsert_rows(
            supabase,
            "amazon_sales_orders",
            order_rows,
            "amazon_order_id",
        )
        upsert_rows(
            supabase,
            "amazon_sales_order_items",
            item_rows,
            "amazon_order_item_id",
        )
        LOGGER.info(
            "Amazon sales order sync complete. orders=%s items=%s",
            len(order_rows),
            len(item_rows),
        )
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon SP-API sales order sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Amazon sales order sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Amazon sales orders into MBOP.")
    parser.add_argument("--order-id", help="Target a single Amazon order ID.")
    parser.add_argument(
        "--last-updated-after",
        help="Incremental sync lower bound as ISO timestamp.",
    )
    parser.add_argument("--created-after", help="CreatedAfter ISO timestamp.")
    parser.add_argument("--created-before", help="CreatedBefore ISO timestamp.")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Default LastUpdatedAfter lookback when no explicit range is provided.",
    )
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum orders to process after listing.",
    )
    parser.add_argument(
        "--order-item-delay-seconds",
        type=float,
        default=DEFAULT_ORDER_ITEM_DELAY_SECONDS,
        help="Delay between getOrderItems calls to stay under Amazon Orders API quotas.",
    )
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Normalize and print counts without writing. This is the default.",
    )
    return parser.parse_args()


def fetch_orders(client: AmazonSPAPIClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.order_id:
        payload = client.get_order(args.order_id)
        order = payload.get("payload") or payload
        return [order] if order else []

    last_updated_after = args.last_updated_after
    if not last_updated_after and not args.created_after:
        last_updated_after = iso_z(
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.lookback_days)
        )

    orders = list(
        client.iter_orders(
            last_updated_after=last_updated_after,
            created_after=args.created_after,
            created_before=args.created_before,
            max_pages=args.max_pages,
        )
    )
    if args.limit is not None:
        return orders[: args.limit]
    return orders


def filter_orders_since_cutoff(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    skipped = 0
    for order in orders:
        purchase_date = parse_amazon_datetime(clean_text(order.get("PurchaseDate")))
        if purchase_date and purchase_date < MIN_PURCHASE_DATE:
            skipped += 1
            continue
        kept.append(order)
    if skipped:
        LOGGER.info(
            "Skipped %s Amazon sales orders before MBOP sales cutoff %s",
            skipped,
            MIN_PURCHASE_DATE.date().isoformat(),
        )
    return kept


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def build_order_row(order: dict[str, Any], import_batch_id: str) -> dict[str, Any]:
    order_total = order.get("OrderTotal") or {}
    cancel = order.get("BuyerRequestedCancel") or {}
    return {
        "amazon_order_id": clean_text(order.get("AmazonOrderId")),
        "purchase_date": clean_text(order.get("PurchaseDate")),
        "last_update_date": clean_text(order.get("LastUpdateDate")),
        "order_status": clean_text(order.get("OrderStatus")),
        "fulfillment_channel": clean_text(order.get("FulfillmentChannel")),
        "sales_channel": clean_text(order.get("SalesChannel")),
        "marketplace_id": clean_text(order.get("MarketplaceId")),
        "buyer_requested_cancel": to_bool(cancel.get("IsBuyerRequestedCancel")),
        "is_replacement_order": to_bool(order.get("IsReplacementOrder")),
        "is_business_order": to_bool(order.get("IsBusinessOrder")),
        "is_prime": to_bool(order.get("IsPrime")),
        "number_of_items_shipped": to_int(order.get("NumberOfItemsShipped")),
        "number_of_items_unshipped": to_int(order.get("NumberOfItemsUnshipped")),
        "order_total_amount": money_amount(order_total),
        "order_total_currency": money_currency(order_total),
        "payment_method": clean_text(order.get("PaymentMethod")),
        "shipment_service_level_category": clean_text(
            order.get("ShipmentServiceLevelCategory")
        ),
        "earliest_ship_date": clean_text(order.get("EarliestShipDate")),
        "latest_ship_date": clean_text(order.get("LatestShipDate")),
        "earliest_delivery_date": clean_text(order.get("EarliestDeliveryDate")),
        "latest_delivery_date": clean_text(order.get("LatestDeliveryDate")),
        "raw_order_json": scrub_order_payload(order),
        "import_batch_id": import_batch_id,
        "updated_at": iso_z(dt.datetime.now(dt.timezone.utc)),
    }


def build_item_row(amazon_order_id: str, item: dict[str, Any]) -> dict[str, Any]:
    item_price = item.get("ItemPrice") or {}
    item_tax = item.get("ItemTax") or {}
    shipping_price = item.get("ShippingPrice") or {}
    shipping_tax = item.get("ShippingTax") or {}
    gift_wrap_price = item.get("GiftWrapPrice") or {}
    gift_wrap_tax = item.get("GiftWrapTax") or {}
    item_discount = item.get("PromotionDiscount") or {}
    ship_discount = item.get("ShippingDiscount") or {}
    return {
        "amazon_order_item_id": clean_text(item.get("OrderItemId")),
        "amazon_order_id": amazon_order_id,
        "asin": clean_text(item.get("ASIN")),
        "seller_sku": clean_text(item.get("SellerSKU")),
        "title": clean_text(item.get("Title")),
        "quantity_ordered": to_int(item.get("QuantityOrdered")),
        "quantity_shipped": to_int(item.get("QuantityShipped")),
        "item_price_amount": money_amount(item_price),
        "item_price_currency": money_currency(item_price),
        "item_tax_amount": money_amount(item_tax),
        "shipping_price_amount": money_amount(shipping_price),
        "shipping_tax_amount": money_amount(shipping_tax),
        "gift_wrap_price_amount": money_amount(gift_wrap_price),
        "gift_wrap_tax_amount": money_amount(gift_wrap_tax),
        "item_promotion_discount_amount": money_amount(item_discount),
        "ship_promotion_discount_amount": money_amount(ship_discount),
        "condition_id": clean_text(item.get("ConditionId")),
        "condition_subtype_id": clean_text(item.get("ConditionSubtypeId")),
        "raw_order_item_json": scrub_item_payload(item),
        "updated_at": iso_z(dt.datetime.now(dt.timezone.utc)),
    }


def scrub_order_payload(order: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "BuyerInfo",
        "DefaultShipFromLocationAddress",
        "ShippingAddress",
        "BuyerTaxInformation",
    }
    return {key: value for key, value in order.items() if key not in blocked}


def scrub_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    blocked = {"BuyerInfo", "ShippingAddress"}
    return {key: value for key, value in item.items() if key not in blocked}


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    usable_rows = [row for row in rows if row.get(on_conflict)]
    for chunk in chunks(usable_rows, BATCH_SIZE):
        supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def money_amount(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("Amount") or value.get("CurrencyAmount") or value.get("amount")
    if amount in (None, ""):
        return None
    try:
        return round(float(amount), 2)
    except (TypeError, ValueError):
        return None


def money_currency(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return clean_text(value.get("CurrencyCode") or value.get("currencyCode"))


def to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def iso_z(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse_amazon_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def print_summary(
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    *,
    apply: bool,
    item_fetch_failures: list[str],
) -> None:
    mode = "write" if apply else "dry run"
    print(f"Amazon sales order {mode}")
    print("------------------------------")
    print(f"Orders: {len(order_rows)}")
    print(f"Items: {len(item_rows)}")
    print(f"Item fetch failures: {len(item_fetch_failures)}")
    for row in order_rows[:5]:
        print(
            f"- {row['amazon_order_id']} {row.get('purchase_date') or '--'} "
            f"{row.get('order_status') or '--'} {row.get('fulfillment_channel') or '--'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
