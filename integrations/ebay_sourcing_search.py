"""Search eBay Browse for sourcing candidates from seed ASINs."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import random
import time
from typing import Any
from urllib.parse import quote

import requests

from sourcing_common import chunked, fetch_settings, get_supabase_client, required_env, to_float
from system_detection import detect_system_from_title, normalize_spaces, normalize_system, remove_system_terms
from title_cleaning import clean_marketplace_title_for_search


EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"
MAX_HTTP_RETRIES = 6
SEARCH_SYSTEM_ALIASES = {
    "Xbox Series X": ["Xbox Series X", "Xbox Series"],
    "Xbox Series S": ["Xbox Series S", "Xbox Series"],
    "Xbox One": ["Xbox One", "xb1"],
    "PS 2": ["PlayStation 2", "ps2"],
    "PS 3": ["PlayStation 3", "ps3"],
    "PS 4": ["PlayStation 4", "ps4"],
    "PS 5": ["PlayStation 5", "ps5"],
    "Switch": ["Nintendo Switch", "Switch"],
    "Wii": ["Nintendo Wii", "Wii"],
    "Wii U": ["Nintendo Wii U", "Wii U", "wiiu"],
    "3DS": ["Nintendo 3DS", "3DS"],
    "DS": ["Nintendo DS", "DS"],
}


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    token = get_access_token()
    seeds = fetch_seeds(supabase, args.run_id, args.limit, args.offset)
    rows_by_item_id: dict[str, dict[str, Any]] = {}
    api_call_count = 0
    searched_seed_count = 0
    rate_limited = False
    rate_limit_message = None

    for index, seed in enumerate(seeds, start=1):
        queries = search_queries_for_seed(seed)
        for query_index, query in enumerate(queries, start=1):
            if args.max_api_calls is not None and api_call_count >= args.max_api_calls:
                rate_limited = True
                rate_limit_message = "eBay Browse daily quota budget exhausted before next search"
                print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                break
            print(f"[{index}/{len(seeds)}:{query_index}/{len(queries)}] {seed['asin']} search: {query}")
            try:
                items = search_ebay(token, query, settings, args.max_results_per_asin)
                api_call_count += 1
            except EbayRateLimitedError as error:
                rate_limited = True
                rate_limit_message = str(error)
                print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                break
            for item in items:
                if args.max_api_calls is not None and api_call_count >= args.max_api_calls:
                    rate_limited = True
                    rate_limit_message = "eBay Browse daily quota budget exhausted before item detail enrichment"
                    print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                    break
                try:
                    item, detail_call_count = enrich_item_if_shipping_missing(token, item, settings)
                except EbayRateLimitedError as error:
                    rate_limited = True
                    rate_limit_message = str(error)
                    print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                    break
                api_call_count += detail_call_count
                row = map_item(seed, item)
                if not is_allowed_candidate(row, item, settings, seed):
                    continue
                ebay_item_id = str(row.get("ebay_item_id") or "")
                if ebay_item_id and ebay_item_id not in rows_by_item_id:
                    rows_by_item_id[ebay_item_id] = row
            if rate_limited:
                break
            time.sleep(args.pause_seconds)
        if rate_limited:
            break
        searched_seed_count += 1
    rows = list(rows_by_item_id.values())

    print("eBay sourcing search")
    print("--------------------")
    print(f"Run ID: {args.run_id}")
    print(f"Seeds searched: {searched_seed_count}")
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
            "search_count": args.offset + searched_seed_count,
            "candidate_count": len(rows),
            "api_call_count": api_call_count,
            "settings_snapshot": settings.__dict__,
            "raw_summary_json": {
                "ebay_search": {
                    "rate_limited": rate_limited,
                    "stop_reason": "ebay_out_of_quota"
                    if rate_limited and "quota budget exhausted" in str(rate_limit_message or "")
                    else "ebay_rate_limited"
                    if rate_limited
                    else None,
                    "message": rate_limit_message,
                    "offset": args.offset,
                    "requested_seed_count": len(seeds),
                    "searched_seed_count": searched_seed_count,
                    "api_call_count": api_call_count,
                    "max_api_calls": args.max_api_calls,
                }
            },
        }
    ).eq("sourcing_run_id", args.run_id).execute()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search eBay Browse for MBOP sourcing candidates.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--limit", type=int, default=50, help="Seed ASINs to search.")
    parser.add_argument("--offset", type=int, default=0, help="Number of prioritized seed ASINs to skip.")
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Maximum eBay Browse calls to spend in this slice.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def fetch_seeds(supabase, run_id: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_seed_asins")
        .select("*")
        .eq("sourcing_run_id", run_id)
        .order("inventory_need_level")
        .range(max(offset, 0), max(offset, 0) + max(limit, 0) - 1)
        .execute()
    )
    return response.data or []


def search_queries_for_seed(seed: dict[str, Any]) -> list[str]:
    amazon_title = str(seed.get("amazon_title") or "")
    base_query = clean_marketplace_title_for_search(amazon_title)
    if not base_query:
        return []

    system_from_title = detect_system_from_title(amazon_title)
    system = system_from_title or inferred_system_from_seed(seed)
    aliases = SEARCH_SYSTEM_ALIASES.get(system or "", [])
    title_without_system = normalize_spaces(remove_system_terms(base_query.lower()))
    queries = [base_query] if system_from_title or not aliases else []

    if title_without_system and aliases:
        for alias in aliases:
            queries.append(normalize_spaces(f"{title_without_system} {alias}"))

    return unique_queries(queries)


def inferred_system_from_seed(seed: dict[str, Any]) -> str | None:
    raw_context = seed.get("raw_context_json") or {}
    if not isinstance(raw_context, dict):
        return None
    return normalize_system(str(raw_context.get("inferred_system") or ""))


def unique_queries(queries: list[str]) -> list[str]:
    seen = set()
    output = []
    for query in queries:
        normalized_key = normalize_spaces(query).casefold()
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        output.append(normalize_spaces(query))
    return output


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
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
    }
    params = {
        "q": query,
        "limit": min(limit, 50),
        "filter": ",".join(filters),
        "sort": "price",
    }
    response = get_with_retries(EBAY_BROWSE_SEARCH_URL, headers=headers, params=params, timeout=30)
    if response.status_code == 400 and "deliveryCountry" in response.text:
        filters_without_delivery_country = [
            filter_value
            for filter_value in filters
            if not filter_value.startswith("deliveryCountry:")
        ]
        response = get_with_retries(
            EBAY_BROWSE_SEARCH_URL,
            headers=headers,
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


def enrich_item_if_shipping_missing(token: str, item: dict[str, Any], settings) -> tuple[dict[str, Any], int]:
    if has_shipping_to_buyer(item):
        return item, 0
    item_id = item.get("itemId")
    if not item_id:
        return item, 0

    response = get_with_retries(
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
        return item, 1
    detail = response.json()
    return {**item, **detail, "rawSearchSummary": item}, 1


class EbayRateLimitedError(RuntimeError):
    pass


def get_with_retries(url: str, **kwargs) -> requests.Response:
    last_response: requests.Response | None = None
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        response = requests.get(url, **kwargs)
        last_response = response
        if response.status_code != 429:
            return response
        if attempt == MAX_HTTP_RETRIES:
            break
        sleep_seconds = retry_after_seconds(response, attempt)
        print(
            f"eBay Browse rate limited (429). Retry {attempt}/{MAX_HTTP_RETRIES - 1} in {sleep_seconds:.1f}s.",
            flush=True,
        )
        time.sleep(sleep_seconds)
    assert last_response is not None
    if last_response.status_code == 429:
        raise EbayRateLimitedError(f"eBay Browse returned 429 after {MAX_HTTP_RETRIES} attempts")
    return last_response


def retry_after_seconds(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(max(float(retry_after), 1.0), 90.0)
        except ValueError:
            pass
    return min(2 ** attempt + random.uniform(0, 1.5), 90.0)


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


def is_allowed_candidate(row: dict[str, Any], item: dict[str, Any], settings, seed: dict[str, Any]) -> bool:
    if row.get("item_location_country") not in settings.item_location_countries:
        return False
    if is_pickup_only(item):
        return False
    seed_system = detect_system_from_title(str(seed.get("amazon_title") or "")) or inferred_system_from_seed(seed)
    candidate_system = detect_system_from_title(str(row.get("ebay_title") or ""))
    if seed_system == "Wii" and candidate_system == "Wii U":
        return False
    return True


def is_pickup_only(item: dict[str, Any]) -> bool:
    delivery_options = []
    for availability in item.get("estimatedAvailabilities") or []:
        if isinstance(availability, dict):
            delivery_options.extend(str(option) for option in availability.get("deliveryOptions") or [])
    has_pickup = any("PICKUP" in option.upper() for option in delivery_options) or bool(item.get("pickupOptions") or [])
    has_shipping = bool(item.get("shippingOptions") or [])
    return has_pickup and not has_shipping


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
