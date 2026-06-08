"""Search eBay Browse for sourcing candidates from seed ASINs."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import time
from typing import Any
from urllib.parse import quote

import requests

from sourcing_common import chunked, fetch_settings, get_supabase_client, required_env, to_float
from title_cleaning import clean_marketplace_title_for_search


EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    token = get_access_token()
    seeds = fetch_seeds(supabase, args.run_id, args.limit)
    rows_by_item_id: dict[str, dict[str, Any]] = {}

    for index, seed in enumerate(seeds, start=1):
        query = clean_marketplace_title_for_search(seed.get("amazon_title"))
        if not query:
            continue
        print(f"[{index}/{len(seeds)}] {seed['asin']} search: {query}")
        items = search_ebay(token, query, settings, args.max_results_per_asin)
        for item in items:
            item = enrich_item_if_shipping_missing(token, item, settings)
            row = map_item(seed, item)
            if not is_allowed_candidate(row, item, settings):
                continue
            ebay_item_id = str(row.get("ebay_item_id") or "")
            if ebay_item_id and ebay_item_id not in rows_by_item_id:
                rows_by_item_id[ebay_item_id] = row
        time.sleep(args.pause_seconds)
    rows = list(rows_by_item_id.values())

    print("eBay sourcing search")
    print("--------------------")
    print(f"Run ID: {args.run_id}")
    print(f"Seeds searched: {len(seeds)}")
    print(f"Candidates found: {len(rows)}")

    if args.dry_run:
        for row in rows[:10]:
            print(f"{row['asin']} | {row['ebay_title']} | ${row['price']} + ${row['shipping_cost']}")
        return 0

    for batch in chunked(rows, 250):
        supabase.table("sourcing_ebay_candidates").upsert(batch, on_conflict="ebay_item_id").execute()
    supabase.table("sourcing_runs").update(
        {
            "status": "running",
            "search_count": len(seeds),
            "candidate_count": len(rows),
            "api_call_count": len(seeds),
            "settings_snapshot": settings.__dict__,
        }
    ).eq("sourcing_run_id", args.run_id).execute()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search eBay Browse for MBOP sourcing candidates.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=50, help="Seed ASINs to search.")
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--pause-seconds", type=float, default=0.3)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def fetch_seeds(supabase, run_id: str, limit: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_seed_asins")
        .select("*")
        .eq("sourcing_run_id", run_id)
        .order("inventory_need_level")
        .limit(limit)
        .execute()
    )
    return response.data or []


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


def search_ebay(token: str, query: str, settings, limit: int) -> list[dict[str, Any]]:
    filters = [
        "conditionIds:{1000}",
        f"itemLocationCountry:{{{'|'.join(settings.item_location_countries)}}}",
        f"deliveryCountry:{settings.delivery_country}",
        "buyingOptions:{FIXED_PRICE|AUCTION}",
    ]
    response = requests.get(
        EBAY_BROWSE_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
        },
        params={
            "q": query,
            "limit": min(limit, 50),
            "filter": ",".join(filters),
            "sort": "price",
        },
        timeout=30,
    )
    if response.status_code == 400 and "deliveryCountry" in response.text:
        filters_without_delivery_country = [
            filter_value
            for filter_value in filters
            if not filter_value.startswith("deliveryCountry:")
        ]
        response = requests.get(
            EBAY_BROWSE_SEARCH_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
            },
            params={
                "q": query,
                "limit": min(limit, 50),
                "filter": ",".join(filters_without_delivery_country),
                "sort": "price",
            },
            timeout=30,
        )
    response.raise_for_status()
    return response.json().get("itemSummaries", [])


def enrich_item_if_shipping_missing(token: str, item: dict[str, Any], settings) -> dict[str, Any]:
    if has_shipping_to_buyer(item):
        return item
    item_id = item.get("itemId")
    if not item_id:
        return item

    response = requests.get(
        f"{EBAY_BROWSE_ITEM_URL}/{item_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
        },
        params={"quantity_for_shipping_estimate": "1"},
        timeout=30,
    )
    if not response.ok:
        return item
    detail = response.json()
    return {**item, **detail, "rawSearchSummary": item}


def map_item(seed: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    shipping = first_shipping_cost(item)
    price = item_price(item)
    landed_cost = round(price + shipping, 2) if shipping is not None else None
    buying_options = item.get("buyingOptions") or []
    return {
        "sourcing_run_id": seed["sourcing_run_id"],
        "seed_id": seed["seed_id"],
        "asin": seed["asin"],
        "ebay_item_id": item.get("itemId"),
        "ebay_legacy_item_id": item.get("legacyItemId"),
        "ebay_item_web_url": item.get("itemWebUrl"),
        "ebay_title": item.get("title"),
        "ebay_image_url": ((item.get("image") or {}).get("imageUrl")),
        "seller_username": ((item.get("seller") or {}).get("username")),
        "item_location_country": ((item.get("itemLocation") or {}).get("country")),
        "condition_id": item.get("conditionId"),
        "condition": item.get("condition"),
        "buying_options": buying_options,
        "price": price,
        "shipping_cost": shipping,
        "landed_cost": landed_cost,
        "shipping_is_separate": shipping > 0 if shipping is not None else False,
        "available_quantity": first_quantity(item),
        "is_multi_quantity": (first_quantity(item) or 0) > 1,
        "auction_end_time": item.get("itemEndDate"),
        "bid_count": item.get("bidCount"),
        "current_bid": to_float(((item.get("currentBidPrice") or {}).get("value")), 0) or None,
        "best_offer_enabled": "BEST_OFFER" in buying_options,
        "raw_ebay_json": item,
        "first_seen_at": dt.datetime.now(dt.UTC).isoformat(),
        "last_seen_at": dt.datetime.now(dt.UTC).isoformat(),
        "listing_status": "active",
    }


def item_price(item: dict[str, Any]) -> float:
    price = to_float((item.get("price") or {}).get("value"), 0)
    if price > 0:
        return price
    return to_float((item.get("currentBidPrice") or {}).get("value"), 0)


def is_allowed_candidate(row: dict[str, Any], item: dict[str, Any], settings) -> bool:
    return row.get("item_location_country") in settings.item_location_countries


def has_shipping_to_buyer(item: dict[str, Any]) -> bool:
    for option in item.get("shippingOptions") or []:
        cost = option.get("shippingCost") or {}
        if cost.get("value") is not None:
            return True
    return False


def first_shipping_cost(item: dict[str, Any]) -> float | None:
    for option in item.get("shippingOptions") or []:
        cost = option.get("shippingCost") or {}
        if cost.get("value") is not None:
            return to_float(cost.get("value"), 0)
    return None


def end_user_context_header(settings) -> str:
    location = f"country={settings.buyer_country},zip={settings.buyer_zip}"
    return f"contextualLocation={quote(location, safe='')}"


def first_quantity(item: dict[str, Any]) -> int | None:
    for availability in item.get("estimatedAvailabilities") or []:
        quantity = availability.get("estimatedAvailableQuantity")
        if quantity is not None:
            return int(to_float(quantity, 0))
    return None


if __name__ == "__main__":
    raise SystemExit(main())
