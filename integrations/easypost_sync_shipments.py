import os
import time
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import easypost
from supabase import create_client

try:
    from status_logic import derive_purchase_item_status
except ImportError:
    from integrations.status_logic import derive_purchase_item_status


MAX_NEW_TRACKERS_PER_RUN = 10
LOOKBACK_DAYS = 30
DEFAULT_START_DATE = "2026-05-01"
MAX_EASYPOST_REQUESTS_PER_SECOND = 5
MAX_EASYPOST_RETRIES = 4
INVALID_TRACKING_VALUES = {
    "no tracking",
    "none",
    "n/a",
    "na",
    "not available",
    "refunded",
    "cancelled",
    "canceled",
    "shipped untracked",
    "shipped without tracking",
}


load_dotenv()

client = easypost.EasyPostClient(
    os.environ["EASYPOST_API_KEY"]
)

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

last_easypost_request_at = 0


def iso_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync inbound shipment tracking status from EasyPost."
    )
    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help="Only sync shipments for purchases on or after this date.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum candidate shipment rows to inspect.",
    )
    parser.add_argument(
        "--max-new-trackers",
        type=int,
        default=MAX_NEW_TRACKERS_PER_RUN,
        help="Maximum new EasyPost trackers to create in this run.",
    )
    parser.add_argument(
        "--tracking-number",
        help="Only sync one inbound shipment tracking number.",
    )
    return parser.parse_args()


def fetch_recent_purchase_ids(start_date):
    result = (
        supabase.table("purchases")
        .select("purchase_id")
        .gte("order_date", start_date)
        .order("order_date", desc=True)
        .limit(1000)
        .execute()
    )

    return [
        row["purchase_id"]
        for row in result.data or []
        if row.get("purchase_id")
    ]


def fetch_shipments(start_date=None, limit=100):
    if start_date:
        purchase_ids = fetch_recent_purchase_ids(start_date)

        if not purchase_ids:
            return []

        shipments = fetch_undelivered_shipments(purchase_ids)

        if len(shipments) >= limit:
            return shipments

        result = (
            supabase.table("inbound_shipments")
            .select("*")
            .in_("purchase_id", purchase_ids)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )

        seen = {
            row["inbound_shipment_id"]
            for row in shipments
            if row.get("inbound_shipment_id")
        }

        for row in result.data or []:
            shipment_id = row.get("inbound_shipment_id")
            if not shipment_id or shipment_id in seen:
                continue

            shipments.append(row)
            seen.add(shipment_id)

            if len(shipments) >= limit:
                break

        return shipments

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


