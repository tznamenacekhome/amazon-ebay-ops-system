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
from score_sourcing_opportunities import (
    conservative_fee_estimate,
    fetch_keepa_price_context_by_asin,
    fetch_matching_context,
    matching_diagnostics_for_candidate,
    profitability_landed_cap,
    sale_price_reference,
    shipping_quote_status,
)
from system_detection import detect_system_from_title, normalize_spaces, normalize_system, remove_system_terms
from title_cleaning import clean_marketplace_title_for_search


EBAY_BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_BROWSE_ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"
EBAY_US_VIDEO_GAMES_CATEGORY_ID = "139973"
MAX_HTTP_RETRIES = 6
SEARCH_PLATFORM_SUFFIXES = {
    "Switch": "Switch",
    "Wii": "Wii",
    "Wii U": "(Wii U,wiiu)",
    "3DS": "3DS",
    "PS 2": "(PlayStation 2,PS2)",
    "PS 3": "(PlayStation 3,PS3)",
    "PS 4": "(PlayStation 4,PS4)",
    "PS 5": "(PlayStation 5,PS5)",
    "PSP": "(PSP,PlayStation Portable)",
    "PS Vita": "(PlayStation Vita,PSVita)",
    "Xbox 360": "(Xbox 360,X360,XB360,Xbox360)",
    "Xbox One": "(Xbox One,XB1)",
    "Xbox Series X": "(Xbox Series X,Series X,Series S)",
    "Xbox Series S": "(Xbox Series X,Series X,Series S)",
}
UNSOURCED_SYSTEMS = {"DS", "Xbox", "Gamecube"}
DETAIL_RECORD_LIMIT = 500


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    token = get_access_token()
    seeds = fetch_seeds(supabase, args.run_id, args.limit, args.offset)
    keepa_prices_by_asin = fetch_keepa_price_context_by_asin(supabase, [row.get("asin") for row in seeds])
    matching_context = fetch_matching_context(supabase)
    rows_by_item_id: dict[str, dict[str, Any]] = {}
    detail_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    metrics = empty_metrics()
    searched_seed_count = 0
    rate_limited = False
    rate_limit_message = None

    for index, seed in enumerate(seeds, start=1):
        queries = search_queries_for_seed(seed)
        metrics["query_variant_count"] += len(queries)
        for query_index, query in enumerate(queries, start=1):
            if args.max_api_calls is not None and total_browse_calls(metrics) >= args.max_api_calls:
                rate_limited = True
                rate_limit_message = "eBay Browse daily quota budget exhausted before next search"
                print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                break
            print(f"[{index}/{len(seeds)}:{query_index}/{len(queries)}] {seed['asin']} search: {query}")
            try:
                items, search_metrics = search_ebay(token, query, settings, args.max_results_per_asin)
                add_metrics(metrics, search_metrics)
                metrics["search_results_returned_count"] += len(items)
            except EbayRateLimitedError as error:
                add_metrics(metrics, error.metrics)
                rate_limited = True
                rate_limit_message = str(error)
                print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                break
            for item in items:
                if args.max_api_calls is not None and total_browse_calls(metrics) >= args.max_api_calls:
                    rate_limited = True
                    rate_limit_message = "eBay Browse daily quota budget exhausted before item detail enrichment"
                    print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                    break
                summary_item = tag_search_context(item, query)
                summary_row = map_item(seed, summary_item)
                ebay_item_id = str(summary_row.get("ebay_item_id") or "")
                if ebay_item_id and ebay_item_id in rows_by_item_id:
                    metrics["duplicate_item_count"] += 1
                    continue
                summary_decision = candidate_decision(
                    summary_row,
                    seed,
                    settings,
                    keepa_prices_by_asin,
                    matching_context,
                )
                if should_reject_summary(summary_decision):
                    increment_summary_filter(metrics, summary_decision)
                    continue
                detail_plan = detail_plan_for_candidate(summary_row, summary_decision)
                final_row = summary_row
                detail_record: dict[str, Any] | None = None
                if detail_plan["required"]:
                    if args.max_api_calls is not None and total_browse_calls(metrics) >= args.max_api_calls:
                        rate_limited = True
                        rate_limit_message = "eBay Browse daily quota budget exhausted before item detail enrichment"
                        print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                        break
                    try:
                        detail_item, detail_record, detail_metrics = enrich_item_with_detail(
                            token,
                            summary_item,
                            seed,
                            query,
                            settings,
                            detail_plan,
                            detail_cache,
                        )
                        add_metrics(metrics, detail_metrics)
                    except EbayRateLimitedError as error:
                        add_metrics(metrics, error.metrics)
                        rate_limited = True
                        rate_limit_message = str(error)
                        print(f"eBay sourcing search paused: {rate_limit_message}", flush=True)
                        break
                    final_row = map_item(seed, detail_item)
                    final_decision = candidate_decision(
                        final_row,
                        seed,
                        settings,
                        keepa_prices_by_asin,
                        matching_context,
                    )
                    update_detail_outcome_metrics(metrics, detail_record, summary_decision, final_decision)
                    if should_reject_summary(final_decision):
                        metrics["detail_calls_candidate_rejected_afterward_count"] += 1
                        if detail_record:
                            detail_record["final_candidate_disposition"] = "rejected"
                            append_detail_record(metrics, detail_record)
                        continue
                    metrics["detail_calls_candidate_retained_count"] += 1
                    if detail_record:
                        detail_record["final_candidate_disposition"] = "retained"
                        mark_detail_reason_retained(metrics, detail_record)
                        append_detail_record(metrics, detail_record)
                else:
                    if shipping_quote_status(summary_row).startswith("unknown"):
                        metrics["detail_calls_skipped_not_needed_count"] += 1
                    else:
                        metrics["detail_calls_skipped_shipping_known_count"] += 1

                if not is_allowed_candidate(final_row, final_row.get("raw_ebay_json") or {}, settings, seed):
                    metrics["summary_filtered_count"] += 1
                    continue
                ebay_item_id = str(final_row.get("ebay_item_id") or "")
                if ebay_item_id:
                    rows_by_item_id[ebay_item_id] = final_row
            if rate_limited:
                break
            time.sleep(args.pause_seconds)
        if rate_limited:
            break
        if not queries:
            metrics["skipped_unsourced_seed_count"] += 1
            metrics["summary_filtered_count"] += 1
        searched_seed_count += 1

    rows = list(rows_by_item_id.values())
    api_call_count = total_browse_calls(metrics)
    metrics["api_call_count"] = api_call_count

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
                    **metrics,
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
                    "max_api_calls": args.max_api_calls,
                    "video_games_category_id": EBAY_US_VIDEO_GAMES_CATEGORY_ID,
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
    parser.add_argument("--max-results-per-asin", type=int, default=200)
    parser.add_argument("--pause-seconds", type=float, default=1.0)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Maximum eBay Browse calls to spend in this slice.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def fetch_seeds(supabase, run_id: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
    query = supabase.table("sourcing_seed_asins").select("*").eq("sourcing_run_id", run_id)
    if has_cycle_queue_columns(supabase, run_id):
        query = query.order("queue_position")
    else:
        query = query.order("inventory_need_level")
    response = query.range(max(offset, 0), max(offset, 0) + max(limit, 0) - 1).execute()
    return response.data or []


def has_cycle_queue_columns(supabase, run_id: str) -> bool:
    try:
        response = (
            supabase.table("sourcing_seed_asins")
            .select("queue_position")
            .eq("sourcing_run_id", run_id)
            .not_.is_("queue_position", "null")
            .limit(1)
            .execute()
        )
    except Exception:
        return False
    return bool(response.data)


def search_queries_for_seed(seed: dict[str, Any]) -> list[str]:
    amazon_title = str(seed.get("amazon_title") or "")
    base_query = clean_marketplace_title_for_search(amazon_title)
    if not base_query:
        return []

    system_from_title = detect_system_from_title(amazon_title)
    system = system_from_title or inferred_system_from_seed(seed)
    if system in UNSOURCED_SYSTEMS:
        return []
    suffix = SEARCH_PLATFORM_SUFFIXES.get(system or "")
    if not suffix:
        return [base_query]
    title_without_system = normalize_spaces(remove_system_terms(base_query.lower()))
    title = title_without_system or base_query
    return unique_queries([normalize_spaces(f"{title} {suffix}")])


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


def empty_call_metrics() -> dict[str, int]:
    return {
        "search_call_count": 0,
        "detail_call_count": 0,
        "retry_http_attempt_count": 0,
        "rate_limited_http_attempt_count": 0,
        "failed_search_call_count": 0,
        "failed_detail_call_count": 0,
        "duplicate_detail_calls_prevented_count": 0,
    }


def empty_metrics() -> dict[str, Any]:
    return {
        **empty_call_metrics(),
        "query_variant_count": 0,
        "search_results_returned_count": 0,
        "summary_filtered_count": 0,
        "skipped_unsourced_seed_count": 0,
        "summary_profitability_filtered_count": 0,
        "detail_eligible_count": 0,
        "detail_calls_skipped_shipping_known_count": 0,
        "detail_calls_skipped_not_needed_count": 0,
        "detail_calls_success_count": 0,
        "detail_calls_missing_data_resolved_count": 0,
        "detail_calls_missing_data_not_resolved_count": 0,
        "detail_calls_changed_decision_count": 0,
        "detail_calls_no_decision_change_count": 0,
        "detail_calls_candidate_rejected_afterward_count": 0,
        "detail_calls_candidate_retained_count": 0,
        "duplicate_item_count": 0,
        "detail_reason_counts": {},
        "detail_reason_breakdown": {},
        "detail_call_records": [],
    }


def add_metrics(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, int):
            target[key] = int(target.get(key) or 0) + value


def total_browse_calls(metrics: dict[str, Any]) -> int:
    return int(metrics.get("search_call_count") or 0) + int(metrics.get("detail_call_count") or 0)


def tag_search_context(item: dict[str, Any], query: str) -> dict[str, Any]:
    return {**item, "_mbop_search_query": query, "_mbop_search_category_id": EBAY_US_VIDEO_GAMES_CATEGORY_ID}


def candidate_decision(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    settings,
    keepa_prices_by_asin: dict[str, dict[str, float | None]],
    matching_context: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = matching_diagnostics_for_candidate(candidate, seed, matching_context, settings)
    hard_blocks = [
        reason
        for reason in diagnostics.get("static_rules", {}).get("hard_blocks", [])
        if not is_allowed_xbox_cross_generation_block(reason, diagnostics)
    ]
    recommendation = "Blocked" if hard_blocks else diagnostics.get("recommendation") or "Review"
    pricing = price_context_for_seed(seed, settings, keepa_prices_by_asin)
    buying_options = candidate.get("buying_options") or []
    item_price = to_float(candidate.get("price"), 0)
    current_bid = to_float(candidate.get("current_bid"), 0)
    shipping_status = shipping_quote_status(candidate)
    landed_cost = candidate.get("landed_cost")
    best_offer = bool(candidate.get("best_offer_enabled"))
    auction = "AUCTION" in buying_options
    min_offer_fraction = max(to_float(getattr(settings, "best_offer_min_ask_percent", 60), 60) / 100, 0.01)
    economic_reject = False
    economic_reason = None
    if item_price > 0:
        if auction:
            auction_price = current_bid or item_price
            if auction_price > pricing["max_profitable_landed_cost"]:
                economic_reject = True
                economic_reason = "auction_current_price_above_landed_cap"
        elif best_offer:
            if item_price > pricing["max_profitable_landed_cost"] / min_offer_fraction:
                economic_reject = True
                economic_reason = "best_offer_ask_above_minimum_offer_ceiling"
        elif item_price > pricing["max_profitable_landed_cost"]:
            economic_reject = True
            economic_reason = "fixed_price_above_landed_cap"
    if landed_cost is not None and not best_offer and not auction and to_float(landed_cost, 0) > pricing["max_profitable_landed_cost"]:
        economic_reject = True
        economic_reason = "known_landed_cost_above_cap"
    return {
        "diagnostics": diagnostics,
        "hard_blocks": hard_blocks,
        "recommendation": recommendation,
        "matching_reject": recommendation == "Blocked" or bool(hard_blocks),
        "economic_reject": economic_reject,
        "economic_reason": economic_reason,
        "shipping_status": shipping_status,
        "pricing": pricing,
        "opportunity_shape": "auction" if auction else "best_offer" if best_offer else "fixed_price",
        "landed_cost": landed_cost,
    }


def price_context_for_seed(seed: dict[str, Any], settings, keepa_prices_by_asin: dict[str, dict[str, float | None]]) -> dict[str, float]:
    seed_sale_price = to_float(seed.get("target_sale_price"), 0)
    pricing_reference = sale_price_reference(seed, keepa_prices_by_asin, seed_sale_price)
    sale_price = to_float(pricing_reference.get("reference_price"), 0)
    raw_context = seed.get("raw_context_json") or {}
    raw_estimated_fees = to_float(raw_context.get("estimated_fee_cost"), 0)
    conservative_fees = conservative_fee_estimate(sale_price)
    estimated_fees = max(raw_estimated_fees, conservative_fees) if raw_estimated_fees > 0 else conservative_fees
    return {
        "sale_price": sale_price,
        "estimated_fees": estimated_fees,
        "max_profitable_landed_cost": profitability_landed_cap(sale_price, estimated_fees, settings),
    }


def is_allowed_xbox_cross_generation_block(reason: str, diagnostics: dict[str, Any]) -> bool:
    if "platform mismatch" not in str(reason).casefold():
        return False
    platform = diagnostics.get("platform_rule") or {}
    systems = {platform.get("seed_system"), *(platform.get("candidate_systems") or [])}
    known = {system for system in systems if system}
    xbox_cross_gen = {"Xbox One", "Xbox Series X", "Xbox Series S"}
    return bool(known) and known.issubset(xbox_cross_gen)


def should_reject_summary(decision: dict[str, Any]) -> bool:
    return bool(decision.get("matching_reject") or decision.get("economic_reject"))


def increment_summary_filter(metrics: dict[str, Any], decision: dict[str, Any]) -> None:
    if decision.get("economic_reject") and not decision.get("matching_reject"):
        metrics["summary_profitability_filtered_count"] += 1
    else:
        metrics["summary_filtered_count"] += 1


def detail_plan_for_candidate(candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    fields = []
    if decision.get("shipping_status", "").startswith("unknown"):
        reasons.append("shipping_missing")
        fields.append("shipping_cost")
    platform_rule = (decision.get("diagnostics") or {}).get("platform_rule") or {}
    if platform_rule.get("result") in {"unknown", "review"} and not platform_rule.get("candidate_item_specific_platform_values"):
        reasons.append("platform_confirmation_needed")
        fields.append("localizedAspects.Platform")
    game_name = (decision.get("diagnostics") or {}).get("game_name") or {}
    if game_name.get("result") == "unknown":
        reasons.append("game_name_confirmation_needed")
        fields.append("localizedAspects.Game Name")
    if not reasons:
        return {"required": False, "reasons": [], "fields_missing_before": []}
    return {"required": True, "reasons": unique_text(reasons), "fields_missing_before": unique_text(fields)}


def unique_text(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def detail_record_for_call(seed: dict[str, Any], item: dict[str, Any], query: str, detail_plan: dict[str, Any], settings) -> dict[str, Any]:
    raw_context = seed.get("raw_context_json") if isinstance(seed.get("raw_context_json"), dict) else {}
    return {
        "sourcing_run_id": seed.get("sourcing_run_id"),
        "coverage_cycle_id": seed.get("coverage_cycle_id") or raw_context.get("coverage_cycle_id"),
        "seed_id": seed.get("seed_id"),
        "asin": seed.get("asin"),
        "ebay_item_id": item.get("itemId"),
        "query": query,
        "detail_call_reasons": detail_plan.get("reasons") or [],
        "fields_missing_before": detail_plan.get("fields_missing_before") or [],
        "called_at": dt.datetime.now(dt.UTC).isoformat(),
        "buyer_context": end_user_context_header(settings),
        "http_status": None,
        "retry_attempt_count": 0,
        "success": False,
        "fields_returned": [],
        "fields_populated": [],
        "fields_remaining_missing": [],
        "detail_changed": {},
        "final_candidate_disposition": "not_persisted",
    }


def returned_fields(detail: dict[str, Any]) -> list[str]:
    fields = []
    if has_shipping_to_buyer(detail):
        fields.append("shipping_cost")
    aspects = detail.get("localizedAspects") or []
    for aspect in aspects:
        if isinstance(aspect, dict) and aspect.get("name"):
            fields.append(f"localizedAspects.{aspect.get('name')}")
    if detail.get("shortDescription") or detail.get("description"):
        fields.append("description")
    if detail.get("estimatedAvailabilities"):
        fields.append("estimatedAvailabilities")
    return unique_text(fields)


def populated_missing_fields(missing: list[str], before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    populated = []
    for field in missing:
        if field == "shipping_cost" and not has_shipping_to_buyer(before) and has_shipping_to_buyer(after):
            populated.append(field)
        elif field.startswith("localizedAspects.") and field in returned_fields(after):
            populated.append(field)
    return populated


def missing_fields(item: dict[str, Any], requested: list[str]) -> list[str]:
    returned = set(returned_fields(item))
    return [field for field in requested if field not in returned]


def update_detail_outcome_metrics(
    metrics: dict[str, Any],
    record: dict[str, Any] | None,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    metrics["detail_eligible_count"] += 1
    if record and record.get("success"):
        metrics["detail_calls_success_count"] += 1
    resolved = bool((record or {}).get("fields_populated"))
    if resolved:
        metrics["detail_calls_missing_data_resolved_count"] += 1
    else:
        metrics["detail_calls_missing_data_not_resolved_count"] += 1
    changed = detail_changed_fields(before, after)
    if record is not None:
        record["detail_changed"] = changed
    if any(changed.values()):
        metrics["detail_calls_changed_decision_count"] += 1
    else:
        metrics["detail_calls_no_decision_change_count"] += 1
    for reason in (record or {}).get("detail_call_reasons") or []:
        counts = metrics.setdefault("detail_reason_counts", {})
        counts[reason] = int(counts.get(reason) or 0) + 1
        breakdown = metrics.setdefault("detail_reason_breakdown", {})
        row = breakdown.setdefault(
            reason,
            {"calls": 0, "missing_data_resolved": 0, "decision_changed": 0, "candidate_retained": 0},
        )
        row["calls"] += 1
        row["missing_data_resolved"] += 1 if resolved else 0
        row["decision_changed"] += 1 if any(changed.values()) else 0


def detail_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    return {
        "match_recommendation": before.get("recommendation") != after.get("recommendation"),
        "hard_block_result": bool(before.get("matching_reject")) != bool(after.get("matching_reject")),
        "shipping_status": before.get("shipping_status") != after.get("shipping_status"),
        "landed_cost": before.get("landed_cost") != after.get("landed_cost"),
        "profitability_result": bool(before.get("economic_reject")) != bool(after.get("economic_reject")),
        "opportunity_type": before.get("opportunity_shape") != after.get("opportunity_shape"),
        "persistence_decision": should_reject_summary(before) != should_reject_summary(after),
    }


def append_detail_record(metrics: dict[str, Any], record: dict[str, Any]) -> None:
    records = metrics.setdefault("detail_call_records", [])
    if len(records) < DETAIL_RECORD_LIMIT:
        records.append(record)


def mark_detail_reason_retained(metrics: dict[str, Any], record: dict[str, Any]) -> None:
    breakdown = metrics.setdefault("detail_reason_breakdown", {})
    for reason in record.get("detail_call_reasons") or []:
        row = breakdown.setdefault(
            reason,
            {"calls": 0, "missing_data_resolved": 0, "decision_changed": 0, "candidate_retained": 0},
        )
        row["candidate_retained"] += 1


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


def search_ebay(token: str, query: str, settings, limit: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
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
        "limit": min(limit, 200),
        "filter": ",".join(filters),
        "category_ids": EBAY_US_VIDEO_GAMES_CATEGORY_ID,
        "sort": "price",
    }
    metrics = empty_call_metrics()
    response, call_metrics = get_with_retries(EBAY_BROWSE_SEARCH_URL, call_type="search", headers=headers, params=params, timeout=30)
    add_metrics(metrics, call_metrics)
    if response.status_code == 400 and "deliveryCountry" in response.text:
        filters_without_delivery_country = [
            filter_value
            for filter_value in filters
            if not filter_value.startswith("deliveryCountry:")
        ]
        response, call_metrics = get_with_retries(
            EBAY_BROWSE_SEARCH_URL,
            call_type="search",
            headers=headers,
            params={
                "q": query,
                "limit": min(limit, 200),
                "filter": ",".join(filters_without_delivery_country),
                "category_ids": EBAY_US_VIDEO_GAMES_CATEGORY_ID,
                "sort": "price",
            },
            timeout=30,
        )
        add_metrics(metrics, call_metrics)
    response.raise_for_status()
    return response.json().get("itemSummaries", []), metrics


def enrich_item_with_detail(
    token: str,
    item: dict[str, Any],
    seed: dict[str, Any],
    query: str,
    settings,
    detail_plan: dict[str, Any],
    detail_cache: dict[tuple[str, str], dict[str, Any] | None],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    metrics = empty_call_metrics()
    item_id = item.get("itemId")
    record = detail_record_for_call(seed, item, query, detail_plan, settings)
    if not item_id:
        record["success"] = False
        record["http_status"] = None
        record["outcome"] = "missing_item_id"
        return item, record, metrics
    cache_key = (str(item_id), end_user_context_header(settings))
    if cache_key in detail_cache:
        metrics["duplicate_detail_calls_prevented_count"] += 1
        cached = detail_cache[cache_key]
        record["success"] = cached is not None
        record["outcome"] = "cache_hit"
        if cached:
            return {**item, **cached, "rawSearchSummary": item}, record, metrics
        return item, record, metrics

    response, call_metrics = get_with_retries(
        f"{EBAY_BROWSE_ITEM_URL}/{item_id}",
        call_type="detail",
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": end_user_context_header(settings),
        },
        params={"quantity_for_shipping_estimate": "1"},
        timeout=30,
    )
    add_metrics(metrics, call_metrics)
    record["http_status"] = response.status_code
    record["retry_attempt_count"] = max(call_metrics.get("detail_call_count", 1) - 1, 0)
    if not response.ok:
        detail_cache[cache_key] = None
        record["success"] = False
        record["outcome"] = "http_error"
        return item, record, metrics
    detail = response.json()
    detail_cache[cache_key] = detail
    record["success"] = True
    record["outcome"] = "success"
    record["fields_returned"] = returned_fields(detail)
    merged = {**item, **detail, "rawSearchSummary": item}
    record["fields_populated"] = populated_missing_fields(detail_plan.get("fields_missing_before") or [], item, merged)
    record["fields_remaining_missing"] = missing_fields(merged, detail_plan.get("fields_missing_before") or [])
    return merged, record, metrics


class EbayRateLimitedError(RuntimeError):
    def __init__(self, message: str, metrics: dict[str, int] | None = None):
        super().__init__(message)
        self.metrics = metrics or empty_call_metrics()


def get_with_retries(url: str, *, call_type: str, **kwargs) -> tuple[requests.Response, dict[str, int]]:
    last_response: requests.Response | None = None
    metrics = empty_call_metrics()
    for attempt in range(1, MAX_HTTP_RETRIES + 1):
        response = requests.get(url, **kwargs)
        metrics[f"{call_type}_call_count"] += 1
        last_response = response
        if response.status_code != 429:
            if not response.ok:
                metrics[f"failed_{call_type}_call_count"] += 1
            return response, metrics
        metrics["rate_limited_http_attempt_count"] += 1
        if attempt == MAX_HTTP_RETRIES:
            break
        metrics["retry_http_attempt_count"] += 1
        sleep_seconds = retry_after_seconds(response, attempt)
        print(
            f"eBay Browse rate limited (429). Retry {attempt}/{MAX_HTTP_RETRIES - 1} in {sleep_seconds:.1f}s.",
            flush=True,
        )
        time.sleep(sleep_seconds)
    assert last_response is not None
    if last_response.status_code == 429:
        metrics[f"failed_{call_type}_call_count"] += 1
        raise EbayRateLimitedError(f"eBay Browse returned 429 after {MAX_HTTP_RETRIES} attempts", metrics)
    return last_response, metrics


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
