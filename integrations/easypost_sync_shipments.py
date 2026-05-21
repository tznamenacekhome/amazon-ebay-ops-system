import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import easypost
from supabase import create_client


MAX_NEW_TRACKERS_PER_RUN = 10
LOOKBACK_DAYS = 30


load_dotenv()

client = easypost.EasyPostClient(
    os.environ["EASYPOST_API_KEY"]
)

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def iso_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_shipments():
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    ).date().isoformat()

    result = (
        supabase.table("inbound_shipments")
        .select("*")
        .or_(
            f"delivered_date.is.null,"
            f"estimated_delivery_date.gte.{cutoff},"
            f"normalized_status.neq.delivered"
        )
        .order("updated_at", desc=True)
        .limit(100)
        .execute()
    )

    return result.data or []


def safe_datetime(value):
    if not value:
        return None

    try:
        return value
    except Exception:
        return None


def extract_latest_event(tracker):
    if not tracker.tracking_details:
        return None

    try:
        latest = sorted(
            tracker.tracking_details,
            key=lambda x: x.datetime or "",
            reverse=True
        )[0]

        return {
            "message": latest.message,
            "status": latest.status,
            "datetime": latest.datetime,
            "location": str(latest.tracking_location)
            if latest.tracking_location else None
        }

    except Exception:
        return None


def normalize_status(status):
    if not status:
        return "unknown"

    status = status.lower()

    mapping = {
        "delivered": "delivered",
        "in_transit": "in_transit",
        "pre_transit": "pre_transit",
        "available_for_pickup": "available_for_pickup",
        "return_to_sender": "return_to_sender",
        "failure": "exception",
        "error": "exception",
        "cancelled": "cancelled",
        "unknown": "unknown"
    }

    return mapping.get(status, status)


def create_tracker(tracking_number):
    return client.tracker.create(
        tracking_code=tracking_number
    )


def retrieve_tracker(tracker_id):
    return client.tracker.retrieve(tracker_id)


def update_shipment(shipment, tracker):
    latest_event = extract_latest_event(tracker)

    payload = {
        "carrier": tracker.carrier,
        "carrier_status": tracker.status,
        "normalized_status": normalize_status(tracker.status),
        "shipment_status": tracker.status,
        "estimated_delivery_date": safe_datetime(
            tracker.est_delivery_date
        ),
        "delivered_date": safe_datetime(
            tracker.delivered_at
        ),
        "tracking_events_json": (
            [detail.to_dict() for detail in tracker.tracking_details]
            if tracker.tracking_details else None
        ),
        "tracking_url": (
            tracker.public_url
            if hasattr(tracker, "public_url")
            else None
        ),
        "last_tracking_sync": iso_now(),
        "updated_at": iso_now(),
    }

    if latest_event:
        payload["last_checkpoint_time"] = latest_event["datetime"]
        payload["last_checkpoint_location"] = latest_event["location"]

        if latest_event["status"] in ["failure", "error"]:
            payload["exception_description"] = latest_event["message"]

    supabase.table("inbound_shipments").update(payload).eq(
        "inbound_shipment_id",
        shipment["inbound_shipment_id"]
    ).execute()


def main():
    print("Starting EasyPost shipment sync...")

    shipments = fetch_shipments()

    print(f"Candidate shipments: {len(shipments)}")

    processed = 0
    created_trackers = 0
    reused_trackers = 0
    skipped = 0
    errors = 0

    for shipment in shipments:
        tracking_number = shipment.get("tracking_number")

        if not tracking_number:
            skipped += 1
            continue

        tracking_number = tracking_number.strip()

        if len(tracking_number) < 8:
            skipped += 1
            continue

        try:
            tracker_id = shipment.get("easypost_tracker_id")

            if tracker_id:
                tracker = retrieve_tracker(tracker_id)
                reused_trackers += 1

            else:
                if created_trackers >= MAX_NEW_TRACKERS_PER_RUN:
                    print(
                        f"Skipping new tracker creation limit reached: "
                        f"{tracking_number}"
                    )
                    skipped += 1
                    continue

                tracker = create_tracker(tracking_number)

                supabase.table("inbound_shipments").update({
                    "easypost_tracker_id": tracker.id
                }).eq(
                    "inbound_shipment_id",
                    shipment["inbound_shipment_id"]
                ).execute()

                created_trackers += 1

            update_shipment(shipment, tracker)

            processed += 1

            print(
                f"Processed: {tracking_number} | "
                f"{tracker.carrier} | "
                f"{tracker.status}"
            )

        except Exception as error:
            errors += 1
            print(f"EasyPost error for {tracking_number}: {error}")

    print()
    print("EasyPost shipment sync complete.")
    print(f"Processed: {processed}")
    print(f"Trackers created: {created_trackers}")
    print(f"Trackers reused: {reused_trackers}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()