def fetch_undelivered_shipments(purchase_ids):
    rows = []
    page_size = 1000

    for purchase_chunk in chunks(purchase_ids, 100):
        offset = 0

        while True:
            result = (
                supabase.table("inbound_shipments")
                .select("*")
                .in_("purchase_id", purchase_chunk)
                .or_("delivered_date.is.null,normalized_status.neq.delivered")
                .order("updated_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page = result.data or []
            rows.extend(page)

            if len(page) < page_size:
                break

            offset += page_size

    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return rows


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def clean_tracking_number(value):
    if not value:
        return None

    tracking_number = value.strip()

    if len(tracking_number) < 8:
        return None

    if tracking_number.lower() in INVALID_TRACKING_VALUES:
        return None

    return tracking_number


def normalize_carrier(value):
    if not value:
        return None

    carrier = value.strip()

    mapping = {
        "us postal service": "USPS",
        "united states postal service": "USPS",
        "usps": "USPS",
        "ups": "UPS",
        "fedex": "FedExDefault",
        "fed ex": "FedExDefault",
        "fedexdefault": "FedExDefault",
        "fedex default": "FedExDefault",
    }

    return mapping.get(carrier.lower(), carrier)


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


def extract_delivered_time(tracker):
    delivered_at = tracker_value(tracker, "delivered_at")

    if delivered_at:
        return delivered_at

    tracking_details = tracker_value(tracker, "tracking_details") or []

    delivered_events = [
        detail
        for detail in tracking_details
        if getattr(detail, "status", None) == "delivered"
    ]

    if not delivered_events:
        return None

    latest = sorted(
        delivered_events,
        key=lambda detail: getattr(detail, "datetime", "") or "",
        reverse=True,
    )[0]

    return getattr(latest, "datetime", None)


def tracker_value(tracker, field):
    try:
        return getattr(tracker, field)
    except AttributeError:
        pass

    try:
        return tracker.to_dict().get(field)
    except Exception:
        return None


def is_rate_limit_error(error):
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True

    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    return "429" in str(error) or "Too Many Requests" in str(error)


def is_carrier_credential_error(error):
    return "Credentials not found for the specified carrier" in str(error)


def wait_for_easypost_slot():
    global last_easypost_request_at

    min_interval_seconds = 1 / MAX_EASYPOST_REQUESTS_PER_SECOND
    elapsed = time.monotonic() - last_easypost_request_at

    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)

    last_easypost_request_at = time.monotonic()


def call_easypost(action):
    for attempt in range(MAX_EASYPOST_RETRIES + 1):
        wait_for_easypost_slot()

        try:
            return action()
        except Exception as error:
            if not is_rate_limit_error(error):
                raise

            if attempt >= MAX_EASYPOST_RETRIES:
                raise

            delay_seconds = min(2 ** attempt, 30)
            print(
                f"EasyPost 429 rate limit hit; retrying in "
                f"{delay_seconds}s..."
            )
            time.sleep(delay_seconds)


def normalize_status(status):
    if not status:
        return "unknown"

    status = status.lower()

    mapping = {
        "delivered": "delivered",
        "in_transit": "in_transit",
        "out_for_delivery": "out_for_delivery",
        "pre_transit": "pre_transit",
        "available_for_pickup": "available_for_pickup",
        "return_to_sender": "return_to_sender",
        "failure": "exception",
        "error": "exception",
        "cancelled": "cancelled",
        "unknown": "unknown"
    }

    return mapping.get(status, status)


def create_tracker(tracking_number, carrier=None):
    payload = {"tracking_code": tracking_number}

    normalized_carrier = normalize_carrier(carrier)

    if normalized_carrier:
        payload["carrier"] = normalized_carrier

    try:
        return call_easypost(lambda: client.tracker.create(**payload))
    except Exception as error:
        if not normalized_carrier or not is_carrier_credential_error(error):
            raise

        print(
            f"Retrying {tracking_number} without carrier "
            f"{normalized_carrier}..."
        )
        return call_easypost(
            lambda: client.tracker.create(tracking_code=tracking_number)
        )


def retrieve_tracker(tracker_id):
    return call_easypost(lambda: client.tracker.retrieve(tracker_id))


def update_shipment(shipment, tracker):
    latest_event = extract_latest_event(tracker)
    carrier_eta = safe_datetime(
        tracker_value(tracker, "est_delivery_date")
    )
    delivered_date = safe_datetime(
        extract_delivered_time(tracker)
    )

    payload = {
        "tracking_number": shipment.get("tracking_number"),
        "carrier": tracker_value(tracker, "carrier"),
        "carrier_status": tracker_value(tracker, "status"),
        "normalized_status": normalize_status(
            tracker_value(tracker, "status")
        ),
        "shipment_status": tracker_value(tracker, "status"),
        "tracking_events_json": (
            [detail.to_dict() for detail in tracker.tracking_details]
            if tracker.tracking_details else None
        ),
        "tracking_url": (
            tracker_value(tracker, "public_url")
        ),
        "last_tracking_sync": iso_now(),
        "updated_at": iso_now(),
    }

    if carrier_eta:
        payload["estimated_delivery_date"] = carrier_eta

    if delivered_date:
        payload["delivered_date"] = delivered_date

    if latest_event:
        payload["last_checkpoint_time"] = latest_event["datetime"]
        payload["last_checkpoint_location"] = latest_event["location"]

        if latest_event["status"] in ["failure", "error"]:
            payload["exception_description"] = latest_event["message"]

    supabase.table("inbound_shipments").update(payload).eq(
        "inbound_shipment_id",
        shipment["inbound_shipment_id"]
    ).execute()

    update_linked_purchase_item_statuses(
        shipment["inbound_shipment_id"],
        payload,
    )


def update_linked_purchase_item_statuses(shipment_id, shipment_payload):
    links = (
        supabase.table("inbound_shipment_items")
        .select("item_id")
        .eq("inbound_shipment_id", shipment_id)
        .execute()
    )
    item_ids = [row["item_id"] for row in links.data or [] if row.get("item_id")]

    if not item_ids:
        return

    items = (
        supabase.table("purchase_items")
        .select("item_id,current_status,tracking_number")
        .in_("item_id", item_ids)
        .execute()
    )

    for item in items.data or []:
        if clean_tracking_number(item.get("tracking_number") or "") != clean_tracking_number(
            shipment_payload.get("tracking_number") or ""
        ):
            continue

        next_status = derive_purchase_item_status(
            current_status=item.get("current_status"),
            tracking_number=item.get("tracking_number"),
            carrier_status=shipment_payload.get("normalized_status"),
            delivered_date=shipment_payload.get("delivered_date"),
            seller_shipped=True,
        )

        if next_status == item.get("current_status"):
            continue

        (
            supabase.table("purchase_items")
            .update({"current_status": next_status})
            .eq("item_id", item["item_id"])
            .execute()
        )


def tracker_has_activity(tracker):
    normalized_status = normalize_status(tracker_value(tracker, "status"))

    if normalized_status not in {"unknown", "pre_transit"}:
        return True

    details = tracker_value(tracker, "tracking_details") or []
    return any(
        normalize_status(getattr(detail, "status", None))
        not in {"unknown", "pre_transit"}
        for detail in details
    )


def extract_tracking_candidates(raw_value):
    candidates = []

    def walk(value):
        if isinstance(value, dict):
            tracking = value.get("ShipmentTrackingNumber")
            carrier = value.get("ShippingCarrierUsed")

            if tracking:
                candidates.append({
                    "tracking_number": str(tracking).strip(),
                    "carrier": str(carrier).strip() if carrier else None,
                })

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(raw_value)

    unique = []
    seen = set()

    for candidate in candidates:
        tracking_number = clean_tracking_number(candidate.get("tracking_number"))
        if not tracking_number or tracking_number in seen:
            continue

        unique.append({
            "tracking_number": tracking_number,
            "carrier": candidate.get("carrier"),
        })
        seen.add(tracking_number)

    return unique


def fetch_purchase_tracking_context(purchase_id):
    purchase = (
        supabase.table("purchases")
        .select("purchase_id,raw_import_json")
        .eq("purchase_id", purchase_id)
        .single()
        .execute()
    )

    items = (
        supabase.table("purchase_items")
        .select("item_id,quantity,tracking_number,current_status")
        .eq("purchase_id", purchase_id)
        .execute()
    )

    return {
        "purchase": purchase.data,
        "items": items.data or [],
    }


def total_units(items):
    total = 0

    for item in items:
        try:
            total += int(item.get("quantity") or 0)
        except Exception:
            continue

    return total


def fetch_shipments_for_tracking_number(tracking_number):
    cleaned = clean_tracking_number(tracking_number)
    if not cleaned:
        return []

    result = (
        supabase.table("inbound_shipments")
        .select("*")
        .eq("tracking_number", cleaned)
        .limit(10)
        .execute()
    )
    return result.data or []


def ensure_inbound_shipment(purchase_id, candidate):
    existing = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id,tracking_number,easypost_tracker_id,carrier")
        .eq("purchase_id", purchase_id)
        .eq("tracking_number", candidate["tracking_number"])
        .limit(1)
        .execute()
    )

    if existing.data:
        return existing.data[0]

    result = supabase.table("inbound_shipments").insert({
        "purchase_id": purchase_id,
        "tracking_number": candidate["tracking_number"],
        "carrier": normalize_carrier(candidate.get("carrier")),
        "shipment_status": "unknown",
        "normalized_status": "unknown",
        "updated_at": iso_now(),
    }).execute()

    return result.data[0]


