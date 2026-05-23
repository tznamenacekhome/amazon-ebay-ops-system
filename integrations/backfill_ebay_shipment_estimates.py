import argparse
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client


DEFAULT_START_DATE = "2026-05-01"


load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Restore missing shipment ETAs from stored eBay order data."
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help="Only inspect purchases on or after this date.",
    )
    return parser.parse_args()


def iso_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def find_nested_value(value, key):
    if not isinstance(value, dict):
        return None

    if key in value:
        return value[key]

    for child in value.values():
        if isinstance(child, dict):
            found = find_nested_value(child, key)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                found = find_nested_value(item, key)
                if found:
                    return found

    return None


def main():
    args = parse_args()

    purchases_result = (
        supabase.table("purchases")
        .select("purchase_id,supplier_order_id,raw_import_json")
        .gte("order_date", args.start_date)
        .limit(1000)
        .execute()
    )
    purchases = purchases_result.data or []
    purchase_ids = [row["purchase_id"] for row in purchases]

    if not purchase_ids:
        print("No purchases found.")
        return

    estimates_by_purchase = {}

    for purchase in purchases:
        estimate = find_nested_value(
            purchase.get("raw_import_json") or {},
            "EstimatedDeliveryTimeMax",
        )

        if estimate:
            estimates_by_purchase[purchase["purchase_id"]] = {
                "estimate": estimate,
                "order_id": purchase.get("supplier_order_id"),
            }

    shipments_result = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id,purchase_id,tracking_number,estimated_delivery_date")
        .in_("purchase_id", purchase_ids)
        .is_("estimated_delivery_date", "null")
        .limit(1000)
        .execute()
    )
    shipments = shipments_result.data or []

    updated = 0
    skipped_without_ebay_eta = 0

    for shipment in shipments:
        ebay_eta = estimates_by_purchase.get(shipment["purchase_id"])

        if not ebay_eta:
            skipped_without_ebay_eta += 1
            continue

        supabase.table("inbound_shipments").update({
            "estimated_delivery_date": ebay_eta["estimate"],
            "updated_at": iso_now(),
        }).eq(
            "inbound_shipment_id",
            shipment["inbound_shipment_id"],
        ).execute()

        updated += 1
        print(
            f"Restored ETA: {ebay_eta['order_id']} | "
            f"{shipment.get('tracking_number')} | {ebay_eta['estimate']}"
        )

    print()
    print("eBay shipment ETA backfill complete.")
    print(f"Candidate shipments missing ETA: {len(shipments)}")
    print(f"Updated from eBay estimate: {updated}")
    print(f"Skipped without eBay estimate: {skipped_without_ebay_eta}")


if __name__ == "__main__":
    main()
