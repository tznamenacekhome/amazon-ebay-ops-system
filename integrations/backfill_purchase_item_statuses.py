import argparse
import os
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client

try:
    from status_logic import derive_purchase_item_status
except ImportError:
    from integrations.status_logic import derive_purchase_item_status


PAGE_SIZE = 1000


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill purchase_items.current_status from canonical backend status logic."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates. Without this flag, only prints a dry-run summary.",
    )
    return parser.parse_args()


def fetch_all(supabase, table, columns):
    rows = []
    offset = 0

    while True:
        result = (
            supabase.table(table)
            .select(columns)
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)

        if len(batch) < PAGE_SIZE:
            return rows

        offset += PAGE_SIZE


def has_seller_shipped(raw_import_json):
    order = raw_import_json.get("Order") if isinstance(raw_import_json, dict) else raw_import_json

    return has_nested_key(order, "ShippedTime")


def is_ebay_cancelled(raw_import_json, order_status=None):
    if normalize_text(order_status).find("cancel") >= 0:
        return True

    order = raw_import_json.get("Order") if isinstance(raw_import_json, dict) else raw_import_json
    cancel_status = find_nested_value(order, "CancelStatus")

    return (
        isinstance(cancel_status, str)
        and cancel_status.strip()
        and normalize_text(cancel_status) != "notapplicable"
    )


def has_nested_key(value, key):
    if not isinstance(value, (dict, list)):
        return False

    if isinstance(value, dict):
        if value.get(key):
            return True

        return any(has_nested_key(child, key) for child in value.values())

    return any(has_nested_key(child, key) for child in value)


def find_nested_value(value, key):
    if not isinstance(value, (dict, list)):
        return None

    if isinstance(value, dict):
        if key in value:
            return value[key]

        for child in value.values():
            found = find_nested_value(child, key)
            if found is not None:
                return found

        return None

    for child in value:
        found = find_nested_value(child, key)
        if found is not None:
            return found

    return None


def normalize_text(value):
    return str(value or "").strip().lower().replace(" ", "").replace("_", "")


def shipment_status(shipment):
    return (
        shipment.get("normalized_status")
        or shipment.get("shipment_status")
        or shipment.get("carrier_status")
    )


def choose_shipment_for_item(item, item_shipments):
    tracking_number = item.get("tracking_number")
    shipments = item_shipments.get(item["item_id"], [])

    if tracking_number:
        for shipment in shipments:
            if shipment.get("tracking_number") == tracking_number:
                return shipment

    if shipments:
        return shipments[0]

    return None


def main():
    args = parse_args()
    load_dotenv()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    items = fetch_all(
        supabase,
        "purchase_items",
        "item_id,purchase_id,current_status,tracking_number",
    )
    purchases = fetch_all(
        supabase,
        "purchases",
        "purchase_id,order_status,raw_import_json",
    )
    shipments = fetch_all(
        supabase,
        "inbound_shipments",
        "inbound_shipment_id,purchase_id,tracking_number,normalized_status,shipment_status,carrier_status,delivered_date",
    )
    shipment_links = fetch_all(
        supabase,
        "inbound_shipment_items",
        "inbound_shipment_id,item_id",
    )

    purchase_by_id = {row["purchase_id"]: row for row in purchases}
    shipment_by_id = {
        row["inbound_shipment_id"]: row
        for row in shipments
        if row.get("inbound_shipment_id")
    }
    item_shipments = defaultdict(list)

    for link in shipment_links:
        shipment = shipment_by_id.get(link.get("inbound_shipment_id"))
        if shipment and link.get("item_id"):
            item_shipments[link["item_id"]].append(shipment)

    changes = []

    for item in items:
        purchase = purchase_by_id.get(item.get("purchase_id"), {})
        shipment = choose_shipment_for_item(item, item_shipments)
        raw_import_json = purchase.get("raw_import_json") or {}
        current_status = item.get("current_status")
        next_status = derive_purchase_item_status(
            current_status=current_status,
            tracking_number=item.get("tracking_number"),
            carrier_status=shipment_status(shipment or {}),
            delivered_date=(shipment or {}).get("delivered_date"),
            seller_shipped=has_seller_shipped(raw_import_json),
            ebay_cancelled=is_ebay_cancelled(
                raw_import_json,
                purchase.get("order_status"),
            ),
        )

        if next_status != current_status:
            changes.append({
                "item_id": item["item_id"],
                "old_status": current_status,
                "new_status": next_status,
            })

    by_status = defaultdict(int)
    for change in changes:
        by_status[(change["old_status"], change["new_status"])] += 1

    print(f"Purchase items scanned: {len(items)}")
    print(f"Status changes found: {len(changes)}")

    for (old_status, new_status), count in sorted(by_status.items(), key=lambda row: (-row[1], str(row[0]))):
        print(f"{old_status or '<blank>'} -> {new_status}: {count}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to write changes.")
        return

    for change in changes:
        (
            supabase.table("purchase_items")
            .update({"current_status": change["new_status"]})
            .eq("item_id", change["item_id"])
            .execute()
        )

    print(f"Applied status updates: {len(changes)}")


if __name__ == "__main__":
    main()
