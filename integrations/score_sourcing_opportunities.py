"""Score eBay sourcing candidates against Amazon seed ASINs."""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Any

from sourcing_common import chunked, fetch_settings, get_supabase_client, paginate_table, to_float
from matching_intelligence import build_listing_snapshot
from sourcing_match_rules import evaluate_static_match_rules, meaningful_title_tokens, resolve_seed_system
from system_detection import detect_system_from_title, normalize_system
from title_cleaning import clean_marketplace_title_for_search


NEED_POINTS = {"critical": 40, "high": 28, "medium": 14, "low": 4}


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    seeds = fetch_seeds(supabase, args.run_id)
    candidates = fetch_candidates(supabase, args.run_id)
    seed_by_id = {row["seed_id"]: row for row in seeds}
    keepa_prices_by_asin = fetch_keepa_price_context_by_asin(supabase, [row.get("asin") for row in seeds])
    historical_status_by_key = fetch_historical_status_by_key(supabase)
    matching_context = fetch_matching_context(supabase)
    rows = [
        score_candidate(
            candidate,
            seed_by_id.get(candidate.get("seed_id")),
            settings,
            keepa_prices_by_asin,
            historical_status_by_key,
            matching_context,
        )
        for candidate in candidates
    ]
    rows = [row for row in rows if row]
    rows.sort(key=lambda row: to_float(row.get("score"), 0), reverse=True)

    print("Sourcing opportunity scoring")
    print("----------------------------")
    print(f"Run ID: {args.run_id}")
    print(f"Candidates scored: {len(rows)}")

    if args.dry_run:
        for row in rows[:15]:
            print(f"{row['asin']} | {row['opportunity_type']} | ${row['profit']} | ROI {row['roi_percent']}% | {row['ai_flags']}")
        return 0

    if args.update_existing:
        updated, inserted = upsert_opportunities(supabase, args.run_id, rows)
        snapshots = snapshot_new_opportunities(supabase, args.run_id)
        supabase.table("sourcing_runs").update(
            {
                "status": "completed",
                "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                "opportunity_count": len(rows),
            }
        ).eq("sourcing_run_id", args.run_id).execute()
        print(f"Updated: {updated}")
        print(f"Inserted: {inserted}")
        print(f"Initial listing snapshots created: {snapshots}")
        return 0

    if args.replace_run:
        deleted = delete_run_opportunities(supabase, args.run_id)
        print(f"Deleted existing opportunities: {deleted}")
    for batch in chunked(rows, 250):
        supabase.table("sourcing_opportunities").insert(batch).execute()
    snapshots = snapshot_new_opportunities(supabase, args.run_id)
    supabase.table("sourcing_runs").update(
        {
            "status": "completed",
            "completed_at": dt.datetime.now(dt.UTC).isoformat(),
            "opportunity_count": len(rows),
        }
    ).eq("sourcing_run_id", args.run_id).execute()
    print(f"Initial listing snapshots created: {snapshots}")
    return 0


def delete_run_opportunities(supabase, run_id: str) -> int:
    deleted = 0
    while True:
        response = (
            supabase.table("sourcing_opportunities")
            .select("opportunity_id")
            .eq("sourcing_run_id", run_id)
            .limit(500)
            .execute()
        )
        ids = [row["opportunity_id"] for row in response.data or [] if row.get("opportunity_id")]
        if not ids:
            return deleted
        supabase.table("sourcing_opportunities").delete().in_("opportunity_id", ids).execute()
        deleted += len(ids)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score MBOP sourcing opportunities.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--replace-run", action="store_true")
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing opportunities by candidate_id and preserve operator workflow statuses.",
    )
    return parser.parse_args()


