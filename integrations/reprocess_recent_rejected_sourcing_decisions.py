"""Populate rejection decision traces for recent rejected sourcing opportunities."""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
    opportunities = fetch_rejected_opportunities(supabase, args.limit)
    keepa = fetch_keepa_price_context_by_asin(supabase, [row.get("asin") for row in opportunities])
    historical = fetch_historical_status_by_key(supabase)
    matching_context = fetch_matching_context(supabase)

    results = []
    evaluated_at = dt.datetime.now(dt.UTC).isoformat()
    for opportunity in dedupe_opportunities(opportunities):
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
            status=opportunity.get("status"),
            opportunity_type=scored.get("opportunity_type"),
            profit=scored.get("profit"),
            roi_percent=scored.get("roi_percent"),
            listing_status=candidate.get("listing_status"),
            evaluated_at=evaluated_at,
        )
        results.append(compare_opportunity(opportunity, scored, diagnostics))

    summary = summarize(results)
    artifact = write_artifacts(results, summary, args.write)
    print_summary(summary, artifact, args.write)

    if args.write:
        write_updates(supabase, results)
        print(f"Rows written: {summary['diagnostic_update_count']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reprocess recent rejected sourcing opportunities for decision traces.")
    parser.add_argument("--limit", type=int, default=500, help="Most recent rejected rows to inspect before de-duping.")
    parser.add_argument("--write", action="store_true", help="Persist matching_diagnostics_json only.")
    return parser.parse_args()


def fetch_rejected_opportunities(supabase, limit: int) -> list[dict[str, Any]]:
    return (
        supabase.table("sourcing_opportunities")
        .select("*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)")
        .eq("status", "rejected")
        .order("updated_at", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


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


def compare_opportunity(opportunity: dict[str, Any], scored: dict[str, Any], diagnostics: dict[str, Any]) -> dict[str, Any]:
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
        "reason_changed": reason_code(old_decision) != reason_code(new_decision),
        "final_recommendation_changed": old_decision.get("finalRecommendation") != new_decision.get("finalRecommendation"),
        "diagnostics": diagnostics,
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
    }


def write_updates(supabase, results: list[dict[str, Any]]) -> None:
    for batch in chunked(results, 100):
        for row in batch:
            supabase.table("sourcing_opportunities").update(
                {
                    "matching_diagnostics_json": row["diagnostics"],
                    "updated_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            ).eq("opportunity_id", row["opportunity_id"]).execute()


def write_artifacts(results: list[dict[str, Any]], summary: dict[str, Any], write: bool) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    mode = "write" if write else "dry_run"
    path = ROOT / "tmp" / f"sourcing_rejected_decision_trace_{mode}_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact_rows = [{key: value for key, value in row.items() if key != "diagnostics"} for row in results]
    path.write_text(json.dumps({"summary": summary, "rows": artifact_rows}, indent=2, default=str), encoding="utf-8")
    return path


def print_summary(summary: dict[str, Any], artifact: Path, write: bool) -> None:
    print("Rejected sourcing decision trace reprocess")
    print("------------------------------------------")
    print(f"Mode: {'write' if write else 'dry-run'}")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Artifact: {artifact}")


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


if __name__ == "__main__":
    raise SystemExit(main())
