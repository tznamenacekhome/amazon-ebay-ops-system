"""Read-only audit of recent MBOP sourcing dismissal patterns.

This script reads sourcing evidence from Supabase and writes local audit files
only. It does not call marketplace APIs, rescore production rows, update
opportunities, or write production data.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from matching_intelligence import BUSINESS_REASONS, IDENTITY_REASONS
from sourcing_common import fetch_settings, get_supabase_client
from sourcing_match_rules import (
    edition_signals,
    evaluate_static_match_rules,
    keyword_hits,
    meaningful_title_tokens,
)


SYSTEM_REASONS = {"no_longer_available"}
CONDITION_REASONS = {"missing_shrink_wrap", "suspected_reseal", "packaging_damage", "packaging_condition_issue"}
MAIN_EXCLUDED_REASONS = SYSTEM_REASONS
DEFAULT_REPORT = Path("docs/sourcing_dismissal_pattern_audit_latest_1000_2026-08-01.md")
DEFAULT_CSV = Path("tmp/sourcing-dismissal-pattern-audit-latest-1000.csv")
CONDITION_TEXT_CLUES = {
    "case damage",
    "damaged",
    "disc sounds loose",
    "loose disc",
    "missing shrink",
    "no shrink",
    "not sealed",
    "open box",
    "reseal",
    "resealed",
    "tested works",
    "unsealed",
}

EDITION_PATTERNS: list[tuple[str, set[str]]] = [
    ("base game vs deluxe edition", {"deluxe"}),
    ("base game vs collector's edition", {"collector"}),
    ("base game vs limited edition", {"limited"}),
    ("base game vs ultimate edition", {"ultimate"}),
    ("base game vs complete/GOTY edition", {"complete", "goty", "game of the year"}),
    ("standard packaging vs Greatest Hits", {"greatest hits"}),
    ("standard packaging vs Platinum Hits", {"platinum hits"}),
    ("standard packaging vs Player's Choice", {"player's choice", "players choice"}),
    ("standard packaging vs Nintendo Selects", {"nintendo selects"}),
    ("standard packaging vs PlayStation Hits", {"playstation hits", "ps hits"}),
    ("standard packaging vs Xbox Classics", {"xbox classics", "classics"}),
    ("standard vs steelbook", {"steelbook", "steel book"}),
    ("steelbook only vs full product", {"steelbook only", "steel book only"}),
    ("bundled content difference", {"bundle", "bundled", "starter pack", "minecoins", "coins"}),
    ("included DLC/content difference", {"dlc", "season pass", "expansion", "content pack", "song pack"}),
    ("remaster/remake/original mismatch", {"remaster", "remastered", "remake"}),
    ("definitive/director's cut difference", {"definitive", "director's cut", "directors cut"}),
    ("launch/day-one edition difference", {"day one", "launch edition"}),
    ("anniversary edition difference", {"anniversary"}),
    ("season/pass/content-pack difference", {"season pass", "content pack", "pass disc"}),
    ("collection/trilogy/compilation mismatch", {"collection", "trilogy", "compilation"}),
    ("volume/episode/part mismatch", {"episode", "part", "vol", "volume"}),
]

WRONG_PRODUCT_PATTERNS: list[tuple[str, set[str]]] = [
    ("strategy guide/manual/book", {"strategy guide", "guide book", "manual only", "instruction manual", "book"}),
    ("replacement case/artwork", {"replacement case", "cover art", "artwork only", "case only", "cover insert"}),
    ("steelbook only", {"steelbook only", "empty steelbook"}),
    ("digital code/DLC/account/service", {"digital", "download", "dlc", "code", "account", "boost", "skin", "service"}),
    ("controller/peripheral", {"controller", "pedal", "cable", "drum sticks", "battery cover"}),
    ("accessory", {"accessory", "carrying case", "faceplate", "thumb grip"}),
    ("collectible/merchandise", {"plush", "figure", "poster", "sticker", "patch", "keychain", "pin", "decal"}),
    ("toy/figure/card", {"toy", "trading card", "amiibo", "power disc", "card lot"}),
    ("soundtrack/movie/non-game media", {"soundtrack", "movie", "blu-ray", "dvd"}),
    ("console/hardware", {"console", "system only", "hardware"}),
    ("compilation/collection mismatch", {"collection", "trilogy", "compilation"}),
    ("bundle containing a different game", {"bundle", "lot"}),
]

RULE_CANDIDATES = [
    {
        "name": "edition_alias_family_expansion",
        "pattern": "wrong-version edition aliases and content-pack variants",
        "fields": "title, item specifics Features/Type",
        "behavior": "probable non-match or hard block for explicit conflicting families",
        "code": "integrations/sourcing_match_rules.py: EDITION_SIGNALS / edition_rule",
        "risk": "medium",
        "tests": "Add base-vs-deluxe, GOTY, starter-pack/content-pack fixtures.",
    },
    {
        "name": "short_title_stricter_identity",
        "pattern": "short/generic titles with weak identity evidence",
        "fields": "title tokens, Game Name, platform",
        "behavior": "review flag or probable non-match",
        "code": "integrations/sourcing_match_rules.py: title_overlap_rule / game_name_rule",
        "risk": "medium",
        "tests": "Add one-word title and same-franchise wrong-game fixtures.",
    },
    {
        "name": "game_name_conflict_block",
        "pattern": "eBay item-specific Game Name conflicts with Amazon title",
        "fields": "localizedAspects.Game Name",
        "behavior": "hard block when no meaningful overlap",
        "code": "integrations/sourcing_match_rules.py: game_name_rule",
        "risk": "low/medium",
        "tests": "Add item-specific Game Name conflict fixtures.",
    },
    {
        "name": "numeric_installment_year_conflict_tuning",
        "pattern": "sequel, installment, release-year, sports-year mismatch",
        "fields": "title, Game Name, Release Year",
        "behavior": "hard block for clear conflicts; review for annual sports edge cases",
        "code": "integrations/sourcing_match_rules.py: numeric_identity_rule",
        "risk": "medium",
        "tests": "Add Just Dance, LEGO, sports-year safe/unsafe fixtures.",
    },
    {
        "name": "accessory_non_game_phrase_expansion",
        "pattern": "wrong-product accessories, guides, cases, merchandise",
        "fields": "title, category, Type/Format, description",
        "behavior": "hard block for exact non-game phrases",
        "code": "integrations/sourcing_match_rules.py: NOT_GAME_BLOCK_TERMS / category_rule",
        "risk": "low/medium",
        "tests": "Add strategy guide, empty steelbook, replacement case, merch fixtures.",
    },
]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    actions, excluded = fetch_operator_dismissals(supabase, args)
    evidence = enrich_actions(supabase, actions)
    rows = [analyze_action(action, evidence, settings) for action in actions]

    if args.reason:
        requested = {normalize_reason(value) for value in args.reason}
        rows = [row for row in rows if normalize_reason(row.get("dismiss_reason")) in requested]
    if args.rule_miss_class:
        requested = {normalize_filter_value(value) for value in args.rule_miss_class}
        rows = [row for row in rows if normalize_filter_value(row.get("rule_miss_class")) in requested]
    if args.action_id:
        requested = {str(value) for value in args.action_id}
        rows = [row for row in rows if str(row.get("action_id")) in requested]
    if args.opportunity_id:
        requested = {str(value) for value in args.opportunity_id}
        rows = [row for row in rows if str(row.get("opportunity_id")) in requested]
    if args.candidate_id:
        requested = {str(value) for value in args.candidate_id}
        rows = [row for row in rows if str(row.get("candidate_id")) in requested]

    summary = build_summary(rows, excluded, args.limit)
    write_csv(args.csv, rows)
    if args.json:
        write_json(args.json, {"summary": summary, "rows": rows})
    write_report(args.report, rows, summary)
    print_console_summary(summary, args.report, args.csv)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only audit of recent sourcing dismissals.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--since-days", type=int)
    parser.add_argument("--reason", action="append", help="Limit analysis to one or more dismiss reasons.")
    parser.add_argument("--rule-miss-class", action="append", help="Limit rows to one or more rule miss classifications.")
    parser.add_argument("--action-id", action="append", help="Limit rows to one or more sourcing action IDs.")
    parser.add_argument("--opportunity-id", action="append", help="Limit rows to one or more sourcing opportunity IDs.")
    parser.add_argument("--candidate-id", action="append", help="Limit rows to one or more sourcing candidate IDs.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fetch-multiplier", type=int, default=4)
    return parser.parse_args()


def fetch_operator_dismissals(supabase, args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=args.since_days) if args.since_days else None
    page_size = 1000
    start = 0
    max_scan = max(args.limit * max(args.fetch_multiplier, 1), args.limit)
    while len(rows) < args.limit and start < max_scan:
        end = start + page_size - 1
        query = (
            supabase.table("sourcing_actions")
            .select("*")
            .eq("action_type", "dismissed")
            .order("created_at", desc=True)
            .range(start, end)
        )
        if since:
            query = query.gte("created_at", since.isoformat())
        response = query.execute()
        batch = response.data or []
        if not batch:
            break
        for action in batch:
            if is_system_action(action):
                excluded.append(action)
                continue
            rows.append(action)
            if len(rows) >= args.limit:
                break
        if len(batch) < page_size:
            break
        start += page_size
    return rows[: args.limit], excluded


def is_system_action(action: dict[str, Any]) -> bool:
    reason = normalize_reason(action.get("dismiss_reason"))
    if reason in MAIN_EXCLUDED_REASONS:
        return True
    context = action.get("raw_action_context")
    if isinstance(context, dict):
        source = " ".join(str(context.get(key) or "") for key in ("source", "actionType", "job", "reason")).casefold()
        if "availability" in source or "refresh" in source:
            return True
    return False


def enrich_actions(supabase, actions: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    opportunity_ids = ids(actions, "opportunity_id")
    candidate_ids = ids(actions, "candidate_id")
    action_ids = ids(actions, "action_id")

    opportunities = fetch_by_ids(
        supabase,
        "sourcing_opportunities",
        "opportunity_id",
        opportunity_ids,
        "*,sourcing_seed_asins(*),sourcing_ebay_candidates(*)",
    )
    for row in opportunities.values():
        if row.get("candidate_id"):
            candidate_ids.append(row["candidate_id"])
    candidates = fetch_by_ids(supabase, "sourcing_ebay_candidates", "candidate_id", candidate_ids, "*")
    seed_ids = [row.get("seed_id") for row in opportunities.values()] + [row.get("seed_id") for row in candidates.values()]
    seeds = fetch_by_ids(supabase, "sourcing_seed_asins", "seed_id", seed_ids, "*")
    snapshots_by_action = fetch_latest_by_key(
        supabase,
        "sourcing_listing_snapshots",
        "action_id",
        action_ids,
        "*",
        "captured_at",
    )
    examples_by_action = fetch_latest_by_key(
        supabase,
        "matching_intelligence_examples",
        "action_id",
        action_ids,
        "*",
        "created_at",
    )
    run_ids = ids(list(opportunities.values()) + list(candidates.values()) + list(snapshots_by_action.values()), "sourcing_run_id")
    runs = fetch_by_ids(supabase, "sourcing_runs", "sourcing_run_id", run_ids, "*")
    batch_items_by_opportunity = fetch_latest_by_key(
        supabase,
        "sourcing_opportunity_batch_items",
        "opportunity_id",
        opportunity_ids,
        "*",
        "created_at",
    )
    batch_ids = ids(list(batch_items_by_opportunity.values()), "batch_id")
    batches = fetch_by_ids(supabase, "sourcing_opportunity_batches", "batch_id", batch_ids, "*")
    return {
        "opportunities": opportunities,
        "candidates": candidates,
        "seeds": seeds,
        "snapshots_by_action": snapshots_by_action,
        "examples_by_action": examples_by_action,
        "runs": runs,
        "batch_items_by_opportunity": batch_items_by_opportunity,
        "batches": batches,
    }


def fetch_by_ids(
    supabase,
    table: str,
    key: str,
    values: list[Any],
    columns: str,
) -> dict[str, dict[str, Any]]:
    unique = sorted({str(value) for value in values if value})
    output: dict[str, dict[str, Any]] = {}
    for chunk in chunks(unique, 100):
        response = supabase.table(table).select(columns).in_(key, chunk).execute()
        for row in response.data or []:
            if row.get(key):
                output[str(row[key])] = row
    return output


def fetch_latest_by_key(
    supabase,
    table: str,
    key: str,
    values: list[Any],
    columns: str,
    order_column: str,
) -> dict[str, dict[str, Any]]:
    unique = sorted({str(value) for value in values if value})
    output: dict[str, dict[str, Any]] = {}
    for chunk in chunks(unique, 100):
        response = (
            supabase.table(table)
            .select(columns)
            .in_(key, chunk)
            .order(order_column, desc=True)
            .execute()
        )
        for row in response.data or []:
            value = str(row.get(key) or "")
            if value and value not in output:
                output[value] = row
    return output


def analyze_action(action: dict[str, Any], evidence: dict[str, dict[str, dict[str, Any]]], settings) -> dict[str, Any]:
    opportunity = evidence["opportunities"].get(str(action.get("opportunity_id") or "")) or {}
    candidate = opportunity.get("sourcing_ebay_candidates") or evidence["candidates"].get(str(action.get("candidate_id") or opportunity.get("candidate_id") or "")) or {}
    seed = opportunity.get("sourcing_seed_asins") or evidence["seeds"].get(str(opportunity.get("seed_id") or candidate.get("seed_id") or "")) or {}
    snapshot = evidence["snapshots_by_action"].get(str(action.get("action_id") or "")) or {}
    example = evidence["examples_by_action"].get(str(action.get("action_id") or "")) or {}
    batch_item = evidence["batch_items_by_opportunity"].get(str(action.get("opportunity_id") or "")) or {}
    batch = evidence["batches"].get(str(batch_item.get("batch_id") or "")) or {}
    candidate_for_rules = merge_candidate(candidate, snapshot, action)
    seed_for_rules = merge_seed(seed, snapshot, action)
    diagnostics = evaluate_static_match_rules(
        candidate_for_rules,
        seed_for_rules,
        excluded_keywords=settings.excluded_keywords,
        allowed_item_location_countries=settings.item_location_countries,
    )
    stored_diagnostics = opportunity.get("matching_diagnostics_json") if isinstance(opportunity.get("matching_diagnostics_json"), dict) else {}
    fields = extracted_fields(candidate_for_rules, snapshot)
    pattern = classify_pattern(action, seed_for_rules, candidate_for_rules, fields)
    rule_class = classify_rule_miss(action, diagnostics, stored_diagnostics, fields)
    dependency = classify_dependency(action, diagnostics, fields)
    notes = str(action.get("notes") or "").strip()
    return {
        "rank": None,
        "action_id": action.get("action_id"),
        "action_date": action.get("created_at"),
        "dismiss_reason": normalize_reason(action.get("dismiss_reason")),
        "dismissal_note": notes,
        "asin": action.get("asin") or opportunity.get("asin") or candidate.get("asin") or seed.get("asin") or snapshot.get("asin"),
        "amazon_title": seed_for_rules.get("amazon_title"),
        "amazon_system": seed_for_rules.get("system") or snapshot.get("amazon_system"),
        "amazon_image_url": seed_for_rules.get("amazon_image_url") or snapshot.get("amazon_image_url"),
        "ebay_item_id": action.get("ebay_item_id") or candidate_for_rules.get("ebay_item_id") or snapshot.get("ebay_item_id"),
        "ebay_title": candidate_for_rules.get("ebay_title"),
        "ebay_description_present": bool(fields["description"]),
        "ebay_condition": candidate_for_rules.get("condition") or snapshot.get("ebay_condition"),
        "item_location_country": candidate_for_rules.get("item_location_country") or snapshot.get("item_location_country"),
        "ebay_category": "; ".join(fields["category_names"]),
        "ebay_category_ids": "; ".join(fields["category_ids"]),
        "ebay_primary_image_url": fields["primary_image_url"],
        "additional_image_count": max(len(fields["image_urls"]) - 1, 0),
        "item_specifics_present": bool(fields["aspects"]),
        "detected_ebay_platform": ", ".join((diagnostics.get("platform_rule") or {}).get("candidate_systems") or []),
        "game_name": "; ".join(fields["game_name_values"]),
        "region_code": "; ".join(fields["region_code_values"] + fields["country_of_origin_values"]),
        "format": "; ".join(fields["format_values"]),
        "type": "; ".join(fields["type_values"]),
        "features": "; ".join(fields["features_values"]),
        "release_year": "; ".join(fields["release_year_values"]),
        "stored_recommendation": nested(stored_diagnostics, "static_rules", "recommendation") or stored_diagnostics.get("recommendation"),
        "current_recommendation": diagnostics.get("recommendation"),
        "current_hard_blocks": "; ".join(diagnostics.get("hard_blocks") or []),
        "current_warnings": "; ".join(diagnostics.get("warnings") or []),
        "presentation_hard_blocks": "; ".join(nested(stored_diagnostics, "static_rules", "hard_blocks") or stored_diagnostics.get("hard_blocks") or []),
        "presentation_warnings": "; ".join(nested(stored_diagnostics, "static_rules", "warnings") or stored_diagnostics.get("warnings") or []),
        "source_run_id": opportunity.get("sourcing_run_id") or candidate.get("sourcing_run_id") or snapshot.get("sourcing_run_id"),
        "run_created_at": (evidence["runs"].get(str(opportunity.get("sourcing_run_id") or candidate.get("sourcing_run_id") or snapshot.get("sourcing_run_id") or "")) or {}).get("created_at"),
        "opportunity_status": opportunity.get("status"),
        "opportunity_type": opportunity.get("opportunity_type"),
        "opportunity_created_at": opportunity.get("created_at"),
        "opportunity_updated_at": opportunity.get("updated_at"),
        "batch_id": batch_item.get("batch_id"),
        "batch_sequence": batch.get("batch_sequence"),
        "batch_status": batch.get("status"),
        "batch_created_at": batch.get("started_at") or batch_item.get("created_at"),
        "seller_username": candidate.get("seller_username") or snapshot.get("seller_username") or example.get("ebay_seller_username"),
        "source_table": "sourcing_actions",
        "opportunity_id": action.get("opportunity_id"),
        "candidate_id": action.get("candidate_id") or opportunity.get("candidate_id"),
        "snapshot_id": snapshot.get("listing_snapshot_id"),
        "matching_example_id": example.get("matching_intelligence_example_id"),
        "pattern": pattern,
        "rule_miss_class": rule_class,
        "evidence_dependency": dependency,
        "title_only_detectable": dependency == "title_only",
        "details_needed": dependency in {"title_plus_item_specifics_or_category", "description"},
        "image_dependent": dependency == "image_or_operator_visual_review",
    }


def merge_candidate(candidate: dict[str, Any], snapshot: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    raw = candidate.get("raw_ebay_json")
    if not raw and snapshot.get("raw_ebay_json"):
        raw = snapshot.get("raw_ebay_json")
    return {
        **candidate,
        "asin": candidate.get("asin") or snapshot.get("asin") or action.get("asin"),
        "ebay_item_id": candidate.get("ebay_item_id") or snapshot.get("ebay_item_id") or action.get("ebay_item_id"),
        "ebay_legacy_item_id": candidate.get("ebay_legacy_item_id") or snapshot.get("ebay_legacy_item_id"),
        "ebay_title": candidate.get("ebay_title") or snapshot.get("ebay_title"),
        "condition": candidate.get("condition") or snapshot.get("ebay_condition"),
        "ebay_image_url": candidate.get("ebay_image_url") or snapshot.get("ebay_primary_image_url"),
        "seller_username": candidate.get("seller_username") or snapshot.get("seller_username"),
        "item_location_country": candidate.get("item_location_country") or snapshot.get("item_location_country"),
        "raw_ebay_json": raw or raw_from_snapshot(snapshot),
    }


def merge_seed(seed: dict[str, Any], snapshot: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    return {
        **seed,
        "asin": seed.get("asin") or snapshot.get("asin") or action.get("asin"),
        "amazon_title": seed.get("amazon_title") or snapshot.get("amazon_title"),
        "amazon_image_url": seed.get("amazon_image_url") or snapshot.get("amazon_image_url"),
        "system": seed.get("system") or snapshot.get("amazon_system"),
    }


def raw_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if snapshot.get("ebay_item_specifics_json"):
        raw["localizedAspects"] = snapshot.get("ebay_item_specifics_json")
    if snapshot.get("ebay_description"):
        raw["description"] = snapshot.get("ebay_description")
    categories = []
    if snapshot.get("ebay_category") or snapshot.get("ebay_category_id"):
        categories.append(
            {
                "categoryName": snapshot.get("ebay_category"),
                "categoryId": snapshot.get("ebay_category_id"),
            }
        )
    if categories:
        raw["categories"] = categories
    if snapshot.get("ebay_primary_image_url"):
        raw["image"] = {"imageUrl": snapshot.get("ebay_primary_image_url")}
    if snapshot.get("ebay_image_urls"):
        raw["additionalImages"] = [{"imageUrl": url} for url in snapshot.get("ebay_image_urls") or []]
    return raw


def extracted_fields(candidate: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    diagnostics = evaluate_static_match_rules(candidate, {"amazon_title": ""})
    evidence = diagnostics.get("normalized_evidence") or {}
    return {
        "title": candidate.get("ebay_title") or snapshot.get("ebay_title"),
        "aspects": evidence.get("aspects") or {},
        "category_ids": evidence.get("category_ids") or ([] if not snapshot.get("ebay_category_id") else [str(snapshot.get("ebay_category_id"))]),
        "category_names": evidence.get("category_names") or ([] if not snapshot.get("ebay_category") else [str(snapshot.get("ebay_category"))]),
        "game_name_values": evidence.get("game_name_values") or [],
        "region_code_values": evidence.get("region_code_values") or [],
        "country_of_origin_values": evidence.get("country_of_origin_values") or [],
        "format_values": evidence.get("format_values") or [],
        "type_values": evidence.get("type_values") or [],
        "features_values": evidence.get("features_values") or [],
        "release_year_values": evidence.get("release_year_values") or [],
        "description": evidence.get("description") or snapshot.get("ebay_description"),
        "primary_image_url": evidence.get("primary_image_url") or snapshot.get("ebay_primary_image_url"),
        "image_urls": evidence.get("image_urls") or snapshot.get("ebay_image_urls") or [],
    }


def classify_pattern(
    action: dict[str, Any],
    seed: dict[str, Any],
    candidate: dict[str, Any],
    fields: dict[str, Any],
) -> str:
    reason = normalize_reason(action.get("dismiss_reason"))
    amazon_title = str(seed.get("amazon_title") or "")
    ebay_title = str(candidate.get("ebay_title") or "")
    text = " ".join(
        [
            amazon_title,
            ebay_title,
            " ".join(fields["features_values"]),
            " ".join(fields["type_values"]),
            " ".join(fields["game_name_values"]),
            str(action.get("notes") or ""),
        ]
    ).casefold()
    if reason == "wrong_edition_version":
        numbers = number_conflict(amazon_title, ebay_title, fields)
        if numbers:
            return numbers
        if fields["game_name_values"] and game_name_or_subtitle_conflict(
            amazon_title,
            fields["game_name_values"],
        ):
            return "item-specific Game Name or Edition conflict"
        for label, terms in EDITION_PATTERNS:
            if any(term in text for term in terms):
                return label
        if year_conflict(amazon_title, ebay_title, fields):
            return "release-year mismatch"
        return "unclear/insufficient evidence"
    if reason == "wrong_product":
        if fields["game_name_values"] and game_name_or_subtitle_conflict(
            amazon_title,
            fields["game_name_values"],
        ):
            return "eBay item-specific Game Name conflict"
        numbers = number_conflict(amazon_title, ebay_title, fields)
        if numbers:
            return "wrong numbered installment"
        for label, terms in WRONG_PRODUCT_PATTERNS:
            if any(term in text for term in terms):
                return label
        amazon_tokens = meaningful_title_tokens(amazon_title)
        ebay_tokens = meaningful_title_tokens(ebay_title)
        if len(amazon_tokens) <= 2:
            return "title ambiguity from a short/generic game name"
        if amazon_tokens and ebay_tokens and not amazon_tokens & ebay_tokens:
            return "entirely different game with similar words"
        return "unclear/insufficient evidence"
    return reason or "unknown"


def classify_rule_miss(
    action: dict[str, Any],
    diagnostics: dict[str, Any],
    stored: dict[str, Any],
    fields: dict[str, Any],
) -> str:
    reason = normalize_reason(action.get("dismiss_reason"))
    if reason not in IDENTITY_REASONS | CONDITION_REASONS:
        return "operator dismissal may be ambiguous or business/system"
    current_blocks = diagnostics.get("hard_blocks") or []
    current_warnings = diagnostics.get("warnings") or []
    if current_blocks:
        return "current rule should already block"
    if current_warnings or diagnostics.get("recommendation") in {"Review", "Probable Non-Match"}:
        return "current rule produces review/probable non-match"
    if fields["description"] and not nested(stored, "normalized_evidence", "description"):
        return "evidence unavailable before detail but available afterward"
    if reason in CONDITION_REASONS and fields["primary_image_url"]:
        return "evidence exists only in images"
    if reason in {"other"}:
        return "operator dismissal may be ambiguous or incorrectly categorized"
    return "no current deterministic rule covers pattern"


def classify_dependency(action: dict[str, Any], diagnostics: dict[str, Any], fields: dict[str, Any]) -> str:
    reason = normalize_reason(action.get("dismiss_reason"))
    hard_and_warn = " ".join((diagnostics.get("hard_blocks") or []) + (diagnostics.get("warnings") or [])).casefold()
    title_text = str(fields.get("title") or "").casefold()
    description_text = str(fields.get("description") or "").casefold()
    if reason in CONDITION_REASONS:
        if any(clue in title_text for clue in CONDITION_TEXT_CLUES):
            return "title_only"
        if any(clue in description_text for clue in CONDITION_TEXT_CLUES):
            return "description"
        return "image_or_operator_visual_review"
    if any(token in hard_and_warn for token in ["title token", "numeric", "edition/version", "digital", "incomplete", "accessory/not game", "non-north"]):
        return "title_only"
    if any(token in hard_and_warn for token in ["platform mismatch", "game name", "category"]):
        return "title_plus_item_specifics_or_category"
    if fields["aspects"] or fields["category_ids"] or fields["category_names"]:
        return "title_plus_item_specifics_or_category"
    if fields["description"]:
        return "description"
    return "unclear"


def build_summary(rows: list[dict[str, Any]], excluded: list[dict[str, Any]], requested: int) -> dict[str, Any]:
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    identity_rows = [row for row in rows if row["dismiss_reason"] in IDENTITY_REASONS]
    product_condition_rows = [
        row for row in rows if row["dismiss_reason"] in IDENTITY_REASONS | CONDITION_REASONS
    ]
    wrong_version = [row for row in rows if row["dismiss_reason"] == "wrong_edition_version"]
    wrong_product = [row for row in rows if row["dismiss_reason"] == "wrong_product"]
    dates = [row["action_date"] for row in rows if row.get("action_date")]
    summary = {
        "requested": requested,
        "operator_dismissals": len(rows),
        "excluded_system_actions": len(excluded),
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
        "complete_titles": sum(1 for row in rows if row.get("amazon_title") and row.get("ebay_title")),
        "with_notes": sum(1 for row in rows if row.get("dismissal_note")),
        "with_snapshots": sum(1 for row in rows if row.get("snapshot_id")),
        "with_item_specifics": sum(1 for row in rows if row.get("item_specifics_present")),
        "with_descriptions": sum(1 for row in rows if row.get("ebay_description_present")),
        "with_primary_images": sum(1 for row in rows if row.get("ebay_primary_image_url")),
        "with_additional_images": sum(1 for row in rows if row.get("additional_image_count", 0) > 0),
        "with_matching_diagnostics": sum(1 for row in rows if row.get("stored_recommendation") or row.get("presentation_hard_blocks") or row.get("presentation_warnings")),
        "reason_counts": Counter(row["dismiss_reason"] or "unknown" for row in rows),
        "reason_windows": {
            "1-100": Counter(row["dismiss_reason"] or "unknown" for row in rows[:100]),
            "101-500": Counter(row["dismiss_reason"] or "unknown" for row in rows[100:500]),
            "501-1000": Counter(row["dismiss_reason"] or "unknown" for row in rows[500:1000]),
        },
        "wrong_version_patterns": Counter(row["pattern"] for row in wrong_version),
        "wrong_product_patterns": Counter(row["pattern"] for row in wrong_product),
        "rule_miss_counts": Counter(row["rule_miss_class"] for row in identity_rows),
        "dependency_counts": Counter(row["evidence_dependency"] for row in product_condition_rows),
        "identity_dependency_counts": Counter(row["evidence_dependency"] for row in identity_rows),
        "note_terms": note_terms(rows),
        "identity_count": len(identity_rows),
        "product_condition_count": len(product_condition_rows),
        "wrong_version_count": len(wrong_version),
        "wrong_product_count": len(wrong_product),
    }
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "action_id",
        "action_date",
        "dismiss_reason",
        "dismissal_note",
        "asin",
        "amazon_title",
        "amazon_system",
        "ebay_item_id",
        "ebay_title",
        "ebay_condition",
        "item_location_country",
        "ebay_category",
        "ebay_category_ids",
        "seller_username",
        "detected_ebay_platform",
        "game_name",
        "region_code",
        "format",
        "type",
        "features",
        "release_year",
        "stored_recommendation",
        "current_recommendation",
        "current_hard_blocks",
        "current_warnings",
        "presentation_hard_blocks",
        "presentation_warnings",
        "pattern",
        "rule_miss_class",
        "evidence_dependency",
        "source_run_id",
        "run_created_at",
        "opportunity_status",
        "opportunity_type",
        "opportunity_created_at",
        "opportunity_updated_at",
        "batch_id",
        "batch_sequence",
        "batch_status",
        "batch_created_at",
        "opportunity_id",
        "candidate_id",
        "snapshot_id",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2), encoding="utf-8")


def write_report(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    add = lines.append
    add("# Sourcing Dismissal Pattern Audit - Latest 1,000")
    add("")
    add("Date: 2026-08-01")
    add("")
    add("Scope: read-only analysis of the most recent operator-created MBOP sourcing dismissals. No production data, matching rules, opportunity statuses, schema, settings, or action history were modified.")
    add("")
    section_dataset(lines, summary)
    section_reason_distribution(lines, summary)
    section_patterns(lines, "Wrong Edition / Version Analysis", "wrong_edition_version", summary["wrong_version_patterns"], rows)
    section_patterns(lines, "Wrong Product Analysis", "wrong_product", summary["wrong_product_patterns"], rows)
    section_rule_miss(lines, summary, rows)
    section_notes(lines, summary, rows)
    section_dependency(lines, summary)
    section_rule_candidates(lines, summary, rows)
    section_memory(lines, rows)
    section_next_sprint(lines, summary)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def section_dataset(lines: list[str], summary: dict[str, Any]) -> None:
    add = lines.append
    add("## Section 1 - Dataset Integrity")
    add("")
    table(
        lines,
        ["Metric", "Value"],
        [
            ["Total actions requested", summary["requested"]],
            ["Operator dismissals analyzed", summary["operator_dismissals"]],
            ["Date range", f"{summary['date_start']} to {summary['date_end']}"],
            ["Excluded system/availability actions", summary["excluded_system_actions"]],
            ["Complete Amazon and eBay titles", summary["complete_titles"]],
            ["With notes", summary["with_notes"]],
            ["With snapshots", summary["with_snapshots"]],
            ["With item specifics", summary["with_item_specifics"]],
            ["With descriptions", summary["with_descriptions"]],
            ["With primary images", summary["with_primary_images"]],
            ["With additional images", summary["with_additional_images"]],
            ["With stored matching diagnostics", summary["with_matching_diagnostics"]],
        ],
    )
    add("")
    add("Limitations: this audit uses stored sourcing action, candidate, snapshot, opportunity, and matching-intelligence evidence. It does not call eBay/Amazon/Keepa, does not inspect images with AI, and cannot prove what was visually obvious to the operator unless a textual note or stored metadata records it.")
    add("")


def section_reason_distribution(lines: list[str], summary: dict[str, Any]) -> None:
    add = lines.append
    add("## Section 2 - Dismissal Reason Distribution")
    add("")
    rows = []
    total = max(summary["operator_dismissals"], 1)
    for reason, count in summary["reason_counts"].most_common():
        rows.append([reason, count, pct(count, total)])
    table(lines, ["Reason", "Count", "Pct"], rows)
    add("")
    add("### Recency Windows")
    add("")
    for window, counter in summary["reason_windows"].items():
        add(f"#### {window}")
        window_total = sum(counter.values()) or 1
        table(lines, ["Reason", "Count", "Pct"], [[k, v, pct(v, window_total)] for k, v in counter.most_common()])
        add("")


def section_patterns(lines: list[str], title: str, reason: str, counter: Counter, rows: list[dict[str, Any]]) -> None:
    add = lines.append
    add(f"## Section {'3' if reason == 'wrong_edition_version' else '4'} - {title}")
    add("")
    total = sum(counter.values()) or 1
    table(lines, ["Pattern", "Count", "Pct"], [[k, v, pct(v, total)] for k, v in counter.most_common()])
    add("")
    add("Representative examples:")
    add("")
    for pattern, _ in counter.most_common(12):
        examples = [row for row in rows if row["dismiss_reason"] == reason and row["pattern"] == pattern][:3]
        if not examples:
            continue
        add(f"- {pattern}")
        for row in examples:
            add(f"  - Amazon: {clean_md(row.get('amazon_title'))}")
            add(f"    eBay: {clean_md(row.get('ebay_title'))}")
            add(f"    Evidence: Game Name={clean_md(row.get('game_name') or '--')}; category={clean_md(row.get('ebay_category') or '--')}; current rules={clean_md(row.get('current_hard_blocks') or row.get('current_warnings') or row.get('current_recommendation'))}")
    add("")


def section_rule_miss(lines: list[str], summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    add = lines.append
    add("## Section 5 - Existing Rule Miss Analysis")
    add("")
    total = sum(summary["rule_miss_counts"].values()) or 1
    table(lines, ["Classification", "Count", "Pct"], [[k, v, pct(v, total)] for k, v in summary["rule_miss_counts"].most_common()])
    add("")
    rule_hits = Counter()
    for row in rows:
        for value in str(row.get("current_hard_blocks") or "").split(";"):
            value = value.strip()
            if value:
                rule_hits[value] += 1
    add("Top current hard-block signals among dismissed identity examples:")
    add("")
    table(lines, ["Signal", "Count"], rule_hits.most_common(15))
    add("")


def section_notes(lines: list[str], summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    add = lines.append
    add("## Section 6 - Notes Analysis")
    add("")
    add(f"Rows with notes: {summary['with_notes']} of {summary['operator_dismissals']}.")
    add("")
    table(lines, ["Recurring note term", "Count"], summary["note_terms"].most_common(25))
    add("")
    inconsistent = [
        row
        for row in rows
        if row.get("dismissal_note")
        and row.get("dismiss_reason") in {"wrong_product", "wrong_edition_version"}
        and any(term in str(row.get("dismissal_note")).casefold() for term in ["shrink", "damage", "reseal"])
    ][:10]
    if inconsistent:
        add("Possible reason/note inconsistencies:")
        add("")
        for row in inconsistent:
            add(f"- {row['dismiss_reason']} | {clean_md(row['dismissal_note'])} | {clean_md(row['ebay_title'])}")
        add("")
    add("No new structured dismissal reason is recommended unless operator review confirms a recurring distinction that cannot be expressed by the existing identity/condition split.")
    add("")


def section_dependency(lines: list[str], summary: dict[str, Any]) -> None:
    add = lines.append
    add("## Section 7 - Image and Description Dependency")
    add("")
    total = sum(summary["dependency_counts"].values()) or 1
    table(lines, ["Evidence dependency", "Count", "Pct"], [[k, v, pct(v, total)] for k, v in summary["dependency_counts"].most_common()])
    add("")
    add("Image-dependent rows are inferred from condition/packaging dismissals or insufficient textual metadata. No image AI was used.")
    add("")


def section_rule_candidates(lines: list[str], summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    add = lines.append
    add("## Section 8 - Deterministic Rule Candidates")
    add("")
    identity_total = max(summary["identity_count"], 1)
    pattern_counts = summary["wrong_version_patterns"] + summary["wrong_product_patterns"]
    table_rows = []
    for candidate in RULE_CANDIDATES:
        observed = candidate_observed_count(candidate["pattern"], pattern_counts)
        table_rows.append(
            [
                candidate["name"],
                candidate["pattern"],
                observed,
                pct(observed, identity_total),
                candidate["fields"],
                candidate["behavior"],
                candidate["risk"],
                candidate["code"],
                candidate["tests"],
            ]
        )
    table(
        lines,
        ["Rule", "Pattern", "Observed", "Pct Identity", "Fields", "Behavior", "Risk", "Code", "Tests"],
        sorted(table_rows, key=lambda row: row[2], reverse=True),
    )
    add("")


def section_memory(lines: list[str], rows: list[dict[str, Any]]) -> None:
    add = lines.append
    add("## Section 9 - Historical Memory Effectiveness")
    add("")
    ebay_counts = Counter(row["ebay_item_id"] for row in rows if row.get("ebay_item_id"))
    pair_counts = Counter((row.get("asin"), normalize_title(row.get("ebay_title"))) for row in rows if row.get("asin") and row.get("ebay_title"))
    seller_pair_counts = Counter((row.get("seller_username"), row.get("asin"), normalize_title(row.get("ebay_title"))) for row in rows if row.get("seller_username") and row.get("asin") and row.get("ebay_title"))
    table(lines, ["Repeated eBay item ID", "Count"], [[k, v] for k, v in ebay_counts.most_common(10) if v > 1])
    add("")
    table(lines, ["Repeated ASIN/title pair", "Count"], [[f"{k[0]} | {k[1]}", v] for k, v in pair_counts.most_common(10) if v > 1])
    add("")
    table(lines, ["Repeated seller/ASIN/title", "Count"], [[f"{k[0]} | {k[1]} | {k[2]}", v] for k, v in seller_pair_counts.most_common(10) if v > 1])
    add("")
    add("Business dismissals were kept separate from identity analysis in this report, preserving the current rule that business reasons should not poison identity matching.")
    add("")


def section_next_sprint(lines: list[str], summary: dict[str, Any]) -> None:
    add = lines.append
    add("## Section 10 - Recommended Next Sprint")
    add("")
    identity_total = max(summary["identity_count"], 1)
    top_candidates = RULE_CANDIDATES[:5]
    expected = sum(candidate_observed_count(candidate["pattern"], summary["wrong_version_patterns"] + summary["wrong_product_patterns"]) for candidate in top_candidates)
    add(f"Expected directly addressable share from the top five conservative rule candidates: about {pct(expected, identity_total)} of identity dismissals, before overlap adjustment.")
    add("")
    add("Recommended sprint:")
    add("")
    add("1. Add focused regression fixtures from this report for wrong-version and wrong-product rows.")
    add("2. Tune edition/content-pack aliases and short-title identity review without hard-blocking single ambiguous edition words.")
    add("3. Strengthen item-specific Game Name and numeric conflict handling where stored evidence is explicit.")
    add("4. Expand exact accessory/non-game phrase tests only for low-risk terms.")
    add("5. Dry-run against recent opportunities, inspect potential false positives, then rescore only after operator approval.")
    add("")
    add("Rollback strategy: keep changes in deterministic rule code behind tests, dry-run before write, and do not change historical actions or business dismissals.")
    add("")


def print_console_summary(summary: dict[str, Any], report: Path, csv_path: Path) -> None:
    print("Recent sourcing dismissal audit")
    print("--------------------------------")
    print(f"Operator dismissals analyzed: {summary['operator_dismissals']}")
    print(f"Date range: {summary['date_start']} to {summary['date_end']}")
    print(f"Excluded system/availability actions: {summary['excluded_system_actions']}")
    print(f"Top reasons: {dict(summary['reason_counts'].most_common(8))}")
    print(f"Top wrong-version patterns: {dict(summary['wrong_version_patterns'].most_common(5))}")
    print(f"Top wrong-product patterns: {dict(summary['wrong_product_patterns'].most_common(5))}")
    print(f"Evidence dependency: {dict(summary['dependency_counts'])}")
    print(f"Report: {report}")
    print(f"CSV: {csv_path}")


def table(lines: list[str], headers: list[str], rows: list[Any]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        values = row if isinstance(row, (list, tuple)) else list(row)
        lines.append("| " + " | ".join(clean_md(value) for value in values) + " |")


def note_terms(rows: list[dict[str, Any]]) -> Counter:
    stop = {"the", "and", "for", "with", "this", "that", "not", "new", "sealed", "game", "item"}
    counter: Counter = Counter()
    for row in rows:
        note = str(row.get("dismissal_note") or "").casefold()
        for token in re.findall(r"[a-z0-9][a-z0-9-]+", note):
            if len(token) > 2 and token not in stop:
                counter[token] += 1
    return counter


def candidate_observed_count(pattern_text: str, counter: Counter) -> int:
    words = {word for word in re.findall(r"[a-z0-9]+", pattern_text.casefold()) if len(word) > 3}
    total = 0
    for pattern, count in counter.items():
        pattern_words = set(re.findall(r"[a-z0-9]+", str(pattern).casefold()))
        if words & pattern_words:
            total += count
    return total


def number_conflict(amazon_title: str, ebay_title: str, fields: dict[str, Any]) -> str | None:
    text = " ".join([ebay_title, " ".join(fields.get("game_name_values") or [])])
    amazon_numbers = set(re.findall(r"(?<![0-9])(?:19|20)\d{2}|(?<![a-z0-9])[2-9][0-9]?(?![a-z0-9])", amazon_title.casefold()))
    ebay_numbers = set(re.findall(r"(?<![0-9])(?:19|20)\d{2}|(?<![a-z0-9])[2-9][0-9]?(?![a-z0-9])", text.casefold()))
    if amazon_numbers and ebay_numbers and amazon_numbers.isdisjoint(ebay_numbers):
        return "console generation/version mismatch" if platform_generation_text(text) else "release-year mismatch"
    return None


def year_conflict(amazon_title: str, ebay_title: str, fields: dict[str, Any]) -> bool:
    amazon_years = set(re.findall(r"(?:19|20)\d{2}", amazon_title))
    candidate_years = set(re.findall(r"(?:19|20)\d{2}", " ".join([ebay_title, " ".join(fields.get("release_year_values") or [])])))
    return bool(amazon_years and candidate_years and amazon_years.isdisjoint(candidate_years))


def platform_generation_text(text: str) -> bool:
    return any(token in text.casefold() for token in ["series x", "series s", "xbox one", "ps4", "ps5", "3ds", "ds"])


def game_name_conflict(amazon_title: str, game_names: list[str]) -> bool:
    amazon_tokens = meaningful_title_tokens(amazon_title)
    for game_name in game_names:
        game_tokens = meaningful_title_tokens(game_name)
        if amazon_tokens and game_tokens and not amazon_tokens & game_tokens:
            return True
    return False


def game_name_or_subtitle_conflict(amazon_title: str, game_names: list[str]) -> bool:
    amazon_tokens = meaningful_title_tokens(amazon_title)
    for game_name in game_names:
        game_tokens = meaningful_title_tokens(game_name)
        if not amazon_tokens or not game_tokens:
            continue
        shared = amazon_tokens & game_tokens
        if not shared:
            return True
        if game_tokens - amazon_tokens:
            return True
    return False


def normalize_reason(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_filter_value(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def normalize_title(value: Any) -> str:
    return " ".join(sorted(meaningful_title_tokens(value)))


def ids(rows: list[dict[str, Any]], key: str) -> list[Any]:
    return [row.get(key) for row in rows if row.get(key)]


def chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def pct(count: int, total: int) -> str:
    return f"{(count / max(total, 1)) * 100:.1f}%"


def clean_md(value: Any) -> str:
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\n", " ").strip()


def json_ready(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