def upsert_opportunities(supabase, run_id: str, scored_rows: list[dict[str, Any]]) -> tuple[int, int]:
    existing_rows = fetch_existing_opportunities(supabase, run_id)
    existing_by_candidate_id: dict[str, list[dict[str, Any]]] = {}
    for row in existing_rows:
        candidate_id = row.get("candidate_id")
        if candidate_id:
            existing_by_candidate_id.setdefault(candidate_id, []).append(row)
    update_rows = []
    insert_rows = []
    for row in scored_rows:
        existing_matches = existing_by_candidate_id.get(row.get("candidate_id")) or []
        if existing_matches:
            update_rows.extend(merge_existing_opportunity(existing, row) for existing in existing_matches)
        else:
            insert_rows.append(row)
    update_rows_by_id = {
        row["opportunity_id"]: row
        for row in update_rows
        if row.get("opportunity_id")
    }
    update_rows = list(update_rows_by_id.values())

    updated = 0
    for batch in chunked(update_rows, 250):
        supabase.table("sourcing_opportunities").upsert(
            batch,
            on_conflict="opportunity_id",
        ).execute()
        updated += len(batch)

    inserted = 0
    for batch in chunked(insert_rows, 250):
        supabase.table("sourcing_opportunities").insert(batch).execute()
        inserted += len(batch)

    return updated, inserted


