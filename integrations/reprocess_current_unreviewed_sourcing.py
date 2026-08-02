from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from sourcing_common import chunked, fetch_settings, get_supabase_client
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
    opportunities = fetch_open_opportunities(supabase, args.limit)
    keepa = fetch_keepa_price_context_by_asin(supabase, [row.get("asin") for row in opportunities])
    historical = fetch_historical_status_by_key(supabase)
    matching_context = fetch_matching_context(supabase)

    results = []
    for opportunity in opportunities:
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
        results.append(compare_opportunity(opportunity, scored))

    summary = summarize(results)
    artifact = write_artifacts(results, summary, args.write)
    print_summary(summary, artifact, args.write)

    if args.write:
        write_updates(supabase, results)
        print(f"Rows written: {summary['rows_processed']}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reprocess current open/unreviewed sourcing opportunities.")
    parser.add_argument("--write", action="store_true", help="Persist recomputed diagnostics/status for in-scope open rows.")
    parser.add_argument("--limit", type=int, help="Optional safety limit for local testing.")
    return parser.parse_args()


def fetch_open_opportunities(supabase, limit: int | None) -> list[dict[str, Any]]:
    query = (
        supabase.table("sourcing_opportunities")
        .select("*,sourcing_ebay_candidates(*),sourcing_seed_asins(*)")
        .eq("status", "open")
        .order("score", desc=True)
        .order("created_at", desc=True)
    )
    if limit:
        query = query.limit(limit)
        return query.execute().data or []

    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        response = query.range(start, start + page_size - 1).execute()
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        start += page_size


def compare_opportunity(opportunity: dict[str, Any], scored: dict[str, Any]) -> dict[str, Any]:
    old_recommendation = recommendation(opportunity.get("matching_diagnostics_json"))
    new_recommendation = recommendation(scored.get("matching_diagnostics_json"))
    old_status = opportunity.get("status")
    new_status = scored.get("status")
    old_score = number_or_none(opportunity.get("score"))
    new_score = number_or_none(scored.get("score"))
    return {
        "opportunity_id": opportunity.get("opportunity_id"),
        "asin": opportunity.get("asin"),
        "ebay_item_id": opportunity.get("ebay_item_id"),
        "candidate_id": opportunity.get("candidate_id"),
        "old_status": old_status,
        "new_status": new_status,
        "old_recommendation": old_recommendation,
        "new_recommendation": new_recommendation,
        "old_score": old_score,
        "new_score": new_score,
        "status_changed": old_status != new_status,
        "recommendation_changed": old_recommendation != new_recommendation,
        "score_changed": old_score != new_score,
        "newly_hard_blocked": new_status == "rejected" and has_block(scored.get("matching_diagnostics_json")),
        "leaves_presentation": new_status != "open",
        "enters_presentation": old_status != "open" and new_status == "open",
        "diagnostic_only_change": old_status == new_status and old_recommendation == new_recommendation and old_score == new_score,
        "scored": scored,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows_in_scope": len(results),
        "rows_processed": len(results),
        "unchanged": sum(1 for row in results if not row["status_changed"] and not row["recommendation_changed"] and not row["score_changed"]),
        "newly_hard_blocked": sum(1 for row in results if row["newly_hard_blocked"]),
        "downgraded": sum(1 for row in results if row["new_status"] == "rejected" and row["old_status"] == "open"),
        "upgraded": sum(1 for row in results if row["new_status"] == "open" and row["old_status"] != "open"),
        "diagnostic_only_changes": sum(1 for row in results if row["diagnostic_only_change"]),
        "rows_leaving_presentation": sum(1 for row in results if row["leaves_presentation"]),
        "rows_entering_presentation": sum(1 for row in results if row["enters_presentation"]),
        "recommendation_changes": sum(1 for row in results if row["recommendation_changed"]),
        "status_transitions": transition_counts(results),
        "purchased_completed_dismissed_touched": 0,
    }


def write_updates(supabase, results: list[dict[str, Any]]) -> None:
    for row in results:
        scored = dict(row["scored"])
        update = {
            "opportunity_type": scored.get("opportunity_type"),
            "status": scored.get("status"),
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
            "matching_diagnostics_json": scored.get("matching_diagnostics_json"),
            "updated_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        supabase.table("sourcing_opportunities").update(update).eq("opportunity_id", row["opportunity_id"]).execute()


def write_artifacts(results: list[dict[str, Any]], summary: dict[str, Any], write: bool) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    mode = "write" if write else "dry_run"
    path = ROOT / "tmp" / f"sourcing_unreviewed_reprocess_{mode}_{timestamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [{key: value for key, value in row.items() if key != "scored"} for row in results]
    path.write_text(json.dumps({"summary": summary, "rows": serializable}, indent=2, default=str), encoding="utf-8")
    return path


def print_summary(summary: dict[str, Any], artifact: Path, write: bool) -> None:
    print("Current unreviewed sourcing reprocess")
    print("-------------------------------------")
    print(f"Mode: {'write' if write else 'dry-run'}")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Artifact: {artifact}")


def recommendation(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    static_rules = value.get("static_rules") if isinstance(value.get("static_rules"), dict) else {}
    return value.get("recommendation") or static_rules.get("recommendation")


def has_block(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    static_rules = value.get("static_rules") if isinstance(value.get("static_rules"), dict) else {}
    return (
        value.get("recommendation") == "Blocked"
        or static_rules.get("recommendation") == "Blocked"
        or bool(value.get("hard_blocks"))
        or bool(static_rules.get("hard_blocks"))
    )


def number_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def transition_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        key = f"{row['old_status']}->{row['new_status']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
