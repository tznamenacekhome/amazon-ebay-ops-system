"""Sync read-only Amazon FBA inventory summaries into MBOP tables.

Reads Amazon SP-API FBA Inventory and writes only Amazon-specific Supabase
tables:
- amazon_skus
- amazon_fba_inventory_snapshots

This script intentionally does not write to purchases or purchase_items.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_fba_inventory_sync")
BATCH_SIZE = 500


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    load_dotenv()

    try:
        client = AmazonSPAPIClient.from_env()
        supabase = get_supabase_client()
        captured_at = utc_now_iso()
        marketplace_id = client.config.marketplace_id
        summaries = list(
            client.iter_inventory_summaries(
                details=True,
                max_pages=args.max_pages,
            )
        )

        if args.limit is not None:
            summaries = summaries[: args.limit]

        LOGGER.info("Fetched Amazon FBA inventory summaries: %s", len(summaries))

        sku_rows = []
        snapshot_rows = []
        skipped_without_sku = 0

        for summary in summaries:
            seller_sku = clean_text(summary.get("sellerSku"))
            if not seller_sku:
                skipped_without_sku += 1
                continue

            sku_rows.append(build_sku_row(summary, seller_sku, marketplace_id))
            snapshot_rows.append(
                build_snapshot_row(summary, seller_sku, marketplace_id, captured_at)
            )

        if args.dry_run:
            LOGGER.info(
                "Dry run complete. sku_rows=%s snapshot_rows=%s skipped_without_sku=%s",
                len(sku_rows),
                len(snapshot_rows),
                skipped_without_sku,
            )
            return 0

        upserted_skus = upsert_amazon_skus(supabase, sku_rows)
        inserted_snapshots = insert_inventory_snapshots(supabase, snapshot_rows)

        LOGGER.info("Amazon FBA inventory sync complete.")
        LOGGER.info("Summaries fetched: %s", len(summaries))
        LOGGER.info("SKU rows upserted: %s", upserted_skus)
        LOGGER.info("Snapshot rows inserted: %s", inserted_snapshots)
        LOGGER.info("Skipped without sellerSku: %s", skipped_without_sku)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon SP-API sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Unexpected Amazon inventory sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Amazon FBA inventory summaries into MBOP."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalize inventory but do not write to Supabase.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of inventory summaries to process.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional maximum Amazon pagination pages to fetch.",
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


def build_sku_row(
    summary: dict[str, Any],
    seller_sku: str,
    marketplace_id: str,
) -> dict[str, Any]:
    return {
        "seller_sku": seller_sku,
        "marketplace_id": marketplace_id,
        "asin": clean_text(summary.get("asin")),
        "fnsku": clean_text(summary.get("fnSku") or summary.get("fnsku")),
        "product_name": clean_text(summary.get("productName")),
        "condition": clean_text(summary.get("condition")),
        "fulfillment_channel": "Amazon",
        "listing_status": clean_text(summary.get("inventoryDetails", {}).get("status")),
        "item_status": clean_text(summary.get("inventoryDetails", {}).get("status")),
        "last_listing_sync_at": utc_now_iso(),
        "raw_listing_json": summary,
        "updated_at": utc_now_iso(),
    }


def build_snapshot_row(
    summary: dict[str, Any],
    seller_sku: str,
    marketplace_id: str,
    captured_at: str,
) -> dict[str, Any]:
    details = summary.get("inventoryDetails") or {}
    reserved = details.get("reservedQuantity") or {}
    researching = details.get("researchingQuantity") or {}
    researching_breakdown = researching.get("researchingQuantityBreakdown") if isinstance(researching, dict) else []
    future_supply = details.get("futureSupplyQuantity") or {}
    unfulfillable = details.get("unfulfillableQuantity") or {}

    return {
        "captured_at": captured_at,
        "marketplace_id": marketplace_id,
        "seller_sku": seller_sku,
        "asin": clean_text(summary.get("asin")),
        "fnsku": clean_text(summary.get("fnSku") or summary.get("fnsku")),
        "product_name": clean_text(summary.get("productName")),
        "condition": clean_text(summary.get("condition")),
        "total_quantity": to_int(summary.get("totalQuantity")),
        "fulfillable_quantity": to_int(details.get("fulfillableQuantity")),
        "inbound_working_quantity": to_int(details.get("inboundWorkingQuantity")),
        "inbound_shipped_quantity": to_int(details.get("inboundShippedQuantity")),
        "inbound_receiving_quantity": to_int(details.get("inboundReceivingQuantity")),
        "reserved_quantity": to_int(
            reserved.get("totalReservedQuantity")
            if isinstance(reserved, dict)
            else reserved
        ),
        "reserved_customer_order_quantity": to_int(
            reserved.get("pendingCustomerOrderQuantity")
            if isinstance(reserved, dict)
            else None
        ),
        "reserved_fc_transfer_quantity": to_int(
            reserved.get("pendingTransshipmentQuantity")
            if isinstance(reserved, dict)
            else None
        ),
        "reserved_fc_processing_quantity": to_int(
            reserved.get("fcProcessingQuantity")
            if isinstance(reserved, dict)
            else None
        ),
        "future_supply_buyable_quantity": to_int(
            future_supply.get("futureSupplyBuyableQuantity")
            if isinstance(future_supply, dict)
            else None
        ),
        "reserved_future_supply_quantity": to_int(
            future_supply.get("reservedFutureSupplyQuantity")
            if isinstance(future_supply, dict)
            else None
        ),
        "researching_quantity": to_int(
            researching.get("totalResearchingQuantity")
            if isinstance(researching, dict)
            else researching
        ),
        "researching_short_term_quantity": researching_quantity_breakdown(
            researching_breakdown,
            "researchingQuantityInShortTerm",
        ),
        "researching_mid_term_quantity": researching_quantity_breakdown(
            researching_breakdown,
            "researchingQuantityInMidTerm",
        ),
        "researching_long_term_quantity": researching_quantity_breakdown(
            researching_breakdown,
            "researchingQuantityInLongTerm",
        ),
        "unfulfillable_quantity": to_int(
            unfulfillable.get("totalUnfulfillableQuantity")
            if isinstance(unfulfillable, dict)
            else unfulfillable
        ),
        "unfulfillable_customer_damaged_quantity": to_int(
            unfulfillable.get("customerDamagedQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "unfulfillable_warehouse_damaged_quantity": to_int(
            unfulfillable.get("warehouseDamagedQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "unfulfillable_distributor_damaged_quantity": to_int(
            unfulfillable.get("distributorDamagedQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "unfulfillable_carrier_damaged_quantity": to_int(
            unfulfillable.get("carrierDamagedQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "unfulfillable_defective_quantity": to_int(
            unfulfillable.get("defectiveQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "unfulfillable_expired_quantity": to_int(
            unfulfillable.get("expiredQuantity")
            if isinstance(unfulfillable, dict)
            else None
        ),
        "raw_inventory_json": summary,
        "source": "amazon_spapi",
    }


def upsert_amazon_skus(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_skus").upsert(
            chunk,
            on_conflict="seller_sku,marketplace_id",
        ).execute()
        count += len(chunk)
    return count


def insert_inventory_snapshots(supabase, rows: list[dict[str, Any]]) -> int:
    count = 0
    for chunk in chunks(rows, BATCH_SIZE):
        supabase.table("amazon_fba_inventory_snapshots").insert(chunk).execute()
        count += len(chunk)
    return count


def chunks(rows: list[dict[str, Any]], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def to_int(value: Any) -> int | None:
    if value is None:
        return None


def researching_quantity_breakdown(rows: Any, name: str) -> int | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("name") == name:
            return to_int(row.get("quantity"))
    return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
