"""Run the on-demand MBOP sourcing workflow for one sourcing run."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sourcing_common import get_supabase_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
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
    return parser.parse_args()


def default_seed_limit(run_type: str) -> int:
    return 5000 if run_type == "full_listings" else 250


def default_search_limit(run_type: str, seed_limit: int) -> int:
    return seed_limit if run_type == "full_listings" else 50


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


def now_iso() -> str:
    import datetime as dt

    return dt.datetime.now(dt.UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
