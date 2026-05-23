import argparse
import os

from dotenv import load_dotenv
from supabase import create_client


load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)


SELLER_RAW_KEYS = {
    "sellerId",
    "orderFulfillmentStatus",
    "fulfillmentStartInstructions",
    "paymentSummary",
    "salesRecordReference",
    "totalMarketplaceFee",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Remove eBay seller orders accidentally stored as purchases."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Omit for dry-run output.",
    )
    return parser.parse_args()


def is_seller_order(purchase):
    raw = purchase.get("raw_import_json") or {}

    if not isinstance(raw, dict):
        return False

    if raw.get("sellerId"):
        return True

    return any(key in raw for key in SELLER_RAW_KEYS)


def fetch_seller_purchases():
    result = (
        supabase.table("purchases")
        .select("purchase_id,supplier_order_id,order_date,order_status,raw_import_json")
        .eq("supplier", "eBay")
        .limit(5000)
        .execute()
    )

    return [
        row
        for row in result.data or []
        if is_seller_order(row)
    ]


def fetch_related_ids(purchase_ids):
    item_result = (
        supabase.table("purchase_items")
        .select("item_id,purchase_id")
        .in_("purchase_id", purchase_ids)
        .execute()
    )
    shipment_result = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id,purchase_id")
        .in_("purchase_id", purchase_ids)
        .execute()
    )

    item_ids = [
        row["item_id"]
        for row in item_result.data or []
        if row.get("item_id")
    ]
    shipment_ids = [
        row["inbound_shipment_id"]
        for row in shipment_result.data or []
        if row.get("inbound_shipment_id")
    ]

    return item_ids, shipment_ids


def delete_in_chunks(table_name, column_name, values):
    deleted = 0

    for start in range(0, len(values), 100):
        chunk = values[start:start + 100]

        if not chunk:
            continue

        result = (
            supabase.table(table_name)
            .delete()
            .in_(column_name, chunk)
            .execute()
        )

        deleted += len(result.data or [])

    return deleted


def main():
    args = parse_args()
    seller_purchases = fetch_seller_purchases()
    purchase_ids = [
        row["purchase_id"]
        for row in seller_purchases
        if row.get("purchase_id")
    ]

    print(f"Seller orders found in purchases: {len(seller_purchases)}")

    for row in seller_purchases:
        print(
            f"- {row.get('supplier_order_id')} | "
            f"{row.get('order_date')} | {row.get('order_status')}"
        )

    if not purchase_ids:
        return

    item_ids, shipment_ids = fetch_related_ids(purchase_ids)

    print()
    print(f"Related purchase_items: {len(item_ids)}")
    print(f"Related inbound_shipments: {len(shipment_ids)}")

    if not args.apply:
        print()
        print("Dry run only. Re-run with --apply to delete these rows.")
        return

    deleted_shipment_item_links = 0

    if shipment_ids:
        deleted_shipment_item_links += delete_in_chunks(
            "inbound_shipment_items",
            "inbound_shipment_id",
            shipment_ids,
        )

    if item_ids:
        deleted_shipment_item_links += delete_in_chunks(
            "inbound_shipment_items",
            "item_id",
            item_ids,
        )

    deleted_shipments = delete_in_chunks(
        "inbound_shipments",
        "purchase_id",
        purchase_ids,
    )
    deleted_items = delete_in_chunks(
        "purchase_items",
        "purchase_id",
        purchase_ids,
    )
    deleted_purchases = delete_in_chunks(
        "purchases",
        "purchase_id",
        purchase_ids,
    )

    print()
    print("Cleanup complete.")
    print(f"Deleted inbound_shipment_items: {deleted_shipment_item_links}")
    print(f"Deleted inbound_shipments: {deleted_shipments}")
    print(f"Deleted purchase_items: {deleted_items}")
    print(f"Deleted purchases: {deleted_purchases}")


if __name__ == "__main__":
    main()
