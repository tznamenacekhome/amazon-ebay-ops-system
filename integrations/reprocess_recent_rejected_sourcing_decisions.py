"""Populate rejection decision traces for recent rejected sourcing opportunities."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from sourcing_common import chunked, fetch_settings, get_supabase_client
from sourcing_decision_trace import enrich_sourcing_diagnostics
from score_sourcing_opportunities import (
    fetch_historical_status_by_key,
    fetch_keepa_price_context_by_asin,
    fetch_matching_context,
    score_candidate,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    lightweight_scan = bool(args.days) or args.only_generic_fallback
    opportunities = fetch_rejected_opportunities(supabase, args.limit, args.days, lightweight=lightweight_scan)
    if args.only_generic_fallback:
        opportunities = [row for row in opportunities if fallback_reason_code(row) == "status_rejected_without_block"]
    if args.only_stale_reason:
        stale_codes = {None, "status_rejected_without_block", "unknown_rejection", "duplicate_history"}
        opportunities = [
            row
            for row in opportunities
            if persisted_primary_reason_code(row.get("matching_diagnostics_json")) in stale_codes
        ]
    if lightweight_scan:
        opportunities = fetch_opportunities_by_id(supabase, [str(row["opportunity_id"]) for row in opportunities if row.get("opportunity_id")])
    keepa = fetch_keepa_price_context_by_asin(supabase, [row.get("asin") for row in opportunities])
    historical = fetch_historical_status_by_key(supabase)
    matching_context = fetch_matching_context(supabase)

    results = []
    evaluated_at = dt.datetime.now(dt.UTC).isoformat()
    scoped_opportunities = opportunities if args.days or args.only_generic_fallback else dedupe_opportunities(opportunities)
    for opportunity in scoped_opportunities:
        candidate = dict(opportunity.get("sourcing_ebay_candidates") or {})
        seed = dict(opportunity.get("sourcing_seed_asins") or {})
        candidate.update(
            {
                "sourcing_run_id": opportunity.get("sourcing_run_id"),
                "seed_id": opportunity.get("seed_id"),
                "candidate_id": opportunity.get("candidate_id"),
                "asin": opportunity.get("asin"),
            }
        )
        scored = score_candidate(candidate, seed, settings, keepa, historical, matching_context)
        if not scored:
            continue
        diagnostics = enrich_sourcing_diagnostics(
            scored.get("matching_diagnostics_json"),
            status=scored.get("status"),
            opportunity_type=scored.get("opportunity_type"),
            profit=scored.get("profit"),
            roi_percent=scored.get("roi_percent"),
            listing_status=candidate.get("listing_status"),
            evaluated_at=evaluated_at,
        )
        results.append(compare_opportunity(opportunity, scored, diagnostics, promote_valid=args.promote_valid))

    summary = summarize(results)
    artifact = write_artifacts(results, summary, args.write)
    print_summary(summary, artifact, args.write)

    if args.write:
        written = write_updates(supabase, results, promote_valid=args.promote_valid, promotions_only=args.promotions_only)
        print(f"Rows written: {written}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reprocess recent rejected sourcing opportunities for decision traces.")
    parser.add_argument("--limit", type=int, default=500, help="Most recent rejected rows to inspect before de-duping.")
    parser.add_argument("--days", type=int, help="Select rejected rows created in the last N days instead of latest N by update time.")
    parser.add_argument("--only-generic-fallback", action="store_true", help="Only process rows that currently resolve to status_rejected_without_block.")
    parser.add_argument("--only-stale-reason", action="store_true", help="Only process rows with missing/generic/old duplicate-history primary reasons.")
    parser.add_argument("--promote-valid", action="store_true", help="Move rows that current rules score as open back to review/open status.")
    parser.add_argument("--promotions-only", action="store_true", help="When writing, update only rows being promoted to open.")
    parser.add_argument("--write", action="store_true", help="Persist diagnostics, and optionally promote valid rows when --promote-valid is set.")
    return parser.parse_args()


def fetch_rejected_opportunities(supabase, limit: int, days: int | None, *, lightweight: bool = False) -> list[dict[str, Any]]:
    columns = (
        "opportunity_id,created_at,updated_at,status,profit,opportunity_type,ai_flags,matching_diagnostics_json"
        if lightweight
        else "*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)"
    )
    query = (
        supabase.table("sourcing_opportunities")
        .select(columns)
        .eq("status", "rejected")
    )
    if days:
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
        query = query.gte("created_at", cutoff.isoformat()).order("created_at", desc=True)
        return paginate_query(query)
    return query.order("updated_at", desc=True).order("created_at", desc=True).limit(limit).execute().data or []


def fetch_opportunities_by_id(supabase, opportunity_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for batch in chunked(opportunity_ids, 50):
        response = execute_with_retries(
            supabase.table("sourcing_opportunities")
            .select("*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)")
            .in_("opportunity_id", batch)
        )
        rows.extend(response.data or [])
    by_id = {str(row.get("opportunity_id")): row for row in rows}
    return [by_id[opportunity_id] for opportunity_id in opportunity_ids if opportunity_id in by_id]


def paginate_query(query, page_size: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def dedupe_opportunities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for row in rows:
        candidate = row.get("sourcing_ebay_candidates") or {}
        key = (
            str(row.get("asin") or "").upper(),
            str(candidate.get("ebay_legacy_item_id") or candidate.get("ebay_item_id") or row.get("ebay_item_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def compare_opportunity(
    opportunity: dict[str, Any],
    scored: dict[str, Any],
    diagnostics: dict[str, Any],
    *,
    promote_valid: bool,
) -> dict[str, Any]:
    old_decision = decision(opportunity.get("matching_diagnostics_json"))
    new_decision = decision(diagnostics)
    return {
        "opportunity_id": opportunity.get("opportunity_id"),
        "asin": opportunity.get("asin"),
        "ebay_item_id": opportunity.get("ebay_item_id"),
        "candidate_id": opportunity.get("candidate_id"),
        "old_status": opportunity.get("status"),
        "current_rules_status": scored.get("status"),
        "current_rules_opportunity_type": scored.get("opportunity_type"),
        "old_primary_reason": reason_code(old_decision),
        "new_primary_reason": reason_code(new_decision),
        "old_trace_count": len(trace(opportunity.get("matching_diagnostics_json"))),
        "new_trace_count": len(trace(diagnostics)),
        "would_be_presentation_eligible": scored.get("status") == "open",
        "will_promote_to_review": promote_valid and scored.get("status") == "open",
        "reason_changed": reason_code(old_decision) != reason_code(new_decision),
        "final_recommendation_changed": old_decision.get("finalRecommendation") != new_decision.get("finalRecommendation"),
        "diagnostics": diagnostics,
        "scored": scored,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    for row in results:
        code = row.get("new_primary_reason") or "none"
        reason_counts[code] = reason_counts.get(code, 0) + 1
    return {
        "rows_in_scope": len(results),
        "diagnostic_update_count": len(results),
        "existing_precise_reason_count": sum(1 for row in results if row.get("old_primary_reason") not in {None, "status_rejected_without_block", "unknown_rejection"}),
        "existing_missing_or_generic_reason_count": sum(1 for row in results if row.get("old_primary_reason") in {None, "status_rejected_without_block", "unknown_rejection"}),
        "primary_reason_changes": sum(1 for row in results if row["reason_changed"]),
        "final_recommendation_changes": sum(1 for row in results if row["final_recommendation_changed"]),
        "new_decision_trace_count": sum(1 for row in results if row["new_trace_count"] > 0),
        "would_be_presentation_eligible_count": sum(1 for row in results if row["would_be_presentation_eligible"]),
        "new_primary_reason_counts": dict(sorted(reason_counts.items())),
        "promote_to_review_count": sum(1 for row in results if row["will_promote_to_review"]),
    }


def write_updates(supabase, results: list[dict[str, Any]], *, promote_valid: bool, promotions_only: bool = False) -> int:
    written = 0
    for batch in chunked(results, 100):
        for row in batch:
            scored = row.get("scored") or {}
            should_promote = promote_valid and row.get("would_be_presentation_eligible")
            if promotions_only and not should_promote:
                continue
            update = {
                "matching_diagnostics_json": row["diagnostics"],
                "updated_at": dt.datetime.now(dt.UTC).isoformat(),
            }
            if should_promote:
                update.update(
                    {
                        "opportunity_type": scored.get("opportunity_type"),
                        "status": "open",
                        "target_sale_price": scored.get("target_sale_price"),
                        "target_sale_price_source": scored.get("target_sale_price_source"),
                        "landed_cost": scored.get("landed_cost"),
                        "profit": scored.get("profit"),
                        "roi_percent": scored.get("roi_percent"),
                        "max_profitable_landed_cost": scored.get("max_profitable_landed_cost"),
                        "max_offer_price": scored.get("max_offer_price"),
                        "required_offer_percent_of_ask": scored.get("required_offer_percent_of_ask"),
                        "max_bid": scored.get("max_bid"),
                        "total_profit_opportunity": scored.get("total_profit_opportunity"),
                        "score": scored.get("score"),
                        "score_reason": scored.get("score_reason"),
                        "warning_flags": scored.get("warning_flags"),
                        "ai_flags": scored.get("ai_flags"),
                        "seller_trust_status": scored.get("seller_trust_status"),
                        "seller_trust_score": scored.get("seller_trust_score"),
                    }
                )
            execute_with_retries(
                supabase.table("sourcing_opportunities").update(
                    update
                ).eq("opportunity_id", row["opportunity_id"])
            )
            written += 1
    return written


def write_artifacts(results: list[dict[str, Any]], summary: dict[str, Any], write: bool) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    mode = "write" if write else "dry_run"
    path = ROOT / "tmp" / f"sourcing_rejected_decision_trace_{mode}_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact_rows = [{key: value for key, value in row.items() if key not in {"diagnostics", "scored"}} for row in results]
    path.write_text(json.dumps({"summary": summary, "rows": artifact_rows}, indent=2, default=str), encoding="utf-8")
    return path


def print_summary(summary: dict[str, Any], artifact: Path, write: bool) -> None:
    print("Rejected sourcing decision trace reprocess")
    print("------------------------------------------")
    print(f"Mode: {'write' if write else 'dry-run'}")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Artifact: {artifact}")


def execute_with_retries(query, attempts: int = 4):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return query.execute()
        except Exception as error:
            last_error = error
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise last_error or RuntimeError("query failed")


def decision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = value.get("presentationDecision")
    return payload if isinstance(payload, dict) else {}


def trace(value: Any) -> list[Any]:
    if not isinstance(value, dict):
        return []
    payload = value.get("decisionTrace")
    return payload if isinstance(payload, list) else []


def reason_code(value: dict[str, Any]) -> str | None:
    primary = value.get("primaryReason")
    if isinstance(primary, dict) and primary.get("code"):
        return str(primary["code"])
    return None


def persisted_primary_reason_code(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return reason_code(decision(value))


def fallback_reason_code(row: dict[str, Any]) -> str:
    diagnostics = row.get("matching_diagnostics_json") if isinstance(row.get("matching_diagnostics_json"), dict) else {}
    decision_payload = diagnostics.get("presentationDecision") if isinstance(diagnostics, dict) else None
    if isinstance(decision_payload, dict):
        primary = decision_payload.get("primaryReason")
        if isinstance(primary, dict) and primary.get("code"):
            return str(primary["code"])

    static_rules = diagnostics.get("static_rules") if isinstance(diagnostics.get("static_rules"), dict) else {}
    hard_blocks = string_list(static_rules.get("hard_blocks") or diagnostics.get("hard_blocks"))
    warnings = string_list(static_rules.get("warnings") or diagnostics.get("warnings") or diagnostics.get("flags"))
    flags = string_list(row.get("ai_flags")) + diagnostic_flags(diagnostics)
    final_recommendation = str(diagnostics.get("recommendation") or static_rules.get("recommendation") or "")
    signal_text = " | ".join(
        hard_blocks
        + warnings
        + [flag for flag in flags if flag.startswith("Blocked:")]
        + ([final_recommendation] if final_recommendation else [])
    ).lower()

    if any(pattern in signal_text for pattern in ["historical non_match", "historical condition_problem", "exact historical"]):
        return "historical_exact_negative"
    if "game name" in signal_text:
        return "game_name_conflict"
    if any(pattern in signal_text for pattern in ["numeric", "identity number", "installment", "sequel"]):
        return "numeric_installment_mismatch"
    if any(pattern in signal_text for pattern in ["platform mismatch", "wrong platform"]):
        return "wrong_platform"
    if "unsupported platform" in signal_text:
        return "unsupported_platform"
    if "edition" in signal_text or "version" in signal_text:
        return "edition_version_conflict"
    if any(pattern in signal_text for pattern in ["digital", "download", "dlc", "account", "service"]):
        return "digital_or_service_listing"
    if any(pattern in signal_text for pattern in ["non-video-game", "not a game", "not-game", "accessory", "category"]):
        return "accessory_not_game"
    if any(pattern in signal_text for pattern in ["incomplete", "disc only", "case only", "missing manual", "missing contents"]):
        return "incomplete_product"
    if any(pattern in signal_text for pattern in ["region", "north american", "non-north", "item location", "pickup"]):
        return "region_or_location"
    if any(pattern in signal_text for pattern in ["no longer available", "unavailable", "ended", "sold out"]):
        return "unavailable_listing"
    if "seller" in signal_text:
        return "seller_policy"
    if (row.get("profit") is not None and row.get("profit") <= 0) or row.get("opportunity_type") == "no_profitable_source_found":
        return "profitability"
    if "probable non-match" in signal_text:
        return "probable_non_match"
    if "review" in final_recommendation.lower():
        return "review_threshold"
    if str(row.get("status") or "").lower() == "rejected":
        return "status_rejected_without_block"
    return "unknown"


def diagnostic_flags(diagnostics: dict[str, Any]) -> list[str]:
    flags = string_list(diagnostics.get("flags"))
    static_rules = diagnostics.get("static_rules") if isinstance(diagnostics.get("static_rules"), dict) else {}
    return flags + string_list(static_rules.get("flags"))


def string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
