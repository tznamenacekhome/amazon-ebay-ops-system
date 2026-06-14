"""Sync Amazon FBA outbound shipment carrier tracking from EasyPost.

This script updates only the Amazon FBA shipment workflow table. It does not
write to purchases, receiving rows, or inbound purchase shipment rows.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from easypost_sync_shipments import (
    clean_tracking_number,
    create_tracker,
    extract_delivered_time,
    extract_latest_event,
    normalize_carrier,
    normalize_status,
    retrieve_tracker,
    safe_datetime,
    tracker_value,
)


DEFAULT_LIMIT = 50
DEFAULT_MAX_NEW_TRACKERS = 10


def main() -> int:
    args = parse_args()
    load_dotenv()
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    shipments = fetch_fba_shipments(supabase, args)
    print("FBA EasyPost shipment tracking sync")
    print("-----------------------------------")
    print(f"Candidate shipments: {len(shipments)}")

    processed = 0
    created = 0
    reused = 0
    skipped = 0
    errors = 0

    for shipment in shipments:
        shipment_code = shipment.get("shipment_code") or shipment.get("fba_shipment_id")
        tracking_number = clean_tracking_number(shipment.get("tracking_number"))
        if not tracking_number:
            skipped += 1
            print(f"Skipping {shipment_code}: no valid tracking number")
            continue

        raw_tracking = shipment.get("raw_tracking_json") or {}
        if not isinstance(raw_tracking, dict):
            raw_tracking = {}
        tracker_id = (
            raw_tracking.get("easypost", {}).get("tracker_id")
            if isinstance(raw_tracking.get("easypost"), dict)
            else None
        )

        try:
            if tracker_id:
                tracker = retrieve_tracker(tracker_id)
                reused += 1
            else:
                if created >= args.max_new_trackers:
                    skipped += 1
                    print(
                        f"Skipping {shipment_code}: new tracker limit reached "
                        f"({args.max_new_trackers})"
                    )
                    continue
                tracker = create_tracker(
                    tracking_number,
                    carrier=shipment.get("carrier_name") or "UPS",
                )
                tracker_id = tracker_value(tracker, "id")
                created += 1

            update_fba_shipment(supabase, shipment, tracker)
            processed += 1
            print(
                f"Processed: {shipment_code} | {tracking_number} | "
                f"{tracker_value(tracker, 'carrier')} | {tracker_value(tracker, 'status')}"
            )
        except Exception as error:  # noqa: BLE001 - carrier sync should continue
            errors += 1
            print(f"EasyPost error for {shipment_code} {tracking_number}: {error}")

    print("\nFBA EasyPost shipment tracking sync complete.")
    print(f"Processed: {processed}")
    print(f"Trackers created: {created}")
    print(f"Trackers reused: {reused}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    return 1 if errors else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Amazon FBA shipment carrier tracking from EasyPost."
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--max-new-trackers", type=int, default=DEFAULT_MAX_NEW_TRACKERS)
    parser.add_argument("--shipment-code", help="Only sync one FBA shipment code.")
    parser.add_argument("--tracking-number", help="Only sync one tracking number.")
    parser.add_argument(
        "--include-delivered",
        action="store_true",
        help="Also refresh shipments that already have carrier delivered timestamps.",
    )
    return parser.parse_args()


def fetch_fba_shipments(supabase, args: argparse.Namespace) -> list[dict[str, Any]]:
    query = (
        supabase.table("fba_shipments")
        .select("*")
        .neq("shipment_code", "legacy_listed_no_shipment_id")
        .not_.is_("tracking_number", "null")
        .order("updated_at", desc=True)
        .limit(args.limit)
    )
    if args.shipment_code:
        query = query.eq("shipment_code", args.shipment_code.strip())
    if args.tracking_number:
        query = query.eq("tracking_number", args.tracking_number.strip())
    if not args.include_delivered:
        query = query.is_("carrier_delivered_at", "null")
    return query.execute().data or []


def update_fba_shipment(supabase, shipment: dict[str, Any], tracker: Any) -> None:
    now = iso_now()
    latest_event = extract_latest_event(tracker)
    tracker_dict = tracker.to_dict() if hasattr(tracker, "to_dict") else {}
    carrier_eta = safe_datetime(tracker_value(tracker, "est_delivery_date"))
    delivered_at = safe_datetime(extract_delivered_time(tracker))
    pickup_at = extract_pickup_time(tracker)
    raw_tracking = shipment.get("raw_tracking_json") or {}
    if not isinstance(raw_tracking, dict):
        raw_tracking = {}

    raw_tracking["easypost"] = {
        "tracker_id": tracker_value(tracker, "id"),
        "tracking_code": tracker_value(tracker, "tracking_code"),
        "carrier": tracker_value(tracker, "carrier"),
        "status": tracker_value(tracker, "status"),
        "normalized_status": normalize_status(tracker_value(tracker, "status")),
        "public_url": tracker_value(tracker, "public_url"),
        "est_delivery_date": carrier_eta,
        "delivered_at": delivered_at,
        "pickup_at": pickup_at,
        "last_checkpoint": latest_event,
        "checked_at": now,
        "raw_tracker": tracker_dict,
    }

    payload = {
        "carrier_name": normalize_carrier(tracker_value(tracker, "carrier")) or "UPS",
        "carrier_tracking_url": tracker_value(tracker, "public_url")
        or shipment.get("carrier_tracking_url"),
        "raw_tracking_json": raw_tracking,
        "updated_at": now,
    }
    if carrier_eta:
        payload["carrier_delivery_eta"] = carrier_eta[:10]
    if delivered_at:
        payload["carrier_delivered_at"] = delivered_at
    if pickup_at:
        payload["carrier_pickup_at"] = pickup_at

    supabase.table("fba_shipments").update(payload).eq(
        "fba_shipment_id",
        shipment["fba_shipment_id"],
    ).execute()

    record_tracking_events(supabase, shipment, tracker)


def extract_pickup_time(tracker: Any) -> str | None:
    tracking_details = tracker_value(tracker, "tracking_details") or []
    pickup_events = []
    for detail in tracking_details:
        status = (getattr(detail, "status", None) or "").lower()
        message = (getattr(detail, "message", None) or "").lower()
        if status == "pre_transit":
            continue
        if any(token in message for token in ("pickup", "origin scan", "picked up")):
            pickup_events.append(detail)

    if not pickup_events and tracking_details:
        pickup_events = [
            detail
            for detail in tracking_details
            if getattr(detail, "datetime", None)
            and (getattr(detail, "status", None) or "").lower()
            not in {"unknown", "pre_transit"}
        ]

    if not pickup_events:
        return None

    earliest = sorted(
        pickup_events,
        key=lambda detail: getattr(detail, "datetime", "") or "",
    )[0]
    return getattr(earliest, "datetime", None)


def record_tracking_events(supabase, shipment: dict[str, Any], tracker: Any) -> None:
    details = tracker_value(tracker, "tracking_details") or []
    for detail in details:
        event_at = getattr(detail, "datetime", None)
        if not event_at:
            continue
        raw = detail.to_dict() if hasattr(detail, "to_dict") else {}
        event_type = f"carrier_{normalize_status(getattr(detail, 'status', None))}"
        supabase.table("fba_shipment_events").upsert(
            {
                "fba_shipment_id": shipment["fba_shipment_id"],
                "event_type": event_type,
                "event_source": "easypost",
                "event_at": event_at,
                "fulfillment_center_id": shipment.get("fulfillment_center_id"),
                "raw_event_json": raw,
            },
            on_conflict="fba_shipment_id,event_type,event_source,event_at",
        ).execute()


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
