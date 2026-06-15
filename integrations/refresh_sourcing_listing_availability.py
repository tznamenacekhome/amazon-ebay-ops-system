"""Refresh active eBay listing availability for MBOP sourcing opportunities."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import time
from typing import Any
from urllib.parse import quote

import requests

from sourcing_common import fetch_settings, get_supabase_client, required_env, to_float


EBAY_BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"
ACTIVE_OPPORTUNITY_STATUSES = ["open", "watching", "roi_snoozed"]
UNAVAILABLE_DISMISS_REASON = "no_longer_available"


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    token = get_access_token()
    opportunities = fetch_active_opportunities(supabase, args.limit)

    checked = 0
    unavailable = 0
    still_active = 0
    errors = 0
    results_by_item_id: dict[str, dict[str, Any]] = {}

    for opportunity in opportunities:
        ebay_item_id = opportunity.get("ebay_item_id")
        candidate_id = opportunity.get("candidate_id")
        if not ebay_item_id or not candidate_id:
            continue

        checked += 1
        ebay_item_id = str(ebay_item_id)
        if ebay_item_id not in results_by_item_id:
            results_by_item_id[ebay_item_id] = fetch_listing(token, ebay_item_id, settings)
            time.sleep(args.pause_seconds)
        result = results_by_item_id[ebay_item_id]
        now = dt.datetime.now(dt.UTC).isoformat()

        if result["error"]:
            errors += 1
            print(f"error {ebay_item_id}: {result['error']}")
            continue

        if result["available"]:
            still_active += 1
            if args.apply:
                update_candidate_active(supabase, opportunity, result["payload"], now)
        else:
            unavailable += 1
            print(f"unavailable {ebay_item_id}: {result['reason']}")
            if args.apply:
                mark_unavailable(supabase, opportunity, result, now)

    print("Sourcing listing availability refresh")
    print("-------------------------------------")
    print("Mode:", "write" if args.apply else "dry run")
    print(f"Opportunities checked: {checked}")
    print(f"Unique eBay items checked: {len(results_by_item_id)}")
    print(f"Still active: {still_active}")
    print(f"No longer available: {unavailable}")
    print(f"Errors: {errors}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh eBay availability for MBOP sourcing opportunities.")
    parser.add_argument("--apply", action="store_true", help="Write availability updates to Supabase.")
    parser.add_argument("--limit", type=int, default=250, help="Maximum opportunities to check.")
    parser.add_argument("--pause-seconds", type=float, default=0.25)
    return parser.parse_args()


def get_access_token() -> str:
    credentials = f"{required_env('EBAY_CLIENT_ID')}:{required_env('EBAY_CLIENT_SECRET')}"
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": required_env("EBAY_REFRESH_TOKEN"),
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_active_opportunities(supabase, limit: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_opportunities")
        .select(
            "opportunity_id,candidate_id,asin,ebay_item_id,status,"
            "sourcing_ebay_candidates(ebay_item_id,listing_status,last_seen_at,price,shipping_cost,landed_cost,raw_ebay_json)"
        )
        .in_("status", ACTIVE_OPPORTUNITY_STATUSES)
        .order("updated_at")
        .limit(limit)
        .execute()
    )
    rows = response.data or []
    return [
        {
            **row,
            "ebay_item_id": row.get("ebay_item_id")
            or ((row.get("sourcing_ebay_candidates") or {}).get("ebay_item_id")),
            "candidate": row.get("sourcing_ebay_candidates") or {},
        }
        for row in rows
    ]


def fetch_listing(token: str, ebay_item_id: str, settings) -> dict[str, Any]:
    response = requests.get(
        f"{EBAY_BROWSE_ITEM_URL}/{ebay_item_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
        },
        params={"quantity_for_shipping_estimate": "1"},
        timeout=30,
    )
    if response.status_code in {404, 410}:
        return {"available": False, "reason": f"eBay returned {response.status_code}", "payload": None, "error": None}
    if response.status_code == 400 and "not found" in response.text.lower():
        return {"available": False, "reason": "eBay item not found", "payload": None, "error": None}
    if not response.ok:
        return {"available": True, "reason": None, "payload": None, "error": f"{response.status_code} {response.text[:200]}"}

    payload = response.json()
    available, reason = listing_is_available(payload)
    return {"available": available, "reason": reason, "payload": payload, "error": None}


def listing_is_available(payload: dict[str, Any]) -> tuple[bool, str | None]:
    end_date = parse_ebay_datetime(payload.get("itemEndDate"))
    if end_date and end_date <= dt.datetime.now(dt.UTC):
        return False, f"itemEndDate passed: {payload.get('itemEndDate')}"

    availability_statuses = []
    quantities = []
    for availability in payload.get("estimatedAvailabilities") or []:
        if not isinstance(availability, dict):
            continue
        status = str(availability.get("estimatedAvailabilityStatus") or "").upper()
        if status:
            availability_statuses.append(status)
        if availability.get("estimatedAvailableQuantity") is not None:
            quantities.append(int(to_float(availability.get("estimatedAvailableQuantity"), 0)))

    if any(status in {"SOLD_OUT", "OUT_OF_STOCK", "UNAVAILABLE"} for status in availability_statuses):
        return False, f"availability status: {', '.join(availability_statuses)}"
    if quantities and max(quantities) <= 0:
        return False, "available quantity is 0"

    buying_options = payload.get("buyingOptions") or []
    if isinstance(buying_options, list) and len(buying_options) == 0:
        return False, "no buying options returned"

    return True, None


def update_candidate_active(supabase, opportunity: dict[str, Any], payload: dict[str, Any] | None, now: str) -> None:
    candidate_id = opportunity["candidate_id"]
    existing_candidate = opportunity.get("candidate") or {}
    existing_raw = existing_candidate.get("raw_ebay_json") or {}
    updates: dict[str, Any] = {
        "listing_status": "active",
        "last_seen_at": now,
    }
    if payload:
        merged_payload = merge_preserving_shipping(payload, existing_raw)
        shipping_cost = first_shipping_cost(merged_payload)
        price = merged_payload.get("price") if isinstance(merged_payload.get("price"), dict) else {}
        item_price = to_float(price.get("value"), 0)
        updates.update(
            {
                "raw_ebay_json": merged_payload,
                "available_quantity": first_quantity(merged_payload),
                "auction_end_time": merged_payload.get("itemEndDate"),
            }
        )
        if shipping_cost is not None:
            updates["shipping_cost"] = shipping_cost
            updates["shipping_is_separate"] = shipping_cost > 0
            updates["landed_cost"] = round(item_price + shipping_cost, 2)
    supabase.table("sourcing_ebay_candidates").update(updates).eq("candidate_id", candidate_id).execute()


def mark_unavailable(supabase, opportunity: dict[str, Any], result: dict[str, Any], now: str) -> None:
    candidate_id = opportunity["candidate_id"]
    opportunity_id = opportunity["opportunity_id"]
    reason = result.get("reason") or "eBay listing no longer available"
    payload = result.get("payload")

    candidate_updates: dict[str, Any] = {"last_seen_at": now}
    if payload:
        candidate_updates["raw_ebay_json"] = payload
        candidate_updates["available_quantity"] = first_quantity(payload)
        candidate_updates["auction_end_time"] = payload.get("itemEndDate")
    supabase.table("sourcing_ebay_candidates").update(candidate_updates).eq("candidate_id", candidate_id).execute()

    supabase.table("sourcing_opportunities").update(
        {
            "status": "dismissed",
            "updated_at": now,
        }
    ).eq("opportunity_id", opportunity_id).execute()

    supabase.table("sourcing_actions").insert(
        {
            "opportunity_id": opportunity_id,
            "candidate_id": candidate_id,
            "asin": opportunity.get("asin"),
            "ebay_item_id": opportunity.get("ebay_item_id"),
            "action_type": "dismissed",
            "dismiss_reason": UNAVAILABLE_DISMISS_REASON,
            "notes": f"Daily availability refresh: {reason}.",
        }
    ).execute()


def first_quantity(payload: dict[str, Any]) -> int | None:
    for availability in payload.get("estimatedAvailabilities") or []:
        if not isinstance(availability, dict):
            continue
        quantity = availability.get("estimatedAvailableQuantity")
        if quantity is not None:
            return int(to_float(quantity, 0))
    return None


def first_shipping_cost(payload: dict[str, Any]) -> float | None:
    for option in payload.get("shippingOptions") or []:
        if not isinstance(option, dict):
            continue
        cost = option.get("shippingCost") or {}
        if isinstance(cost, dict) and cost.get("value") is not None:
            return to_float(cost.get("value"), 0)
    return None


def merge_preserving_shipping(payload: dict[str, Any], existing_raw: dict[str, Any]) -> dict[str, Any]:
    if payload.get("shippingOptions"):
        return payload
    existing_shipping_options = existing_raw.get("shippingOptions") if isinstance(existing_raw, dict) else None
    if existing_shipping_options:
        return {**payload, "shippingOptions": existing_shipping_options}
    return payload


def end_user_context_header(settings) -> str:
    location = f"country={settings.buyer_country},zip={settings.buyer_zip}"
    return f"contextualLocation={quote(location, safe='')}"


def parse_ebay_datetime(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


if __name__ == "__main__":
    raise SystemExit(main())
