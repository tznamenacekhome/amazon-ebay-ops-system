import os
from dotenv import load_dotenv
from supabase import create_client

PAGE_SIZE = 500

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def fetch_tracked_items():
    all_items = []
    start = 0

    while True:
        end = start + PAGE_SIZE - 1

        result = (
            supabase.table("purchase_items")
            .select("item_id, purchase_id, tracking_number, quantity")
            .not_.is_("tracking_number", "null")
            .range(start, end)
            .execute()
        )

        batch = result.data or []
        all_items.extend(batch)

        print(f"Fetched {len(all_items)} tracked items...")

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return all_items


def main():
    print("Starting paginated inbound shipment backfill...")

    items = fetch_tracked_items()

    inserted_shipments = 0
    linked_items = 0
    skipped = 0
    already_linked = 0

    for item in items:
        tracking_number = item.get("tracking_number")
        purchase_id = item.get("purchase_id")
        item_id = item.get("item_id")
        quantity = item.get("quantity") or 1

        if not tracking_number or not purchase_id or not item_id:
            skipped += 1
            continue

        existing = (
            supabase.table("inbound_shipments")
            .select("inbound_shipment_id")
            .eq("tracking_number", tracking_number)
            .eq("purchase_id", purchase_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            shipment_id = existing.data[0]["inbound_shipment_id"]
        else:
            result = (
                supabase.table("inbound_shipments")
                .insert({
                    "purchase_id": purchase_id,
                    "tracking_number": tracking_number,
                    "normalized_status": "unknown",
                    "shipment_status": "unknown"
                })
                .execute()
            )

            shipment_id = result.data[0]["inbound_shipment_id"]
            inserted_shipments += 1

        link_exists = (
            supabase.table("inbound_shipment_items")
            .select("inbound_shipment_item_id")
            .eq("inbound_shipment_id", shipment_id)
            .eq("item_id", item_id)
            .limit(1)
            .execute()
        )

        if link_exists.data:
            already_linked += 1
            continue

        supabase.table("inbound_shipment_items").insert({
            "inbound_shipment_id": shipment_id,
            "item_id": item_id,
            "quantity_expected_in_package": quantity,
            "quantity_received_from_package": None,
            "received_verified": False,
            "notes": "Backfilled from purchase_items.tracking_number"
        }).execute()

        linked_items += 1

    print("Backfill complete.")
    print(f"Tracked items processed: {len(items)}")
    print(f"New shipments inserted: {inserted_shipments}")
    print(f"New shipment item links inserted: {linked_items}")
    print(f"Already linked: {already_linked}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()