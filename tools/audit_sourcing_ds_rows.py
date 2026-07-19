"""Read-only audit for open Nintendo DS sourcing rows."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from sourcing_common import get_supabase_client  # noqa: E402
from sourcing_match_rules import evaluate_static_match_rules  # noqa: E402


def main() -> int:
    supabase = get_supabase_client()
    rows = fetch_open_opportunities(supabase)
    ds_rows = [row for row in rows if should_block_as_ds(row)]
    run_ids = sorted({str(row.get("sourcing_run_id")) for row in ds_rows if row.get("sourcing_run_id")})

    print(f"Open sourcing rows inspected: {len(rows)}")
    print(f"Open rows now blocked by Nintendo DS rule: {len(ds_rows)}")
    print(f"Runs with DS-blocked open rows: {len(run_ids)}")
    for run_id in run_ids:
        print(f"- {run_id}")
    for row in ds_rows[:25]:
        candidate = row.get("sourcing_ebay_candidates") or {}
        print(
            f"{row.get('sourcing_run_id')} | {row.get('opportunity_id')} | "
            f"{row.get('asin')} | {candidate.get('ebay_title')}"
        )
    return 0


def fetch_open_opportunities(supabase: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            supabase.table("sourcing_opportunities")
            .select(
                "opportunity_id,sourcing_run_id,asin,status,"
                "sourcing_seed_asins(amazon_title,raw_context_json),"
                "sourcing_ebay_candidates(ebay_title,condition,item_location_country,raw_ebay_json)"
            )
            .eq("status", "open")
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def should_block_as_ds(row: dict[str, Any]) -> bool:
    candidate = row.get("sourcing_ebay_candidates") or {}
    seed = {
        "asin": row.get("asin"),
        **(row.get("sourcing_seed_asins") or {}),
    }
    diagnostics = evaluate_static_match_rules(candidate, seed)
    return any("unsupported sourcing platform" in reason for reason in diagnostics.get("hard_blocks") or [])


if __name__ == "__main__":
    raise SystemExit(main())
