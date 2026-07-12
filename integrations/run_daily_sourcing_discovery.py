"""Create and run the daily quota-based sourcing discovery job."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sourcing_common import fetch_settings, get_supabase_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    supabase = get_supabase_client()
    settings = fetch_settings(supabase)
    run_id = str(uuid4())
    run_type = args.run_type
    supabase.table("sourcing_runs").insert(
        {
            "sourcing_run_id": run_id,
            "run_type": run_type,
            "status": "planned",
            "started_at": dt.datetime.now(dt.UTC).isoformat(),
            "settings_snapshot": settings.__dict__,
        }
    ).execute()
    step = [
        "integrations/run_sourcing_workflow.py",
        "--run-id",
        run_id,
        "--run-type",
        run_type,
        "--seed-limit",
        str(args.seed_limit),
        "--seed-chunk-size",
        str(args.seed_chunk_size),
        "--max-results-per-asin",
        str(args.max_results_per_asin),
    ]
    if args.browse_quota_reserve:
        step.extend(["--browse-quota-reserve", str(args.browse_quota_reserve)])
    print(f"Daily sourcing discovery run: {run_id} ({run_type})", flush=True)
    subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily MBOP sourcing discovery against the eBay Browse quota.")
    parser.add_argument("--run-type", choices=["full_listings", "recent_sales"], default="full_listings")
    parser.add_argument("--seed-limit", type=int, default=5000)
    parser.add_argument("--seed-chunk-size", type=int, default=50)
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--browse-quota-reserve", type=int, default=0)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
