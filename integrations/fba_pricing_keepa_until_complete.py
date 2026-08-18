"""Refresh Keepa pricing for every current Send to Amazon ASIN.

This manual/on-demand wrapper is intentionally stricter than the scheduled
catalog cycle: it waits for Keepa token refills and keeps retrying until every
ASIN currently eligible for the FBA prep page has a snapshot from this run.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

try:
    from keepa_client import KeepaClient, to_int
    from keepa_sync_products import clean_asin, collect_source_asins, get_supabase_client, parse_timestamp
except ImportError:
    from integrations.keepa_client import KeepaClient, to_int
    from integrations.keepa_sync_products import clean_asin, collect_source_asins, get_supabase_client, parse_timestamp


LOGGER = logging.getLogger("fba_pricing_keepa_until_complete")


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    started_at = datetime.now(timezone.utc)
    supabase = get_supabase_client()
    client = KeepaClient.from_env()
    selected_asins, _priority = collect_source_asins(supabase, source="received_fba_prep")
    target_asins = sorted({asin for asin in selected_asins if asin})

    print("Manual FBA Keepa pricing refresh")
    print("--------------------------------")
    print(f"Selected ASINs: {len(target_asins)}")
    if not target_asins:
        return 0

    refreshed: set[str] = set()
    attempts = 0
    token_waits = 0
    while attempts < args.max_attempts:
        attempts += 1
        refreshed = fetch_asins_refreshed_since(supabase, target_asins, started_at)
        remaining = [asin for asin in target_asins if asin not in refreshed]
        print(f"ASINs refreshed: {len(refreshed)}")
        print(f"ASINs remaining: {len(remaining)}")
        if not remaining:
            print("Manual FBA Keepa refresh complete.")
            print(f"Rows updated: {len(refreshed)}")
            print(f"Token waits: {token_waits}")
            return 0

        token_status = client.get_token_status()
        tokens_left = to_int(token_status.get("tokens_left"), default=0)
        print(f"Tokens before batch: {tokens_left}")
        if tokens_left < args.min_tokens:
            token_waits += 1
            sleep_seconds = refill_sleep_seconds(token_status, args.min_tokens, args.max_sleep_seconds)
            print(f"Rate limit waits: 1")
            LOGGER.info(
                "Waiting for Keepa tokens before manual FBA refresh: tokens_left=%s min=%s sleep=%ss",
                tokens_left,
                args.min_tokens,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            continue

        batch_size = max(1, min(args.batch_size, tokens_left // max(args.estimated_tokens_per_asin, 1)))
        batch = remaining[:batch_size]
        result = run_keepa_batch(batch, args)
        if result.returncode != 0:
            return result.returncode

    refreshed = fetch_asins_refreshed_since(supabase, target_asins, started_at)
    remaining_count = len([asin for asin in target_asins if asin not in refreshed])
    print(f"Failures: {remaining_count}")
    LOGGER.error("Manual FBA Keepa refresh stopped with %s ASIN(s) remaining.", remaining_count)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh all FBA prep Keepa pricing, waiting for token refills.")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--min-tokens", type=int, default=20)
    parser.add_argument("--estimated-tokens-per-asin", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=200)
    parser.add_argument("--max-sleep-seconds", type=int, default=15 * 60)
    parser.add_argument("--offers", type=int, default=20)
    return parser.parse_args()


def fetch_asins_refreshed_since(supabase: Any, asins: list[str], started_at: datetime) -> set[str]:
    refreshed: set[str] = set()
    started_timestamp = started_at.timestamp()
    for chunk in chunks(asins, 200):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,captured_at")
            .in_("asin", chunk)
            .execute()
        )
        for row in response.data or []:
            asin = clean_asin(row.get("asin"))
            captured_at = parse_timestamp(row.get("captured_at"))
            if asin and captured_at and captured_at.timestamp() >= started_timestamp:
                refreshed.add(asin)
    return refreshed


def refill_sleep_seconds(token_status: dict[str, Any], min_tokens: int, max_sleep_seconds: int) -> int:
    tokens_left = to_int(token_status.get("tokens_left"), default=0)
    refill_ms = to_int(token_status.get("refill_in"), default=0)
    refill_rate = max(to_int(token_status.get("refill_rate"), default=1), 1)
    missing_tokens = max(min_tokens - tokens_left, 1)
    refill_cycles = (missing_tokens + refill_rate - 1) // refill_rate
    estimated_seconds = max(refill_ms / 1000, 1) * refill_cycles
    return max(1, min(int(estimated_seconds) + 2, max_sleep_seconds))


def run_keepa_batch(asins: list[str], args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "integrations/keepa_sync_products.py",
        "--source",
        "explicit",
        "--batch-size",
        str(min(args.batch_size, len(asins))),
        "--offers",
        str(args.offers),
        "--only-live-offers",
        "--no-history",
        "--no-rating",
        "--write",
    ]
    for asin in asins:
        command.extend(["--asin", asin])

    LOGGER.info("Running explicit FBA Keepa batch for %s ASIN(s).", len(asins))
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        LOGGER.error("Explicit FBA Keepa batch failed with exit code %s.", result.returncode)
    return result


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


if __name__ == "__main__":
    raise SystemExit(main())
