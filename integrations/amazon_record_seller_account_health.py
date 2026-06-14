"""Record manual Seller Central account health and feedback snapshots.

Seller Central account-health and feedback manager values are operator-visible
signals. This script records those read-only observations into Amazon-specific
tables for MBOP dashboard history without calling Amazon write APIs.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from dotenv import load_dotenv
from supabase import create_client


def main() -> int:
    load_dotenv()
    args = parse_args()
    supabase = get_supabase_client()

    if args.account_health_score is not None:
        upsert_health_snapshot(supabase, args)

    feedback_snapshot_id = None
    if args.feedback_star_rating is not None or args.feedback_rating_count is not None:
        if args.feedback_star_rating is None or args.feedback_rating_count is None:
            raise ValueError("--feedback-star-rating and --feedback-rating-count must be provided together.")
        feedback_snapshot_id = insert_feedback_snapshot(supabase, args)
    elif args.feedback_item:
        feedback_snapshot_id = latest_feedback_snapshot_id(supabase)

    for item in args.feedback_item:
        insert_feedback_item(supabase, item, feedback_snapshot_id)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record manual Seller Central health and feedback dashboard values.")
    parser.add_argument("--account-health-score", type=int, help="Seller Central Account Health Rating score.")
    parser.add_argument("--feedback-star-rating", type=float, help="Feedback Manager lifetime star rating.")
    parser.add_argument("--feedback-rating-count", type=int, help="Feedback Manager lifetime rating count.")
    parser.add_argument(
        "--feedback-item",
        action="append",
        default=[],
        help="Recent feedback row as date|rating|amazon_order_id|comment. Repeat for up to three rows.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable.")
    return create_client(supabase_url, supabase_key)


def upsert_health_snapshot(supabase, args: argparse.Namespace) -> None:
    latest = (
        supabase.table("amazon_account_health_snapshots")
        .select("account_health_score")
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if latest and int(latest[0].get("account_health_score") or 0) == args.account_health_score:
        print(f"Account health already current: {args.account_health_score}")
        return

    supabase.table("amazon_account_health_snapshots").insert(
        {
            "account_health_score": args.account_health_score,
            "source": "seller_central_manual",
            "notes": "Recorded from Seller Central Account Health dashboard.",
            "raw_json": {"account_health_score": args.account_health_score},
        }
    ).execute()
    print(f"Inserted account health: {args.account_health_score}")


def insert_feedback_snapshot(supabase, args: argparse.Namespace) -> str:
    result = (
        supabase.table("amazon_seller_feedback_snapshots")
        .insert(
            {
                "star_rating": args.feedback_star_rating,
                "rating_count": args.feedback_rating_count,
                "source": "seller_central_manual",
                "raw_json": {
                    "star_rating": args.feedback_star_rating,
                    "rating_count": args.feedback_rating_count,
                },
            }
        )
        .execute()
    )
    snapshot_id = (result.data or [{}])[0].get("snapshot_id")
    print(f"Inserted feedback summary: {args.feedback_star_rating} / {args.feedback_rating_count}")
    return str(snapshot_id) if snapshot_id else ""


def latest_feedback_snapshot_id(supabase) -> str:
    latest = (
        supabase.table("amazon_seller_feedback_snapshots")
        .select("snapshot_id")
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return str(latest[0].get("snapshot_id") or "") if latest else ""


def insert_feedback_item(supabase, item: str, snapshot_id: str | None) -> None:
    feedback = parse_feedback_item(item)
    if snapshot_id:
        feedback["snapshot_id"] = snapshot_id
    existing = (
        supabase.table("amazon_seller_feedback_items")
        .select("feedback_id")
        .eq("feedback_date", feedback["feedback_date"])
        .eq("rating", feedback["rating"])
    )
    existing = add_nullable_filter(existing, "amazon_order_id", feedback["amazon_order_id"])
    existing = add_nullable_filter(existing, "comment", feedback["comment"])
    existing_rows = existing.limit(1).execute().data or []
    if existing_rows:
        print(f"Feedback item already exists: {feedback.get('feedback_date')} {feedback.get('amazon_order_id') or '--'}")
        return
    supabase.table("amazon_seller_feedback_items").insert(feedback).execute()
    print(f"Inserted feedback item: {feedback.get('feedback_date')} {feedback.get('amazon_order_id') or '--'}")


def parse_feedback_item(item: str) -> dict[str, Any]:
    parts = item.split("|", 3)
    if len(parts) != 4:
        raise ValueError("Feedback items must use date|rating|amazon_order_id|comment.")

    feedback_date, rating, order_id, comment = (part.strip() for part in parts)
    return {
        "feedback_date": feedback_date or None,
        "rating": int(rating),
        "amazon_order_id": order_id or None,
        "comment": comment or None,
        "source": "seller_central_manual",
        "raw_json": {"input": item},
    }


def add_nullable_filter(query, column: str, value: str | None):
    if value:
        return query.eq(column, value)
    return query.is_(column, "null")


if __name__ == "__main__":
    raise SystemExit(main())
