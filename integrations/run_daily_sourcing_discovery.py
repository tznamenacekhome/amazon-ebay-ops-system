"""Create and run the unified daily quota-based sourcing discovery job."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from ebay_api_limits import browse_call_budget, fetch_browse_quota


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    if args.skip_weekends and is_weekend(args.business_timezone):
        print(f"Daily sourcing discovery skipped for weekend in {args.business_timezone}.", flush=True)
        return 0
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
    for pass_number in range(1, args.max_weekday_passes + 1):
        print(f"Daily sourcing discovery pass {pass_number}: daily_catalog_sourcing", flush=True)
        subprocess.run([sys.executable, *step], cwd=ROOT, check=True)
        remaining = browse_call_budget(fetch_browse_quota(), args.browse_quota_reserve)
        if remaining is None or remaining <= 0:
            return 0
        if args.max_api_calls is not None:
            return 0
        print(f"Browse quota still has {remaining} usable calls; starting another coverage pass.", flush=True)
    raise RuntimeError(
        f"Browse quota remained after {args.max_weekday_passes} sourcing passes; refusing an unbounded loop."
    )


def is_weekend(timezone_name: str, *, now: dt.datetime | None = None) -> bool:
    current = now or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.UTC)
    return current.astimezone(ZoneInfo(timezone_name)).weekday() >= 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily MBOP sourcing discovery against the eBay Browse quota.")
    parser.add_argument("--run-type", choices=["full_listings", "recent_sales", "daily_catalog_sourcing"], default="daily_catalog_sourcing", help="Ignored compatibility option; daily sourcing is unified.")
    parser.add_argument("--seed-limit", type=int, default=5000, help="Ignored compatibility option from the old split workflow.")
    parser.add_argument("--queue-limit", type=int, default=20000)
    parser.add_argument("--seed-chunk-size", type=int, default=50)
    parser.add_argument("--max-results-per-asin", type=int, default=200)
    parser.add_argument("--browse-quota-reserve", type=int, default=0)
    parser.add_argument("--max-api-calls", type=int, default=None, help="Diagnostic cap only; production uses live quota.")
    parser.add_argument("--skip-weekends", action="store_true", help="Do not spend Browse quota on Saturday or Sunday.")
    parser.add_argument("--business-timezone", default="America/Los_Angeles")
    parser.add_argument("--max-weekday-passes", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
