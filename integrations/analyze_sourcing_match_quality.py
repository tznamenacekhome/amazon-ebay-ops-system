"""Dry-run sourcing match quality rules against recent MBOP opportunities."""

from __future__ import annotations

import argparse
import datetime as dt
from collections import Counter
from typing import Any

from sourcing_common import fetch_settings, get_supabase_client
from sourcing_match_rules import evaluate_static_match_rules


REVIEW_STATUSES = {"open", "watching", "roi_snoozed", "purchased_pending_match", "best_offer"}
POSITIVE_STATUSES = {"matched_to_purchase", "purchased_pending_match", "watching"}


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    opportunities = fetch_opportunities(supabase, args)

    evaluated = []
    for opportunity in opportunities:
        candidate = opportunity.get("sourcing_ebay_candidates") or {}
        seed = opportunity.get("sourcing_seed_asins") or {}
        diagnostics = evaluate_static_match_rules(
            candidate,
            seed,
            excluded_keywords=settings.excluded_keywords,
            allowed_item_location_countries=settings.item_location_countries,
        )
        if args.reason and not reason_matches(diagnostics, args.reason):
            continue
        evaluated.append((opportunity, diagnostics))

    summarize(evaluated, args)

    if args.write:
        updated = write_diagnostics(supabase, evaluated)
        print(f"\nDiagnostics written: {updated}")
    else:
        print("\nDry run only. Use --write to store rule diagnostics without changing opportunity status.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze deterministic sourcing match quality rules.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Default mode; does not write data.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum opportunities to inspect.")
    parser.add_argument("--since-days", type=int, default=30, help="Only inspect opportunities created in the last N days.")
    parser.add_argument("--reason", help="Only show opportunities whose block/warn reason contains this text.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write rule diagnostics to matching_diagnostics_json. Does not update status or auto-dismiss.",
    )
    return parser.parse_args()


