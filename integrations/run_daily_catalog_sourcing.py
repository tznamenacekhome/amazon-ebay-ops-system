"""Run the unified daily MBOP sourcing coverage cycle."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from ebay_api_limits import browse_call_budget, fetch_browse_quota, quota_summary
from run_sourcing_workflow import (
    clean_ebay_key,
    complete_batch,
    create_batch,
    fetch_ebay_search_summary,
    select_unbatched_open_opportunities,
    summarize_funnel,
    write_batch_items,
)
from sourcing_common import chunked, fetch_settings, get_supabase_client
from sourcing_coverage_cycle import (
    PRIORITY_CATALOG_REMAINING,
    PRIORITY_PURCHASED_NOT_SENT,
    PRIORITY_RECENTLY_SOLD,
    build_unified_priority_queue,
    refresh_cycle_metrics,
    seed_row_for_run,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    quota = fetch_browse_quota()
    quota_snapshot = quota_summary(quota)
    budget = browse_call_budget(quota, args.browse_quota_reserve)
    if args.max_api_calls is not None:
        budget = min(budget if budget is not None else args.max_api_calls, args.max_api_calls)

    if args.plan_only:
        queue = build_unified_priority_queue(supabase, settings, limit=args.queue_limit)
        print("Daily catalog sourcing plan")
        print("---------------------------")
        print(f"Eligible ASINs: {len(queue.rows)}")
        print(f"Recently sold: {queue.counts[PRIORITY_RECENTLY_SOLD]}")
        print(f"Purchased not sent to Amazon: {queue.counts[PRIORITY_PURCHASED_NOT_SENT]}")
        print(f"Catalog remaining: {queue.counts[PRIORITY_CATALOG_REMAINING]}")
        print(f"Browse quota remaining: {quota_snapshot.get('remaining')}")
        print(f"Browse quota reserve: {args.browse_quota_reserve}")
        print(f"Usable Browse call budget: {budget}")
        print(f"Browse quota resets: {quota_snapshot.get('reset')}")
        return 0

    cycle = get_or_create_active_cycle(supabase, settings, args.queue_limit)
    added_count = refresh_active_cycle_queue(supabase, cycle["coverage_cycle_id"], settings, args.queue_limit)
    run_id = args.run_id or str(uuid.uuid4())
    create_daily_run(supabase, run_id, cycle["coverage_cycle_id"], settings, quota_snapshot, args.browse_quota_reserve)

    batch = create_batch(supabase, run_id, 1, 0)
    batch_id = batch["batch_id"]
    if budget == 0:
        stop_reason = "quota_reserve_reached"
        finish_daily_run(supabase, run_id, cycle["coverage_cycle_id"], batch_id, stop_reason, quota, args.browse_quota_reserve, 0, 0)
        print("Daily catalog sourcing")
        print("----------------------")
        print(f"Run ID: {run_id}")
        print(f"Coverage cycle: {cycle['coverage_cycle_id']}")
        print("Stop reason: quota_reserve_reached")
        return 0

    searched_total = 0
    api_calls_used = 0
    stop_reason = "no_pending_asins"
    last_queue_position = None

    while True:
        remaining_budget = None if budget is None else max(budget - api_calls_used, 0)
        if remaining_budget == 0:
            stop_reason = "quota_reserve_reached"
            break

        pending = fetch_pending_cycle_items(
            supabase,
            cycle["coverage_cycle_id"],
            min(args.seed_chunk_size, remaining_budget) if remaining_budget is not None else args.seed_chunk_size,
        )
        if not pending:
            stop_reason = "cycle_completed"
            break

        mark_items_status(supabase, [row["cycle_item_id"] for row in pending], "searching")
        insert_seed_rows(supabase, pending, run_id, cycle["coverage_cycle_id"])
        offset = searched_total
        search_limit = len(pending)
        search_step = [
            "integrations/ebay_sourcing_search.py",
            "--run-id",
            run_id,
            "--offset",
            str(offset),
            "--limit",
            str(search_limit),
            "--max-results-per-asin",
            str(args.max_results_per_asin),
        ]
        if remaining_budget is not None:
            search_step.extend(["--max-api-calls", str(remaining_budget)])
        run_python(search_step)

        search_summary = fetch_ebay_search_summary(supabase, run_id)
        searched_this_chunk = int_value(search_summary.get("searched_seed_count"), search_limit)
        calls_this_chunk = int_value(search_summary.get("api_call_count"), searched_this_chunk)
        searched_items = pending[:searched_this_chunk]
        searched_total += searched_this_chunk
        api_calls_used += calls_this_chunk
        last_queue_position = searched_items[-1]["queue_position"] if searched_items else last_queue_position

        run_python(["integrations/score_sourcing_opportunities.py", "--run-id", run_id, "--update-existing"])
        update_cycle_items_after_chunk(supabase, run_id, searched_items, calls_this_chunk)
        refresh_cycle_metrics(supabase, cycle["coverage_cycle_id"], run_id=run_id)

        if searched_this_chunk < len(pending):
            mark_items_status(supabase, [row["cycle_item_id"] for row in pending[searched_this_chunk:]], "retryable_failed")
        if search_summary.get("stop_reason") == "ebay_out_of_quota":
            stop_reason = "quota_reserve_reached"
            break
        if search_summary.get("rate_limited"):
            stop_reason = "ebay_rate_limited"
            break
        if args.single_chunk:
            stop_reason = "manual_chunk_limit"
            break

    selected = select_unbatched_open_opportunities(supabase, run_id, 0)
    write_batch_items(supabase, batch_id, run_id, selected)
    funnel = summarize_funnel(supabase, run_id, batch_id)
    source_count = count_rows(supabase, "sourcing_seed_asins", run_id)
    complete_batch(
        supabase,
        batch_id,
        run_id,
        1,
        0,
        selected,
        funnel,
        searched_total,
        searched_total,
        max(source_count - searched_total, 0),
        api_calls_used,
        stop_reason,
        quota,
        args.browse_quota_reserve,
    )
    finish_daily_run(
        supabase,
        run_id,
        cycle["coverage_cycle_id"],
        batch_id,
        stop_reason,
        quota,
        args.browse_quota_reserve,
        searched_total,
        api_calls_used,
        last_queue_position=last_queue_position,
        added_count=added_count,
    )
    print("Daily catalog sourcing")
    print("----------------------")
    print(f"Run ID: {run_id}")
    print(f"Coverage cycle: {cycle['coverage_cycle_id']}")
    print(f"ASINs searched: {searched_total}")
    print(f"Browse calls used: {api_calls_used}")
    print(f"Opportunities found: {len(selected)}")
    print(f"Stop reason: {stop_reason}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unified daily quota-driven MBOP sourcing.")
    parser.add_argument("--run-id")
    parser.add_argument("--queue-limit", type=int, default=20000)
    parser.add_argument("--seed-chunk-size", type=int, default=50)
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--browse-quota-reserve", type=int, default=0)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Diagnostic cap only; production uses live quota.")
    parser.add_argument("--single-chunk", action="store_true", help="Diagnostic mode for one chunk only.")
    parser.add_argument("--plan-only", action="store_true", help="Read-only plan: build the queue and quota summary without writing rows.")
    return parser.parse_args()


def get_or_create_active_cycle(supabase, settings, queue_limit: int) -> dict[str, Any]:
    response = (
        supabase.table("sourcing_coverage_cycles")
        .select("*")
        .eq("status", "active")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]
    queue = build_unified_priority_queue(supabase, settings, limit=queue_limit)
    cycle_response = (
        supabase.table("sourcing_coverage_cycles")
        .insert(
            {
                "status": "active",
                "total_eligible_asins": len(queue.rows),
                "priority_1_count": queue.counts[PRIORITY_RECENTLY_SOLD],
                "priority_2_count": queue.counts[PRIORITY_PURCHASED_NOT_SENT],
                "priority_3_count": queue.counts[PRIORITY_CATALOG_REMAINING],
                "remaining_count": len(queue.rows),
                "raw_metrics_json": {"created_from": "run_daily_catalog_sourcing"},
            }
        )
        .execute()
    )
    cycle = cycle_response.data[0]
    insert_cycle_items(supabase, cycle["coverage_cycle_id"], queue.rows)
    refresh_cycle_metrics(supabase, cycle["coverage_cycle_id"])
    return cycle


def refresh_active_cycle_queue(supabase, cycle_id: str, settings, queue_limit: int) -> int:
    queue = build_unified_priority_queue(supabase, settings, limit=queue_limit)
    existing = {
        str(row.get("asin") or "").upper(): row
        for row in (
            supabase.table("sourcing_coverage_cycle_items")
            .select("asin,queue_position")
            .eq("coverage_cycle_id", cycle_id)
            .execute()
            .data
            or []
        )
    }
    max_position = max([int(row.get("queue_position") or 0) for row in existing.values()] or [0])
    new_rows = []
    for row in queue.rows:
        asin = str(row.get("asin") or "").upper()
        if asin in existing:
            continue
        max_position += 1
        new_rows.append({**row, "queue_position": max_position})
    insert_cycle_items(supabase, cycle_id, new_rows)
    refresh_cycle_metrics(supabase, cycle_id)
    return len(new_rows)


def insert_cycle_items(supabase, cycle_id: str, rows: list[dict[str, Any]]) -> None:
    payload = [{**row, "coverage_cycle_id": cycle_id} for row in rows]
    for batch in chunked(payload, 250):
        supabase.table("sourcing_coverage_cycle_items").upsert(batch, on_conflict="coverage_cycle_id,asin").execute()


def fetch_pending_cycle_items(supabase, cycle_id: str, limit: int) -> list[dict[str, Any]]:
    response = (
        supabase.table("sourcing_coverage_cycle_items")
        .select("*")
        .eq("coverage_cycle_id", cycle_id)
        .in_("processing_status", ["pending", "retryable_failed"])
        .order("queue_position")
        .limit(limit)
        .execute()
    )
    return response.data or []


def insert_seed_rows(supabase, items: list[dict[str, Any]], run_id: str, cycle_id: str) -> None:
    seeds = [seed_row_for_run(item, run_id, cycle_id) for item in items]
    for batch in chunked(seeds, 250):
        supabase.table("sourcing_seed_asins").insert(batch).execute()
    supabase.table("sourcing_runs").update({"source_count": count_rows(supabase, "sourcing_seed_asins", run_id)}).eq("sourcing_run_id", run_id).execute()


def update_cycle_items_after_chunk(supabase, run_id: str, items: list[dict[str, Any]], calls_used: int) -> None:
    if not items:
        return
    seed_rows = (
        supabase.table("sourcing_seed_asins")
        .select("seed_id,coverage_cycle_item_id")
        .eq("sourcing_run_id", run_id)
        .in_("coverage_cycle_item_id", [row["cycle_item_id"] for row in items])
        .execute()
        .data
        or []
    )
    seed_id_by_item_id = {row["coverage_cycle_item_id"]: row["seed_id"] for row in seed_rows}
    candidate_counts = count_by_seed(supabase, "sourcing_ebay_candidates", run_id, seed_id_by_item_id.values())
    opportunity_counts = count_by_seed(supabase, "sourcing_opportunities", run_id, seed_id_by_item_id.values())
    per_item_calls = max(round(calls_used / len(items)), 0) if items else 0
    updates = []
    for item in items:
        seed_id = seed_id_by_item_id.get(item["cycle_item_id"])
        updates.append(
            {
                "cycle_item_id": item["cycle_item_id"],
                "processing_status": "searched",
                "last_ebay_checked_at": now_iso(),
                "browse_calls_used": per_item_calls,
                "candidate_count": candidate_counts.get(seed_id, 0),
                "qualifying_opportunity_count": opportunity_counts.get(seed_id, 0),
                "last_error": None,
                "updated_at": now_iso(),
            }
        )
    for update in updates:
        item_id = update.pop("cycle_item_id")
        supabase.table("sourcing_coverage_cycle_items").update(update).eq("cycle_item_id", item_id).execute()


def count_by_seed(supabase, table_name: str, run_id: str, seed_ids) -> dict[str, int]:
    output: dict[str, int] = {}
    seed_ids = [str(seed_id) for seed_id in seed_ids if seed_id]
    for seed_batch in chunked(seed_ids, 100):
        rows = (
            supabase.table(table_name)
            .select("seed_id")
            .eq("sourcing_run_id", run_id)
            .in_("seed_id", seed_batch)
            .execute()
            .data
            or []
        )
        for row in rows:
            seed_id = str(row.get("seed_id") or "")
            output[seed_id] = output.get(seed_id, 0) + 1
    return output


def create_daily_run(supabase, run_id: str, cycle_id: str, settings, quota: dict[str, Any], reserve: int) -> None:
    supabase.table("sourcing_runs").insert(
        {
            "sourcing_run_id": run_id,
            "run_type": "daily_catalog_sourcing",
            "status": "running",
            "started_at": now_iso(),
            "coverage_cycle_id": cycle_id,
            "settings_snapshot": settings.__dict__,
            "starting_browse_quota_limit": quota.get("limit"),
            "starting_browse_quota_count": quota.get("count"),
            "starting_browse_quota_remaining": quota.get("remaining"),
            "browse_quota_reserve": reserve,
            "browse_quota_reset_at": quota.get("reset"),
        }
    ).execute()


def finish_daily_run(
    supabase,
    run_id: str,
    cycle_id: str,
    batch_id: str,
    stop_reason: str,
    quota,
    reserve: int,
    searched_total: int,
    api_calls_used: int,
    *,
    last_queue_position: int | None = None,
    added_count: int = 0,
) -> None:
    metrics = refresh_cycle_metrics(supabase, cycle_id, run_id=run_id, stop_reason=stop_reason)
    bucket = fetch_bucket_progress(supabase, cycle_id)
    opportunity_type_counts = fetch_opportunity_type_counts(supabase, run_id)
    end_quota = quota_summary(fetch_browse_quota())
    update = {
        "status": "completed",
        "completed_at": now_iso(),
        "stop_reason": stop_reason,
        "ending_browse_quota_remaining": end_quota.get("remaining"),
        "asins_searched_this_run": searched_total,
        "cumulative_asins_searched": metrics.get("searched_count"),
        "asins_remaining_in_cycle": metrics.get("remaining_count"),
        "priority_1_searched": bucket[PRIORITY_RECENTLY_SOLD]["searched"],
        "priority_1_remaining": bucket[PRIORITY_RECENTLY_SOLD]["remaining"],
        "priority_2_searched": bucket[PRIORITY_PURCHASED_NOT_SENT]["searched"],
        "priority_2_remaining": bucket[PRIORITY_PURCHASED_NOT_SENT]["remaining"],
        "priority_3_searched": bucket[PRIORITY_CATALOG_REMAINING]["searched"],
        "priority_3_remaining": bucket[PRIORITY_CATALOG_REMAINING]["remaining"],
        "buy_now_opportunity_count": opportunity_type_counts.get("buy_now", 0),
        "best_offer_opportunity_count": opportunity_type_counts.get("best_offer", 0),
        "auction_opportunity_count": opportunity_type_counts.get("auction", 0),
        "multi_unit_opportunity_count": opportunity_type_counts.get("multi_unit", 0),
        "coverage_percentage": metrics.get("completion_percentage"),
        "last_processed_queue_position": last_queue_position,
        "api_call_count": api_calls_used,
        "raw_summary_json": {
            "daily_catalog_sourcing": {
                "coverage_cycle_id": cycle_id,
                "batch_id": batch_id,
                "stop_reason": stop_reason,
                "added_to_cycle_count": added_count,
                "starting_quota": quota_summary(quota),
                "ending_quota": end_quota,
                "quota_reserve": reserve,
                "bucket_progress": bucket,
            }
        },
    }
    supabase.table("sourcing_runs").update(update).eq("sourcing_run_id", run_id).execute()
    supabase.table("sourcing_coverage_cycles").update(
        {
            "last_run_id": run_id,
            "last_stop_reason": stop_reason,
            "last_quota_reset_at": (quota_summary(quota) or {}).get("reset"),
            "updated_at": now_iso(),
        }
    ).eq("coverage_cycle_id", cycle_id).execute()


def fetch_bucket_progress(supabase, cycle_id: str) -> dict[str, dict[str, int]]:
    rows = (
        supabase.table("sourcing_coverage_cycle_items")
        .select("priority_bucket,processing_status")
        .eq("coverage_cycle_id", cycle_id)
        .execute()
        .data
        or []
    )
    result = {
        PRIORITY_RECENTLY_SOLD: {"total": 0, "searched": 0, "remaining": 0},
        PRIORITY_PURCHASED_NOT_SENT: {"total": 0, "searched": 0, "remaining": 0},
        PRIORITY_CATALOG_REMAINING: {"total": 0, "searched": 0, "remaining": 0},
    }
    for row in rows:
        bucket = row.get("priority_bucket")
        if bucket not in result:
            continue
        result[bucket]["total"] += 1
        if row.get("processing_status") == "searched":
            result[bucket]["searched"] += 1
        if row.get("processing_status") in {"pending", "retryable_failed", "paused"}:
            result[bucket]["remaining"] += 1
    return result


def fetch_opportunity_type_counts(supabase, run_id: str) -> dict[str, int]:
    rows = (
        supabase.table("sourcing_opportunities")
        .select("opportunity_type,status,ebay_item_id")
        .eq("sourcing_run_id", run_id)
        .eq("status", "open")
        .execute()
        .data
        or []
    )
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for row in rows:
        key = clean_ebay_key(row.get("ebay_item_id")) if row.get("ebay_item_id") else None
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        value = str(row.get("opportunity_type") or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def mark_items_status(supabase, item_ids: list[str], status: str) -> None:
    if not item_ids:
        return
    for batch in chunked(item_ids, 100):
        supabase.table("sourcing_coverage_cycle_items").update({"processing_status": status, "updated_at": now_iso()}).in_("cycle_item_id", batch).execute()


def count_rows(supabase, table_name: str, run_id: str) -> int:
    response = supabase.table(table_name).select("sourcing_run_id", count="exact").eq("sourcing_run_id", run_id).limit(1).execute()
    return int(response.count or 0)


def run_python(step: list[str]) -> None:
    print(f"\n--- python {' '.join(step)} ---", flush=True)
    subprocess.run([sys.executable, *step], cwd=ROOT, check=True)


def int_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