def fetch_existing_opportunities(supabase, run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        end = start + page_size - 1
        response = (
            supabase.table("sourcing_opportunities")
            .select("opportunity_id,candidate_id,status,created_at")
            .eq("sourcing_run_id", run_id)
            .order("opportunity_id")
            .range(start, end)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def snapshot_new_opportunities(supabase, run_id: str) -> int:
    opportunities = fetch_opportunities_for_snapshot(supabase, run_id)
    created = 0
    for opportunity in opportunities:
        candidate = opportunity.get("sourcing_ebay_candidates") or {}
        seed = opportunity.get("sourcing_seed_asins") or {}
        snapshot = build_listing_snapshot(
            opportunity=opportunity,
            candidate=candidate,
            seed=seed,
            event="opportunity_created",
            source="score_sourcing_opportunities",
            raw_context={
                "score": opportunity.get("score"),
                "score_reason": opportunity.get("score_reason"),
                "opportunity_type": opportunity.get("opportunity_type"),
            },
        )
        response = supabase.table("sourcing_listing_snapshots").insert(snapshot).execute()
        snapshot_id = (response.data or [{}])[0].get("listing_snapshot_id")
        if snapshot_id:
            supabase.table("sourcing_opportunities").update(
                {
                    "initial_listing_snapshot_id": snapshot_id,
                    "latest_listing_snapshot_id": snapshot_id,
                }
            ).eq("opportunity_id", opportunity["opportunity_id"]).execute()
            created += 1
    return created


def fetch_opportunities_for_snapshot(supabase, run_id: str) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_opportunities")
        .select(
            """
            *,
            sourcing_ebay_candidates (*),
            sourcing_seed_asins (*)
            """
        )
        .eq("sourcing_run_id", run_id)
        .is_("initial_listing_snapshot_id", "null")
        .neq("status", "rejected")
        .execute()
    )
    return response.data or []


def merge_existing_opportunity(existing: dict[str, Any], scored: dict[str, Any]) -> dict[str, Any]:
    preserved_statuses = {
        "dismissed",
        "purchased_pending_match",
        "matched_to_purchase",
    }
    status = existing.get("status") if existing.get("status") in preserved_statuses else scored.get("status")
    return {
        **scored,
        "opportunity_id": existing.get("opportunity_id"),
        "status": status,
        "created_at": existing.get("created_at") or scored.get("created_at"),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def fetch_seeds(supabase, run_id: str) -> list[dict[str, Any]]:
    return fetch_run_rows(supabase, "sourcing_seed_asins", run_id)


def fetch_candidates(supabase, run_id: str) -> list[dict[str, Any]]:
    return fetch_run_rows(supabase, "sourcing_ebay_candidates", run_id)


def fetch_run_rows(supabase, table_name: str, run_id: str, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        end = start + page_size - 1
        response = (
            supabase.table(table_name)
            .select("*")
            .eq("sourcing_run_id", run_id)
            .range(start, end)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def fetch_historical_status_by_key(supabase) -> dict[tuple[str, str], dict[str, Any]]:
    rows = paginate_table(
        supabase,
        "sourcing_actions",
        "asin,ebay_item_id,action_type,created_at,expected_purchase_cost,required_max_landed_cost,required_roi_percent",
        order_column="created_at",
        desc=False,
    )
    status_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    action_status = {
        "dismissed": "dismissed",
        "watching": "watching",
        "purchased": "purchased_pending_match",
        "roi_snoozed": "roi_snoozed",
    }
    for row in rows:
        asin = str(row.get("asin") or "").upper()
        status = action_status.get(str(row.get("action_type") or ""))
        for ebay_item_id in ebay_identity_values(row):
            if asin and ebay_item_id and status:
                status_by_key[(asin, ebay_item_id)] = {**row, "status": status}
    return status_by_key


def fetch_matching_context(supabase) -> dict[str, Any]:
    examples = paginate_table(
        supabase,
        "matching_intelligence_examples",
        "asin,amazon_system,detected_system,ebay_item_id,ebay_legacy_item_id,ebay_title,match_label,label_type,dismiss_reason,source_weight,evidence_strength,created_at",
        order_column="created_at",
        desc=True,
    )
    seller_rows = paginate_table(
        supabase,
        "sourcing_seller_intelligence",
        "seller_username,seller_status,seller_trust_score,status_reason,product_condition_return_count,purchase_conversion_rate",
    )
    examples_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    examples_by_asin: dict[str, list[dict[str, Any]]] = {}
    for example in examples:
        asin = clean_asin(example.get("asin"))
        if asin:
            examples_by_asin.setdefault(asin, []).append(example)
        for ebay_id in ebay_identity_values(example):
            if asin and ebay_id:
                examples_by_key.setdefault((asin, ebay_id), []).append(example)
    sellers = {
        str(row.get("seller_username") or "").casefold(): row
        for row in seller_rows
        if row.get("seller_username")
    }
    return {"examples_by_key": examples_by_key, "examples_by_asin": examples_by_asin, "sellers": sellers}


def fetch_keepa_price_context_by_asin(supabase, asins: list[Any]) -> dict[str, dict[str, float | None]]:
    unique_asins = sorted({str(asin or "").upper() for asin in asins if asin})
    by_asin: dict[str, dict[str, float | None]] = {}
    for batch in chunked(unique_asins, 100):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,raw_keepa_json")
            .in_("asin", batch)
            .execute()
        )
        for row in response.data or []:
            asin = str(row.get("asin") or "").upper()
            if not asin:
                continue
            buy_box_current = cents_to_dollars(row.get("buy_box_price_current_cents"))
            low_fba_current = cents_to_dollars(row.get("new_fba_price_current_cents"))
            new_current = cents_to_dollars(row.get("new_price_current_cents"))
            buy_box_avg90 = cents_to_dollars(row.get("buy_box_price_avg90_cents"))
            new_avg90 = keepa_stats_cents_to_dollars(row.get("raw_keepa_json"), "avg90", 1)
            by_asin[asin] = {
                "avg90_price": buy_box_avg90 if buy_box_avg90 is not None else new_avg90,
                "current_price": buy_box_current if buy_box_current is not None else low_fba_current if low_fba_current is not None else new_current,
            }
    return by_asin


def score_candidate(
    candidate: dict[str, Any],
    seed: dict[str, Any] | None,
    settings,
    keepa_prices_by_asin: dict[str, dict[str, float | None]] | None = None,
    historical_status_by_key: dict[tuple[str, str], dict[str, Any]] | None = None,
    matching_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not seed:
        return None
    title = str(candidate.get("ebay_title") or "")
    matching_diagnostics = matching_diagnostics_for_candidate(candidate, seed, matching_context or {}, settings)
    flags = advisory_flags(title, candidate, seed, settings) + matching_diagnostics["flags"]
    has_excluded_keyword = any("excluded keyword" in flag.lower() for flag in flags)
    has_hard_block = any(flag.startswith("Blocked:") for flag in flags)
    match_recommendation = str(matching_diagnostics.get("recommendation") or "Review")
    is_review_or_non_match = match_recommendation in {"Review", "Probable Non-Match", "Blocked"}

    seed_sale_price = to_float(seed.get("target_sale_price"), 0)
    pricing_reference = sale_price_reference(seed, keepa_prices_by_asin or {}, seed_sale_price)
    sale_price = pricing_reference["reference_price"]
    shipping_status = shipping_quote_status(candidate)
    shipping_unknown = shipping_status.startswith("unknown")
    landed_cost = to_float(candidate.get("landed_cost"), 0) if not shipping_unknown else None
    item_price = to_float(candidate.get("price"), 0)
    raw_context = seed.get("raw_context_json") or {}
    raw_estimated_fees = to_float(raw_context.get("estimated_fee_cost"), 0)
    conservative_fees = conservative_fee_estimate(sale_price)
    estimated_fees = max(raw_estimated_fees, conservative_fees) if raw_estimated_fees > 0 else conservative_fees
    max_profitable_landed_cost = profitability_landed_cap(sale_price, estimated_fees, settings)
    best_offer_sale_price = sale_price
    best_offer_landed_cap = (
        profitability_landed_cap(best_offer_sale_price, estimated_fees, settings)
        if best_offer_sale_price is not None
        else max_profitable_landed_cost
    )
    profit = round(sale_price - estimated_fees - landed_cost, 2) if landed_cost is not None else None
    roi = round((profit / landed_cost) * 100, 1) if profit is not None and landed_cost and landed_cost > 0 else None

    buying_options = candidate.get("buying_options") or []
    quantity_available = int(to_float(candidate.get("available_quantity"), 1) or 1)
    passes = (
        not has_excluded_keyword
        and not has_hard_block
        and not is_review_or_non_match
        and profit is not None
        and roi is not None
        and profit >= settings.min_profit_dollars
        and roi >= settings.min_roi_percent
    )
    best_offer_cap = best_offer_landed_cap if candidate.get("best_offer_enabled") else max_profitable_landed_cost
    opportunity_type = classify(
        candidate,
        buying_options,
        landed_cost,
        best_offer_cap,
        passes,
        settings,
        shipping_unknown,
        has_excluded_keyword or has_hard_block or is_review_or_non_match,
    )
    potential_without_shipping = shipping_unknown and item_price > 0 and item_price <= max_profitable_landed_cost
    status = (
        "open"
        if not has_excluded_keyword
        and not has_hard_block
        and not is_review_or_non_match
        and passes
        else "rejected"
    )
    score = opportunity_score(seed, profit, roi, quantity_available, opportunity_type)
    score = max(0, min(100, score + matching_diagnostics["score_adjustment"]))
    displayed_max_landed_cost = best_offer_cap if opportunity_type == "best_offer" else max_profitable_landed_cost
    max_offer_price = suggested_offer(candidate, best_offer_cap, settings)
    required_offer_percent_of_ask = required_offer_percent(candidate, max_offer_price)
    max_bid = suggested_max_bid(candidate, max_profitable_landed_cost, shipping_unknown)
    historical_status = first_historical_status(historical_status_by_key or {}, candidate)
    if historical_status:
        status = apply_historical_status(
            historical_status,
            status,
            opportunity_type,
            landed_cost,
            item_price,
            max_offer_price,
            displayed_max_landed_cost,
        )
    score_reason = (
        f"{seed.get('inventory_need_level')} need, shipping unknown, max landed cost ${displayed_max_landed_cost}"
        if shipping_unknown
        else f"{seed.get('inventory_need_level')} need, ${profit} profit, {roi}% ROI"
    )
    matching_diagnostics = {
        **matching_diagnostics,
        "pricing_reference": {
            **pricing_reference,
            "estimated_fees": estimated_fees,
            "conservative_fees": conservative_fees,
            "raw_estimated_fees": raw_estimated_fees or None,
        },
    }

    return {
        "sourcing_run_id": candidate["sourcing_run_id"],
        "seed_id": candidate["seed_id"],
        "candidate_id": candidate["candidate_id"],
        "asin": candidate["asin"],
        "ebay_item_id": candidate.get("ebay_item_id"),
        "opportunity_type": opportunity_type,
        "status": status,
        "target_sale_price": sale_price,
        "target_sale_price_source": seed.get("target_sale_price_source"),
        "landed_cost": landed_cost,
        "profit": profit,
        "roi_percent": roi,
        "max_profitable_landed_cost": displayed_max_landed_cost,
        "max_offer_price": max_offer_price,
        "required_offer_percent_of_ask": required_offer_percent_of_ask,
        "max_bid": max_bid if "AUCTION" in buying_options else None,
        "total_profit_opportunity": round(max(profit, 0) * max(quantity_available, 1), 2) if profit is not None else None,
        "inventory_need_level": seed.get("inventory_need_level"),
        "months_of_supply": seed.get("months_of_supply"),
        "monthly_velocity": seed.get("monthly_velocity"),
        "score": score,
        "score_reason": score_reason,
        "warning_flags": seed.get("warning_flags") or [],
        "ai_flags": flags,
        "seller_trust_status": matching_diagnostics.get("seller_status"),
        "seller_trust_score": matching_diagnostics.get("seller_score"),
        "matching_diagnostics_json": matching_diagnostics,
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "updated_at": dt.datetime.now(dt.UTC).isoformat(),
    }


def apply_historical_status(
    historical_status: dict[str, Any],
    scored_status: str,
    opportunity_type: str,
    landed_cost: float | None,
    item_price: float,
    max_offer_price: float | None,
    max_landed_cost: float,
) -> str:
    status = str(historical_status.get("status") or "")
    if status in {"watching", "roi_snoozed"}:
        if should_reactivate_watched_opportunity(
            historical_status,
            scored_status,
            opportunity_type,
            landed_cost,
            item_price,
            max_offer_price,
            max_landed_cost,
        ):
            return scored_status
        return status
    return status or scored_status


def first_historical_status(
    historical_status_by_key: dict[tuple[str, str], dict[str, Any]],
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    asin = str(candidate.get("asin") or "").upper()
    for ebay_item_id in ebay_identity_values(candidate):
        status = historical_status_by_key.get((asin, ebay_item_id))
        if status:
            return status
    return None


def should_reactivate_watched_opportunity(
    historical_status: dict[str, Any],
    scored_status: str,
    opportunity_type: str,
    landed_cost: float | None,
    item_price: float,
    max_offer_price: float | None,
    max_landed_cost: float,
) -> bool:
    if scored_status != "open":
        return False

    current_purchase_cost = watch_reference_purchase_cost(opportunity_type, landed_cost, item_price, max_offer_price)
    watched_purchase_cost = nullable_float(historical_status.get("expected_purchase_cost"))
    watched_max_landed_cost = nullable_float(historical_status.get("required_max_landed_cost"))

    price_improved = (
        watched_purchase_cost is not None
        and current_purchase_cost is not None
        and current_purchase_cost < watched_purchase_cost - 0.009
    )
    sell_price_cap_improved = (
        watched_max_landed_cost is not None
        and max_landed_cost > watched_max_landed_cost + 0.009
    )
    return price_improved or sell_price_cap_improved


def watch_reference_purchase_cost(
    opportunity_type: str,
    landed_cost: float | None,
    item_price: float,
    max_offer_price: float | None,
) -> float | None:
    if opportunity_type == "best_offer" and max_offer_price is not None:
        return max_offer_price
    if landed_cost is not None:
        return landed_cost
    return item_price if item_price > 0 else None


def nullable_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = to_float(value, 0)
    return number if number > 0 else None


def best_offer_reference_price(seed: dict[str, Any], keepa_prices_by_asin: dict[str, dict[str, float | None]]) -> float | None:
    sale_price = to_float(seed.get("target_sale_price"), 0)
    return sale_price_reference(seed, keepa_prices_by_asin, sale_price)["reference_price"] or None


def sale_price_reference(
    seed: dict[str, Any],
    keepa_prices_by_asin: dict[str, dict[str, float | None]],
    seed_sale_price: float | None = None,
) -> dict[str, Any]:
    asin = str(seed.get("asin") or "").upper()
    keepa = keepa_prices_by_asin.get(asin) or {}
    seed_price = seed_sale_price if seed_sale_price is not None else to_float(seed.get("target_sale_price"), 0)
    candidates: list[tuple[str, float]] = []
    if seed_price and seed_price > 0:
        candidates.append(("seed_target_sale_price", round(seed_price, 2)))
    for source, price in (
        ("keepa_avg90_price", keepa.get("avg90_price")),
        ("keepa_current_price", keepa.get("current_price")),
    ):
        if isinstance(price, (int, float)) and price > 0:
            candidates.append((source, round(price, 2)))
    if not candidates:
        return {
            "reference_price": 0,
            "source": "none",
            "seed_target_sale_price": seed_price if seed_price and seed_price > 0 else None,
            "keepa_avg90_price": keepa.get("avg90_price"),
            "keepa_current_price": keepa.get("current_price"),
        }
    source, reference_price = min(candidates, key=lambda item: item[1])
    return {
        "reference_price": reference_price,
        "source": source,
        "seed_target_sale_price": round(seed_price, 2) if seed_price and seed_price > 0 else None,
        "keepa_avg90_price": keepa.get("avg90_price"),
        "keepa_current_price": keepa.get("current_price"),
    }


def profitability_landed_cap(sale_price: float, estimated_fees: float, settings) -> float:
    max_buy_cost = max(sale_price - estimated_fees - settings.min_profit_dollars, 0)
    max_buy_for_roi = max((sale_price - estimated_fees) / (1 + settings.min_roi_percent / 100), 0)
    return round(min(max_buy_cost, max_buy_for_roi), 2)


def conservative_fee_estimate(sale_price: float) -> float:
    return round(sale_price * 0.22 + 4.0, 2)


def advisory_flags(title: str, candidate: dict[str, Any], seed: dict[str, Any], settings) -> list[str]:
    flags = []
    shipping_status = shipping_quote_status(candidate)
    if shipping_status == "unknown_no_options":
        flags.append("Unknown shipping estimate: no ZIP shipping option returned")
    elif shipping_status == "unknown_no_cost":
        flags.append("Unknown shipping estimate: eBay returned option without price")
    if to_float(seed.get("current_inventory_units"), 0) <= 0 and to_float(seed.get("monthly_velocity"), 0) > 0:
        flags.append("Out of stock")
    if seed.get("is_suppressed"):
        flags.append("Suppressed listing")
    if seed.get("is_return_heavy"):
        flags.append("Return-heavy ASIN")
    return flags


def matching_diagnostics_for_candidate(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    matching_context: dict[str, Any],
    settings=None,
) -> dict[str, Any]:
    static_rules = evaluate_static_match_rules(
        candidate,
        seed,
        excluded_keywords=list(getattr(settings, "excluded_keywords", []) or []),
        allowed_item_location_countries=list(getattr(settings, "item_location_countries", []) or []),
    )
    asin = clean_asin(seed.get("asin") or candidate.get("asin"))
    examples_by_key = matching_context.get("examples_by_key") or {}
    examples = []
    for ebay_id in ebay_identity_values(candidate):
        examples.extend(examples_by_key.get((asin, ebay_id), []))
    exact_example_count = len(examples)
    if not examples:
        examples.extend(title_memory_examples(candidate, seed, matching_context, asin))
    examples = dedupe_examples(examples)

    positive_examples = [row for row in examples if row.get("match_label") == "match"]
    negative_examples = [
        row
        for row in examples
        if row.get("match_label") in {"non_match", "condition_problem"}
    ]
    business_examples = [
        row
        for row in examples
        if row.get("match_label") == "valid_match_poor_opportunity"
    ]
    availability_examples = [
        row
        for row in examples
        if row.get("match_label") == "availability_system"
    ]

    flags: list[str] = list(static_rules.get("flags") or [])
    score_adjustment = int(static_rules.get("score_adjustment") or 0)
    recommendation = static_rules.get("recommendation") or "Review"
    if negative_examples:
        label = negative_examples[0].get("match_label")
        reason = negative_examples[0].get("dismiss_reason") or label
        flags.append(f"Blocked: historical {label} ({reason})")
        score_adjustment -= 40
        recommendation = "Blocked"
    elif positive_examples and recommendation != "Blocked":
        flags.append("Historical positive match" if exact_example_count else "Historical positive title/system match")
        score_adjustment += 15
        recommendation = "Strong Match" if recommendation in {"Review", "Probable Match"} else recommendation
    elif business_examples and recommendation != "Blocked":
        flags.append("Historical poor opportunity")
        score_adjustment -= 8
        recommendation = "Probable Match"
    elif availability_examples and recommendation != "Blocked":
        flags.append("Historical availability issue")
        score_adjustment -= 4
        recommendation = "Review"

    seller = seller_context(candidate, matching_context)
    seller_status = seller.get("seller_status")
    seller_score = nullable_float(seller.get("seller_trust_score"))
    if seller_status == "avoid":
        flags.append(f"Seller warning: avoid ({seller.get('status_reason') or 'seller intelligence'})")
        score_adjustment -= 25
    elif seller_status == "watch":
        flags.append(f"Seller warning: watch ({seller.get('status_reason') or 'seller intelligence'})")
        score_adjustment -= 10

    return {
        "hard_rule_pass": not negative_examples and not static_rules.get("hard_blocks"),
        "static_rules": static_rules,
        "platform_rule": static_rules.get("platform_rule"),
        "title_overlap": static_rules.get("title_overlap"),
        "excluded_keywords": static_rules.get("excluded_keywords"),
        "digital_download": static_rules.get("digital_download"),
        "category": static_rules.get("category"),
        "normalized_evidence": static_rules.get("normalized_evidence"),
        "game_name": static_rules.get("game_name"),
        "numeric_identity": static_rules.get("numeric_identity"),
        "edition_version": static_rules.get("edition_version"),
        "region": static_rules.get("region"),
        "incomplete_listing": static_rules.get("incomplete_listing"),
        "not_game": static_rules.get("not_game"),
        "delivery": static_rules.get("delivery"),
        "historical_positive_count": len(positive_examples),
        "historical_negative_count": len(negative_examples),
        "historical_business_count": len(business_examples),
        "historical_availability_count": len(availability_examples),
        "historical_exact_example_count": exact_example_count,
        "historical_title_memory_count": 0 if exact_example_count else len(examples),
        "seller_status": seller_status,
        "seller_score": seller_score,
        "seller_reason": seller.get("status_reason"),
        "score_adjustment": score_adjustment,
        "recommendation": recommendation,
        "flags": flags,
    }


def title_memory_examples(
    candidate: dict[str, Any],
    seed: dict[str, Any],
    matching_context: dict[str, Any],
    asin: str | None,
) -> list[dict[str, Any]]:
    if not asin:
        return []

    candidate_key = title_memory_key(candidate.get("ebay_title"))
    if not candidate_key:
        return []

    seed_system, _ = resolve_seed_system(seed, str(seed.get("amazon_title") or ""))
    candidate_system = detect_system_from_title(str(candidate.get("ebay_title") or ""))
    examples = []
    for example in (matching_context.get("examples_by_asin") or {}).get(asin, []):
        example_key = title_memory_key(example.get("ebay_title"))
        if not example_key or example_key != candidate_key:
            continue

        example_system = normalize_system(str(example.get("amazon_system") or example.get("detected_system") or ""))
        if not systems_compatible(seed_system, candidate_system, example_system):
            continue

        examples.append(example)
    return examples


def systems_compatible(*systems: str | None) -> bool:
    known = {system for system in systems if system}
    return len(known) <= 1


def title_memory_key(value: Any) -> str | None:
    cleaned = clean_marketplace_title_for_search(str(value or ""))
    tokens = meaningful_title_tokens(cleaned)
    if not tokens:
        return None
    return " ".join(sorted(tokens))


def seller_context(candidate: dict[str, Any], matching_context: dict[str, Any]) -> dict[str, Any]:
    seller = str(candidate.get("seller_username") or "").casefold()
    if not seller:
        return {}
    return (matching_context.get("sellers") or {}).get(seller) or {}


def dedupe_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (row.get("match_label"), row.get("dismiss_reason"), row.get("created_at"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def ebay_identity_values(row: dict[str, Any]) -> list[str]:
    values = [
        row.get("ebay_item_id"),
        row.get("ebay_legacy_item_id"),
        legacy_item_id(row.get("ebay_item_id")),
    ]
    return [value for value in dict.fromkeys(clean_ebay_id(value) for value in values) if value]


def clean_asin(value: Any) -> str:
    return str(value or "").strip().upper()


def clean_ebay_id(value: Any) -> str:
    return str(value or "").strip()


def legacy_item_id(value: Any) -> str:
    text = clean_ebay_id(value)
    if text.startswith("v1|"):
        parts = text.split("|")
        return parts[1] if len(parts) > 1 else text
    return text


def has_shipping_to_buyer(candidate: dict[str, Any]) -> bool:
    return not shipping_quote_status(candidate).startswith("unknown")


def shipping_quote_status(candidate: dict[str, Any]) -> str:
    stored_shipping_cost = candidate.get("shipping_cost")
    if stored_shipping_cost is not None:
        return "known_free" if to_float(stored_shipping_cost, 0) == 0 else "known_paid"

    raw = candidate.get("raw_ebay_json") or {}
    options = raw.get("shippingOptions") or []
    if not options:
        return "unknown_no_options"
    has_option_without_cost = False
    for option in options:
        cost = option.get("shippingCost") or {}
        if cost.get("value") is not None:
            return "known_free" if to_float(cost.get("value"), 0) == 0 else "known_paid"
        has_option_without_cost = True
    return "unknown_no_cost" if has_option_without_cost else "unknown_no_options"


def classify(
    candidate,
    buying_options,
    landed_cost: float | None,
    max_profitable_landed_cost: float,
    passes: bool,
    settings,
    shipping_unknown: bool = False,
    blocked: bool = False,
) -> str:
    if blocked:
        return "no_profitable_source_found"
    if shipping_unknown:
        return "watch"
    if "AUCTION" in buying_options:
        return "auction" if landed_cost is not None and landed_cost <= max_profitable_landed_cost else "watch"
    if candidate.get("best_offer_enabled") and suggested_offer(candidate, max_profitable_landed_cost, settings) is not None:
        return "best_offer"
    if passes and int(to_float(candidate.get("available_quantity"), 1) or 1) > 1:
        return "multi_unit"
    if passes:
        return "buy_now"
    return "no_profitable_source_found"


def suggested_offer(candidate: dict[str, Any], max_profitable_landed_cost: float, settings) -> float | None:
    if not candidate.get("best_offer_enabled"):
        return None
    if shipping_quote_status(candidate).startswith("unknown"):
        return None
    item_price = to_float(candidate.get("price"), 0)
    shipping_price = to_float(candidate.get("shipping_cost"), 0)
    if item_price <= 0:
        return None
    max_item_offer = max(max_profitable_landed_cost - shipping_price, 0)
    target_offer = min(max_item_offer, item_price * 0.95)
    if target_offer >= item_price - 0.009:
        return None
    if target_offer < item_price * (settings.best_offer_min_ask_percent / 100):
        return None
    return round(target_offer, 2)


def required_offer_percent(candidate: dict[str, Any], suggested_offer_price: float | None) -> float | None:
    if shipping_quote_status(candidate).startswith("unknown"):
        return None
    if suggested_offer_price is None:
        return None
    item_price = to_float(candidate.get("price"), 0)
    if item_price <= 0:
        return None
    return round(max(suggested_offer_price / item_price, 0) * 100, 1)


def suggested_max_bid(candidate: dict[str, Any], max_profitable_landed_cost: float, shipping_unknown: bool) -> float | None:
    if shipping_unknown:
        return None
    shipping_price = to_float(candidate.get("shipping_cost"), 0)
    return round(max(max_profitable_landed_cost - shipping_price, 0), 2)


def cents_to_dollars(value: Any) -> float | None:
    if value is None or value == "":
        return None
    cents = to_float(value, -1)
    return round(cents / 100, 2) if cents >= 0 else None


def keepa_stats_cents_to_dollars(raw_keepa: Any, stats_key: str, index: int) -> float | None:
    if not isinstance(raw_keepa, dict):
        return None
    stats = raw_keepa.get("stats")
    if not isinstance(stats, dict):
        return None
    values = stats.get(stats_key)
    if not isinstance(values, list) or len(values) <= index:
        return None
    return cents_to_dollars(values[index])


def opportunity_score(seed: dict[str, Any], profit: float | None, roi: float | None, quantity: int, opportunity_type: str) -> int:
    score = NEED_POINTS.get(str(seed.get("inventory_need_level")), 0)
    score += min(int(to_float(seed.get("monthly_velocity"), 0) * 8), 30)
    score += min(int(max(profit or 0, 0) * 3), 35)
    score += min(int(max(roi or 0, 0) / 4), 25)
    score += min(max(quantity - 1, 0) * 4, 20)
    if opportunity_type == "multi_unit":
        score += 15
    elif opportunity_type == "buy_now":
        score += 10
    elif opportunity_type in {"best_offer", "auction"}:
        score += 5
    return min(score, 100)


if __name__ == "__main__":
    raise SystemExit(main())
