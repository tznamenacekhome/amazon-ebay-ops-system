"""Sync read-only Keepa product snapshots into MBOP.

Default behavior is a dry run. Use --write to insert snapshots.

Keepa data is catalog intelligence for price history, sales rank, sales-rank
drop frequency, offers, reviews, and rating. It must remain separate from
purchases, purchase_items, and Amazon seller workflow ownership.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from keepa_client import KeepaAPIError, KeepaClient

LOGGER = logging.getLogger("keepa_product_sync")
BATCH_SIZE = 500
KEEPA_EPOCH_SECONDS = 1293840000
SOURCE_PRIORITY_HIGH = 0
SOURCE_PRIORITY_MEDIUM = 1
SOURCE_PRIORITY_LOW = 2
BLOCKED_CATALOG_STATUSES = {"cancelled", "return_opened", "return_pending"}

CSV_AMAZON = 0
CSV_NEW = 1
CSV_USED = 2
CSV_SALES_RANK = 3
CSV_NEW_FBA = 10
CSV_COUNT_NEW = 11
CSV_RATING = 16
CSV_COUNT_REVIEWS = 17
CSV_BUY_BOX = 18

HISTORY_METRICS = {
    CSV_AMAZON: "amazon_price",
    CSV_NEW: "new_price",
    CSV_USED: "used_price",
    CSV_SALES_RANK: "sales_rank",
    CSV_NEW_FBA: "new_fba_price",
    CSV_COUNT_NEW: "offer_count",
    CSV_RATING: "rating",
    CSV_COUNT_REVIEWS: "review_count",
    CSV_BUY_BOX: "buy_box_price",
}


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = KeepaClient.from_env()
        supabase = get_supabase_client()
        captured_at = utc_now_iso()
        asins, priority_by_asin = collect_source_asins(supabase, source=args.source)
        cycle_state: dict[str, Any] | None = None
        eligible_asins = list(asins)
        if args.cycle_progress and args.source == "catalog_priority":
            cycle_state = build_catalog_cycle_state(
                supabase,
                eligible_asins,
                priority_by_asin=priority_by_asin,
                captured_at=captured_at,
            )
            asins = cycle_state["remaining_asins"]
        if args.missing_only:
            existing_asins = fetch_existing_keepa_asins(supabase)
            asins = [asin for asin in asins if asin not in existing_asins]
        if args.stale_days is not None and cycle_state is None:
            asins = filter_stale_keepa_asins(
                supabase,
                asins,
                stale_days=args.stale_days,
                priority_by_asin=priority_by_asin,
            )
        if args.asin:
            asins = sorted(set(asins) | {asin.strip().upper() for asin in args.asin if asin.strip()})
        if args.limit is not None:
            asins = asins[: args.limit]

        LOGGER.info("Keepa ASINs selected: %s source=%s", len(asins), args.source)
        if not asins:
            LOGGER.info("No ASINs selected. Nothing to do.")
            return 0

        token_status_before = client.get_token_status()
        tokens_left = to_int(token_status_before.get("tokens_left"), default=0)
        LOGGER.info(
            "Keepa tokens before sync: tokens_left=%s refill_in_ms=%s refill_rate=%s",
            token_status_before.get("tokens_left"),
            token_status_before.get("refill_in"),
            token_status_before.get("refill_rate"),
        )
        if args.min_tokens is not None and tokens_left < args.min_tokens:
            LOGGER.info(
                "Skipping Keepa sync because tokens_left=%s is below min_tokens=%s.",
                tokens_left,
                args.min_tokens,
            )
            print_plan_summary(asins, token_status_before)
            print(f"Skipped: Keepa tokens below minimum threshold ({tokens_left} < {args.min_tokens}).")
            if cycle_state is not None and args.write:
                cycle_state = finalize_catalog_cycle_state(cycle_state, inserted_asins=[])
                print_cycle_summary(cycle_state)
                print_metadata_json(
                    cycle_state,
                    selected=0,
                    rows_read=0,
                    token_status_before=token_status_before,
                    token_cost_total=0,
                    tokens_left_after=tokens_left,
                )
            return 0

        if args.adaptive_limit:
            adaptive_limit = max(1, tokens_left // max(args.estimated_tokens_per_asin, 1))
            if args.limit is not None:
                adaptive_limit = min(args.limit, adaptive_limit)
            if adaptive_limit < len(asins):
                LOGGER.info(
                    "Adaptive Keepa limit selected %s ASIN(s) from %s using tokens_left=%s estimate=%s.",
                    adaptive_limit,
                    len(asins),
                    tokens_left,
                    args.estimated_tokens_per_asin,
                )
                asins = asins[:adaptive_limit]

        if args.plan_only:
            print_plan_summary(asins, token_status_before)
            LOGGER.info("Plan-only mode complete. No Keepa product call made.")
            return 0

        snapshot_rows: list[dict[str, Any]] = []
        history_rows: list[dict[str, Any]] = []
        rows_read = 0
        missing_products = 0
        failures = 0
        token_cost_total = 0
        tokens_left_after: int | None = None

        for chunk in chunks(asins, args.batch_size):
            try:
                payload = client.get_products(
                    chunk,
                    stats_days=args.stats_days,
                    history=not args.no_history,
                    offers=args.offers,
                    only_live_offers=args.only_live_offers,
                    stock=args.stock,
                    rating=not args.no_rating,
                    wait=True,
                )
            except KeepaAPIError as error:
                failures += len(chunk)
                LOGGER.warning("Keepa product batch failed for %s ASINs: %s", len(chunk), error)
                continue

            products = payload.get("products") or []
            token_cost_total += to_int(payload.get("tokenFlowReduction"), default=0) or 0
            tokens_left_after = to_int(payload.get("tokensLeft"), default=tokens_left_after)
            rows_read += len(products)
            seen_asins = {clean_asin(product.get("asin")) for product in products}
            missing_products += len([asin for asin in chunk if clean_asin(asin) not in seen_asins])

            for product in products:
                snapshot = build_snapshot_row(
                    product=product,
                    captured_at=captured_at,
                    domain_id=client.config.domain_id,
                    token_cost=to_int(payload.get("tokenFlowReduction"), default=None),
                    tokens_left=to_int(payload.get("tokensLeft"), default=None),
                )
                snapshot_rows.append(snapshot)
                history_rows.extend(
                    build_history_rows(
                        product=product,
                        snapshot_id_placeholder=None,
                        domain_id=client.config.domain_id,
                        max_points_per_metric=args.max_history_points,
                    )
                )

            LOGGER.info(
                "Keepa batch complete: requested=%s returned=%s tokens_left=%s",
                len(chunk),
                len(products),
                payload.get("tokensLeft"),
            )

        print_summary(
            write=args.write,
            selected=len(asins),
            eligible=len(eligible_asins),
            rows_read=rows_read,
            snapshots=len(snapshot_rows),
            history_points=len(history_rows),
            missing_products=missing_products,
            failures=failures,
            token_status_before=token_status_before,
            token_cost_total=token_cost_total,
            tokens_left_after=tokens_left_after,
            cycle_state=cycle_state,
        )

        if not args.write:
            LOGGER.info("Dry run complete. Use --write to insert Keepa snapshots.")
            return 0

        inserted_snapshots, inserted_history = insert_keepa_rows(
            supabase,
            snapshot_rows,
            build_history=args.write_history and not args.no_history,
            domain_id=client.config.domain_id,
            max_points_per_metric=args.max_history_points,
        )
        updated_purchase_titles = update_missing_purchase_titles(supabase, snapshot_rows)
        if cycle_state is not None:
            cycle_state = finalize_catalog_cycle_state(
                cycle_state,
                inserted_asins=[row["asin"] for row in snapshot_rows if row.get("asin")],
            )
            print_cycle_summary(cycle_state)
            print_metadata_json(
                cycle_state,
                selected=len(asins),
                rows_read=rows_read,
                token_status_before=token_status_before,
                token_cost_total=token_cost_total,
                tokens_left_after=tokens_left_after,
            )
        LOGGER.info("Keepa product sync complete.")
        LOGGER.info("Product snapshots inserted: %s", inserted_snapshots)
        LOGGER.info("History points inserted: %s", inserted_history)
        LOGGER.info("Purchase titles updated: %s", updated_purchase_titles)
        LOGGER.info("Failures: %s", failures)
        print(f"Purchase titles updated: {updated_purchase_titles}")
        return 0
    except KeepaAPIError as error:
        LOGGER.error("Keepa sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Keepa sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Keepa product snapshots into MBOP.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Insert Keepa product snapshots. Default is dry-run only.",
    )
    parser.add_argument(
        "--source",
        choices=[
            "canonical",
            "amazon_active",
            "purchase_pre_listed",
            "received_fba_prep",
            "sourcing_active",
            "catalog_priority",
            "explicit",
        ],
        default="canonical",
        help=(
            "ASIN source. canonical = current Amazon FBA plus pre-Listed MBOP purchase inventory. "
            "received_fba_prep = received Amazon-bound purchase items waiting for FBA shipment. "
            "sourcing_active = ASINs from active sourcing opportunities/watchlist. "
            "catalog_priority = received FBA prep first, active sourcing second, then all known catalog ASINs. "
            "explicit = only ASINs passed with --asin."
        ),
    )
    parser.add_argument("--asin", action="append", default=[], help="Additional ASIN to include.")
    parser.add_argument("--limit", type=int, default=None, help="Limit selected ASINs.")
    parser.add_argument("--batch-size", type=int, default=50, help="Keepa ASINs per product request.")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Exclude ASINs that already have at least one Keepa product snapshot.",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help=(
            "Only select ASINs without a snapshot or with latest snapshot older than this many days. "
            "Selected ASINs are ordered oldest first."
        ),
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=None,
        help="Skip product calls unless Keepa has at least this many tokens available.",
    )
    parser.add_argument("--stats-days", type=int, default=90, help="Keepa stats window in days.")
    parser.add_argument("--offers", type=int, default=None, help="Optional Keepa offers parameter.")
    parser.add_argument(
        "--only-live-offers",
        action="store_true",
        help="Ask Keepa to return only live offers when --offers is used.",
    )
    parser.add_argument(
        "--adaptive-limit",
        action="store_true",
        help="Reduce selected ASINs using current Keepa token balance and --estimated-tokens-per-asin.",
    )
    parser.add_argument(
        "--estimated-tokens-per-asin",
        type=int,
        default=10,
        help="Token estimate used by --adaptive-limit.",
    )
    parser.add_argument(
        "--cycle-progress",
        action="store_true",
        help="For catalog_priority, select ASINs not yet refreshed in the current catalog cycle and emit cycle telemetry.",
    )
    parser.add_argument(
        "--stock",
        action="store_true",
        help="Request Keepa offer stock detail when available. Use selectively because it may cost extra tokens.",
    )
    parser.add_argument("--no-history", action="store_true", help="Do not request Keepa history arrays.")
    parser.add_argument("--no-rating", action="store_true", help="Do not request Keepa rating/review stats.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Count selected ASINs and token status without calling the Keepa product endpoint.",
    )
    parser.add_argument(
        "--write-history",
        action="store_true",
        help="Also write normalized history points. Raw history is always preserved on the product snapshot.",
    )
    parser.add_argument(
        "--max-history-points",
        type=int,
        default=60,
        help="Maximum history points per metric when --write-history is used.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def collect_source_asins(supabase, *, source: str) -> tuple[list[str], dict[str, int]]:
    asins: set[str] = set()
    priority_by_asin: dict[str, int] = {}

    def add_asin(value: Any, priority: int) -> None:
        asin = clean_asin(value)
        if not asin:
            return
        asins.add(asin)
        priority_by_asin[asin] = min(priority_by_asin.get(asin, priority), priority)

    if source in {"canonical", "amazon_active"}:
        for row in fetch_latest_fba_inventory_rows(supabase):
            asin = clean_asin(row.get("asin"))
            if asin and current_quantity(row) > 0:
                add_asin(asin, SOURCE_PRIORITY_LOW)

    if source == "catalog_priority":
        for row in fetch_all(
            supabase,
            "purchase_items",
            "item_id,asin,amazon_title,current_status,exclude_from_purchase_reporting",
        ):
            asin = clean_asin(row.get("asin"))
            status = clean_text(row.get("current_status"))
            if (
                asin
                and not clean_text(row.get("amazon_title"))
                and row.get("exclude_from_purchase_reporting") is not True
                and status not in BLOCKED_CATALOG_STATUSES
            ):
                add_asin(asin, SOURCE_PRIORITY_HIGH)

    if source == "received_fba_prep":
        for row in fetch_all(
            supabase,
            "purchase_items",
            "item_id,asin,current_status,marketplace,exclude_from_purchase_reporting",
        ):
            asin = clean_asin(row.get("asin"))
            status = clean_text(row.get("current_status"))
            marketplace = clean_text(row.get("marketplace"))
            if (
                asin
                and status == "received"
                and marketplace != "ebay"
                and row.get("exclude_from_purchase_reporting") is not True
            ):
                add_asin(asin, SOURCE_PRIORITY_HIGH)
        for asin in fetch_return_recovery_fba_asins(supabase):
            add_asin(asin, SOURCE_PRIORITY_HIGH)

    if source in {"canonical", "purchase_pre_listed"}:
        purchase_rows = fetch_all(
            supabase,
            "vw_purchases_dashboard",
            "item_id,asin,current_status",
        )
        excluded_item_ids = fetch_excluded_item_ids(supabase, purchase_rows)
        for row in purchase_rows:
            asin = clean_asin(row.get("asin"))
            status = clean_text(row.get("current_status"))
            should_include = status not in {"listed", "cancelled", "return_opened", "return_pending"}

            if asin and should_include and row.get("item_id") not in excluded_item_ids:
                priority = SOURCE_PRIORITY_LOW if source == "catalog_priority" else SOURCE_PRIORITY_MEDIUM
                add_asin(asin, priority)

    if source in {"sourcing_active", "catalog_priority"}:
        for row in fetch_all(
            supabase,
            "sourcing_opportunities",
            "asin,status",
        ):
            asin = clean_asin(row.get("asin"))
            status = clean_text(row.get("status"))
            if asin and status in {"open", "watching", "roi_snoozed", "purchased_pending_match"}:
                add_asin(asin, SOURCE_PRIORITY_MEDIUM)

    if source == "catalog_priority":
        for asin in fetch_return_recovery_fba_asins(supabase):
            add_asin(asin, SOURCE_PRIORITY_HIGH)

        for row in fetch_all(
            supabase,
            "purchase_items",
            "asin,current_status,exclude_from_purchase_reporting",
        ):
            status = clean_text(row.get("current_status"))
            if row.get("exclude_from_purchase_reporting") is not True and status not in BLOCKED_CATALOG_STATUSES:
                add_asin(row.get("asin"), SOURCE_PRIORITY_LOW)

        for row in fetch_all(
            supabase,
            "amazon_skus",
            "asin,listing_status,item_status",
        ):
            add_asin(row.get("asin"), SOURCE_PRIORITY_LOW)

        for row in fetch_all(
            supabase,
            "amazon_sales_profitability",
            "asin",
        ):
            add_asin(row.get("asin"), SOURCE_PRIORITY_LOW)

        for row in fetch_all(
            supabase,
            "manual_item_matches",
            "asin",
        ):
            add_asin(row.get("asin"), SOURCE_PRIORITY_LOW)

    return sorted(asins), priority_by_asin


def fetch_return_recovery_fba_asins(supabase) -> list[str]:
    rows = fetch_all(
        supabase,
        "amazon_return_recovery_cases",
        "asin,workflow_state,decision",
        filters={
            "workflow_state": "ready_to_send_back_to_amazon",
            "decision": "send_back_to_amazon",
        },
    )
    return sorted(
        {
            asin
            for row in rows
            if (asin := clean_asin(row.get("asin")))
        }
    )


def update_missing_purchase_titles(
    supabase,
    snapshot_rows: list[dict[str, Any]],
) -> int:
    title_by_asin = {
        asin: title
        for row in snapshot_rows
        if (asin := clean_asin(row.get("asin"))) and (title := clean_text(row.get("title")))
    }
    updated = 0

    for asin, title in title_by_asin.items():
        response = (
            supabase.table("purchase_items")
            .select("item_id,current_status,exclude_from_purchase_reporting")
            .eq("asin", asin)
            .is_("amazon_title", "null")
            .execute()
        )
        rows = response.data or []
        for row in rows:
            status = clean_text(row.get("current_status"))
            if row.get("exclude_from_purchase_reporting") is True or status in BLOCKED_CATALOG_STATUSES:
                continue
            supabase.table("purchase_items").update({"amazon_title": title}).eq(
                "item_id",
                row["item_id"],
            ).execute()
            updated += 1

    return updated


def fetch_latest_fba_inventory_rows(supabase) -> list[dict[str, Any]]:
    latest = (
        supabase.table("amazon_fba_inventory_snapshots")
        .select("captured_at")
        .order("captured_at", desc=True)
        .limit(1)
        .execute()
    )
    captured_at = (latest.data or [{}])[0].get("captured_at")
    if not captured_at:
        return []

    return fetch_all(
        supabase,
        "amazon_fba_inventory_snapshots",
        "asin,total_quantity,fulfillable_quantity,inbound_working_quantity,"
        "inbound_shipped_quantity,inbound_receiving_quantity,reserved_quantity,"
        "unfulfillable_quantity",
        filters={"captured_at": captured_at},
    )


def fetch_excluded_item_ids(
    supabase,
    purchase_rows: list[dict[str, Any]],
) -> set[str]:
    item_ids = sorted(
        {
            str(row.get("item_id"))
            for row in purchase_rows
            if row.get("item_id")
        }
    )
    excluded: set[str] = set()

    for chunk in chunks(item_ids, 100):
        response = (
            supabase.table("purchase_items")
            .select("item_id")
            .eq("exclude_from_purchase_reporting", True)
            .in_("item_id", chunk)
            .execute()
        )
        for row in response.data or []:
            if row.get("item_id"):
                excluded.add(str(row["item_id"]))

    return excluded


def fetch_existing_keepa_asins(supabase) -> set[str]:
    existing: set[str] = set()
    for row in fetch_all(
        supabase,
        "vw_latest_keepa_product_snapshot",
        "asin",
    ):
        asin = clean_asin(row.get("asin"))
        if asin:
            existing.add(asin)
    return existing


def filter_stale_keepa_asins(
    supabase,
    asins: list[str],
    *,
    stale_days: int,
    priority_by_asin: dict[str, int] | None = None,
) -> list[str]:
    if stale_days < 0:
        raise ValueError("--stale-days must be zero or greater.")

    asin_set = {clean_asin(asin) for asin in asins}
    asin_set.discard(None)
    latest_by_asin: dict[str, datetime | None] = {}

    for chunk in chunks(sorted(asin for asin in asin_set if asin), 200):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,captured_at")
            .in_("asin", chunk)
            .execute()
        )
        for row in response.data or []:
            asin = clean_asin(row.get("asin"))
            if asin and asin in asin_set:
                latest_by_asin[asin] = parse_timestamp(row.get("captured_at"))

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    selected = []
    for asin in asins:
        captured_at = latest_by_asin.get(asin)
        if captured_at is None or captured_at < cutoff:
            selected.append(asin)

    priority_by_asin = priority_by_asin or {}

    def sort_key(asin: str) -> tuple[int, int, datetime]:
        captured_at = latest_by_asin.get(asin)
        priority = priority_by_asin.get(asin, SOURCE_PRIORITY_LOW)
        if captured_at is None:
            return (priority, 0, datetime.min.replace(tzinfo=timezone.utc))
        return (priority, 1, captured_at)

    return sorted(selected, key=sort_key)


def build_catalog_cycle_state(
    supabase,
    asins: list[str],
    *,
    priority_by_asin: dict[str, int],
    captured_at: str,
) -> dict[str, Any]:
    eligible_asins = sorted({asin for asin in asins if asin})
    eligible_set = set(eligible_asins)
    previous = fetch_latest_keepa_cycle_metadata(supabase)
    previous_cycle = previous.get("keepa_catalog_cycle") if isinstance(previous, dict) else None
    previous_remaining = []
    if isinstance(previous_cycle, dict):
        previous_remaining = [
            asin
            for asin in previous_cycle.get("remaining_asins_after") or []
            if isinstance(asin, str) and asin in eligible_set
        ]

    previous_eligible = (
        to_int(previous_cycle.get("eligible_count"), default=None)
        if isinstance(previous_cycle, dict)
        else None
    )
    previous_start = (
        clean_text(previous_cycle.get("cycle_started_at"))
        if isinstance(previous_cycle, dict)
        else None
    )
    previous_remaining_count = (
        to_int(previous_cycle.get("remaining_after"), default=None)
        if isinstance(previous_cycle, dict)
        else None
    )

    if (
        previous_start
        and previous_eligible == len(eligible_set)
        and previous_remaining
        and previous_remaining_count
        and previous_remaining_count > 0
    ):
        cycle_started_at = previous_start
        remaining = previous_remaining
        covered_before = max(len(eligible_set) - len(remaining), 0)
    else:
        cycle_started_at = captured_at
        latest_by_asin = fetch_latest_snapshot_by_asin(supabase, eligible_asins)

        def sort_key(asin: str) -> tuple[int, int, str, str]:
            latest_at = latest_by_asin.get(asin)
            return (
                priority_by_asin.get(asin, SOURCE_PRIORITY_LOW),
                1 if latest_at else 0,
                latest_at or "",
                asin,
            )

        remaining = sorted(eligible_asins, key=sort_key)
        covered_before = 0
    cycle_hash = hashlib.sha1(cycle_started_at.encode("utf-8")).hexdigest()[:8]
    cycle_id = f"keepa-{cycle_started_at[:10].replace('-', '')}-{cycle_hash}"
    return {
        "cycle_id": cycle_id,
        "cycle_started_at": cycle_started_at,
        "eligible_count": len(eligible_set),
        "covered_before": covered_before,
        "remaining_before": len(remaining),
        "remaining_asins": remaining,
    }


def finalize_catalog_cycle_state(cycle_state: dict[str, Any], *, inserted_asins: list[str]) -> dict[str, Any]:
    inserted = {asin for asin in inserted_asins if asin}
    remaining_before = [
        asin
        for asin in cycle_state.get("remaining_asins") or []
        if isinstance(asin, str)
    ]
    remaining_after = [asin for asin in remaining_before if asin not in inserted]
    eligible = to_int(cycle_state.get("eligible_count"), default=0) or 0
    covered_after = max(eligible - len(remaining_after), 0)
    return {
        **cycle_state,
        "run_covered_count": len(inserted),
        "covered_after": covered_after,
        "remaining_after": len(remaining_after),
        "remaining_asins_after": remaining_after,
    }


def fetch_latest_snapshot_by_asin(supabase, asins: list[str]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for chunk in chunks(sorted(set(asins)), 200):
        response = (
            supabase.table("vw_latest_keepa_product_snapshot")
            .select("asin,captured_at")
            .in_("asin", chunk)
            .execute()
        )
        for row in response.data or []:
            asin = clean_asin(row.get("asin"))
            if asin:
                latest[asin] = clean_text(row.get("captured_at")) or ""
    return latest


def fetch_latest_keepa_cycle_metadata(supabase) -> dict[str, Any]:
    try:
        response = (
            supabase.table("scheduler_run_jobs")
            .select("metadata,started_at")
            .eq("job_name", "Keepa catalog priority refresh")
            .order("started_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception:
        return {}

    for row in response.data or []:
        metadata = row.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("keepa_catalog_cycle"), dict):
            return metadata
    return {}


def has_offer_data(raw_keepa: Any) -> bool:
    if not isinstance(raw_keepa, dict):
        return False
    offers = raw_keepa.get("offers")
    stats = raw_keepa.get("stats") if isinstance(raw_keepa.get("stats"), dict) else {}
    return bool(
        (isinstance(offers, list) and offers)
        or stats.get("buyBoxSellerId")
        or stats.get("sellerIdsLowestFBA")
        or stats.get("sellerIdsLowestFBM")
    )


def fetch_all(
    supabase,
    table: str,
    select: str,
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        query = supabase.table(table).select(select)
        for column, value in (filters or {}).items():
            query = query.eq(column, value)
        response = query.range(offset, offset + BATCH_SIZE - 1).execute()
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def build_snapshot_row(
    *,
    product: dict[str, Any],
    captured_at: str,
    domain_id: int,
    token_cost: int | None,
    tokens_left: int | None,
) -> dict[str, Any]:
    stats = product.get("stats") if isinstance(product.get("stats"), dict) else {}
    current = stats.get("current") if isinstance(stats.get("current"), list) else []
    avg30 = stats.get("avg30") if isinstance(stats.get("avg30"), list) else []
    avg90 = stats.get("avg90") if isinstance(stats.get("avg90"), list) else []
    avg180 = stats.get("avg180") if isinstance(stats.get("avg180"), list) else []

    return {
        "captured_at": captured_at,
        "domain_id": domain_id,
        "asin": clean_asin(product.get("asin")),
        "title": clean_text(product.get("title")),
        "brand": clean_text(product.get("brand")),
        "manufacturer": clean_text(product.get("manufacturer")),
        "product_group": clean_text(product.get("productGroup")),
        "root_category": to_int(product.get("rootCategory"), default=None),
        "category_tree_json": product.get("categoryTree"),
        "buy_box_price_current_cents": stat_value(current, CSV_BUY_BOX),
        "buy_box_price_avg30_cents": stat_value(avg30, CSV_BUY_BOX),
        "buy_box_price_avg90_cents": stat_value(avg90, CSV_BUY_BOX),
        "amazon_price_current_cents": stat_value(current, CSV_AMAZON),
        "new_price_current_cents": stat_value(current, CSV_NEW),
        "new_fba_price_current_cents": stat_value(current, CSV_NEW_FBA),
        "used_price_current_cents": stat_value(current, CSV_USED),
        "sales_rank_current": stat_value(current, CSV_SALES_RANK),
        "sales_rank_avg30": stat_value(avg30, CSV_SALES_RANK),
        "sales_rank_avg90": stat_value(avg90, CSV_SALES_RANK),
        "sales_rank_avg180": stat_value(avg180, CSV_SALES_RANK),
        "sales_rank_drops30": to_int(stats.get("salesRankDrops30"), default=None),
        "sales_rank_drops90": to_int(stats.get("salesRankDrops90"), default=None),
        "sales_rank_drops180": to_int(stats.get("salesRankDrops180"), default=None),
        "offer_count_current": stat_value(current, CSV_COUNT_NEW),
        "review_count_current": stat_value(current, CSV_COUNT_REVIEWS),
        "rating_current": rating_value(stat_value(current, CSV_RATING)),
        "raw_keepa_json": product,
        "token_cost": token_cost,
        "tokens_left": tokens_left,
        "source": "keepa_product",
    }


def build_history_rows(
    *,
    product: dict[str, Any],
    snapshot_id_placeholder: str | None,
    domain_id: int,
    max_points_per_metric: int,
) -> list[dict[str, Any]]:
    asin = clean_asin(product.get("asin"))
    csv_rows = product.get("csv") if isinstance(product.get("csv"), list) else []
    if not asin:
        return []

    rows: list[dict[str, Any]] = []
    for index, metric_name in HISTORY_METRICS.items():
        if index >= len(csv_rows) or not isinstance(csv_rows[index], list):
            continue
        points = csv_rows[index]
        parsed = parse_keepa_history_points(points)
        for observed_at, metric_value in parsed[-max_points_per_metric:]:
            rows.append(
                {
                    "keepa_product_snapshot_id": snapshot_id_placeholder,
                    "domain_id": domain_id,
                    "asin": asin,
                    "metric_name": metric_name,
                    "observed_at": observed_at,
                    "metric_value": metric_value,
                }
            )
    return rows


def insert_keepa_rows(
    supabase,
    snapshot_rows: list[dict[str, Any]],
    *,
    build_history: bool,
    domain_id: int,
    max_points_per_metric: int,
) -> tuple[int, int]:
    inserted_snapshots = 0
    inserted_history = 0

    for row in snapshot_rows:
        response = supabase.table("keepa_product_snapshots").insert(row).execute()
        inserted = (response.data or [{}])[0]
        snapshot_id = inserted.get("keepa_product_snapshot_id")
        inserted_snapshots += 1

        if not build_history or not snapshot_id:
            continue
        history_rows = build_history_rows(
            product=row["raw_keepa_json"],
            snapshot_id_placeholder=snapshot_id,
            domain_id=domain_id,
            max_points_per_metric=max_points_per_metric,
        )
        for chunk in chunks(history_rows, BATCH_SIZE):
            supabase.table("keepa_product_history_points").insert(chunk).execute()
            inserted_history += len(chunk)

    return inserted_snapshots, inserted_history


def print_summary(
    *,
    write: bool,
    selected: int,
    eligible: int,
    rows_read: int,
    snapshots: int,
    history_points: int,
    missing_products: int,
    failures: int,
    token_status_before: dict[str, Any],
    token_cost_total: int,
    tokens_left_after: int | None,
    cycle_state: dict[str, Any] | None,
) -> None:
    print("Keepa product sync write" if write else "Keepa product sync dry run")
    print("---------------------------")
    print(f"Eligible ASINs: {eligible}")
    print(f"ASINs selected: {selected}")
    print(f"Products returned: {rows_read}")
    print(f"Snapshot rows prepared: {snapshots}")
    print(f"History points parsed: {history_points}")
    print(f"Missing products: {missing_products}")
    print(f"Failures: {failures}")
    print(f"Tokens before: {token_status_before.get('tokens_left')}")
    print(f"Keepa tokens used: {token_cost_total}")
    print(f"Tokens after: {tokens_left_after}")
    if cycle_state:
        print(f"Cycle eligible ASINs: {cycle_state.get('eligible_count')}")
        print(f"Cycle covered before: {cycle_state.get('covered_before')}")
        print(f"Cycle remaining before: {cycle_state.get('remaining_before')}")


def print_cycle_summary(cycle_state: dict[str, Any]) -> None:
    print(f"Run ASINs covered: {cycle_state.get('run_covered_count')}")
    print(f"Cycle covered after: {cycle_state.get('covered_after')}")
    print(f"Cycle remaining after: {cycle_state.get('remaining_after')}")


def print_metadata_json(
    cycle_state: dict[str, Any],
    *,
    selected: int,
    rows_read: int,
    token_status_before: dict[str, Any],
    token_cost_total: int,
    tokens_left_after: int | None,
) -> None:
    cycle = {
        key: value
        for key, value in cycle_state.items()
        if key not in {"remaining_asins"}
    }
    cycle["asins_selected"] = selected
    cycle["run_covered"] = rows_read
    cycle["tokens_before"] = to_int(token_status_before.get("tokens_left"), default=None)
    cycle["tokens_after"] = tokens_left_after
    cycle["tokens_used"] = token_cost_total
    metadata = {
        "keepa_catalog_cycle": cycle,
        "metrics": [
            {"label": "Run ASINs covered", "value": rows_read},
            {"label": "Keepa tokens used", "value": token_cost_total},
            {"label": "Tokens before", "value": to_int(token_status_before.get("tokens_left"), default=0) or 0},
            {"label": "Tokens after", "value": tokens_left_after or 0},
            {"label": "Cycle eligible ASINs", "value": cycle_state.get("eligible_count") or 0},
            {"label": "Cycle covered after", "value": cycle_state.get("covered_after") or 0},
            {"label": "Cycle remaining after", "value": cycle_state.get("remaining_after") or 0},
            {"label": "ASINs selected", "value": selected},
        ],
    }
    print(f"METADATA_JSON: {json.dumps(metadata, sort_keys=True)}")


def print_plan_summary(asins: list[str], token_status_before: dict[str, Any]) -> None:
    print("Keepa product sync plan")
    print("-----------------------")
    print(f"ASINs selected: {len(asins)}")
    print(f"Tokens available: {token_status_before.get('tokens_left')}")
    print(f"Refill in ms: {token_status_before.get('refill_in')}")
    print(f"Refill rate: {token_status_before.get('refill_rate')}")


def current_quantity(row: dict[str, Any]) -> int:
    return sum(
        to_int(row.get(field), default=0) or 0
        for field in (
            "total_quantity",
            "fulfillable_quantity",
            "inbound_working_quantity",
            "inbound_shipped_quantity",
            "inbound_receiving_quantity",
            "reserved_quantity",
            "unfulfillable_quantity",
        )
    )


def parse_keepa_history_points(values: list[Any]) -> list[tuple[str, int | None]]:
    points: list[tuple[str, int | None]] = []
    for index in range(0, len(values) - 1, 2):
        keepa_minute = to_int(values[index], default=None)
        if keepa_minute is None:
            continue
        metric_value = normalized_metric_value(values[index + 1])
        observed_at = datetime.fromtimestamp(
            KEEPA_EPOCH_SECONDS + keepa_minute * 60,
            tz=timezone.utc,
        ).replace(microsecond=0)
        points.append((observed_at.isoformat().replace("+00:00", "Z"), metric_value))
    return points


def stat_value(values: list[Any], index: int) -> int | None:
    if index >= len(values):
        return None
    return normalized_metric_value(values[index])


def normalized_metric_value(value: Any) -> int | None:
    integer = to_int(value, default=None)
    if integer is None or integer < 0:
        return None
    return integer


def rating_value(value: int | None) -> float | None:
    if value is None:
        return None
    if value > 50:
        return round(value / 10, 2)
    return float(value)


def chunks(rows: list[Any], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.upper()
    return text if len(text) == 10 else None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_timestamp(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
