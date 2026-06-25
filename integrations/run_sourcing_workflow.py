"""Run the on-demand MBOP sourcing workflow for one sourcing run."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    steps = [
        [
            "integrations/build_sourcing_seed_asins.py",
            "--mode",
            args.run_type,
            "--limit",
            str(args.seed_limit),
            "--run-id",
            args.run_id,
            "--replace-run",
        ],
        [
            "integrations/ebay_sourcing_search.py",
            "--run-id",
            args.run_id,
            "--limit",
            str(args.search_limit),
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

    for step in steps:
        print(f"\n--- python {' '.join(step)} ---", flush=True)
        subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MBOP sourcing workflow.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-type", choices=["recent_sales", "full_listings"], required=True)
    parser.add_argument("--seed-limit", type=int, default=250)
    parser.add_argument("--search-limit", type=int, default=50)
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