def switch_purchase_to_shipment(context, shipment, tracker):
    tracking_number = shipment.get("tracking_number")

    if not tracking_number:
        return False

    switched = False

    for item in context["items"]:
        if clean_tracking_number(str(item.get("tracking_number") or "")) == tracking_number:
            continue

        supabase.table("purchase_items").update({
            "tracking_number": tracking_number,
            "current_status": derive_purchase_item_status(
                current_status=item.get("current_status"),
                tracking_number=tracking_number,
                carrier_status=normalize_status(tracker_value(tracker, "status")),
                delivered_date=extract_delivered_time(tracker),
                seller_shipped=True,
            ),
        }).eq("item_id", item["item_id"]).execute()
        switched = True

        existing_link = (
            supabase.table("inbound_shipment_items")
            .select("inbound_shipment_item_id")
            .eq("inbound_shipment_id", shipment["inbound_shipment_id"])
            .eq("item_id", item["item_id"])
            .limit(1)
            .execute()
        )

        if not existing_link.data:
            supabase.table("inbound_shipment_items").insert({
                "inbound_shipment_id": shipment["inbound_shipment_id"],
                "item_id": item["item_id"],
                "quantity_expected_in_package": item.get("quantity") or 1,
                "notes": "Linked after alternate tracking activity check",
            }).execute()

    return switched


