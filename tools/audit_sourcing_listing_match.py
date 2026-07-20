"""Read-only diagnostic for a specific ASIN and eBay listing in sourcing."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from ebay_sourcing_search import search_queries_for_seed  # noqa: E402
from sourcing_common import get_supabase_client  # noqa: E402


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    asin = args.asin.upper()
    wanted_ids = {args.missing_ebay_id, args.found_ebay_id}

    seeds = fetch_rows(
        supabase,
        "sourcing_seed_asins",
        "seed_id,sourcing_run_id,asin,amazon_title,target_sale_price,target_sale_price_source,priority_bucket,queue_position,raw_context_json,created_at",
        "asin",
        asin,
    )
    print(f"Seeds for {asin}: {len(seeds)}")
    for seed in seeds[:12]:
        print(
            f"- run={seed.get('sourcing_run_id')} seed={seed.get('seed_id')} "
            f"bucket={seed.get('priority_bucket')} pos={seed.get('queue_position')} "
            f"title={seed.get('amazon_title')!r}"
        )
        print(f"  queries={search_queries_for_seed(seed)}")

    candidates = fetch_rows(
        supabase,
        "sourcing_ebay_candidates",
        "candidate_id,sourcing_run_id,seed_id,asin,ebay_item_id,ebay_legacy_item_id,ebay_title,price,shipping_cost,landed_cost,buying_options,raw_ebay_json,last_seen_at",
        "asin",
        asin,
    )
    print(f"\nCandidates for {asin}: {len(candidates)}")
    matching_candidates = [
        row
        for row in candidates
        if legacy_id(row.get("ebay_item_id")) in wanted_ids
        or legacy_id(row.get("ebay_legacy_item_id")) in wanted_ids
    ]
    print(f"Candidates matching requested eBay IDs: {len(matching_candidates)}")
    for row in matching_candidates:
        print_candidate(row)

    opportunities = fetch_rows(
        supabase,
        "sourcing_opportunities",
        "opportunity_id,sourcing_run_id,candidate_id,asin,ebay_item_id,opportunity_type,status,profit,roi_percent,score,ai_flags,matching_diagnostics_json,created_at,updated_at",
        "asin",
        asin,
    )
    print(f"\nOpportunities for {asin}: {len(opportunities)}")
    matching_opps = [
        row
        for row in opportunities
        if legacy_id(row.get("ebay_item_id")) in wanted_ids
    ]
    print(f"Opportunities matching requested eBay IDs: {len(matching_opps)}")
    for row in matching_opps:
        print_opportunity(row)

    run_ids = sorted({str(seed.get("sourcing_run_id")) for seed in seeds if seed.get("sourcing_run_id")})
    print("\nRun summaries")
    for run in fetch_by_ids(
        supabase,
        "sourcing_runs",
        "sourcing_run_id,run_type,status,started_at,completed_at,search_count,candidate_count,opportunity_count,raw_summary_json",
        "sourcing_run_id",
        run_ids,
    ):
        summary = run.get("raw_summary_json") or {}
        ebay = summary.get("ebay_search") if isinstance(summary, dict) else {}
        print(
            f"- run={run.get('sourcing_run_id')} started={run.get('started_at')} "
            f"search_count={run.get('search_count')} candidates={run.get('candidate_count')} "
            f"opps={run.get('opportunity_count')}"
        )
        if isinstance(ebay, dict):
            print(
                f"  returned={ebay.get('search_results_returned_count')} "
                f"filtered={ebay.get('summary_filtered_count')} "
                f"profit_filtered={ebay.get('summary_profitability_filtered_count')} "
                f"details={ebay.get('detail_call_count')}"
            )

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit one ASIN/eBay sourcing match.")
    parser.add_argument("--asin", required=True)
    parser.add_argument("--missing-ebay-id", required=True)
    parser.add_argument("--found-ebay-id", required=True)
    return parser.parse_args()


def fetch_rows(supabase: Any, table: str, columns: str, column: str, value: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            supabase.table(table)
            .select(columns)
            .eq(column, value)
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def fetch_by_ids(supabase: Any, table: str, columns: str, column: str, values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    return (
        supabase.table(table)
        .select(columns)
        .in_(column, values)
        .execute()
        .data
        or []
    )


def print_candidate(row: dict[str, Any]) -> None:
    raw = row.get("raw_ebay_json") or {}
    print(
        f"- candidate={row.get('candidate_id')} run={row.get('sourcing_run_id')} "
        f"item={row.get('ebay_item_id')} legacy={row.get('ebay_legacy_item_id')} "
        f"price={row.get('price')} ship={row.get('shipping_cost')} title={row.get('ebay_title')!r}"
    )
    if isinstance(raw, dict):
        print(f"  search_query={raw.get('_mbop_search_query')!r}")
        print(f"  item_url={raw.get('itemWebUrl')!r}")


def print_opportunity(row: dict[str, Any]) -> None:
    diagnostics = row.get("matching_diagnostics_json") or {}
    print(
        f"- opp={row.get('opportunity_id')} run={row.get('sourcing_run_id')} "
        f"item={row.get('ebay_item_id')} status={row.get('status')} "
        f"type={row.get('opportunity_type')} profit={row.get('profit')} roi={row.get('roi_percent')} score={row.get('score')}"
    )
    print(f"  flags={row.get('ai_flags')}")
    if isinstance(diagnostics, dict):
        print(f"  recommendation={diagnostics.get('recommendation')}")
        print(f"  platform={diagnostics.get('platform_rule')}")
        static = diagnostics.get("static_rules") or {}
        if isinstance(static, dict):
            print(f"  hard_blocks={static.get('hard_blocks')}")
            print(f"  warnings={static.get('warnings')}")


def legacy_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("v1|"):
        parts = text.split("|")
        return parts[1] if len(parts) > 1 else text
    return text


if __name__ == "__main__":
    raise SystemExit(main())
