from dotenv import load_dotenv
from supabase import create_client

from easypost_sync_shipments import (
    create_tracker,
    retrieve_tracker,
    tracker_value,
    update_shipment,
)

import os


RECENT_PURCHASE_LIMIT = 100
TRACKING_TEST_LIMIT = 10


load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)


def clean_tracking_number(value):
    if not value:
        return None

    tracking_number = value.strip()

    if len(tracking_number) < 8:
        return None

    if tracking_number.lower() in {
        "no tracking",
        "none",
        "n/a",
        "na",
        "not available",
        "refunded",
    }:
        return None

    return tracking_number


def fetch_recent_tracking_candidates():
    result = (
        supabase.table("purchases")
        .select(
            "purchase_id, supplier_order_id, order_date, "
            "purchase_items(item_id, title, tracking_number)"
        )
        .not_.is_("order_date", "null")
        .order("order_date", desc=True)
        .limit(RECENT_PURCHASE_LIMIT)
        .execute()
    )

    candidates = []
    seen_tracking_numbers = set()

    for purchase in result.data or []:
        for item in purchase.get("purchase_items", []):
            tracking_number = clean_tracking_number(
                item.get("tracking_number")
            )

            if not tracking_number:
                continue

            if tracking_number in seen_tracking_numbers:
                continue

            seen_tracking_numbers.add(tracking_number)

            candidates.append({
                "purchase_id": purchase.get("purchase_id"),
                "order_id": purchase.get("supplier_order_id"),
                "order_date": purchase.get("order_date"),
                "item_id": item.get("item_id"),
                "title": item.get("title"),
                "tracking_number": tracking_number,
            })

            if len(candidates) >= TRACKING_TEST_LIMIT:
                return candidates

    return candidates


def fetch_shipments_by_tracking(tracking_numbers):
    result = (
        supabase.table("inbound_shipments")
        .select("*")
        .in_("tracking_number", tracking_numbers)
        .execute()
    )

    return {
        row["tracking_number"]: row
        for row in result.data or []
        if row.get("tracking_number")
    }


def main():
    candidates = fetch_recent_tracking_candidates()

    if not candidates:
        print("No recent tracked orders found.")
        return

    shipments_by_tracking = fetch_shipments_by_tracking([
        row["tracking_number"] for row in candidates
    ])

    print(f"Testing recent tracked orders: {len(candidates)}")
    print()

    created_trackers = 0
    reused_trackers = 0
    updated_shipments = 0
    skipped_missing_shipments = 0
    errors = 0

    for candidate in candidates:
        tracking_number = candidate["tracking_number"]
        shipment = shipments_by_tracking.get(tracking_number)

        print(f"Order date: {candidate['order_date']}")
        print(f"Order ID: {candidate['order_id']}")
        print(f"Tracking: {tracking_number}")
        print(f"Title: {candidate['title']}")

        if not shipment:
            skipped_missing_shipments += 1
            print("Result: skipped, no inbound_shipment row")
            print()
            continue

        try:
            tracker_id = shipment.get("easypost_tracker_id")

            if tracker_id:
                tracker = retrieve_tracker(tracker_id)
                reused_trackers += 1
            else:
                tracker = create_tracker(tracking_number)
                created_trackers += 1

                supabase.table("inbound_shipments").update({
                    "easypost_tracker_id": tracker.id,
                }).eq(
                    "inbound_shipment_id",
                    shipment["inbound_shipment_id"],
                ).execute()

                shipment["easypost_tracker_id"] = tracker.id

            update_shipment(shipment, tracker)
            updated_shipments += 1

            print(f"Carrier: {tracker_value(tracker, 'carrier')}")
            print(f"Status: {tracker_value(tracker, 'status')}")
            print(
                "Estimated delivery: "
                f"{tracker_value(tracker, 'est_delivery_date')}"
            )
            print(f"Delivered at: {tracker_value(tracker, 'delivered_at')}")

            if tracker.tracking_details:
                latest = sorted(
                    tracker.tracking_details,
                    key=lambda detail: detail.datetime or "",
                    reverse=True,
                )[0]
                print(f"Latest event: {latest.status} | {latest.message}")
                print(f"Latest event time: {latest.datetime}")
            else:
                print("Latest event: none returned")

        except Exception as error:
            errors += 1
            print(f"EasyPost error: {error}")

        print()

    print("Recent EasyPost tracking test complete.")
    print(f"Shipments updated: {updated_shipments}")
    print(f"Trackers created: {created_trackers}")
    print(f"Trackers reused: {reused_trackers}")
    print(f"Missing inbound shipment rows: {skipped_missing_shipments}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()
