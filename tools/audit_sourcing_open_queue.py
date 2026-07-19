"""Read-only audit for sourcing batch visibility and open queue scope."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from sourcing_common import get_supabase_client  # noqa: E402


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    batches = fetch_completed_batches(supabase, args.batch_limit)
    print("Latest completed sourcing batches")
    for batch in batches:
        print(
            f"- {batch.get('completed_at')} batch={batch.get('batch_id')} "
            f"run={batch.get('sourcing_run_id')} qualifying={batch.get('qualifying_opportunity_count')}"
        )

    if not batches:
        print("No completed batches found.")
        return 0

    latest = batches[0]
    latest_ids = fetch_batch_opportunity_ids(supabase, [latest["batch_id"]])
    prior_batches = batches[1 : 1 + args.prior_batch_count]
    prior_ids = fetch_batch_opportunity_ids(supabase, [row["batch_id"] for row in prior_batches])
    hidden_by_latest_scope = prior_ids - latest_ids
    status_counts = opportunity_status_counts(supabase, hidden_by_latest_scope)
    dismiss_counts = dismissal_reason_counts(supabase, hidden_by_latest_scope)

    print("")
    print("Visibility audit")
    print(f"Latest batch total presented: {len(latest_ids)}")
    print(f"Prior batches inspected: {len(prior_batches)}")
    print(f"Prior presented unique opportunities: {len(prior_ids)}")
    print(f"Prior opportunities absent from latest batch: {len(hidden_by_latest_scope)}")
    print(f"Still open but hidden only by latest-batch scope: {status_counts.get('open', 0)}")
    print(f"Dismissed among absent prior opportunities: {status_counts.get('dismissed', 0)}")
    print(f"No longer available dismissals among absent prior opportunities: {dismiss_counts.get('no_longer_available', 0)}")
    print(f"Status counts: {dict(sorted(status_counts.items()))}")
    print(f"Dismiss reason counts: {dict(sorted(dismiss_counts.items()))}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only sourcing queue visibility audit.")
    parser.add_argument("--batch-limit", type=int, default=10)
    parser.add_argument("--prior-batch-count", type=int, default=3)
    return parser.parse_args()


def fetch_completed_batches(supabase: Any, limit: int) -> list[dict[str, Any]]:
    return (
        supabase.table("sourcing_opportunity_batches")
        .select("batch_id,sourcing_run_id,status,qualifying_opportunity_count,completed_at")
        .eq("status", "completed")
        .order("completed_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def fetch_batch_opportunity_ids(supabase: Any, batch_ids: list[str]) -> set[str]:
    output: set[str] = set()
    for batch in chunked(batch_ids, 100):
        if not batch:
            continue
        rows = (
            supabase.table("sourcing_opportunity_batch_items")
            .select("opportunity_id")
            .in_("batch_id", batch)
            .execute()
            .data
            or []
        )
        output.update(str(row["opportunity_id"]) for row in rows if row.get("opportunity_id"))
    return output


def opportunity_status_counts(supabase: Any, opportunity_ids: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for batch in chunked(list(opportunity_ids), 100):
        rows = (
            supabase.table("sourcing_opportunities")
            .select("opportunity_id,status")
            .in_("opportunity_id", batch)
            .execute()
            .data
            or []
        )
        counts.update(str(row.get("status") or "unknown") for row in rows)
    return counts


def dismissal_reason_counts(supabase: Any, opportunity_ids: set[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for batch in chunked(list(opportunity_ids), 100):
        rows = (
            supabase.table("sourcing_actions")
            .select("opportunity_id,dismiss_reason")
            .in_("opportunity_id", batch)
            .eq("action_type", "dismissed")
            .execute()
            .data
            or []
        )
        counts.update(str(row.get("dismiss_reason") or "unknown") for row in rows)
    return counts


def chunked(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


if __name__ == "__main__":
    raise SystemExit(main())