def fetch_opportunities(supabase, args: argparse.Namespace) -> list[dict[str, Any]]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=args.since_days)
    rows: list[dict[str, Any]] = []
    page_size = min(args.limit, 1000)
    start = 0
    while len(rows) < args.limit:
        end = min(start + page_size - 1, args.limit - 1)
        response = (
            supabase.table("sourcing_opportunities")
            .select(
                """
                opportunity_id,
                status,
                opportunity_type,
                asin,
                score,
                ai_flags,
                matching_diagnostics_json,
                created_at,
                sourcing_seed_asins (*),
                sourcing_ebay_candidates (*)
                """
            )
            .gte("created_at", since.isoformat())
            .order("created_at", desc=True)
            .range(start, end)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows[: args.limit]


def summarize(evaluated: list[tuple[dict[str, Any], dict[str, Any]]], args: argparse.Namespace) -> None:
    total = len(evaluated)
    status_counts = Counter(row.get("status") or "unknown" for row, _ in evaluated)
    recommendation_counts = Counter(diagnostics.get("recommendation") for _, diagnostics in evaluated)
    block_reasons = Counter()
    warning_reasons = Counter()
    metadata_availability = Counter()
    structured_rule_hits = Counter()
    platform_sources = Counter()
    category_sources = Counter()
    newly_blocked = []
    potential_false_positives = []
    manual_review = []

    for opportunity, diagnostics in evaluated:
        hard_blocks = diagnostics.get("hard_blocks") or []
        warnings = diagnostics.get("warnings") or []
        for reason in hard_blocks:
            block_reasons[reason] += 1
        for reason in warnings:
            warning_reasons[reason] += 1

        evidence = diagnostics.get("normalized_evidence") or {}
        for key, available in evidence_availability(evidence).items():
            if available:
                metadata_availability[key] += 1
        platform_rule = diagnostics.get("platform_rule") or {}
        platform_sources[str(platform_rule.get("seed_system_source") or "missing")] += 1
        platform_sources[str(platform_rule.get("candidate_system_source") or "missing")] += 1
        category = diagnostics.get("category") or {}
        if category.get("category_ids") or category.get("category_names"):
            category_sources["category_present"] += 1
        if category.get("positive_game_software_category"):
            category_sources["game_software_category"] += 1
        for key in (
            "game_name",
            "numeric_identity",
            "edition_version",
            "digital_download",
            "not_game",
            "incomplete_listing",
            "region",
            "category",
        ):
            rule = diagnostics.get(key) or {}
            if rule.get("result") in {"blocked", "review"}:
                structured_rule_hits[f"{key}:{rule.get('result')}"] += 1

        status = opportunity.get("status")
        if hard_blocks and status in REVIEW_STATUSES:
            newly_blocked.append((opportunity, diagnostics))
        if hard_blocks and status in POSITIVE_STATUSES:
            potential_false_positives.append((opportunity, diagnostics))
        if diagnostics.get("recommendation") in {"Review", "Probable Non-Match"} and not hard_blocks:
            manual_review.append((opportunity, diagnostics))

    print("Sourcing match quality dry run")
    print("--------------------------------")
    print(f"Window: last {args.since_days} day(s)")
    print(f"Limit: {args.limit}")
    print(f"Rows evaluated: {total}")
    print(f"Current statuses: {dict(status_counts)}")
    print(f"Rule recommendations: {dict(recommendation_counts)}")
    print(f"Before open/review count: {sum(status_counts.get(status, 0) for status in REVIEW_STATUSES)}")
    print(f"Newly blocked reviewable rows: {len(newly_blocked)}")
    print(f"After open/review count if hard blocks were excluded: {max(sum(status_counts.get(status, 0) for status in REVIEW_STATUSES) - len(newly_blocked), 0)}")

    print_counter("\nTop block reasons", block_reasons)
    print_counter("\nTop warning reasons", warning_reasons)
    print_counter("\nStructured metadata availability", metadata_availability)
    print_counter("\nStructured metadata rule hits", structured_rule_hits)
    print_counter("\nPlatform-source coverage", platform_sources)
    print_counter("\nCategory-source coverage", category_sources)
    print_examples("\nNewly blocked examples", newly_blocked, limit=8)
    print_examples("\nPotential false positive examples", potential_false_positives, limit=8)
    print_examples("\nManual review examples", manual_review, limit=8)


def evidence_availability(evidence: dict[str, Any]) -> dict[str, bool]:
    return {
        "localized_aspects": bool(evidence.get("aspects")),
        "item_specific_platform": bool(evidence.get("platform_values")),
        "item_specific_game_name": bool(evidence.get("game_name_values")),
        "item_specific_region": bool(evidence.get("region_code_values") or evidence.get("country_of_origin_values")),
        "item_specific_format": bool(evidence.get("format_values")),
        "item_specific_type": bool(evidence.get("type_values")),
        "item_specific_features": bool(evidence.get("features_values")),
        "item_specific_release_year": bool(evidence.get("release_year_values")),
        "category": bool(evidence.get("category_ids") or evidence.get("category_names")),
        "description": bool(evidence.get("description")),
        "primary_image": bool(evidence.get("primary_image_url")),
        "additional_images": len(evidence.get("image_urls") or []) > 1,
    }


def print_counter(title: str, counter: Counter) -> None:
    print(title)
    if not counter:
        print("- none")
        return
    for reason, count in counter.most_common(10):
        print(f"- {count}: {reason}")


def print_examples(title: str, rows: list[tuple[dict[str, Any], dict[str, Any]]], *, limit: int) -> None:
    print(title)
    if not rows:
        print("- none")
        return
    for opportunity, diagnostics in rows[:limit]:
        seed = opportunity.get("sourcing_seed_asins") or {}
        candidate = opportunity.get("sourcing_ebay_candidates") or {}
        reasons = diagnostics.get("hard_blocks") or diagnostics.get("warnings") or []
        print(f"- {opportunity.get('status')} | {opportunity.get('asin')} | {', '.join(reasons[:2])}")
        print(f"  Amazon: {seed.get('amazon_title')}")
        print(f"  eBay:   {candidate.get('ebay_title')}")


def reason_matches(diagnostics: dict[str, Any], reason: str) -> bool:
    needle = reason.casefold()
    values = []
    values.extend(diagnostics.get("hard_blocks") or [])
    values.extend(diagnostics.get("warnings") or [])
    values.extend(diagnostics.get("flags") or [])
    return any(needle in str(value).casefold() for value in values)


def write_diagnostics(supabase, evaluated: list[tuple[dict[str, Any], dict[str, Any]]]) -> int:
    rows = []
    for opportunity, diagnostics in evaluated:
        existing = opportunity.get("matching_diagnostics_json")
        if not isinstance(existing, dict):
            existing = {}
        rows.append(
            {
                "opportunity_id": opportunity["opportunity_id"],
                "matching_diagnostics_json": {
                    **existing,
                    "static_rules": diagnostics,
                    "platform_rule": diagnostics.get("platform_rule"),
                    "title_overlap": diagnostics.get("title_overlap"),
                    "excluded_keywords": diagnostics.get("excluded_keywords"),
                    "digital_download": diagnostics.get("digital_download"),
                    "category": diagnostics.get("category"),
                    "normalized_evidence": diagnostics.get("normalized_evidence"),
                    "game_name": diagnostics.get("game_name"),
                    "numeric_identity": diagnostics.get("numeric_identity"),
                    "edition_version": diagnostics.get("edition_version"),
                    "region": diagnostics.get("region"),
                    "incomplete_listing": diagnostics.get("incomplete_listing"),
                    "not_game": diagnostics.get("not_game"),
                    "delivery": diagnostics.get("delivery"),
                    "rule_analysis_written_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            }
        )
    updated = 0
    for row in rows:
        opportunity_id = row.pop("opportunity_id")
        supabase.table("sourcing_opportunities").update(row).eq("opportunity_id", opportunity_id).execute()
        updated += 1
    return updated


if __name__ == "__main__":
    raise SystemExit(main())
