"""Read-only eBay Post-Order returns sync for MBOP Order Problems.

This script reads eBay return data and writes only to MBOP local workflow tables:
order_problem_cases and order_problem_events. It does not create returns, send
messages, accept offers, escalate cases, issue refunds, upload files, or call any
other eBay write endpoint.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client


LOGGER = logging.getLogger("ebay_order_problem_returns_sync")
EBAY_POST_ORDER_BASE_URL = "https://api.ebay.com/post-order/v2"


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv()

    try:
        supabase = get_supabase_client()
        token = get_access_token()
        returns = search_returns(token, lookback_days=args.lookback_days, limit=args.limit)
        LOGGER.info("eBay returns retrieved: %s", len(returns))

        inserted = 0
        updated = 0
        skipped = 0
        for return_row in returns:
            mapped = map_return(return_row, supabase)
            if not mapped:
                skipped += 1
                continue

            if not args.apply:
                print_summary(mapped, dry_run=True)
                skipped += 1
                continue

            result = upsert_order_problem_case(supabase, mapped)
            if result == "inserted":
                inserted += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

        print("eBay order problem returns sync")
        print("--------------------------------")
        print("Mode:", "write" if args.apply else "dry run")
        print(f"Returns retrieved: {len(returns)}")
        print(f"Inserted: {inserted}")
        print(f"Updated: {updated}")
        print(f"Skipped: {skipped}")
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("eBay order problem returns sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only eBay returns sync into MBOP Order Problems.")
    parser.add_argument("--apply", action="store_true", help="Write mapped return cases to Supabase.")
    parser.add_argument("--lookback-days", type=int, default=90, help="Return creation lookback window.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum returns to request from eBay.")
    return parser.parse_args()


def get_supabase_client():
    return create_client(required_env("SUPABASE_URL"), required_env("SUPABASE_SERVICE_ROLE_KEY"))


def get_access_token() -> str:
    credentials = f"{required_env('EBAY_CLIENT_ID')}:{required_env('EBAY_CLIENT_SECRET')}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": required_env("EBAY_REFRESH_TOKEN"),
            "scope": " ".join(
                [
                    "https://api.ebay.com/oauth/api_scope",
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
                ]
            ),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_returns(token: str, *, lookback_days: int, limit: int) -> list[dict[str, Any]]:
    end_date = dt.datetime.now(dt.timezone.utc)
    start_date = end_date - dt.timedelta(days=lookback_days)
    response = requests.get(
        f"{EBAY_POST_ORDER_BASE_URL}/return/search",
        headers={
            "Authorization": f"IAF {token}",
            "Content-Type": "application/json",
        },
        params={
            "limit": str(max(1, min(limit, 200))),
            "creation_date_range_from": iso_z(start_date),
            "creation_date_range_to": iso_z(end_date),
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    members = payload.get("members") or []
    return [row for row in members if isinstance(row, dict)]


def map_return(return_row: dict[str, Any], supabase) -> dict[str, Any] | None:
    return_id = clean_text(return_row.get("returnId"))
    order_id = clean_text(return_row.get("orderId"))
    purchase = find_purchase_for_order(supabase, order_id)
    if not purchase:
        LOGGER.warning("Skipping eBay return %s; no purchase matched order %s", return_id, order_id)
        return None

    item = find_purchase_item_for_purchase(supabase, purchase["purchase_id"])
    if not item:
        LOGGER.warning("Skipping eBay return %s; no purchase item matched order %s", return_id, order_id)
        return None

    creation_info = return_row.get("creationInfo") or {}
    buyer_refund = return_row.get("buyerTotalRefund") or {}
    seller_due = return_row.get("sellerResponseDue") or {}
    buyer_due = return_row.get("buyerResponseDue") or {}
    escalation_info = return_row.get("escalationInfo") or {}
    buyer_escalation = escalation_info.get("buyerEscalationEligibilityInfo") or {}
    seller_escalation = escalation_info.get("sellerEscalationEligibilityInfo") or {}

    workflow_state = map_workflow_state(return_row)
    problem_type = map_problem_type(creation_info.get("reason"), return_row.get("currentType"))
    needs_response = workflow_state == "seller_message_needs_response"
    estimated_refund = money_value(buyer_refund.get("estimatedRefundAmount"))
    actual_refund = money_value(buyer_refund.get("actualRefundAmount"))
    currency = (
        money_currency(buyer_refund.get("estimatedRefundAmount"))
        or money_currency(buyer_refund.get("actualRefundAmount"))
        or "USD"
    )

    return {
        "purchase_item_id": item["item_id"],
        "purchase_id": purchase["purchase_id"],
        "supplier": purchase.get("supplier") or "eBay",
        "supplier_order_id": order_id,
        "problem_source": "ebay_return_sync",
        "problem_type": problem_type,
        "workflow_state": workflow_state,
        "priority": "urgent" if needs_response else "normal",
        "is_open": not is_confidently_closed(return_row),
        "needs_response": needs_response,
        "next_action": next_action_for_state(workflow_state),
        "next_action_due_at": unwrap_value(
            seller_due.get("respondByDate")
            or buyer_due.get("respondByDate")
            or nested(return_row, "timeoutDate", "value")
        ),
        "last_detected_at": iso_z(dt.datetime.now(dt.timezone.utc)),
        "return_needed_at": unwrap_value(creation_info.get("creationDate")),
        "ebay_return_opened_at": unwrap_value(creation_info.get("creationDate")),
        "seller_message_last_at": unwrap_value(seller_due.get("respondByDate")) if needs_response else None,
        "partial_refund_offered_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "partial_refund_offered"
        else None,
        "label_available_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "label_received"
        else None,
        "return_shipped_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "return_shipped"
        else None,
        "seller_received_return_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "seller_received_return"
        else None,
        "refund_received_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if actual_refund is not None and is_confidently_closed(return_row)
        else None,
        "escalation_available_at": unwrap_value(
            buyer_escalation.get("startTime") or seller_escalation.get("startTime")
        ),
        "closed_at": iso_z(dt.datetime.now(dt.timezone.utc)) if is_confidently_closed(return_row) else None,
        "ebay_return_id": return_id,
        "ebay_case_id": return_id,
        "ebay_return_state": clean_text(return_row.get("state")),
        "ebay_return_status": clean_text(return_row.get("status")),
        "ebay_current_type": clean_text(return_row.get("currentType")),
        "ebay_action_url": f"https://www.ebay.com/rtn/Return/Details?returnId={return_id}" if return_id else None,
        "expected_refund_amount": estimated_refund,
        "actual_refund_amount": actual_refund,
        "partial_refund_amount": estimated_refund if workflow_state == "partial_refund_offered" else None,
        "refund_currency": currency,
        "raw_ebay_json": return_row,
    }


def upsert_order_problem_case(supabase, mapped: dict[str, Any]) -> str:
    existing = find_existing_case(supabase, mapped)
    now = iso_z(dt.datetime.now(dt.timezone.utc))
    if existing:
        case_id = existing["problem_case_id"]
        updates = {key: value for key, value in mapped.items() if value is not None}
        updates["updated_at"] = now
        supabase.table("order_problem_cases").update(updates).eq("problem_case_id", case_id).execute()
        append_event(supabase, case_id, "ebay_return_sync_updated", mapped)
        return "updated"

    payload = dict(mapped)
    payload["created_at"] = now
    payload["updated_at"] = now
    response = supabase.table("order_problem_cases").insert(payload).execute()
    case_id = response.data[0]["problem_case_id"]
    append_event(supabase, case_id, "ebay_return_sync_inserted", mapped)
    return "inserted"


def append_event(supabase, case_id: str, event_type: str, mapped: dict[str, Any]) -> None:
    supabase.table("order_problem_events").insert(
        {
            "problem_case_id": case_id,
            "event_type": event_type,
            "event_source": "ebay_api",
            "message": f"Read-only eBay return sync mapped state {mapped.get('workflow_state')}.",
            "amount": mapped.get("actual_refund_amount") or mapped.get("expected_refund_amount"),
            "currency": mapped.get("refund_currency"),
            "raw_json": mapped.get("raw_ebay_json"),
        }
    ).execute()


def find_existing_case(supabase, mapped: dict[str, Any]) -> dict[str, Any] | None:
    return_id = mapped.get("ebay_return_id")
    if return_id:
        response = (
            supabase.table("order_problem_cases")
            .select("problem_case_id")
            .eq("ebay_return_id", return_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    response = (
        supabase.table("order_problem_cases")
        .select("problem_case_id")
        .eq("purchase_item_id", mapped["purchase_item_id"])
        .eq("is_open", True)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def find_purchase_for_order(supabase, order_id: str | None) -> dict[str, Any] | None:
    if not order_id:
        return None
    response = (
        supabase.table("purchases")
        .select("purchase_id,supplier,supplier_order_id")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def find_purchase_item_for_purchase(supabase, purchase_id: str) -> dict[str, Any] | None:
    response = (
        supabase.table("purchase_items")
        .select("item_id")
        .eq("purchase_id", purchase_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def map_workflow_state(return_row: dict[str, Any]) -> str:
    status = clean_upper(return_row.get("status"))
    state = clean_upper(return_row.get("state"))
    current_type = clean_upper(return_row.get("currentType"))
    combined = {status, state, current_type}

    if "ESCALATED" in combined:
        return "escalated"
    if combined & {"PARTIAL_REFUND_REQUESTED", "PARTIAL_REFUND_INITIATED", "LESS_THAN_A_FULL_REFUND_ISSUED"}:
        return "partial_refund_offered"
    if combined & {"WAITING_FOR_RETURN_LABEL", "RETURN_LABEL_REQUESTED"}:
        return "label_pending"
    if "READY_FOR_SHIPPING" in combined:
        return "label_received"
    if "ITEM_SHIPPED" in combined:
        return "return_shipped"
    if "ITEM_DELIVERED" in combined:
        return "seller_received_return"
    if "CLOSED" in combined and is_confidently_closed(return_row):
        return "resolved_refunded"
    if "RETURN_REQUESTED" in combined:
        return "return_opened"
    if "BUYER_ACTION" in combined or "SELLER_MESSAGE" in combined:
        return "seller_message_needs_response"
    return "waiting_on_seller" if "CLOSED" not in combined else "return_opened"


def map_problem_type(reason: Any, current_type: Any) -> str:
    text = f"{reason or ''} {current_type or ''}".upper()
    if "MISSING" in text or "INCOMPLETE" in text:
        return "missing_items"
    if "CHANGED" in text or "BUYER" in text:
        return "buyer_choice"
    return "not_as_listed"


def next_action_for_state(state: str) -> str | None:
    return {
        "return_opened": "Review eBay return/case status.",
        "seller_message_needs_response": "Respond to seller in eBay.",
        "waiting_on_seller": "Wait for seller response.",
        "partial_refund_offered": "Review partial refund offer.",
        "label_pending": "Wait for return label.",
        "label_received": "Ship item back to seller.",
        "return_shipped": "Wait for seller to receive return.",
        "seller_received_return": "Wait for refund.",
        "escalated": "Wait for eBay case decision.",
    }.get(state)


def is_confidently_closed(return_row: dict[str, Any]) -> bool:
    status = clean_upper(return_row.get("status"))
    state = clean_upper(return_row.get("state"))
    actual_refund = money_value(nested(return_row, "buyerTotalRefund", "actualRefundAmount"))
    return "CLOSED" in {status, state} and actual_refund is not None


def print_summary(mapped: dict[str, Any], *, dry_run: bool) -> None:
    prefix = "DRY RUN" if dry_run else "WRITE"
    print(
        f"{prefix}: order={mapped.get('supplier_order_id')} return={mapped.get('ebay_return_id')} "
        f"state={mapped.get('workflow_state')} expected={mapped.get('expected_refund_amount')}"
    )


def nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def unwrap_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("Value")
    return value


def money_value(value: Any) -> float | None:
    value = unwrap_value(value)
    if isinstance(value, dict):
        value = value.get("value")
    try:
        if value is None or value == "":
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def money_currency(value: Any) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("currency") or value.get("currencyId"))
    return None


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def clean_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
