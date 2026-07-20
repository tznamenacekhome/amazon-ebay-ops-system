"""Read-only audit for rejected sourcing rows recovered by numeric-rule changes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from score_sourcing_opportunities import (  # noqa: E402
    fetch_historical_status_by_key,
    fetch_keepa_price_context_by_asin,
    fetch_matching_context,
    score_candidate,
)
from sourcing_common import fetch_settings, get_supabase_client  # noqa: E402


OPPORTUNITY_SELECT = """
opportunity_id,
sourcing_run_id,
candidate_id,
asin,
ebay_item_id,
status,
opportunity_type,
score,
ai_flags,
matching_diagnostics_json,
sourcing_ebay_candidates (*),
sourcing_seed_asins (*)
"""


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    rows = fetch_rejected_numeric_rows(supabase, args.limit)
    print(f"Rejected numeric-mismatch rows inspected: {len(rows)}")
    if not rows:
        return 0

    seeds = [row.get("sourcing_seed_asins") or {} for row in rows]
    keepa_prices = fetch_keepa_price_context_by_asin(supabase, [seed.get("asin") for seed in seeds])
    historical_status = fetch_historical_status_by_key(supabase)
    matching_context = fetch_matching_context(supabase)

    recoveries: list[dict[str, Any]] = []
    still_rejected = 0
    for row in rows:
        candidate = row.get("sourcing_ebay_candidates") or {}
        seed = row.get("sourcing_seed_asins") or {}
        scored = score_candidate(candidate, seed, settings, keepa_prices, historical_status, matching_context)
        if not scored:
            continue
        if scored.get("status") == "open":
            recoveries.append({"existing": row, "scored": scored})
        else:
            still_rejected += 1

    run_ids = sorted({str(row["scored"].get("sourcing_run_id")) for row in recoveries if row["scored"].get("sourcing_run_id")})
    print(f"Would now score open: {len(recoveries)}")
    print(f"Still rejected/non-open: {still_rejected}")
    print(f"Affected runs: {len(run_ids)}")
    for run_id in run_ids:
        print(f"- {run_id}")

    print("\nRecovered listing candidates")
    for item in recoveries[: args.print_limit]:
        existing = item["existing"]
        scored = item["scored"]
        candidate = existing.get("sourcing_ebay_candidates") or {}
        seed = existing.get("sourcing_seed_asins") or {}
        print(
            f"- run={scored.get('sourcing_run_id')} asin={scored.get('asin')} "
            f"ebay={legacy_id(scored.get('ebay_item_id'))} type={scored.get('opportunity_type')} "
            f"profit={scored.get('profit')} roi={scored.get('roi_percent')} score={scored.get('score')}"
        )
        print(f"  amazon={safe_text(seed.get('amazon_title'))}")
        print(f"  ebay={safe_text(candidate.get('ebay_title'))}")
    if len(recoveries) > args.print_limit:
        print(f"... {len(recoveries) - args.print_limit} more")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit rejected numeric sourcing rows under current rules.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max rejected numeric rows to inspect.")
    parser.add_argument("--print-limit", type=int, default=50)
    return parser.parse_args()


def fetch_rejected_numeric_rows(supabase: Any, limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            supabase.table("sourcing_opportunities")
            .select(OPPORTUNITY_SELECT)
            .eq("status", "rejected")
            .contains("ai_flags", ["Blocked: numeric sequel/year mismatch"])
            .order("opportunity_id")
            .range(start, start + 999)
            .execute()
            .data
            or []
        )
        for row in batch:
            if has_numeric_block(row):
                output.append(row)
                if limit and len(output) >= limit:
                    return output
        if len(batch) < 1000:
            return output
        start += 1000


def has_numeric_block(row: dict[str, Any]) -> bool:
    flags = [str(value or "") for value in row.get("ai_flags") or []]
    diagnostics = row.get("matching_diagnostics_json") or {}
    if isinstance(diagnostics, dict):
        static = diagnostics.get("static_rules") or {}
        if isinstance(static, dict):
            flags.extend(str(value or "") for value in static.get("hard_blocks") or [])
        numeric = diagnostics.get("numeric_identity") or {}
        if isinstance(numeric, dict):
            flags.append(str(numeric.get("reason") or ""))
    return any("numeric sequel/year mismatch" in value.casefold() for value in flags)


def legacy_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("v1|"):
        parts = text.split("|")
        return parts[1] if len(parts) > 1 else text
    return text


def safe_text(value: Any) -> str:
    return str(value or "").encode("ascii", "replace").decode("ascii")


if __name__ == "__main__":
    raise SystemExit(main())