def resolve_alternate_tracking_if_needed(shipment, tracker, remaining_new_trackers):
    if tracker_has_activity(tracker):
        return 0

    purchase_id = shipment.get("purchase_id")
    if not purchase_id:
        return 0

    context = fetch_purchase_tracking_context(purchase_id)
    candidates = extract_tracking_candidates(context["purchase"].get("raw_import_json"))

    if len(candidates) <= total_units(context["items"]):
        return 0

    created = 0
    current_tracking = clean_tracking_number(shipment.get("tracking_number") or "")

    # eBay often appends replacement tracking after a dead label, so check newest first.
    for candidate in reversed(candidates):
        tracking_number = candidate["tracking_number"]
        if tracking_number == current_tracking:
            continue

        alternate_shipment = ensure_inbound_shipment(purchase_id, candidate)
        alternate_tracker_id = alternate_shipment.get("easypost_tracker_id")

        if alternate_tracker_id:
            alternate_tracker = retrieve_tracker(alternate_tracker_id)
        else:
            if created >= remaining_new_trackers:
                continue

            alternate_tracker = create_tracker(
                tracking_number,
                carrier=candidate.get("carrier"),
            )
            created += 1
            supabase.table("inbound_shipments").update({
                "easypost_tracker_id": tracker_value(alternate_tracker, "id"),
            }).eq(
                "inbound_shipment_id",
                alternate_shipment["inbound_shipment_id"],
            ).execute()

        update_shipment(alternate_shipment, alternate_tracker)

        if tracker_has_activity(alternate_tracker):
            switched = switch_purchase_to_shipment(
                context,
                alternate_shipment,
                alternate_tracker,
            )
            if switched:
                print(
                    "Switching purchase "
                    f"{purchase_id} to active tracking {tracking_number}"
                )
            return created

    return created


def main():
    args = parse_args()
    print("Starting EasyPost shipment sync...")
    print(f"Purchase start date: {args.start_date}")
    print(
        "EasyPost request rate cap: "
        f"{MAX_EASYPOST_REQUESTS_PER_SECOND}/second"
    )

    if args.tracking_number:
        shipments = fetch_shipments_for_tracking_number(args.tracking_number)
    else:
        shipments = fetch_shipments(
            start_date=args.start_date,
            limit=args.limit,
        )

    print(f"Candidate shipments: {len(shipments)}")

    processed = 0
    created_trackers = 0
    reused_trackers = 0
    skipped = 0
    errors = 0

    for shipment in shipments:
        tracking_number = clean_tracking_number(
            shipment.get("tracking_number")
        )

        if not tracking_number:
            skipped += 1
            continue

        try:
            tracker_id = shipment.get("easypost_tracker_id")

            if tracker_id:
                tracker = retrieve_tracker(tracker_id)
                reused_trackers += 1

            else:
                if created_trackers >= args.max_new_trackers:
                    print(
                        f"Skipping new tracker creation limit reached: "
                        f"{tracking_number}"
                    )
                    skipped += 1
                    continue

                tracker = create_tracker(
                    tracking_number,
                    carrier=shipment.get("carrier"),
                )

                supabase.table("inbound_shipments").update({
                    "easypost_tracker_id": tracker.id
                }).eq(
                    "inbound_shipment_id",
                    shipment["inbound_shipment_id"]
                ).execute()

                created_trackers += 1

            update_shipment(shipment, tracker)
            created_trackers += resolve_alternate_tracking_if_needed(
                shipment,
                tracker,
                max(args.max_new_trackers - created_trackers, 0),
            )

            processed += 1

            print(
                f"Processed: {tracking_number} | "
                f"{tracker_value(tracker, 'carrier')} | "
                f"{tracker_value(tracker, 'status')}"
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
