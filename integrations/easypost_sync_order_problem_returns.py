"""Sync buyer return-label tracking for MBOP Order Problems.

This monitors return labels that eBay issued to send items back to sellers. It
updates only order_problem_cases and order_problem_events; inbound supplier
shipment tables remain owned by purchase-delivery tracking.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from easypost_sync_shipments import (
    clean_tracking_number,
    create_tracker,
    extract_delivered_time,
    normalize_status,
    retrieve_tracker,
    safe_datetime,
    tracker_value,
)


DEFAULT_LIMIT = 100


def iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Order Problems return-label tracking from EasyPost.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Maximum open return-label episodes to sync.")
    parser.add_argument("--max-new-trackers", type=int, default=10, help="Maximum new EasyPost trackers to create.")
    parser.add_argument("--tracking-number", help="Only sync one return tracking number.")
    return parser.parse_args()


def fetch_candidates(supabase, *, limit: int, tracking_number: str | None) -> list[dict]:
    query = (
        supabase.table("order_problem_cases")
        .select(
            "problem_case_id,workflow_state,next_action,return_tracking_number,"
            "return_tracking_carrier,return_easypost_tracker_id,return_tracking_delivered_at"
        )
        .eq("is_open", True)
        .not_.is_("return_tracking_number", "null")
        .in_("workflow_state", ["label_received", "return_shipped", "seller_received_return", "refund_pending"])
        .order("updated_at", desc=True)
        .limit(limit)
    )
    if tracking_number:
        query = query.eq("return_tracking_number", tracking_number)
    return query.execute().data or []


def tracker_events(tracker) -> list[dict] | None:
    details = tracker_value(tracker, "tracking_details") or []
    if not details:
        return None
    rows = []
    for detail in details:
        try:
            rows.append(detail.to_dict())
        except Exception:
            rows.append(
                {
                    "message": getattr(detail, "message", None),
                    "status": getattr(detail, "status", None),
                    "datetime": getattr(detail, "datetime", None),
                }
            )
    return rows


def sync_case(supabase, row: dict, *, allow_new_tracker: bool) -> tuple[str, bool]:
    tracking_number = clean_tracking_number(row.get("return_tracking_number") or "")
    if not tracking_number:
        return "skipped-invalid-tracking", False

    tracker_id = row.get("return_easypost_tracker_id")
    if tracker_id:
        tracker = retrieve_tracker(tracker_id)
        created = False
    else:
        if not allow_new_tracker:
            return "skipped-new-tracker-limit", False
        tracker = create_tracker(tracking_number, row.get("return_tracking_carrier"))
        tracker_id = tracker_value(tracker, "id")
        created = True

    status = tracker_value(tracker, "status")
    normalized_status = normalize_status(status)
    delivered_at = safe_datetime(extract_delivered_time(tracker))
    now = iso_now()
    updates: dict[str, object] = {
        "return_easypost_tracker_id": tracker_id,
        "return_tracking_carrier": tracker_value(tracker, "carrier") or row.get("return_tracking_carrier"),
        "return_tracking_status": normalized_status,
        "return_tracking_url": tracker_value(tracker, "public_url"),
        "return_tracking_last_sync_at": now,
        "return_tracking_events_json": tracker_events(tracker),
        "updated_at": now,
    }

    event_type = "return_tracking_synced"
    message = f"Return tracking synced: {tracking_number} {normalized_status}."

    if delivered_at:
        updates["return_tracking_delivered_at"] = delivered_at
        if row.get("workflow_state") in {"label_received", "return_shipped"}:
            updates["workflow_state"] = "seller_received_return"
            updates["seller_received_return_at"] = delivered_at
            updates["next_action"] = "Wait for refund."
            updates["refund_due_at"] = now
            event_type = "return_delivered_to_seller"
            message = f"Return delivered to seller: {tracking_number}."

    supabase.table("order_problem_cases").update(updates).eq("problem_case_id", row["problem_case_id"]).execute()
    supabase.table("order_problem_events").insert(
        {
            "problem_case_id": row["problem_case_id"],
            "event_type": event_type,
            "event_source": "system",
            "message": message,
            "tracking_number": tracking_number,
            "raw_json": {
                "tracker_id": tracker_id,
                "status": status,
                "normalized_status": normalized_status,
                "delivered_at": delivered_at,
            },
        }
    ).execute()

    return normalized_status, created


def main() -> int:
    args = parse_args()
    load_dotenv()
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    tracking_number = clean_tracking_number(args.tracking_number or "") if args.tracking_number else None
    rows = fetch_candidates(supabase, limit=args.limit, tracking_number=tracking_number)

    created = 0
    processed = 0
    for row in rows:
        try:
            status, did_create = sync_case(supabase, row, allow_new_tracker=created < args.max_new_trackers)
            created += 1 if did_create else 0
            processed += 1
            print(f"Processed return tracking {row.get('return_tracking_number')}: {status}")
        except Exception as error:  # noqa: BLE001 - sync should continue per row
            print(f"EasyPost return tracking error for {row.get('return_tracking_number')}: {error}")

    print("EasyPost Order Problem return tracking sync complete.")
    print(f"Candidates: {len(rows)}")
    print(f"Processed: {processed}")
    print(f"Trackers created: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
