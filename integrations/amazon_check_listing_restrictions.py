"""Check Amazon Listings Restrictions and block non-sellable ASINs for sourcing.

This integration is read-only against Amazon SP-API. It writes only ASIN-level
workflow exclusions to MBOP's sourcing blocklist so restricted products are not
fed back into Keepa catalog refreshes or eBay sourcing.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock, local
from typing import Any

from postgrest.exceptions import APIError

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError
from keepa_sync_products import collect_source_asins
from sourcing_common import chunked, get_supabase_client, paginate_table


LOGGER = logging.getLogger("amazon_listing_restrictions")
AMAZON_RESTRICTION_REASONS = {
    "amazon_approval_required",
    "amazon_listing_not_eligible",
    "amazon_asin_not_found",
}
BLOCKED_STATUSES = {"approval_required", "not_eligible", "asin_not_found"}
THREAD_LOCAL = local()


@dataclass(frozen=True)
class RestrictionResult:
    asin: str
    status: str
    block_reason: str | None
    reason_codes: list[str]
    messages: list[str]
    restriction_count: int
    raw: dict[str, Any]
    error: str | None = None


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("amazon_spapi").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        supabase = get_supabase_client()
        client = AmazonSPAPIClient.from_env()
        asins = collect_catalog_asins(supabase, source=args.source)
        if args.asin:
            asins = sorted(set(asins) | {asin.strip().upper() for asin in args.asin if asin.strip()})
        if args.offset:
            asins = asins[args.offset :]
        if args.limit is not None:
            asins = asins[: args.limit]

        LOGGER.info(
            "Amazon restriction ASINs selected: %s source=%s offset=%s",
            len(asins),
            args.source,
            args.offset,
        )
        client.test_lwa_access_token()
        results = check_restrictions(
            asins,
            condition_type=args.condition_type,
            reason_locale=args.reason_locale,
            max_workers=args.max_workers,
            requests_per_second=args.requests_per_second,
            progress_every=args.progress_every,
        )

        if args.write:
            apply_blocklist_results(supabase, results)

        print_summary(results, write=args.write, sample_limit=args.sample_limit)
        return 0
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Amazon listing restriction check failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check ASIN sellability via Amazon Listings Restrictions.")
    parser.add_argument(
        "--source",
        choices=["amazon_skus", "catalog_priority"],
        default="amazon_skus",
        help="ASIN population to check. amazon_skus is the seller catalog; catalog_priority mirrors Keepa catalog input.",
    )
    parser.add_argument("--asin", action="append", default=[], help="Additional ASIN to check.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many sorted source ASINs before checking.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum ASINs to process.")
    parser.add_argument(
        "--condition-type",
        default="new_new",
        help="Amazon restriction conditionType. Default is new_new for new-condition sourcing.",
    )
    parser.add_argument("--reason-locale", default="en_US")
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.25,
        help="Deprecated serial delay option retained for CLI compatibility.",
    )
    parser.add_argument("--max-workers", type=int, default=5)
    parser.add_argument("--requests-per-second", type=float, default=4.0)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--write", action="store_true", help="Persist clear restricted ASINs to sourcing_blocked_asins.")
    return parser.parse_args()


def check_restrictions(
    asins: list[str],
    *,
    condition_type: str,
    reason_locale: str,
    max_workers: int,
    requests_per_second: float,
    progress_every: int,
) -> list[RestrictionResult]:
    limiter = RateLimiter(max(requests_per_second, 0.1))
    completed = 0
    order = {asin: index for index, asin in enumerate(asins)}
    results: list[RestrictionResult] = []

    def check_one(asin: str) -> RestrictionResult:
        limiter.wait()
        client = thread_client()
        try:
            payload = client.get_listings_restrictions(
                asin,
                condition_type=condition_type,
                reason_locale=reason_locale,
            )
            return classify_restriction_payload(asin, payload)
        except AmazonSPAPIError as error:
            return RestrictionResult(
                asin=asin,
                status="unknown",
                block_reason=None,
                reason_codes=[],
                messages=[],
                restriction_count=0,
                raw={},
                error=str(error),
            )

    with ThreadPoolExecutor(max_workers=max(max_workers, 1)) as executor:
        futures = [executor.submit(check_one, asin) for asin in asins]
        for future in as_completed(futures):
            results.append(future.result())
            completed += 1
            if completed % progress_every == 0:
                LOGGER.info("Checked Amazon listing restrictions: %s/%s", completed, len(asins))

    return sorted(results, key=lambda result: order.get(result.asin, len(order)))


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._interval = 1.0 / requests_per_second
        self._next_at = time.monotonic()
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_seconds = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self._interval
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)


def thread_client() -> AmazonSPAPIClient:
    client = getattr(THREAD_LOCAL, "client", None)
    if client is None:
        client = AmazonSPAPIClient.from_env()
        THREAD_LOCAL.client = client
    return client


def collect_catalog_asins(supabase, *, source: str) -> list[str]:
    if source == "catalog_priority":
        asins, _priority_by_asin = collect_source_asins(supabase, source="catalog_priority")
        return asins

    rows = paginate_table(
        supabase,
        "amazon_skus",
        "asin",
        max_rows=50000,
    )
    return sorted({asin for row in rows if (asin := clean_asin(row.get("asin")))})


def classify_restriction_payload(asin: str, payload: dict[str, Any]) -> RestrictionResult:
    container = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    restrictions = container.get("restrictions") if isinstance(container, dict) else None
    if not isinstance(restrictions, list):
        return RestrictionResult(
            asin=asin,
            status="unknown",
            block_reason=None,
            reason_codes=[],
            messages=[],
            restriction_count=0,
            raw=payload,
            error="Missing restrictions array in Listings Restrictions response.",
        )

    reason_codes: list[str] = []
    messages: list[str] = []
    for restriction in restrictions:
        if not isinstance(restriction, dict):
            continue
        for reason in restriction.get("reasons") or []:
            if not isinstance(reason, dict):
                continue
            code = clean_text(reason.get("reasonCode")).upper()
            message = clean_text(reason.get("message"))
            if code:
                reason_codes.append(code)
            if message:
                messages.append(message)

    status = "sellable"
    block_reason = None
    if "NOT_ELIGIBLE" in reason_codes:
        status = "not_eligible"
        block_reason = "amazon_listing_not_eligible"
    elif "APPROVAL_REQUIRED" in reason_codes:
        status = "approval_required"
        block_reason = "amazon_approval_required"
    elif "ASIN_NOT_FOUND" in reason_codes:
        status = "asin_not_found"
        block_reason = "amazon_asin_not_found"
    elif restrictions:
        status = "unknown"

    return RestrictionResult(
        asin=asin,
        status=status,
        block_reason=block_reason,
        reason_codes=sorted(set(reason_codes)),
        messages=messages,
        restriction_count=len(restrictions),
        raw=payload,
    )


def apply_blocklist_results(supabase, results: list[RestrictionResult]) -> None:
    restricted = [result for result in results if result.status in BLOCKED_STATUSES and result.block_reason]
    sellable_asins = [result.asin for result in results if result.status == "sellable"]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    rows = [
        {
            "asin": result.asin,
            "reason": result.block_reason,
            "notes": restriction_notes(result),
            "blocked_by": "amazon_listings_restrictions",
            "blocked_at": now,
            "updated_at": now,
        }
        for result in restricted
    ]
    for batch in chunked(rows, 500):
        supabase.table("sourcing_blocked_asins").upsert(batch, on_conflict="asin").execute()

    release_amazon_restriction_blocks(supabase, sellable_asins)


def release_amazon_restriction_blocks(supabase, asins: list[str]) -> None:
    for batch in chunked(asins, 100):
        if not batch:
            continue
        try:
            supabase.table("sourcing_blocked_asins").delete().in_("asin", batch).in_(
                "reason",
                sorted(AMAZON_RESTRICTION_REASONS),
            ).execute()
        except APIError as error:
            if "sourcing_blocked_asins" not in str(error):
                raise


def restriction_notes(result: RestrictionResult) -> str:
    codes = ", ".join(result.reason_codes) or result.status
    message = " | ".join(result.messages[:3])
    if message:
        return f"Amazon Listings Restrictions: {codes}; {message}"
    return f"Amazon Listings Restrictions: {codes}"


def print_summary(results: list[RestrictionResult], *, write: bool, sample_limit: int) -> None:
    counts = Counter(result.status for result in results)
    print("Amazon Listings Restrictions check")
    print("-----------------------------------")
    print(f"Mode: {'write' if write else 'dry-run'}")
    print(f"Checked: {len(results)}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")

    proposed = [result for result in results if result.status in BLOCKED_STATUSES]
    if proposed:
        print("\nRestricted ASIN sample:")
        for result in proposed[:sample_limit]:
            print(
                f"- {result.asin} | {result.status} | "
                f"{','.join(result.reason_codes) or '--'} | {restriction_notes(result)}"
            )

    unknowns = [result for result in results if result.status == "unknown"]
    if unknowns:
        print("\nUnknown sample:")
        for result in unknowns[: min(sample_limit, 10)]:
            print(
                f"- {result.asin} | codes={','.join(result.reason_codes) or '--'} | "
                f"error={result.error or '--'}"
            )


def clean_asin(value: Any) -> str | None:
    asin = str(value or "").strip().upper()
    return asin if asin else None


def clean_text(value: Any) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
