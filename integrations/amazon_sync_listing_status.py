"""Sync read-only Amazon Listings Items status into MBOP.

Reads Amazon SP-API Listings Items and writes only Amazon-specific Supabase
tables:
- amazon_listing_snapshots
- amazon_skus listing-status fields

This script intentionally does not write to purchases or purchase_items.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_listing_status_sync")
BATCH_SIZE = 500
DEFAULT_INCLUDED_DATA = [
    "summaries",
    "issues",
    "fulfillmentAvailability",
]


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        client = AmazonSPAPIClient.from_env()
        if not client.config.seller_id:
            raise AmazonSPAPIError(
                "Amazon Listings Items sync requires AMAZON_SP_API_SELLER_ID "
                "(or AMAZON_SELLER_ID / AMAZON_MERCHANT_ID) in .env."
            )
        supabase = get_supabase_client()
        marketplace_id = client.config.marketplace_id
        captured_at = utc_now_iso()
        sku_rows = fetch_amazon_skus(
            supabase,
            marketplace_id,
            active_only=args.active_only,
            stale_days=args.stale_days,
        )

        if args.limit is not None:
            sku_rows = sku_rows[: args.limit]

        LOGGER.info("Amazon SKUs selected for listing sync: %s", len(sku_rows))

        snapshot_rows: list[dict[str, Any]] = []
        sku_updates: list[dict[str, Any]] = []
        failures = 0

        for index, sku in enumerate(sku_rows, start=1):
            seller_sku = clean_text(sku.get("seller_sku"))
            if not seller_sku:
                continue

            try:
                payload = client.get_listing_item(
                    seller_sku,
                    included_data=DEFAULT_INCLUDED_DATA,
                )
            except AmazonSPAPIError as error:
                failures += 1
                LOGGER.warning("Listing fetch failed for seller_sku=%s: %s", seller_sku, error)
                continue

            snapshot = build_listing_snapshot(
                payload=payload,
                sku=sku,
                marketplace_id=marketplace_id,
                captured_at=captured_at,
            )
            snapshot_rows.append(snapshot)
            sku_updates.append(build_sku_update(snapshot, sku))

            if index % 50 == 0:
                LOGGER.info("Fetched listing status rows: %s/%s", index, len(sku_rows))

            if args.request_delay_seconds > 0:
                time.sleep(args.request_delay_seconds)

        if args.dry_run:
            LOGGER.info(
                "Dry run complete. listing_snapshots=%s sku_updates=%s failures=%s",
                len(snapshot_rows),
                len(sku_updates),
                failures,
            )
            print_summary(snapshot_rows, failures)
            return 0

        inserted = insert_listing_snapshots(supabase, snapshot_rows)
        updated = upsert_amazon_skus(supabase, sku_updates)

        LOGGER.info("Amazon listing status sync complete.")
        LOGGER.info("Listing snapshots inserted: %s", inserted)
        LOGGER.info("Amazon SKU rows updated: %s", updated)
        LOGGER.info("Listing fetch failures: %s", failures)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon SP-API listing sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Amazon listing sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Amazon Listings Items status into MBOP."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalize listing status but do not write to Supabase.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of Amazon SKUs to process.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only sync SKUs with positive current FBA inventory snapshot quantity.",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=None,
        help="Only sync SKUs whose last real Listings API sync is missing or older than this many days.",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.25,
        help="Delay between Listings Items calls. Default stays near 4 requests/sec.",
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


def fetch_amazon_skus(
    supabase,
    marketplace_id: str,
    active_only: bool,
    stale_days: int | None,
) -> list[dict[str, Any]]:
    if not active_only:
        return filter_stale_skus(fetch_all(
            supabase,
            "amazon_skus",
            "amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name,condition,last_listing_sync_at",
            marketplace_id=marketplace_id,
        ), stale_days)

    snapshots = fetch_all(
        supabase,
        "vw_latest_amazon_fba_inventory_snapshot",
        "seller_sku,marketplace_id,total_quantity,fulfillable_quantity,"
        "inbound_working_quantity,inbound_shipped_quantity,inbound_receiving_quantity,"
        "reserved_quantity,unfulfillable_quantity",
        marketplace_id=marketplace_id,
    )
    active_skus = {
        row.get("seller_sku")
        for row in snapshots
        if current_quantity(row) > 0 and row.get("seller_sku")
    }
    if not active_skus:
        return []

    rows: list[dict[str, Any]] = []
    for chunk in chunks(sorted(active_skus), 100):
        response = (
            supabase.table("amazon_skus")
            .select("amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name,condition,last_listing_sync_at")
            .eq("marketplace_id", marketplace_id)
            .in_("seller_sku", chunk)
            .execute()
        )
        rows.extend(response.data or [])
    return filter_stale_skus(rows, stale_days)


def filter_stale_skus(rows: list[dict[str, Any]], stale_days: int | None) -> list[dict[str, Any]]:
    if stale_days is None:
        return rows

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(stale_days, 0))
    filtered = []
    for row in rows:
        synced_at = parse_datetime(row.get("last_listing_sync_at"))
        if synced_at is None or synced_at < cutoff:
            filtered.append(row)
    return filtered


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_all(
    supabase,
    table: str,
    select: str,
    *,
    marketplace_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        query = supabase.table(table).select(select)
        if marketplace_id:
            query = query.eq("marketplace_id", marketplace_id)
        response = query.range(offset, offset + BATCH_SIZE - 1).execute()
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def build_listing_snapshot(
    *,
    payload: dict[str, Any],
    sku: dict[str, Any],
    marketplace_id: str,
    captured_at: str,
) -> dict[str, Any]:
    summary = first_for_marketplace(payload.get("summaries"), marketplace_id)
    fulfillment = payload.get("fulfillmentAvailability") or []
    issues = payload.get("issues") or []
    listing_status = normalize_status_value(summary.get("status") if summary else None)
    condition = clean_text((summary or {}).get("conditionType")) or clean_text(sku.get("condition"))

    return {
        "captured_at": captured_at,
        "amazon_sku_id": sku.get("amazon_sku_id"),
        "marketplace_id": marketplace_id,
        "seller_sku": clean_text(sku.get("seller_sku")),
        "asin": clean_text((summary or {}).get("asin")) or clean_text(sku.get("asin")),
        "product_name": clean_text((summary or {}).get("itemName")) or clean_text(sku.get("product_name")),
        "condition": condition,
        "listing_status": listing_status,
        "item_status": listing_status,
        "fulfillment_channel": fulfillment_channel(fulfillment),
        "fulfillment_availability": fulfillment,
        "issue_count": len(issues),
        "issue_severity": max_issue_severity(issues),
        "issues_json": issues,
        "raw_listing_json": payload,
        "source": "amazon_spapi_listings_items",
    }


def build_sku_update(snapshot: dict[str, Any], sku: dict[str, Any]) -> dict[str, Any]:
    return {
        "amazon_sku_id": sku.get("amazon_sku_id"),
        "seller_sku": sku.get("seller_sku"),
        "marketplace_id": sku.get("marketplace_id"),
        "asin": snapshot.get("asin") or sku.get("asin"),
        "fnsku": sku.get("fnsku"),
        "product_name": snapshot.get("product_name") or sku.get("product_name"),
        "condition": snapshot.get("condition") or sku.get("condition"),
        "listing_status": snapshot.get("listing_status"),
        "item_status": snapshot.get("item_status"),
        "fulfillment_channel": snapshot.get("fulfillment_channel"),
        "last_listing_sync_at": utc_now_iso(),
        "raw_listing_json": snapshot.get("raw_listing_json"),
        "updated_at": utc_now_iso(),
    }


def insert_listing_snapshots(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_listing_snapshots").insert(chunk).execute()
        count += len(chunk)
    return count


def upsert_amazon_skus(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_skus").upsert(
            chunk,
            on_conflict="seller_sku,marketplace_id",
        ).execute()
        count += len(chunk)
    return count


def print_summary(snapshot_rows: list[dict[str, Any]], failures: int) -> None:
    with_issues = [row for row in snapshot_rows if row["issue_count"] > 0]
    statuses: dict[str, int] = {}
    for row in snapshot_rows:
        status = row.get("listing_status") or "unknown"
        statuses[status] = statuses.get(status, 0) + 1

    print("Amazon listing status dry run")
    print("-----------------------------")
    print(f"Rows fetched: {len(snapshot_rows)}")
    print(f"Rows with issues: {len(with_issues)}")
    print(f"Failures: {failures}")
    print("Statuses:")
    for status, count in sorted(statuses.items()):
        print(f"- {status}: {count}")

    if with_issues:
        print("\nFirst listing issue rows:")
        for row in with_issues[:10]:
            print(
                f"- seller_sku={row.get('seller_sku')} asin={row.get('asin')} "
                f"status={row.get('listing_status') or '--'} issues={row.get('issue_count')}"
            )


def current_quantity(row: dict[str, Any]) -> int:
    return sum(
        to_int(row.get(field), default=0)
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


def first_for_marketplace(value: Any, marketplace_id: str) -> dict[str, Any] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict) and item.get("marketplaceId") == marketplace_id:
            return item
    for item in value:
        if isinstance(item, dict):
            return item
    return None


def normalize_status_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ",".join(str(item).strip() for item in value if str(item).strip()) or None
    return clean_text(value)


def fulfillment_channel(fulfillment: Any) -> str | None:
    if not isinstance(fulfillment, list) or not fulfillment:
        return None
    channels = sorted(
        {
            str(item.get("fulfillmentChannelCode") or "").strip()
            for item in fulfillment
            if isinstance(item, dict) and item.get("fulfillmentChannelCode")
        }
    )
    return ",".join(channels) or None


def max_issue_severity(issues: Any) -> str | None:
    if not isinstance(issues, list) or not issues:
        return None
    order = {"ERROR": 3, "WARNING": 2, "INFO": 1}
    severities = [
        str(issue.get("severity") or "").upper()
        for issue in issues
        if isinstance(issue, dict)
    ]
    severities = [severity for severity in severities if severity]
    if not severities:
        return None
    return max(severities, key=lambda severity: order.get(severity, 0))


def chunks(rows: list[Any] | list[str] | set[str], size: int):
    items = list(rows)
    for index in range(0, len(items), size):
        yield items[index : index + size]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any, default: int = 0) -> int:
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
