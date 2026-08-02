"""Read-only positive-match safety audit for sourcing deterministic rules.

This script reads Supabase sourcing/matching evidence and writes local audit
artifacts only. It does not update production data, call marketplace APIs,
rescore rows, deploy, or train/use AI.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sourcing_common import fetch_settings, get_supabase_client
from sourcing_match_rules import (
    edition_rule,
    edition_signals,
    evaluate_static_match_rules,
    identity_numbers,
    keyword_hits,
    meaningful_title_tokens,
    normalize_candidate_evidence,
)


DEFAULT_CSV = Path("tmp/sourcing-positive-match-safety-audit-2026-08-01.csv")
DEFAULT_REPORT = Path("docs/sourcing_positive_match_safety_audit_2026-08-01.md")
DEFAULT_ROOT_CAUSE_CSV = Path("tmp/sourcing-positive-conflict-root-cause-analysis-2026-08-01.csv")
DEFAULT_ROOT_CAUSE_REPORT = Path("docs/sourcing_positive_conflict_root_cause_analysis_2026-08-01.md")
POSITIVE_STATUSES = {"purchased_pending_match", "matched_to_purchase"}
REVIEW_ONLY_STATUS = "watching"
PROPOSED_EDITION_TERMS = {
    "complete": {"complete", "complete edition", "goty", "game of the year"},
    "nintendo_selects": {"nintendo selects"},
    "playstation_hits": {"playstation hits", "ps hits"},
    "xbox_classics": {"xbox classics", "classics"},
    "remaster": {"remaster", "remastered"},
    "definitive": {"definitive", "director's cut", "directors cut"},
    "anniversary": {"anniversary"},
}


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    raw_rows = fetch_positive_rows(supabase, args.limit)
    rows = [evaluate_row(row, settings) for row in dedupe_positive_rows(raw_rows)]
    rows = apply_filters(rows, args)
    summary = summarize(rows, raw_rows)
    if args.root_cause:
        conflict_rows = root_cause_rows(rows)
        root_summary = summarize_root_cause(conflict_rows, rows, raw_rows)
        output_rows = root_summary["review_queue"] if args.output_review_queue else conflict_rows
        write_root_cause_csv(args.csv, output_rows)
        write_root_cause_report(args.report, conflict_rows, root_summary)
    else:
        write_csv(args.csv, rows)
        write_report(args.report, rows, summary)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload_rows = output_rows if args.root_cause else rows
        payload_summary = root_summary if args.root_cause else summary
        args.json.write_text(json.dumps({"summary": json_ready(payload_summary), "rows": payload_rows}, indent=2), encoding="utf-8")
    print("Sourcing positive match safety audit")
    print("------------------------------------")
    print(f"Raw positive evidence rows: {len(raw_rows)}")
    print(f"Deduplicated positive rows: {summary['deduped_count']}")
    print(f"Authoritative confirmed positives: {summary['confirmed_count']}")
    print(f"Review-only watching rows: {summary['review_only_count']}")
    print(f"Current hard-blocked confirmed positives: {summary['current_blocked_count']}")
    print(f"Proposed game-name blocks: {summary['sim_counts'].get('game_name_strict', 0)}")
    print(f"Proposed numeric/installment blocks: {summary['sim_counts'].get('numeric_installment_strict', 0)}")
    print(f"Proposed edition-family blocks: {summary['sim_counts'].get('edition_family_strict', 0)}")
    print(f"Proposed short-title blocks: {summary['sim_counts'].get('short_title_strict', 0)}")
    if args.root_cause:
        print(f"Root-cause conflict rows: {root_summary['conflict_count']}")
        print(f"Strongest confirmed conflict rows: {root_summary['strongest_confirmed_count']}")
        print(f"Operator review queue rows: {root_summary['review_queue_count']}")
    print(f"Report: {args.report}")
    print(f"CSV: {args.csv}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only positive match safety audit.")
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--root-cause", action="store_true", help="Write positive conflict root-cause analysis artifacts.")
    parser.add_argument("--rule-family", action="append", help="Filter output to current/simulated rule family.")
    parser.add_argument("--confidence-tier", action="append", help="Filter output to one or more evidence confidence tiers.")
    parser.add_argument("--asin", action="append", help="Filter output to one or more ASINs.")
    parser.add_argument("--ebay-item-id", action="append", help="Filter output to one or more eBay item IDs.")
    parser.add_argument("--rock-band-only", action="store_true", help="Filter output to Rock Band-related rows.")
    parser.add_argument("--output-review-queue", action="store_true", help="With --root-cause, output only operator-review queue rows.")
    args = parser.parse_args()
    if args.root_cause and args.csv == DEFAULT_CSV:
        args.csv = DEFAULT_ROOT_CAUSE_CSV
    if args.root_cause and args.report == DEFAULT_REPORT:
        args.report = DEFAULT_ROOT_CAUSE_REPORT
    return args


def fetch_positive_rows(supabase, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(fetch_positive_opportunities(supabase, limit))
    rows.extend(fetch_positive_examples(supabase, limit))
    rows.extend(fetch_purchased_actions(supabase, limit))
    return rows


def fetch_positive_opportunities(supabase, limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in fetch_pages(
        supabase,
        "sourcing_opportunities",
        "*,sourcing_seed_asins(*),sourcing_ebay_candidates(*)",
        limit,
        lambda query: query.in_("status", sorted(POSITIVE_STATUSES | {REVIEW_ONLY_STATUS})),
    ):
        status = row.get("status")
        confidence = "confirmed_positive" if status in POSITIVE_STATUSES else "review_only"
        rows.append(
            {
                "source": "sourcing_opportunities",
                "source_id": row.get("opportunity_id"),
                "positive_confidence": confidence,
                "opportunity": row,
                "candidate": row.get("sourcing_ebay_candidates") or {},
                "seed": row.get("sourcing_seed_asins") or {},
                "status": status,
            }
        )
    return rows


def fetch_positive_examples(supabase, limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in fetch_pages(
        supabase,
        "matching_intelligence_examples",
        "*",
        limit,
        lambda query: query.eq("match_label", "match"),
    ):
        rows.append(
            {
                "source": f"matching_intelligence_examples:{row.get('source_table') or 'unknown'}",
                "source_id": row.get("matching_intelligence_example_id") or row.get("source_id"),
                "positive_confidence": "confirmed_positive",
                "opportunity": {},
                "candidate": candidate_from_example(row),
                "seed": seed_from_example(row),
                "status": "match_example",
                "example": row,
            }
        )
    return rows


def fetch_purchased_actions(supabase, limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in fetch_pages(
        supabase,
        "sourcing_actions",
        "*,sourcing_opportunities(*,sourcing_seed_asins(*),sourcing_ebay_candidates(*))",
        limit,
        lambda query: query.eq("action_type", "purchased"),
    ):
        opportunity = row.get("sourcing_opportunities") or {}
        rows.append(
            {
                "source": "sourcing_actions:purchased",
                "source_id": row.get("action_id"),
                "positive_confidence": "confirmed_positive",
                "opportunity": opportunity,
                "candidate": opportunity.get("sourcing_ebay_candidates") or {},
                "seed": opportunity.get("sourcing_seed_asins") or {},
                "status": "purchased_action",
            }
        )
    return rows


def fetch_pages(supabase, table: str, columns: str, limit: int, apply_filters) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_size = 1000
    start = 0
    while len(rows) < limit:
        end = min(start + page_size - 1, limit - 1)
        query = apply_filters(supabase.table(table).select(columns)).range(start, end)
        response = query.execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows[:limit]


def candidate_from_example(row: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    if row.get("ebay_item_specifics_json"):
        raw["localizedAspects"] = row.get("ebay_item_specifics_json")
    if row.get("ebay_description"):
        raw["description"] = row.get("ebay_description")
    if row.get("ebay_category"):
        raw["categories"] = [{"categoryName": row.get("ebay_category")}]
    if row.get("ebay_primary_image_url"):
        raw["image"] = {"imageUrl": row.get("ebay_primary_image_url")}
    return {
        "asin": row.get("asin"),
        "ebay_item_id": row.get("ebay_item_id"),
        "ebay_legacy_item_id": row.get("ebay_legacy_item_id"),
        "ebay_title": row.get("ebay_title"),
        "ebay_image_url": row.get("ebay_primary_image_url"),
        "condition": row.get("ebay_condition"),
        "raw_ebay_json": raw,
    }


def seed_from_example(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asin": row.get("asin"),
        "amazon_title": row.get("amazon_title"),
        "amazon_image_url": row.get("amazon_image_url"),
        "system": row.get("amazon_system") or row.get("detected_system"),
    }


def dedupe_positive_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate = row.get("candidate") or {}
        seed = row.get("seed") or {}
        key = positive_key(seed, candidate)
        existing = by_key.get(key)
        if not existing:
            by_key[key] = row
            row["evidence_sources"] = [row.get("source")]
            continue
        existing.setdefault("evidence_sources", [])
        if row.get("source") not in existing["evidence_sources"]:
            existing["evidence_sources"].append(row.get("source"))
        if existing.get("positive_confidence") != "confirmed_positive" and row.get("positive_confidence") == "confirmed_positive":
            row["evidence_sources"] = existing["evidence_sources"]
            by_key[key] = row
    return list(by_key.values())


def positive_key(seed: dict[str, Any], candidate: dict[str, Any]) -> str:
    asin = clean_asin(seed.get("asin") or candidate.get("asin"))
    ebay_id = clean_ebay_id(candidate.get("ebay_item_id") or candidate.get("ebay_legacy_item_id"))
    if ebay_id:
        return f"asin-ebay|{asin}|{legacy_item_id(ebay_id)}"
    amazon_title = normalize_text(seed.get("amazon_title"))
    ebay_title = normalize_text(candidate.get("ebay_title"))
    system = normalize_text(seed.get("system"))
    return f"title|{asin}|{system}|{amazon_title}|{ebay_title}"


def evaluate_row(row: dict[str, Any], settings) -> dict[str, Any]:
    candidate = row.get("candidate") or {}
    seed = row.get("seed") or {}
    diagnostics = evaluate_static_match_rules(
        candidate,
        seed,
        excluded_keywords=settings.excluded_keywords,
        allowed_item_location_countries=settings.item_location_countries,
    )
    evidence = diagnostics.get("normalized_evidence") or normalize_candidate_evidence(candidate)
    simulations = simulate_proposed_rules(seed, candidate, evidence)
    current_blocks = diagnostics.get("hard_blocks") or []
    example = row.get("example") or {}
    opportunity = row.get("opportunity") or {}
    raw = candidate.get("raw_ebay_json") or {}
    seller = raw.get("seller") if isinstance(raw, dict) else {}
    return {
        "dedupe_key": positive_key(seed, candidate),
        "positive_confidence": row.get("positive_confidence"),
        "status": row.get("status"),
        "sources": "; ".join(row.get("evidence_sources") or [row.get("source")]),
        "source_id": row.get("source_id"),
        "source_table": example.get("source_table") or row.get("source"),
        "source_detail": example.get("source_detail"),
        "evidence_strength": example.get("evidence_strength"),
        "source_weight": example.get("source_weight"),
        "asin": clean_asin(seed.get("asin") or candidate.get("asin")),
        "amazon_title": seed.get("amazon_title"),
        "amazon_system": seed.get("system"),
        "amazon_image_url": seed.get("amazon_image_url") or example.get("amazon_image_url"),
        "ebay_item_id": candidate.get("ebay_item_id") or candidate.get("ebay_legacy_item_id"),
        "ebay_title": candidate.get("ebay_title"),
        "ebay_description": evidence.get("description") or example.get("ebay_description"),
        "ebay_condition": candidate.get("condition") or example.get("ebay_condition"),
        "ebay_platform": "; ".join(evidence.get("platform_values") or []),
        "ebay_item_specifics": json.dumps(evidence.get("aspects") or {}, sort_keys=True),
        "features": "; ".join(evidence.get("features_values") or []),
        "type": "; ".join(evidence.get("type_values") or []),
        "format": "; ".join(evidence.get("format_values") or []),
        "release_year": "; ".join(evidence.get("release_year_values") or []),
        "primary_image_url": evidence.get("primary_image_url") or example.get("ebay_primary_image_url"),
        "image_url_count": len(evidence.get("image_urls") or []),
        "seller_username": candidate.get("seller_username") or example.get("ebay_seller_username") or ((seller or {}).get("username") if isinstance(seller, dict) else None),
        "item_location_country": candidate.get("item_location_country"),
        "game_name": "; ".join(evidence.get("game_name_values") or []),
        "category": "; ".join(evidence.get("category_names") or []),
        "purchase_or_review_date": example.get("created_at") or example.get("reviewed_at") or opportunity.get("updated_at") or opportunity.get("created_at"),
        "later_purchase_matched": bool(example.get("later_purchase_matched")),
        "later_received": bool(example.get("later_received")),
        "later_listed": bool(example.get("later_listed")),
        "later_sold": bool(example.get("later_sold")),
        "operator_notes": example.get("dismissal_note"),
        "current_recommendation": diagnostics.get("recommendation"),
        "current_hard_blocks": "; ".join(current_blocks),
        "current_blocked": bool(current_blocks),
        "current_block_family": block_family(current_blocks),
        "game_name_strict_block": simulations["game_name_strict"]["blocked"],
        "game_name_strict_reason": simulations["game_name_strict"]["reason"],
        "numeric_installment_strict_block": simulations["numeric_installment_strict"]["blocked"],
        "numeric_installment_strict_reason": simulations["numeric_installment_strict"]["reason"],
        "edition_family_strict_block": simulations["edition_family_strict"]["blocked"],
        "edition_family_strict_reason": simulations["edition_family_strict"]["reason"],
        "short_title_strict_block": simulations["short_title_strict"]["blocked"],
        "short_title_strict_reason": simulations["short_title_strict"]["reason"],
        "any_simulated_block": any(value["blocked"] for value in simulations.values()),
    }


def simulate_proposed_rules(seed: dict[str, Any], candidate: dict[str, Any], evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    amazon_title = str(seed.get("amazon_title") or "")
    ebay_title = str(candidate.get("ebay_title") or "")
    amazon_tokens = meaningful_title_tokens(amazon_title)
    ebay_tokens = meaningful_title_tokens(" ".join([ebay_title, " ".join(evidence.get("game_name_values") or [])]))
    return {
        "game_name_strict": simulate_game_name_strict(amazon_title, evidence),
        "numeric_installment_strict": simulate_numeric_strict(amazon_title, ebay_title, evidence),
        "edition_family_strict": simulate_edition_family_strict(amazon_title, ebay_title, evidence),
        "short_title_strict": simulate_short_title_strict(amazon_tokens, ebay_tokens, evidence),
    }


def simulate_game_name_strict(amazon_title: str, evidence: dict[str, Any]) -> dict[str, Any]:
    amazon_tokens = meaningful_title_tokens(amazon_title)
    for value in evidence.get("game_name_values") or []:
        game_tokens = meaningful_title_tokens(value)
        if not amazon_tokens or not game_tokens:
            continue
        shared = amazon_tokens & game_tokens
        if not shared:
            return {"blocked": True, "reason": f"Game Name no-overlap: {value}"}
        if game_tokens != amazon_tokens:
            extra_game = sorted(game_tokens - amazon_tokens)
            extra_amazon = sorted(amazon_tokens - game_tokens)
            if extra_game or extra_amazon:
                return {
                    "blocked": True,
                    "reason": f"Game Name token-set mismatch: {value}; extra_game={extra_game}; extra_amazon={extra_amazon}",
                }
    return {"blocked": False, "reason": ""}


def simulate_numeric_strict(amazon_title: str, ebay_title: str, evidence: dict[str, Any]) -> dict[str, Any]:
    candidate_text = " ".join([ebay_title, " ".join(evidence.get("game_name_values") or [])])
    amazon_numbers = identity_numbers(amazon_title)
    ebay_numbers = identity_numbers(candidate_text)
    shared = meaningful_title_tokens(amazon_title) & meaningful_title_tokens(candidate_text)
    amazon_all = amazon_numbers["years"] | amazon_numbers["numbers"]
    ebay_all = ebay_numbers["years"] | ebay_numbers["numbers"]
    if shared and amazon_all != ebay_all:
        return {
            "blocked": True,
            "reason": f"numeric/installment mismatch: amazon={sorted(amazon_all)} ebay={sorted(ebay_all)} shared={sorted(shared)}",
        }
    return {"blocked": False, "reason": ""}


def simulate_edition_family_strict(amazon_title: str, ebay_title: str, evidence: dict[str, Any]) -> dict[str, Any]:
    current = edition_rule(amazon_title, ebay_title, evidence)
    amazon_signals = set(current.get("amazon_signals") or []) | proposed_edition_signals(amazon_title)
    ebay_text = " ".join([ebay_title, " ".join(evidence.get("features_values") or []), " ".join(evidence.get("type_values") or [])])
    ebay_signals = set(current.get("ebay_signals") or []) | proposed_edition_signals(ebay_text)
    if amazon_signals != ebay_signals:
        return {
            "blocked": True,
            "reason": f"edition-family mismatch: amazon={sorted(amazon_signals)} ebay={sorted(ebay_signals)}",
        }
    return {"blocked": False, "reason": ""}


def proposed_edition_signals(text: str) -> set[str]:
    signals = edition_signals(text)
    for label, terms in PROPOSED_EDITION_TERMS.items():
        if keyword_hits(text.casefold(), terms):
            signals.add(label)
    return signals


def simulate_short_title_strict(amazon_tokens: set[str], ebay_tokens: set[str], evidence: dict[str, Any]) -> dict[str, Any]:
    if len(amazon_tokens) > 2 or not amazon_tokens:
        return {"blocked": False, "reason": ""}
    if evidence.get("game_name_values"):
        return {"blocked": False, "reason": ""}
    shared = amazon_tokens & ebay_tokens
    extra = ebay_tokens - amazon_tokens
    if shared and extra:
        return {"blocked": True, "reason": f"short-title extra candidate tokens: shared={sorted(shared)} extra={sorted(extra)}"}
    return {"blocked": False, "reason": ""}


def summarize(rows: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed = [row for row in rows if row.get("positive_confidence") == "confirmed_positive"]
    current_blocked = [row for row in confirmed if row.get("current_blocked")]
    sim_counts = Counter()
    for row in confirmed:
        for key in ("game_name_strict", "numeric_installment_strict", "edition_family_strict", "short_title_strict"):
            if row.get(f"{key}_block"):
                sim_counts[key] += 1
    return {
        "raw_count": len(raw_rows),
        "deduped_count": len(rows),
        "confirmed_count": len(confirmed),
        "review_only_count": len([row for row in rows if row.get("positive_confidence") == "review_only"]),
        "current_blocked_count": len(current_blocked),
        "current_block_families": Counter(row.get("current_block_family") for row in current_blocked),
        "sim_counts": sim_counts,
        "rock_band_rows": [row for row in confirmed if "rock band" in f"{row.get('amazon_title')} {row.get('ebay_title')}".casefold()],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "dedupe_key",
        "positive_confidence",
        "status",
        "sources",
        "source_id",
        "asin",
        "amazon_title",
        "amazon_system",
        "ebay_item_id",
        "ebay_title",
        "item_location_country",
        "game_name",
        "category",
        "current_recommendation",
        "current_hard_blocks",
        "current_blocked",
        "current_block_family",
        "game_name_strict_block",
        "game_name_strict_reason",
        "numeric_installment_strict_block",
        "numeric_installment_strict_reason",
        "edition_family_strict_block",
        "edition_family_strict_reason",
        "short_title_strict_block",
        "short_title_strict_reason",
        "any_simulated_block",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def apply_filters(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    output = rows
    if args.asin:
        wanted = {clean_asin(value) for value in args.asin}
        output = [row for row in output if clean_asin(row.get("asin")) in wanted]
    if args.ebay_item_id:
        wanted = {legacy_item_id(value) for value in args.ebay_item_id}
        output = [row for row in output if legacy_item_id(row.get("ebay_item_id")) in wanted]
    if args.rock_band_only:
        output = [row for row in output if is_rock_band(row)]
    if args.confidence_tier:
        wanted = {normalize_label(value) for value in args.confidence_tier}
        output = [row for row in output if normalize_label(evidence_confidence_group(row)) in wanted]
    if args.rule_family:
        wanted = {normalize_label(value) for value in args.rule_family}
        output = [row for row in output if wanted & {normalize_label(value) for value in row_rule_families(row)}]
    return output


def root_cause_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    conflicts = [
        row
        for row in rows
        if row.get("current_blocked")
        or row.get("any_simulated_block")
        or is_rock_band(row)
    ]
    output = []
    for row in conflicts:
        enriched = dict(row)
        numeric = classify_numeric_conflict(row)
        enriched.update(
            {
                "evidence_confidence_group": evidence_confidence_group(row),
                "strongest_confirmed_positive": evidence_confidence_group(row) in {
                    "Confirmed received correct item",
                    "Confirmed listed/sold successfully",
                    "Manually verified exact match",
                },
                "rule_families": "; ".join(row_rule_families(row)),
                "primary_root_cause": primary_root_cause(row, numeric),
                "numeric_root_cause": numeric["root_cause"],
                "amazon_numbers": "; ".join(numeric["amazon_numbers"]),
                "ebay_numbers": "; ".join(numeric["ebay_numbers"]),
                "number_classifications": "; ".join(numeric["classifications"]),
                "rock_band_classification": classify_rock_band(row),
                "game_name_conflict_classification": classify_game_name_conflict(row),
                "edition_conflict_classification": classify_edition_conflict(row),
                "short_title_classification": classify_short_title_conflict(row),
                "operator_review_priority": operator_review_priority(row, numeric),
                "operator_review_question": operator_review_question(row, numeric),
            }
        )
        output.append(enriched)
    output.sort(key=lambda row: (0 if row.get("operator_review_priority") else 1, row.get("asin") or "", row.get("ebay_title") or ""))
    return output


def summarize_root_cause(conflicts: list[dict[str, Any]], rows: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    confirmed_conflicts = [row for row in conflicts if row.get("positive_confidence") == "confirmed_positive"]
    review_queue = [row for row in conflicts if row.get("operator_review_priority")]
    return {
        "raw_count": len(raw_rows),
        "deduped_count": len(rows),
        "confirmed_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive"),
        "review_only_count": sum(1 for row in rows if row.get("positive_confidence") == "review_only"),
        "conflict_count": len(conflicts),
        "confirmed_conflict_count": len(confirmed_conflicts),
        "strongest_confirmed_count": sum(1 for row in confirmed_conflicts if row.get("strongest_confirmed_positive")),
        "current_blocked_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and row.get("current_blocked")),
        "game_name_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and row.get("game_name_strict_block")),
        "numeric_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and row.get("numeric_installment_strict_block")),
        "edition_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and row.get("edition_family_strict_block")),
        "short_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and row.get("short_title_strict_block")),
        "rock_band_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and is_rock_band(row)),
        "rock_band_numeric_count": sum(1 for row in rows if row.get("positive_confidence") == "confirmed_positive" and is_rock_band(row) and row.get("numeric_installment_strict_block")),
        "confidence_counts": Counter(row.get("evidence_confidence_group") for row in conflicts),
        "root_cause_counts": Counter(row.get("primary_root_cause") for row in conflicts),
        "confirmed_root_cause_counts": Counter(row.get("primary_root_cause") for row in confirmed_conflicts),
        "numeric_root_cause_counts": Counter(row.get("numeric_root_cause") for row in conflicts if row.get("numeric_installment_strict_block")),
        "confirmed_numeric_root_cause_counts": Counter(row.get("numeric_root_cause") for row in confirmed_conflicts if row.get("numeric_installment_strict_block")),
        "current_family_counts": Counter(row.get("current_block_family") for row in conflicts if row.get("current_blocked")),
        "game_name_class_counts": Counter(row.get("game_name_conflict_classification") for row in conflicts if row.get("game_name_strict_block")),
        "confirmed_game_name_class_counts": Counter(row.get("game_name_conflict_classification") for row in confirmed_conflicts if row.get("game_name_strict_block")),
        "edition_class_counts": Counter(row.get("edition_conflict_classification") for row in conflicts if row.get("edition_family_strict_block")),
        "confirmed_edition_class_counts": Counter(row.get("edition_conflict_classification") for row in confirmed_conflicts if row.get("edition_family_strict_block")),
        "short_class_counts": Counter(row.get("short_title_classification") for row in conflicts if row.get("short_title_strict_block")),
        "confirmed_short_class_counts": Counter(row.get("short_title_classification") for row in confirmed_conflicts if row.get("short_title_strict_block")),
        "rock_band_class_counts": Counter(row.get("rock_band_classification") for row in conflicts if is_rock_band(row)),
        "confirmed_rock_band_class_counts": Counter(row.get("rock_band_classification") for row in confirmed_conflicts if is_rock_band(row)),
        "review_queue_count": min(len(review_queue), 50),
        "review_queue": review_queue[:50],
    }


def evidence_confidence_group(row: dict[str, Any]) -> str:
    source = str(row.get("sources") or row.get("source_table") or "").casefold()
    strength = str(row.get("evidence_strength") or "").casefold()
    status = str(row.get("status") or "").casefold()
    if row.get("positive_confidence") == "review_only":
        return "Watch-only / not a confirmed match"
    if row.get("later_received"):
        return "Confirmed received correct item"
    if row.get("later_listed") or row.get("later_sold"):
        return "Confirmed listed/sold successfully"
    if "manual_item_matches" in source or strength == "high":
        return "Manually verified exact match"
    if status in {"matched_to_purchase", "match_example"} or "sourcing_purchase_matches" in source:
        return "Purchased and matched, but not yet receiving-confirmed"
    if status in {"purchased_pending_match", "purchased_action"} or "sourcing_actions:purchased" in source:
        return "Purchase pending / weaker positive"
    return "Insufficient evidence"


def row_rule_families(row: dict[str, Any]) -> list[str]:
    families = []
    if row.get("current_blocked"):
        families.append(f"current:{row.get('current_block_family') or 'other'}")
    for key, label in [
        ("game_name_strict_block", "game_name"),
        ("numeric_installment_strict_block", "numeric"),
        ("edition_family_strict_block", "edition"),
        ("short_title_strict_block", "short_title"),
    ]:
        if row.get(key):
            families.append(label)
    if is_rock_band(row):
        families.append("rock_band")
    return families


def classify_numeric_conflict(row: dict[str, Any]) -> dict[str, Any]:
    amazon_title = str(row.get("amazon_title") or "")
    ebay_text = " ".join([str(row.get("ebay_title") or ""), str(row.get("game_name") or ""), str(row.get("release_year") or "")])
    amazon_numbers = sorted(numbers_in_text(amazon_title))
    ebay_numbers = sorted(numbers_in_text(ebay_text))
    classifications = []
    for side, text, values in [("amazon", amazon_title, amazon_numbers), ("ebay", ebay_text, ebay_numbers)]:
        for value in values:
            classifications.append(f"{side}:{value}={classify_number(value, text, row)}")
    root = "no numeric conflict"
    if row.get("numeric_installment_strict_block"):
        classes = " ".join(classifications)
        title = f"{amazon_title} {ebay_text}".casefold()
        if "lot of" in title or "2 games" in title or "games" in title and any("package quantity" in item for item in classifications):
            root = "quantity/lot number mistaken for installment number"
        elif any(token in title for token in ["ps3", "ps4", "ps5", "xbox 360", "series x", "series s", "xbox one"]):
            root = "platform number mistaken for installment number" if amazon_numbers != ebay_numbers else "release year mistaken for installment number"
        elif any("release year" in item for item in classifications):
            root = "release year mistaken for installment number"
        elif any("included currency/content amount" in item for item in classifications):
            root = "included currency/content amount mistaken for installment number"
        elif any("anniversary" in item for item in classifications):
            root = "anniversary number mistaken for installment number"
        elif sports_title(title):
            root = "annual sports release identifier conflict"
        elif amazon_numbers and ebay_numbers and set(amazon_numbers).isdisjoint(ebay_numbers):
            root = "different sequel/installment"
        elif amazon_numbers and not ebay_numbers:
            root = "Amazon title number missing from eBay title"
        elif ebay_numbers and not amazon_numbers:
            root = "eBay extra number too aggressively treated as identity"
        else:
            root = "simulation logic too aggressive"
    return {
        "amazon_numbers": amazon_numbers,
        "ebay_numbers": ebay_numbers,
        "classifications": classifications,
        "root_cause": root,
    }


def classify_number(value: str, text: str, row: dict[str, Any]) -> str:
    lower = text.casefold()
    if re.fullmatch(r"(?:19|20)\d{2}", value):
        return "release year"
    if value in {"2", "3", "4", "5"} and re.search(rf"(ps{value}|playstation {value})", lower):
        return "platform token"
    if value == "360" and "xbox 360" in lower:
        return "platform token"
    if value in {"700", "3500"} or "coin" in lower or "minecoin" in lower:
        return "included currency/content amount"
    if "anniversary" in lower:
        return "anniversary number"
    if re.search(rf"(lot of|lot|pack of|set of|\({value}\)\s*games?|{value}\s*games?)", lower):
        return "package quantity"
    if sports_title(lower):
        return "annual sports release identifier"
    if any(word in lower for word in ["model", "sku", "item #", "item#"]):
        return "model/SKU number"
    return "game installment"


def primary_root_cause(row: dict[str, Any], numeric: dict[str, Any]) -> str:
    text = combined_text(row)
    current = str(row.get("current_hard_blocks") or "").casefold()
    if row.get("current_block_family") == "location":
        return "current rule logic correct"
    if row.get("numeric_installment_strict_block"):
        return numeric["root_cause"]
    if row.get("game_name_strict_block"):
        return classify_game_name_conflict(row)
    if row.get("edition_family_strict_block"):
        return classify_edition_conflict(row)
    if row.get("short_title_strict_block"):
        return classify_short_title_conflict(row)
    if "accessory/not game" in current or "category is not video games" in current:
        return "positive evidence likely incorrect" if weak_evidence(row) else "current rule logic correct"
    if "platform mismatch" in current:
        return "valid Xbox cross-generation packaging" if "xbox one" in text and "series x" in text else "current rule logic correct"
    if "no meaningful title token overlap" in current:
        return "catalog metadata inconsistency"
    return "unclear / needs operator review"


def classify_rock_band(row: dict[str, Any]) -> str:
    if not is_rock_band(row):
        return ""
    text = combined_text(row)
    amazon = str(row.get("amazon_title") or "").casefold()
    ebay = str(row.get("ebay_title") or "").casefold()
    if any(term in text for term in ["guitar", "drum", "pedal", "sticks", "battery cover", "cable"]):
        return "accessory/peripheral"
    if "track pack" in amazon or "track pack" in ebay or "beatles" in text or "ac/dc" in text:
        return "true same-product match" if title_core_overlap(row) else "bundle"
    if "rock band 3" in amazon and re.search(r"\brock band\b(?!\s*3)", ebay):
        return "seller title ambiguity"
    if "rock band" in amazon and "rock band 3" in ebay and "rock band 3" not in amazon:
        return "same franchise but wrong installment"
    if title_core_overlap(row):
        return "true same-product match"
    return "unresolved"


def classify_game_name_conflict(row: dict[str, Any]) -> str:
    if not row.get("game_name_strict_block"):
        return ""
    amazon_tokens = meaningful_title_tokens(row.get("amazon_title"))
    game_tokens = meaningful_title_tokens(row.get("game_name"))
    if not amazon_tokens or not game_tokens:
        return "unresolved"
    shared = amazon_tokens & game_tokens
    extra_game = game_tokens - amazon_tokens
    extra_amazon = amazon_tokens - game_tokens
    if not shared:
        return "same franchise, different game"
    if extra_game <= {"select", "bonus", "bundle", "starter", "football", "movie"} or extra_amazon <= {"deluxe", "ultimate", "legendary", "collector", "pack", "starter", "kinect"}:
        return "same core game, edition omitted"
    if len(shared) >= 2:
        return "same core game, subtitle variation"
    return "item-specific Game Name incomplete"


def classify_edition_conflict(row: dict[str, Any]) -> str:
    if not row.get("edition_family_strict_block"):
        return ""
    reason = str(row.get("edition_family_strict_reason") or "").casefold()
    text = combined_text(row)
    if "nintendo_selects" in reason or "playstation_hits" in reason or "greatest" in text or "platinum" in text or "player" in text:
        return "Greatest Hits / Platinum Hits / Player's Choice / Nintendo Selects packaging difference"
    if "steelbook" in reason:
        return "steelbook-only versus full product" if "only" in text else "harmless packaging-line variation"
    if "complete" in reason and "complete in box" in text:
        return "seller omitted edition wording"
    if any(term in reason for term in ["gold", "deluxe", "ultimate", "collector", "premium", "limited"]):
        return "seller omitted edition wording"
    if "remaster" in reason:
        return "same physical product with packaging-line difference"
    return "edition omission only"


def classify_short_title_conflict(row: dict[str, Any]) -> str:
    if not row.get("short_title_strict_block"):
        return ""
    text = combined_text(row)
    if any(term in text for term in ["lot of", "2 games", "bundle", "with "]):
        return "needs review; bundle or multi-title listing"
    if any(term in text for term in ["plush", "balloon", "card", "case", "skin", "poster", "sticker"]):
        return "safe only with accessory/category corroboration"
    if row.get("game_name"):
        return "preserved by item-specific Game Name corroboration"
    if row.get("amazon_system") and (row.get("ebay_platform") or row.get("ebay_title")):
        return "preserved by platform plus phrase overlap"
    return "downgrade to Review, not hard block"


def operator_review_priority(row: dict[str, Any], numeric: dict[str, Any]) -> bool:
    if evidence_confidence_group(row) in {"Watch-only / not a confirmed match", "Insufficient evidence"}:
        return False
    if is_rock_band(row) and classify_rock_band(row) not in {"true same-product match"}:
        return True
    cause = primary_root_cause(row, numeric)
    return cause in {
        "different sequel/installment",
        "same franchise, different game",
        "positive evidence likely incorrect",
        "current rule logic correct",
        "unclear / needs operator review",
    }


def operator_review_question(row: dict[str, Any], numeric: dict[str, Any]) -> str:
    if is_rock_band(row):
        return "Is this the exact Rock Band disc/track-pack product, or a different installment/accessory?"
    cause = primary_root_cause(row, numeric)
    if "edition" in cause.lower() or row.get("edition_family_strict_block"):
        return "Is the edition/package line materially different for resale, or only seller/Amazon wording?"
    if row.get("game_name_strict_block"):
        return "Does the eBay Game Name identify the same core game as the Amazon ASIN?"
    if row.get("numeric_installment_strict_block"):
        return "Which numbers are product identity, and which are platform/year/quantity/content?"
    return "Is this historical positive evidence a true product match?"


def write_root_cause_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "dedupe_key",
        "positive_confidence",
        "evidence_confidence_group",
        "strongest_confirmed_positive",
        "status",
        "sources",
        "source_table",
        "source_detail",
        "evidence_strength",
        "asin",
        "amazon_title",
        "amazon_system",
        "ebay_item_id",
        "ebay_title",
        "ebay_description",
        "category",
        "ebay_item_specifics",
        "game_name",
        "ebay_platform",
        "features",
        "type",
        "release_year",
        "ebay_condition",
        "item_location_country",
        "seller_username",
        "purchase_or_review_date",
        "later_purchase_matched",
        "later_received",
        "later_listed",
        "later_sold",
        "current_hard_blocks",
        "current_block_family",
        "game_name_strict_reason",
        "numeric_installment_strict_reason",
        "edition_family_strict_reason",
        "short_title_strict_reason",
        "rule_families",
        "primary_root_cause",
        "numeric_root_cause",
        "amazon_numbers",
        "ebay_numbers",
        "number_classifications",
        "rock_band_classification",
        "game_name_conflict_classification",
        "edition_conflict_classification",
        "short_title_classification",
        "primary_image_url",
        "image_url_count",
        "operator_notes",
        "operator_review_priority",
        "operator_review_question",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_root_cause_report(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    add = lines.append
    add("# Sourcing Positive Conflict Root-Cause Analysis")
    add("")
    add("Date: 2026-08-01")
    add("")
    add("Scope: read-only root-cause analysis using the same positive dataset and deduplication as `docs/sourcing_positive_match_safety_audit_2026-08-01.md`. No production rows, statuses, settings, schema, rules, marketplace data, AI calls, or deployments were changed.")
    add("")
    add("## Dataset And Conflict Counts")
    add("")
    table(lines, ["Metric", "Count"], [
        ["Raw positive evidence rows", summary["raw_count"]],
        ["Deduplicated positive rows", summary["deduped_count"]],
        ["Authoritative confirmed positives", summary["confirmed_count"]],
        ["Review-only watching rows", summary["review_only_count"]],
        ["Conflict rows in this analysis", summary["conflict_count"]],
        ["Confirmed conflict rows", summary["confirmed_conflict_count"]],
        ["Strongest confirmed-positive conflict rows", summary["strongest_confirmed_count"]],
        ["Current evaluator hard-blocked confirmed positives", summary["current_blocked_count"]],
        ["Game Name strict simulated confirmed blocks", summary["game_name_count"]],
        ["Numeric/installment strict simulated confirmed blocks", summary["numeric_count"]],
        ["Edition-family strict simulated confirmed blocks", summary["edition_count"]],
        ["Short-title strict simulated confirmed blocks", summary["short_count"]],
        ["Rock Band-related confirmed positives", summary["rock_band_count"]],
        ["Rock Band numeric simulated blocks", summary["rock_band_numeric_count"]],
    ])
    add("")
    add("## Evidence Quality")
    add("")
    table(lines, ["Evidence group", "Rows"], summary["confidence_counts"].most_common())
    add("")
    add("Rows with `later_received`, `later_listed`, or `later_sold` are sparse because much of the current positive evidence comes from historical purchase/match memory rather than receiving outcome rows. Counts therefore distinguish fully confirmed operational outcomes from purchased/matched evidence.")
    add("")
    add("## Root-Cause Distribution")
    add("")
    table(lines, ["Primary root cause among confirmed conflicts", "Rows"], summary["confirmed_root_cause_counts"].most_common())
    add("")
    add("## Numeric Conflict Deep Dive")
    add("")
    table(lines, ["Numeric root cause among confirmed conflicts", "Rows"], summary["confirmed_numeric_root_cause_counts"].most_common())
    add("")
    add("Numeric conflicts are dominated by the strict simulation treating release years, platform tokens, lot quantities, and content/currency amounts as if they were sequel/installment identity. As written, the strict numeric simulation is not safe as a hard block.")
    add("")
    add("Explicit cases:")
    add("")
    add("- Rock Band vs Rock Band 3: hard block is safe only when both sides identify software discs and one side explicitly says `Rock Band 3` while the other explicitly identifies base `Rock Band` with no track-pack/accessory/bundle ambiguity. The reverse should also hard-block under the same exact-product conditions.")
    add("- Rock Band 2 vs Rock Band 3: safe hard block when both are software and the installment numbers conflict.")
    add("- Sports Champions vs Sports Champions 2, Jackbox Party Pack vs 7, NBA 2K19 vs NBA 2K26: safe hard blocks only when the conflicting number is part of the game identity, not a year, bundle quantity, or platform token.")
    add("- PS3/PS4/PS5, Xbox 360, Series X/S, lot of 2, 2 games, release years, anniversary editions, and Minecoin/currency amounts must be classified before they can influence hard-blocking.")
    add("")
    add("Rock Band classifications:")
    table(lines, ["Classification among confirmed positives", "Rows"], summary["confirmed_rock_band_class_counts"].most_common())
    add("")
    add("## Game Name Conflict Deep Dive")
    add("")
    table(lines, ["Classification among confirmed conflicts", "Rows"], summary["confirmed_game_name_class_counts"].most_common())
    add("")
    add("A safe Game Name hard block should require strong Game Name conflict plus conflicting title evidence plus no valid shared core identity. Exact token-set equality is too strict and false-blocks confirmed positives with omitted edition words, subtitles, publisher prefixes, and item-specific shorthand.")
    add("")
    add("## Edition Conflict Deep Dive")
    add("")
    table(lines, ["Classification among confirmed conflicts", "Rows"], summary["confirmed_edition_class_counts"].most_common())
    add("")
    add("Omission-only edition differences and packaging-line labels should usually be ignored or downgraded to Review. Hard blocks are safer for explicit conflicting material editions, bundle contents, steelbook-only listings, and starter/collector/complete content differences when both sides have explicit evidence.")
    add("")
    add("## Short/Generic Title Deep Dive")
    add("")
    table(lines, ["Classification among confirmed conflicts", "Rows"], summary["confirmed_short_class_counts"].most_common())
    add("")
    add("Short titles should not hard-block by themselves. Safer logic requires corroboration from Video Games category, matching platform, item-specific Game Name, strong phrase overlap, absence of accessory/merchandise terms, and no numeric/version conflict.")
    add("")
    add("## Current Hard-Block Safety")
    add("")
    table(lines, ["Current family", "Rows"], summary["current_family_counts"].most_common())
    add("")
    add("Canada item-location blocks are intentional business policy and are kept separate from product-identity matching quality. Product-rule families with positive conflicts should be reviewed before broad rescoring or stricter hard-block expansion.")
    add("")
    add("## Presentation Gate Recommendation")
    add("")
    add("Recommendation: DEPLOY GATE WITH RESTRICTIONS.")
    add("")
    add("The gate merely enforces stored diagnostics for `open` rows before presentation. It can hide valid open opportunities when current stored diagnostics are too aggressive, especially numeric, edition, accessory/category, platform, and title-overlap blocks. Do not recompute diagnostics inside the gate; keep recomputation in explicit dry-run/rescore jobs. Deploy only if the gate is limited to open presentation eligibility, accepted/purchased statuses remain exempt, and Canada remains understood as an intentional sourcing policy.")
    add("")
    add("## Safe Rule Blueprint")
    add("")
    add("### Safe Hard Blocks")
    add("")
    add("- Exact historical negative identity memory by ASIN + eBay item ID when there is no positive-memory conflict. Evidence: matching intelligence exact key. Behavior: hard block. Positive conflicts: none expected after conflict check. Backoff: if any confirmed positive exists for the same key, route to Review.")
    add("- Explicit non-game/accessory category plus exact accessory term and no bundle-with-game signal. Evidence: category, Type, title. Behavior: hard block. Backoff: Review if Video Games category or bundle language is present.")
    add("- Explicit different software installment where both numbers are classified as game installment or annual sports identity and platform/category match. Evidence: Amazon title, eBay title, Game Name. Behavior: hard block. Backoff: Review if either number is platform/year/quantity/content.")
    add("")
    add("### Review / Penalty Only")
    add("")
    add("- Strict numeric/installment mismatch without number classification.")
    add("- Strict Game Name token-set mismatch.")
    add("- Edition-family omission or packaging-line mismatch.")
    add("- Short/generic title with extra candidate tokens.")
    add("- Seller/listing text that conflicts with otherwise plausible title/platform evidence.")
    add("")
    add("### Needs Operator Clarification")
    add("")
    add("- Rock Band base vs numbered installment rows with ambiguous seller title.")
    add("- Xbox One / Series X cross-generation packaging when Amazon/eBay system fields disagree.")
    add("- Edition omission cases where Amazon and eBay titles differ but photos would settle the packaging.")
    add("")
    add("### Do Not Implement")
    add("")
    add("- Any hard block based solely on short title length.")
    add("- Any hard block based on exact Game Name token-set equality.")
    add("- Any numeric hard block that treats all extra numbers as identity.")
    add("- Any expanded edition hard block that treats omission-only packaging labels as mismatch.")
    add("")
    add("## Operator Review Queue")
    add("")
    add(f"Queue size: {summary['review_queue_count']} rows.")
    add("")
    examples(lines, summary["review_queue"], ["amazon_title", "ebay_title", "game_name", "rule_families", "evidence_confidence_group", "operator_review_question"], limit=50)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    confirmed = [row for row in rows if row.get("positive_confidence") == "confirmed_positive"]
    current_blocked = [row for row in confirmed if row.get("current_blocked")]
    lines: list[str] = []
    add = lines.append
    add("# Sourcing Positive Match Safety Audit")
    add("")
    add("Date: 2026-08-01")
    add("")
    add("Scope: read-only safety audit of confirmed positive sourcing matches. No production data, rules, scores, statuses, marketplace data, AI, or deployments were modified.")
    add("")
    add("## Dataset")
    add("")
    table(
        lines,
        ["Metric", "Count"],
        [
            ["Raw positive evidence rows", summary["raw_count"]],
            ["Deduplicated positive rows", summary["deduped_count"]],
            ["Authoritative confirmed positives", summary["confirmed_count"]],
            ["Review-only watching rows", summary["review_only_count"]],
        ],
    )
    add("")
    add("The authoritative positive dataset includes deduplicated `matched_to_purchase`, `purchased_pending_match`, `purchased` actions, and `matching_intelligence_examples.match` rows. `watching` rows were audited separately as review-only because they are not confirmed purchases or verified matches.")
    add("")
    add("## 34 vs 45 Reconciliation")
    add("")
    add("The prior investigation reported 45 current-rule hard blocks across non-open positive/review statuses: 11 `watching`, 11 `purchased_pending_match`, and 23 `matched_to_purchase`. The 34 figure excludes the 11 `watching` rows and counts only accepted/purchased positive statuses. This audit treats 34 as the status-only confirmed-positive safety number and 45 as the broader status-only positive-or-review caution number.")
    add("")
    add(f"The all-source deduplicated audit found {summary['current_blocked_count']} confirmed positives currently hard-blocked because it expands beyond status-only sourcing opportunities to include `matching_intelligence_examples.match` rows and purchased action history.")
    add("")
    add("## Current Evaluator Blocks")
    add("")
    table(lines, ["Rule family", "Count"], summary["current_block_families"].most_common())
    add("")
    add(f"Confirmed positives currently hard-blocked: {summary['current_blocked_count']}.")
    add("")
    examples(lines, current_blocked, ["asin", "amazon_title", "ebay_title", "current_hard_blocks"], limit=25)
    add("")
    add("The CSV contains every confirmed/review positive row and every current/proposed block flag. Markdown examples are capped at 25 rows per section for readability.")
    add("")
    add("Canada location blocking is treated as intentional business policy for this audit. Canadian positives are still reported in the CSV when present, but this audit does not recommend relaxing the Canada location block.")
    add("")
    add("## Proposed Rule Simulation")
    add("")
    table(
        lines,
        ["Simulation", "Confirmed positives blocked", "Recommendation"],
        [
            ["Game Name strict token-set block", summary["sim_counts"].get("game_name_strict", 0), "Needs relaxation; exact token-set matching is too strict for confirmed positives."],
            ["Numeric/installment strict block", summary["sim_counts"].get("numeric_installment_strict", 0), "Needs relaxation and title-family guards before implementation."],
            ["Edition-family strict block", summary["sim_counts"].get("edition_family_strict", 0), "Needs relaxation; use review/penalty first unless high-confidence edition evidence exists."],
            ["Short-title strict block", summary["sim_counts"].get("short_title_strict", 0), "Needs relaxation; short-title ambiguity should route to review, not hard block."],
        ],
    )
    add("")
    add("### Game Name Simulation")
    add("")
    game_rows = [row for row in confirmed if row.get("game_name_strict_block")]
    examples(lines, game_rows, ["asin", "amazon_title", "ebay_title", "game_name", "game_name_strict_reason"], limit=25)
    add("")
    add("### Numeric / Rock Band Simulation")
    add("")
    numeric_rows = [row for row in confirmed if row.get("numeric_installment_strict_block")]
    rock_rows = summary["rock_band_rows"]
    add(f"Rock Band-related confirmed positives found: {len(rock_rows)}.")
    examples(lines, rock_rows, ["asin", "amazon_title", "ebay_title", "numeric_installment_strict_reason"], limit=25)
    add("")
    add("Numeric simulation examples:")
    examples(lines, numeric_rows, ["asin", "amazon_title", "ebay_title", "numeric_installment_strict_reason"], limit=25)
    add("")
    add("### Edition-Family Safety")
    add("")
    edition_rows = [row for row in confirmed if row.get("edition_family_strict_block")]
    examples(lines, edition_rows, ["asin", "amazon_title", "ebay_title", "edition_family_strict_reason"], limit=25)
    add("")
    add("### Short-Title Safety")
    add("")
    short_rows = [row for row in confirmed if row.get("short_title_strict_block")]
    examples(lines, short_rows, ["asin", "amazon_title", "ebay_title", "short_title_strict_reason"], limit=25)
    add("")
    add("## Recommendations")
    add("")
    add("- Presentation gate: safe to deploy as written. It only honors stored hard-block diagnostics for `open` rows before presentation and does not rescore or modify confirmed positives.")
    add("- Safe now: enforcement of already-stored hard blocks at presentation; exact historical negative memory for future candidates when the positive-memory conflict is absent.")
    add("- Needs relaxation: strict Game Name token-set blocks, Rock Band/Rock Band 3-style numeric blocks, expanded edition-family hard blocks, and short-title hard blocks.")
    add("- Recommended backoff: use review/probable-non-match for proposed identity expansions until confirmed-positive fixtures are added and false positives are cleared.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def examples(lines: list[str], rows: list[dict[str, Any]], fields: list[str], *, limit: int) -> None:
    if not rows:
        lines.append("No rows.")
        return
    table(lines, fields, [[row.get(field) for field in fields] for row in rows[:limit]])


def table(lines: list[str], headers: list[str], rows: list[Any]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        values = row if isinstance(row, (list, tuple)) else list(row)
        lines.append("| " + " | ".join(clean_md(value) for value in values) + " |")


def block_family(blocks: list[str]) -> str:
    if not blocks:
        return ""
    text = " ".join(blocks).casefold()
    families = [
        ("location", "location"),
        ("platform", "platform"),
        ("numeric", "numeric"),
        ("edition", "edition"),
        ("category", "category"),
        ("accessory", "accessory"),
        ("digital", "digital"),
        ("incomplete", "incomplete"),
        ("region", "region"),
        ("title_overlap", "title token"),
        ("game_name", "game name"),
    ]
    return next((label for label, needle in families if needle in text), "other")


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


def normalize_text(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def normalize_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def combined_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "amazon_title",
            "ebay_title",
            "game_name",
            "ebay_description",
            "category",
            "features",
            "type",
            "format",
            "release_year",
        )
    ).casefold()


def numbers_in_text(value: Any) -> set[str]:
    return set(re.findall(r"(?<![a-z0-9])(?:19|20)\d{2}(?![a-z0-9])|(?<![a-z0-9])(?:[2-9]|[1-9][0-9]|[1-9][0-9]{2,3})(?![a-z0-9])", str(value or "").casefold()))


def sports_title(value: Any) -> bool:
    text = str(value or "").casefold()
    return any(
        token in text
        for token in (
            "madden",
            "fifa",
            "nba 2k",
            "nhl",
            "mlb",
            "ncaa football",
            "wwe 2k",
            "ufc",
            "pga",
        )
    )


def title_core_overlap(row: dict[str, Any]) -> bool:
    amazon_tokens = meaningful_title_tokens(row.get("amazon_title"))
    ebay_tokens = meaningful_title_tokens(row.get("ebay_title"))
    shared = amazon_tokens & ebay_tokens
    return bool(shared and len(shared) >= min(len(amazon_tokens), len(ebay_tokens), 2))


def is_rock_band(row: dict[str, Any]) -> bool:
    return "rock band" in f"{row.get('amazon_title')} {row.get('ebay_title')} {row.get('game_name')}".casefold()


def weak_evidence(row: dict[str, Any]) -> bool:
    return evidence_confidence_group(row) in {
        "Purchase pending / weaker positive",
        "Watch-only / not a confirmed match",
        "Insufficient evidence",
    }


def clean_md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def json_ready(value: Any) -> Any:
    if isinstance(value, Counter):
        return dict(value)
    if isinstance(value, defaultdict):
        return dict(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
