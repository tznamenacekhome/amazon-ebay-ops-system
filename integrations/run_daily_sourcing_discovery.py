"""Create and run the unified daily quota-based sourcing discovery job."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    step = [
        "integrations/run_daily_catalog_sourcing.py",
        "--queue-limit",
        str(args.queue_limit),
        "--seed-chunk-size",
        str(args.seed_chunk_size),
        "--max-results-per-asin",
        str(args.max_results_per_asin),
    ]
    if args.browse_quota_reserve:
        step.extend(["--browse-quota-reserve", str(args.browse_quota_reserve)])
    if args.max_api_calls is not None:
        step.extend(["--max-api-calls", str(args.max_api_calls)])
    print("Daily sourcing discovery run: daily_catalog_sourcing", flush=True)
    subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily MBOP sourcing discovery against the eBay Browse quota.")
    parser.add_argument("--run-type", choices=["full_listings", "recent_sales", "daily_catalog_sourcing"], default="daily_catalog_sourcing", help="Ignored compatibility option; daily sourcing is unified.")
    parser.add_argument("--seed-limit", type=int, default=5000, help="Ignored compatibility option from the old split workflow.")
    parser.add_argument("--queue-limit", type=int, default=20000)
    parser.add_argument("--seed-chunk-size", type=int, default=50)
    parser.add_argument("--max-results-per-asin", type=int, default=10)
    parser.add_argument("--browse-quota-reserve", type=int, default=0)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Diagnostic cap only; production uses live quota.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
