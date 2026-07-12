"""Run the on-demand MBOP sourcing workflow for one sourcing run."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from typing import Any

from ebay_api_limits import browse_call_budget, fetch_browse_quota, quota_summary
from sourcing_common import get_supabase_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    if not args.single_pass:
        try:
            return run_progressive(args)
        except Exception as error:
            mark_run_failed(args.run_id, str(error))
            raise

    seed_limit = args.seed_limit or default_seed_limit(args.run_type)
    search_limit = args.search_limit or default_search_limit(args.run_type, seed_limit)
    steps = [
        [
            "integrations/build_sourcing_seed_asins.py",
            "--mode",
            args.run_type,
            "--limit",
            str(seed_limit),
            "--run-id",
            args.run_id,
            "--replace-run",
        ],
        [
            "integrations/ebay_sourcing_search.py",
            "--run-id",
            args.run_id,
            "--limit",
            str(search_limit),
            "--max-results-per-asin",
            str(args.max_results_per_asin),
        ],
        [
            "integrations/score_sourcing_opportunities.py",
            "--run-id",
            args.run_id,
            "--replace-run",
        ],
    ]

    try:
        for step in steps:
            print(f"\n--- python {' '.join(step)} ---", flush=True)
            subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
        return 0
    except Exception as error:
        mark_run_failed(args.run_id, str(error))
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MBOP sourcing workflow.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-type", choices=["recent_sales", "full_listings"], required=True)
    parser.add_argument("--seed-limit", type=int, default=None)
    parser.add_argument("--search-limit", type=int, default=None)
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--target-opportunities", type=int, default=0, help="Optional row target. Default 0 spends the daily Browse quota.")
    parser.add_argument("--seed-chunk-size", type=int, default=50)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Optional cap after eBay Analytics quota preflight.")
    parser.add_argument("--browse-quota-reserve", type=int, default=0, help="Browse calls to leave unused for other MBOP jobs.")
    parser.add_argument("--continue-run", action="store_true")
    parser.add_argument("--single-pass", action="store_true", help="Run the legacy single search slice workflow.")
    return parser.parse_args()


def default_seed_limit(run_type: str) -> int:
    return 5000 if run_type == "full_listings" else 250


def default_search_limit(run_type: str, seed_limit: int) -> int:
    return seed_limit if run_type == "full_listings" else 50


def run_progressive(args: argparse.Namespace) -> int:
    if args.single_pass:
        args.target_opportunities = None
        return main()

    supabase = get_supabase_client()
    seed_limit = args.seed_limit or default_seed_limit(args.run_type)
    target = max(args.target_opportunities or 0, 0)
    chunk_size = max(args.seed_chunk_size, 1)
    quota = fetch_browse_quota()
    quota_budget = browse_call_budget(quota, args.browse_quota_reserve)
    max_api_calls = min_positive(args.max_api_calls, quota_budget)
    batch_sequence = next_batch_sequence(supabase, args.run_id)
    batch = create_batch(supabase, args.run_id, batch_sequence, target)
    batch_id = batch["batch_id"]
    if max_api_calls == 0:
        complete_quota_exhausted_batch(
            supabase,
            batch_id,
            args.run_id,
            batch_sequence,
            target,
            quota,
            args.browse_quota_reserve,
        )
        print(f"Progressive sourcing batch {batch_sequence}: out of eBay Browse quota")
        return 0

    try:
        if not args.continue_run:
            run_python(
                [
                    "integrations/build_sourcing_seed_asins.py",
                    "--mode",
                    args.run_type,
                    "--limit",
                    str(seed_limit),
                    "--run-id",
                    args.run_id,
                    "--replace-run",
                ]
            )

        source_count = count_run_rows(supabase, "sourcing_seed_asins", args.run_id)
        cumulative_offset = previous_cumulative_seeds(supabase, args.run_id, batch_sequence)
        offset = min(cumulative_offset, source_count)
        api_calls_used = 0
        stop_reason = "no_seeds_remaining"

        while offset < source_count:
            remaining_budget = None if max_api_calls is None else max(max_api_calls - api_calls_used, 0)
            if remaining_budget == 0:
                stop_reason = "ebay_out_of_quota"
                break
            search_limit = min(chunk_size, source_count - offset)
            if remaining_budget is not None:
                search_limit = min(search_limit, remaining_budget)
            search_step = [
                "integrations/ebay_sourcing_search.py",
                "--run-id",
                args.run_id,
                "--offset",
                str(offset),
                "--limit",
                str(search_limit),
                "--max-results-per-asin",
                str(args.max_results_per_asin),
            ]
            if remaining_budget is not None:
                search_step.extend(["--max-api-calls", str(remaining_budget)])
            run_python(
                search_step
            )
            search_summary = fetch_ebay_search_summary(supabase, args.run_id)
            searched_this_chunk = int_value(search_summary.get("searched_seed_count"), search_limit)
            calls_this_chunk = int_value(search_summary.get("api_call_count"), searched_this_chunk)
            offset += searched_this_chunk
            api_calls_used += calls_this_chunk

            run_python(
                [
                    "integrations/score_sourcing_opportunities.py",
                    "--run-id",
                    args.run_id,
                    "--update-existing",
                ]
            )
            mark_run_running(supabase, args.run_id)

            selected = select_unbatched_open_opportunities(supabase, args.run_id, target)
            update_batch_progress(
                supabase,
                batch_id,
                args.run_id,
                target,
                offset - cumulative_offset,
                offset,
                source_count - offset,
                api_calls_used,
            )
            if target and len(selected) >= target:
                stop_reason = "target_reached"
                break
            if search_summary.get("stop_reason") == "ebay_out_of_quota":
                stop_reason = "ebay_out_of_quota"
                break
            if search_summary.get("rate_limited"):
                stop_reason = "ebay_rate_limited"
                break
            if max_api_calls is not None and api_calls_used >= max_api_calls:
                stop_reason = "ebay_out_of_quota"
                break

        selected = select_unbatched_open_opportunities(supabase, args.run_id, target)
        write_batch_items(supabase, batch_id, args.run_id, selected)
        funnel = summarize_funnel(supabase, args.run_id, batch_id)
        complete_batch(
            supabase,
            batch_id,
            args.run_id,
            batch_sequence,
            target,
            selected,
            funnel,
            offset - cumulative_offset,
            offset,
            source_count - offset,
            api_calls_used,
            stop_reason,
            quota,
            args.browse_quota_reserve,
        )
        requested_label = "daily quota" if target == 0 else str(target)
        print(f"Progressive sourcing batch {batch_sequence}: {len(selected)}/{requested_label} opportunities ({stop_reason})")
        return 0
    except Exception as error:
        fail_batch(supabase, batch_id, str(error))
        raise


def run_python(step: list[str]) -> None:
    print(f"\n--- python {' '.join(step)} ---", flush=True)
    subprocess.run([sys.executable, *step], cwd=ROOT, check=True)


def create_batch(supabase, run_id: str, sequence: int, target: int) -> dict[str, Any]:
    response = (
        supabase.table("sourcing_opportunity_batches")
        .insert(
            {
                "sourcing_run_id": run_id,
                "batch_sequence": sequence,
                "status": "running",
                "requested_opportunity_count": target,
                "started_at": now_iso(),
            }
        )
        .execute()
    )
    return (response.data or [{}])[0]


def next_batch_sequence(supabase, run_id: str) -> int:
    response = (
        supabase.table("sourcing_opportunity_batches")
        .select("batch_sequence")
        .eq("sourcing_run_id", run_id)
        .order("batch_sequence", desc=True)
        .limit(1)
        .execute()
    )
    row = (response.data or [{}])[0]
    return int(row.get("batch_sequence") or 0) + 1


def previous_cumulative_seeds(supabase, run_id: str, batch_sequence: int) -> int:
    if batch_sequence <= 1:
        return 0
    response = (
        supabase.table("sourcing_opportunity_batches")
        .select("cumulative_seeds_searched")
        .eq("sourcing_run_id", run_id)
        .lt("batch_sequence", batch_sequence)
        .order("batch_sequence", desc=True)
        .limit(1)
        .execute()
    )
    row = (response.data or [{}])[0]
    return int(row.get("cumulative_seeds_searched") or 0)


def count_run_rows(supabase, table_name: str, run_id: str) -> int:
    response = supabase.table(table_name).select("sourcing_run_id", count="exact").eq("sourcing_run_id", run_id).limit(1).execute()
    return int(response.count or 0)


def fetch_ebay_search_summary(supabase, run_id: str) -> dict[str, Any]:
    response = (
        supabase.table("sourcing_runs")
        .select("raw_summary_json")
        .eq("sourcing_run_id", run_id)
        .maybe_single()
        .execute()
    )
    raw_summary = (response.data or {}).get("raw_summary_json") or {}
    if not isinstance(raw_summary, dict):
        return {}
    search_summary = raw_summary.get("ebay_search") or {}
    return search_summary if isinstance(search_summary, dict) else {}


def select_unbatched_open_opportunities(supabase, run_id: str, target: int) -> list[dict[str, Any]]:
    batched_ids = batched_opportunity_ids(supabase, run_id)
    limit = target * 5 if target else 5000
    response = (
        supabase.table("sourcing_opportunities")
        .select("opportunity_id,asin,ebay_item_id,score,opportunity_type,created_at")
        .eq("sourcing_run_id", run_id)
        .eq("status", "open")
        .in_("opportunity_type", ["buy_now", "multi_unit", "best_offer", "auction"])
        .order("score", desc=True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return choose_batch_opportunities(response.data or [], batched_ids, target)


def choose_batch_opportunities(rows: list[dict[str, Any]], batched_ids: set[str], target: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ebay_ids: set[str] = set()
    for row in rows:
        opportunity_id = str(row.get("opportunity_id") or "")
        if not opportunity_id or opportunity_id in batched_ids:
            continue
        if row.get("status") not in {None, "open"}:
            continue
        if row.get("opportunity_type") not in {None, "buy_now", "multi_unit", "best_offer", "auction"}:
            continue
        ebay_key = clean_ebay_key(row.get("ebay_item_id"))
        if ebay_key and ebay_key in seen_ebay_ids:
            continue
        if ebay_key:
            seen_ebay_ids.add(ebay_key)
        selected.append(row)
        if target and len(selected) >= target:
            break
    return selected


def batched_opportunity_ids(supabase, run_id: str) -> set[str]:
    response = (
        supabase.table("sourcing_opportunity_batch_items")
        .select("opportunity_id")
        .eq("sourcing_run_id", run_id)
        .execute()
    )
    return {str(row.get("opportunity_id")) for row in response.data or [] if row.get("opportunity_id")}


def write_batch_items(supabase, batch_id: str, run_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    items = [
        {
            "batch_id": batch_id,
            "sourcing_run_id": run_id,
            "opportunity_id": row["opportunity_id"],
            "asin": row.get("asin"),
            "ebay_item_id": row.get("ebay_item_id"),
            "score": row.get("score"),
            "opportunity_type": row.get("opportunity_type"),
        }
        for row in rows
    ]
    supabase.table("sourcing_opportunity_batch_items").insert(items).execute()


def summarize_funnel(supabase, run_id: str, batch_id: str) -> dict[str, Any]:
    opportunities = fetch_run_opportunity_summary(supabase, run_id)
    open_rows = [row for row in opportunities if row.get("status") == "open"]
    rejected_rows = [row for row in opportunities if row.get("status") == "rejected"]
    hard_blocked = [row for row in opportunities if has_blocked_flag(row)]
    batch_items = (
        supabase.table("sourcing_opportunity_batch_items")
        .select("opportunity_id")
        .eq("batch_id", batch_id)
        .execute()
        .data
        or []
    )
    return summarize_funnel_from_rows(opportunities, batch_item_count=len(batch_items))


def summarize_funnel_from_rows(opportunities: list[dict[str, Any]], *, batch_item_count: int) -> dict[str, Any]:
    open_rows = [row for row in opportunities if row.get("status") == "open"]
    rejected_rows = [row for row in opportunities if row.get("status") == "rejected"]
    hard_blocked = [row for row in opportunities if has_blocked_flag(row)]
    return {
        "scored_opportunities": len(opportunities),
        "valid_open_opportunities": len(open_rows),
        "batch_opportunities": batch_item_count,
        "rejected_opportunities": len(rejected_rows),
        "hard_blocked_opportunities": len(hard_blocked),
        "profitability_rejects": max(len(rejected_rows) - len(hard_blocked), 0),
        "review_or_watch": len([row for row in opportunities if row.get("opportunity_type") == "watch"]),
    }


def fetch_run_opportunity_summary(supabase, run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        response = (
            supabase.table("sourcing_opportunities")
            .select("status,opportunity_type,ai_flags,matching_diagnostics_json")
            .eq("sourcing_run_id", run_id)
            .range(start, start + 999)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def has_blocked_flag(row: dict[str, Any]) -> bool:
    flags = list(row.get("ai_flags") or [])
    diagnostics = row.get("matching_diagnostics_json") or {}
    if isinstance(diagnostics, dict):
        flags.extend(diagnostics.get("flags") or [])
    return any(str(flag).startswith("Blocked:") for flag in flags)


def update_batch_progress(
    supabase,
    batch_id: str,
    run_id: str,
    target: int,
    seeds_searched: int,
    cumulative_seeds: int,
    seeds_remaining: int,
    api_calls_used: int,
) -> None:
    selected_count = len(select_unbatched_open_opportunities(supabase, run_id, target))
    supabase.table("sourcing_opportunity_batches").update(
        {
            "qualifying_opportunity_count": selected_count,
            "seeds_searched": seeds_searched,
            "cumulative_seeds_searched": cumulative_seeds,
            "seeds_remaining": seeds_remaining,
            "api_call_count": api_calls_used,
            "updated_at": now_iso(),
        }
    ).eq("batch_id", batch_id).execute()


def complete_batch(
    supabase,
    batch_id: str,
    run_id: str,
    sequence: int,
    target: int,
    selected: list[dict[str, Any]],
    funnel: dict[str, Any],
    seeds_searched: int,
    cumulative_seeds: int,
    seeds_remaining: int,
    api_calls_used: int,
    stop_reason: str,
    quota=None,
    quota_reserve: int = 0,
) -> None:
    completed_at = now_iso()
    candidate_count = count_run_rows(supabase, "sourcing_ebay_candidates", run_id)
    opportunity_count = count_run_rows(supabase, "sourcing_opportunities", run_id)
    batch_update = {
        "status": "completed",
        "qualifying_opportunity_count": len(selected),
        "cumulative_qualifying_count": batched_count(supabase, run_id),
        "seeds_searched": seeds_searched,
        "cumulative_seeds_searched": cumulative_seeds,
        "seeds_remaining": seeds_remaining,
        "candidates_found": candidate_count,
        "hard_blocked_count": funnel.get("hard_blocked_opportunities", 0),
        "profitability_reject_count": funnel.get("profitability_rejects", 0),
        "api_call_count": api_calls_used,
        "stop_reason": stop_reason,
        "funnel_json": {
            **funnel,
            "ebay_browse_quota": quota_summary(quota),
            "ebay_browse_quota_reserve": quota_reserve,
        },
        "completed_at": completed_at,
        "updated_at": completed_at,
    }
    supabase.table("sourcing_opportunity_batches").update(batch_update).eq("batch_id", batch_id).execute()
    supabase.table("sourcing_runs").update(
        {
            "status": "completed",
            "completed_at": completed_at,
            "search_count": cumulative_seeds,
            "candidate_count": candidate_count,
            "opportunity_count": opportunity_count,
            "api_call_count": api_calls_used,
            "raw_summary_json": {
                "progressive_batch": {
                    "batch_id": batch_id,
                    "batch_sequence": sequence,
                    "requested_opportunity_count": target,
                    "qualifying_opportunity_count": len(selected),
                    "stop_reason": stop_reason,
                    "funnel": funnel,
                    "ebay_browse_quota": quota_summary(quota),
                    "ebay_browse_quota_reserve": quota_reserve,
                }
            },
        }
    ).eq("sourcing_run_id", run_id).execute()


def complete_quota_exhausted_batch(
    supabase,
    batch_id: str,
    run_id: str,
    sequence: int,
    target: int,
    quota,
    quota_reserve: int,
) -> None:
    reset = (quota_summary(quota) or {}).get("reset")
    message = f"Out of eBay Browse quota. Resets at {reset}." if reset else "Out of eBay Browse quota."
    complete_batch(
        supabase,
        batch_id,
        run_id,
        sequence,
        target,
        [],
        {"quota_message": message},
        0,
        previous_cumulative_seeds(supabase, run_id, sequence),
        None,
        0,
        "ebay_out_of_quota",
        quota,
        quota_reserve,
    )
    supabase.table("sourcing_runs").update({"error_message": message}).eq("sourcing_run_id", run_id).execute()


def batched_count(supabase, run_id: str) -> int:
    response = supabase.table("sourcing_opportunity_batch_items").select("batch_item_id", count="exact").eq("sourcing_run_id", run_id).limit(1).execute()
    return int(response.count or 0)


def fail_batch(supabase, batch_id: str, message: str) -> None:
    supabase.table("sourcing_opportunity_batches").update(
        {
            "status": "failed",
            "stop_reason": "failed",
            "funnel_json": {"error": message[:1000]},
            "completed_at": now_iso(),
            "updated_at": now_iso(),
        }
    ).eq("batch_id", batch_id).execute()


def mark_run_running(supabase, run_id: str) -> None:
    supabase.table("sourcing_runs").update({"status": "running"}).eq("sourcing_run_id", run_id).execute()


def clean_ebay_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("v1|"):
        parts = text.split("|")
        return parts[1] if len(parts) > 1 else text
    return text


def mark_run_failed(run_id: str, message: str) -> None:
    try:
        get_supabase_client().table("sourcing_runs").update(
            {
                "status": "failed",
                "completed_at": now_iso(),
                "error_message": message[:1000],
            }
        ).eq("sourcing_run_id", run_id).execute()
    except Exception as update_error:  # noqa: BLE001 - best-effort task cleanup
        print(f"Could not mark sourcing run {run_id} failed: {update_error}", flush=True)


def min_positive(*values: int | None) -> int | None:
    positive = [value for value in values if value is not None and value >= 0]
    if not positive:
        return None
    return min(positive)


def int_value(value: Any, fallback: int) -> int:
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
