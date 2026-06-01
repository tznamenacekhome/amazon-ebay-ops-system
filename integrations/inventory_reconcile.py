"""Project MBOP inventory positions and reconcile them to Amazon FBA snapshots.

This integration builds a derived inventory-state layer from authoritative
workflow tables. It does not update purchases, purchase_items, receiving, FBA
shipment workflow rows, or Amazon SP-API snapshot rows.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

LOGGER = logging.getLogger("inventory_reconcile")
BATCH_SIZE = 500
ITEM_LOOKUP_BATCH_SIZE = 100
DERIVATION_VERSION = "inventory_state_v1"


@dataclass(frozen=True)
class StateProjection:
    inventory_state: str
    physical_location: str
    marketplace_intent: str
    listing_channel: str
    operational_status: str
    condition_disposition: str = "new"
    needs_reconciliation: bool = False
    reconciliation_status: str = "not_checked"


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()

    try:
        supabase = get_supabase_client()
        purchase_rows = fetch_all(
            supabase,
            "vw_purchases_dashboard",
            "*",
            order_by="item_id",
        )
        item_meta = fetch_item_meta(supabase, purchase_rows)
        fba_item_links = fetch_fba_item_links(supabase)
        amazon_skus = fetch_amazon_skus(supabase)
        inventorylab_backfill = fetch_inventorylab_backfill(supabase)
        amazon_snapshots = fetch_all(
            supabase,
            "vw_latest_amazon_fba_inventory_snapshot",
            "*",
        )
        amazon_listing_snapshots = fetch_all(
            supabase,
            "vw_latest_amazon_listing_snapshot",
            "*",
        )
        amazon_current_asins = current_amazon_asins(amazon_snapshots)

        mbop_positions = build_mbop_positions(
            purchase_rows,
            item_meta,
            fba_item_links,
            amazon_current_asins,
        )
        amazon_positions = build_amazon_positions(
            amazon_snapshots,
            amazon_skus,
            inventorylab_backfill,
        )
        reconciliation = reconcile_amazon_inventory(
            mbop_positions,
            amazon_positions,
            amazon_listing_snapshots,
        )

        LOGGER.info("MBOP positions projected: %s", len(mbop_positions))
        LOGGER.info("Amazon positions projected: %s", len(amazon_positions))
        LOGGER.info("Reconciliation findings: %s", len(reconciliation["items"]))

        if args.dry_run:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        replace_current_positions(supabase, mbop_positions + amazon_positions)
        write_reconciliation_event(supabase, reconciliation)

        LOGGER.info("Inventory reconciliation complete.")
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("Inventory reconciliation failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build MBOP inventory positions and reconcile Amazon FBA inventory."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build projections and reconciliation findings without writing to Supabase.",
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


def fetch_all(
    supabase,
    table: str,
    select: str,
    order_by: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        query = supabase.table(table).select(select)
        if order_by:
            query = query.order(order_by)
        response = query.range(offset, offset + BATCH_SIZE - 1).execute()
        data = response.data or []
        rows.extend(data)

        if len(data) < BATCH_SIZE:
            return rows

        offset += BATCH_SIZE


def fetch_item_meta(
    supabase,
    purchase_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    item_ids = [
        row.get("item_id")
        for row in purchase_rows
        if isinstance(row.get("item_id"), str)
    ]
    if not item_ids:
        return {}

    meta: dict[str, dict[str, Any]] = {}
    select = (
        "item_id,amazon_title,marketplace,received_date,"
        "exclude_from_purchase_reporting,exclusion_reason"
    )

    for chunk in chunks(item_ids, ITEM_LOOKUP_BATCH_SIZE):
        response = supabase.table("purchase_items").select(select).in_("item_id", chunk).execute()
        for item in response.data or []:
            meta[item["item_id"]] = item

    return meta


def fetch_fba_item_links(supabase) -> dict[str, list[dict[str, Any]]]:
    links: dict[str, list[dict[str, Any]]] = defaultdict(list)
    shipment_meta = {
        row["fba_shipment_id"]: row
        for row in fetch_all(
            supabase,
            "fba_shipments",
            "fba_shipment_id,shipment_code,workflow_status",
        )
        if row.get("fba_shipment_id")
    }
    rows = fetch_all(
        supabase,
        "fba_shipment_items",
        "fba_shipment_item_id,fba_shipment_id,item_id,quantity,included",
    )

    for row in rows:
        item_id = row.get("item_id")
        if row.get("included") and isinstance(item_id, str):
            shipment = shipment_meta.get(row.get("fba_shipment_id"), {})
            row["fba_shipment_code"] = shipment.get("shipment_code")
            row["fba_shipment_workflow_status"] = shipment.get("workflow_status")
            links[item_id].append(row)

    return links


def fetch_amazon_skus(supabase) -> dict[tuple[str, str], dict[str, Any]]:
    rows = fetch_all(
        supabase,
        "amazon_skus",
        "amazon_sku_id,seller_sku,marketplace_id,asin,fnsku,product_name,condition",
    )
    return {
        (str(row.get("seller_sku") or ""), str(row.get("marketplace_id") or "")): row
        for row in rows
        if row.get("seller_sku") and row.get("marketplace_id")
    }


def fetch_inventorylab_backfill(supabase) -> dict[str, dict[str, Any]]:
    try:
        rows = fetch_all(
            supabase,
            "inventorylab_active_inventory_backfill",
            "seller_sku,asin,title,on_hand_quantity,active_cost_per_unit,"
            "active_date_purchased,match_status,match_method,requires_review",
        )
    except Exception as error:  # noqa: BLE001 - optional historical overlay
        LOGGER.warning("InventoryLab backfill lookup skipped: %s", error)
        return {}

    backfill_by_sku: dict[str, dict[str, Any]] = {}
    for row in rows:
        seller_sku = clean_text(row.get("seller_sku"))
        if not seller_sku:
            continue
        if row.get("match_status") != "matched":
            continue
        if row.get("match_method") != "seller_sku":
            continue
        if row.get("requires_review"):
            continue
        if to_float(row.get("active_cost_per_unit")) is None:
            continue
        backfill_by_sku[seller_sku] = row

    LOGGER.info("InventoryLab cost/date overlay rows loaded: %s", len(backfill_by_sku))
    return backfill_by_sku


def build_mbop_positions(
    purchase_rows: list[dict[str, Any]],
    item_meta: dict[str, dict[str, Any]],
    fba_item_links: dict[str, list[dict[str, Any]]],
    amazon_current_asins: set[str],
) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []
    projected_fba_shipment_item_ids: set[str] = set()
    effective_at = utc_now_iso()

    for row in purchase_rows:
        item_id = row.get("item_id")
        if not isinstance(item_id, str):
            continue

        meta = item_meta.get(item_id, {})
        if bool(meta.get("exclude_from_purchase_reporting")):
            continue

        quantity = to_int(row.get("quantity"), default=0)
        if quantity <= 0:
            continue

        links = fba_item_links.get(item_id) or [{}]
        projection = project_purchase_state(
            row,
            meta,
            has_current_fba_shipment_link(links),
            amazon_current_asins,
        )
        unit_cost = to_float(row.get("unit_cost"))
        title = meta.get("amazon_title") or row.get("amazon_title") or row.get("title")

        for link in links:
            fba_shipment_item_id = link.get("fba_shipment_item_id")
            if isinstance(fba_shipment_item_id, str):
                if fba_shipment_item_id in projected_fba_shipment_item_ids:
                    continue
                projected_fba_shipment_item_ids.add(fba_shipment_item_id)

            link_quantity = to_int(link.get("quantity"), default=quantity)
            link_quantity = min(max(link_quantity, 1), quantity)
            positions.append(
                {
                    "purchase_item_id": item_id,
                    "fba_shipment_id": link.get("fba_shipment_id"),
                    "fba_shipment_item_id": fba_shipment_item_id,
                    "source_system": "mbop",
                    "source_table": "purchase_items",
                    "source_id": item_id,
                    "external_reference_type": "supplier_order_id",
                    "external_reference_id": row.get("supplier_order_id"),
                    "asin": clean_asin(row.get("asin")),
                    "title": clean_text(title),
                    "system": clean_text(row.get("system")),
                    "quantity": link_quantity,
                    "unit_cost": unit_cost,
                    "total_cost": unit_cost * link_quantity if unit_cost is not None else None,
                    "currency": "USD",
                    "inventory_state": projection.inventory_state,
                    "physical_location": projection.physical_location,
                    "marketplace_intent": projection.marketplace_intent,
                    "listing_channel": projection.listing_channel,
                    "operational_status": projection.operational_status,
                    "condition_disposition": projection.condition_disposition,
                    "reconciliation_status": projection.reconciliation_status,
                    "needs_reconciliation": projection.needs_reconciliation,
                    "derived_from": "workflow_projection",
                    "derivation_version": DERIVATION_VERSION,
                    "effective_at": effective_at,
                }
            )

    return positions


def has_current_fba_shipment_link(links: list[dict[str, Any]]) -> bool:
    for link in links:
        shipment_code = clean_text(link.get("fba_shipment_code"))
        workflow_status = normalize_status(link.get("fba_shipment_workflow_status"))
        if not shipment_code or shipment_code == "legacy_listed_no_shipment_id":
            continue
        if workflow_status == "historical":
            continue
        return True
    return False


def project_purchase_state(
    row: dict[str, Any],
    meta: dict[str, Any],
    has_current_fba_link: bool,
    amazon_current_asins: set[str],
) -> StateProjection:
    status = normalize_status(row.get("current_status"))
    marketplace = clean_text(meta.get("marketplace"))
    asin = clean_asin(row.get("asin"))

    if status == "cancelled":
        return StateProjection(
            "cancelled_refund_follow_up",
            "supplier",
            "none",
            "none",
            "cancelled",
            needs_reconciliation=True,
            reconciliation_status="ignored",
        )
    if status == "return_opened":
        return StateProjection("return_opened", "home", "return_to_supplier", "none", "return_opened")
    if status == "return_pending":
        return StateProjection("return_pending", "home", "return_to_supplier", "none", "return_pending")
    if status == "listed":
        if marketplace == "eBay":
            return StateProjection("home_ebay_resale_listed", "home", "ebay_resale", "ebay", "listed")
        if has_current_fba_link:
            return StateProjection(
                "outbound_to_amazon",
                "in_transit_to_amazon",
                "amazon_fba",
                "amazon",
                "listed",
                needs_reconciliation=True,
            )
        return StateProjection("sold_amazon", "buyer", "amazon_fba", "amazon", "sold")
    if status == "received":
        if marketplace == "eBay":
            return StateProjection("transferred_to_ebay", "home", "ebay_resale", "none", "transferred")
        if marketplace == "Amazon":
            return StateProjection(
                "received_assigned_amazon_not_sent",
                "home",
                "amazon_fba",
                "none",
                "ready_to_list",
            )
        return StateProjection("received_unassigned", "home", "undecided", "none", "received")
    if status == "delivered":
        return StateProjection("delivered_not_received", "home", "undecided", "none", "delivered")
    if status == "no_tracking":
        return StateProjection("purchased_not_shipped", "supplier", "undecided", "none", "purchased")
    if status in {
        "shipped_no_tracking",
        "awaiting_carrier_scan",
        "in_transit",
        "available_for_pickup",
        "out_for_delivery",
    }:
        return StateProjection("shipped_not_delivered", "in_transit_to_me", "undecided", "none", "shipped")
    if status == "exception":
        return StateProjection(
            "shipped_not_delivered",
            "in_transit_to_me",
            "undecided",
            "none",
            "needs_review",
            needs_reconciliation=True,
            reconciliation_status="needs_review",
        )

    return StateProjection(
        "purchased_not_shipped",
        "unknown",
        "undecided",
        "none",
        "needs_review",
        needs_reconciliation=True,
        reconciliation_status="needs_review",
    )


def build_amazon_positions(
    snapshots: list[dict[str, Any]],
    amazon_skus: dict[tuple[str, str], dict[str, Any]],
    inventorylab_backfill: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []

    for snapshot in snapshots:
        seller_sku = clean_text(snapshot.get("seller_sku"))
        marketplace_id = clean_text(snapshot.get("marketplace_id"))
        if not seller_sku or not marketplace_id:
            continue

        sku = amazon_skus.get((seller_sku, marketplace_id), {})
        legacy_cost = inventorylab_backfill.get(seller_sku, {})
        legacy_unit_cost = to_float(legacy_cost.get("active_cost_per_unit"))
        legacy_purchase_date = clean_text(legacy_cost.get("active_date_purchased"))
        base = {
            "amazon_sku_id": sku.get("amazon_sku_id"),
            "source_system": "amazon_spapi",
            "source_table": "amazon_fba_inventory_snapshots",
            "external_reference_type": "seller_sku",
            "external_reference_id": seller_sku,
            "asin": clean_asin(snapshot.get("asin") or sku.get("asin")),
            "seller_sku": seller_sku,
            "fnsku": clean_text(snapshot.get("fnsku") or sku.get("fnsku")),
            "title": clean_text(snapshot.get("product_name") or sku.get("product_name")),
            "system": None,
            "unit_cost": legacy_unit_cost,
            "currency": "USD",
            "physical_location": "amazon_fba",
            "marketplace_intent": "amazon_fba",
            "listing_channel": "amazon",
            "derived_from": (
                "amazon_spapi_snapshot_inventorylab_backfill"
                if legacy_unit_cost is not None
                else "amazon_spapi_snapshot"
            ),
            "derivation_version": DERIVATION_VERSION,
            "effective_at": legacy_purchase_date or utc_now_iso(),
        }

        add_amazon_position(
            positions,
            base,
            "amazon_fba_sellable",
            "listed",
            "new",
            quantity=to_int(snapshot.get("fulfillable_quantity"), default=0),
        )
        add_amazon_position(
            positions,
            base,
            "amazon_fba_inbound_receiving",
            "listed",
            "new",
            quantity=sum(
                [
                    to_int(snapshot.get("inbound_working_quantity"), default=0),
                    to_int(snapshot.get("inbound_shipped_quantity"), default=0),
                    to_int(snapshot.get("inbound_receiving_quantity"), default=0),
                ]
            ),
            needs_reconciliation=True,
        )
        add_amazon_position(
            positions,
            base,
            "amazon_fba_reserved",
            "listed",
            "new",
            quantity=to_int(snapshot.get("reserved_quantity"), default=0),
            needs_reconciliation=True,
        )
        add_amazon_position(
            positions,
            base,
            "amazon_fba_unsellable_damaged",
            "needs_review",
            "unsellable",
            quantity=to_int(snapshot.get("unfulfillable_quantity"), default=0),
            needs_reconciliation=True,
            reconciliation_status="needs_review",
        )

    return positions


def current_amazon_asins(snapshots: list[dict[str, Any]]) -> set[str]:
    current: set[str] = set()
    quantity_fields = (
        "total_quantity",
        "fulfillable_quantity",
        "inbound_working_quantity",
        "inbound_shipped_quantity",
        "inbound_receiving_quantity",
        "reserved_quantity",
        "unfulfillable_quantity",
    )

    for snapshot in snapshots:
        asin = clean_asin(snapshot.get("asin"))
        if not asin:
            continue
        if any(to_int(snapshot.get(field), default=0) > 0 for field in quantity_fields):
            current.add(asin)

    return current


def add_amazon_position(
    positions: list[dict[str, Any]],
    base: dict[str, Any],
    inventory_state: str,
    operational_status: str,
    condition_disposition: str,
    quantity: int,
    needs_reconciliation: bool = False,
    reconciliation_status: str = "not_checked",
) -> None:
    if quantity <= 0:
        return

    positions.append(
        {
            **base,
            "quantity": quantity,
            "total_cost": (
                float(base["unit_cost"]) * quantity
                if base.get("unit_cost") is not None
                else None
            ),
            "inventory_state": inventory_state,
            "operational_status": operational_status,
            "condition_disposition": condition_disposition,
            "needs_reconciliation": needs_reconciliation,
            "reconciliation_status": reconciliation_status,
        }
    )


def reconcile_amazon_inventory(
    mbop_positions: list[dict[str, Any]],
    amazon_positions: list[dict[str, Any]],
    amazon_listing_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mbop_by_asin: dict[str, int] = defaultdict(int)
    amazon_by_asin: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sample_internal: dict[str, dict[str, Any]] = {}
    sample_external: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []

    for position in mbop_positions:
        if position.get("marketplace_intent") != "amazon_fba":
            continue
        if position.get("inventory_state") not in {
            "outbound_to_amazon",
            "received_assigned_amazon_not_sent",
        }:
            continue
        asin = clean_asin(position.get("asin"))
        if not asin:
            items.append(reconciliation_item("asin_mapping_missing", "warning", position, None))
            continue
        mbop_by_asin[asin] += to_int(position.get("quantity"), default=0)
        sample_internal.setdefault(asin, position)

    for position in amazon_positions:
        asin = clean_asin(position.get("asin"))
        if not asin:
            items.append(reconciliation_item("asin_mapping_missing", "warning", None, position))
            continue
        state = str(position.get("inventory_state"))
        quantity = to_int(position.get("quantity"), default=0)
        sample_external.setdefault(asin, position)
        amazon_by_asin[asin]["total"] += quantity
        if state == "amazon_fba_sellable":
            amazon_by_asin[asin]["sellable"] += quantity
        elif state == "amazon_fba_inbound_receiving":
            amazon_by_asin[asin]["inbound"] += quantity
        elif state == "amazon_fba_reserved":
            amazon_by_asin[asin]["reserved"] += quantity
        elif state == "amazon_fba_unsellable_damaged":
            amazon_by_asin[asin]["unsellable"] += quantity

    all_asins = set(mbop_by_asin) | set(amazon_by_asin)
    for asin in sorted(all_asins):
        mbop_quantity = mbop_by_asin.get(asin, 0)
        amazon = amazon_by_asin.get(asin, {})
        amazon_quantity = amazon.get("total", 0)
        internal = sample_internal.get(asin)
        external = sample_external.get(asin)

        if mbop_quantity and not amazon_quantity:
            items.append(
                reconciliation_item(
                    "mbop_missing_from_amazon",
                    "warning",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )
        elif amazon_quantity and not mbop_quantity:
            items.append(
                reconciliation_item(
                    "amazon_unknown_to_mbop",
                    "warning",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )
        elif mbop_quantity != amazon_quantity:
            items.append(
                reconciliation_item(
                    "quantity_mismatch",
                    "warning",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )

        if amazon.get("unsellable", 0) > 0:
            items.append(
                reconciliation_item(
                    "amazon_unsellable",
                    "critical",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )
        if amazon.get("reserved", 0) > 0:
            items.append(
                reconciliation_item(
                    "amazon_reserved",
                    "info",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )
        if amazon.get("inbound", 0) > 0 and mbop_quantity != amazon.get("inbound", 0):
            items.append(
                reconciliation_item(
                    "amazon_inbound_discrepancy",
                    "warning",
                    internal,
                    external,
                    mbop_quantity=mbop_quantity,
                    amazon=amazon,
                )
            )

    listing_issue_items = amazon_listing_issue_items(
        amazon_listing_snapshots or [],
        amazon_by_asin,
        sample_external,
    )
    items.extend(listing_issue_items)

    summary = {
        "reconciliation_type": "amazon_fba_inventory",
        "external_source": "amazon_spapi",
        "status": "completed",
        "started_at": utc_now_iso(),
        "completed_at": utc_now_iso(),
        "internal_positions_scanned": len(mbop_positions),
        "external_rows_scanned": len(amazon_positions)
        + len(amazon_listing_snapshots or []),
        "matched_count": sum(
            1
            for asin in all_asins
            if mbop_by_asin.get(asin, 0) > 0
            and mbop_by_asin.get(asin, 0) == amazon_by_asin.get(asin, {}).get("total", 0)
        ),
        "mismatch_count": sum(
            1
            for item in items
            if item["issue_type"]
            in {"quantity_mismatch", "amazon_inbound_discrepancy"}
        ),
        "missing_internal_count": sum(
            1 for item in items if item["issue_type"] == "amazon_unknown_to_mbop"
        ),
        "missing_external_count": sum(
            1 for item in items if item["issue_type"] == "mbop_missing_from_amazon"
        ),
        "needs_review_count": len(items),
        "notes": "ASIN-level first-pass reconciliation between MBOP Amazon-intended inventory and latest Amazon FBA inventory snapshots.",
        "raw_summary_json": {
            "mbop_asins": len(mbop_by_asin),
            "amazon_asins": len(amazon_by_asin),
            "amazon_listing_rows": len(amazon_listing_snapshots or []),
            "amazon_listing_issue_findings": len(listing_issue_items),
        },
    }
    return {"summary": summary, "items": items}


def amazon_listing_issue_items(
    listing_snapshots: list[dict[str, Any]],
    amazon_by_asin: dict[str, dict[str, int]],
    sample_external: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for listing in listing_snapshots:
        issue_count = to_int(listing.get("issue_count"), default=0)
        listing_status = clean_text(listing.get("listing_status"))
        if issue_count <= 0 and listing_status_is_buyable(listing_status):
            continue

        asin = clean_asin(listing.get("asin"))
        amazon = amazon_by_asin.get(asin or "", {})
        if amazon.get("sellable", 0) > 0:
            continue
        external = {
            "amazon_sku_id": listing.get("amazon_sku_id"),
            "source_system": "amazon_spapi",
            "source_table": "amazon_listing_snapshots",
            "external_reference_type": "seller_sku",
            "external_reference_id": clean_text(listing.get("seller_sku")),
            "asin": asin,
            "seller_sku": clean_text(listing.get("seller_sku")),
            "title": clean_text(listing.get("product_name")),
            "inventory_state": "amazon_fba_stranded",
            "physical_location": "amazon_fba",
            "marketplace_intent": "amazon_fba",
            "listing_channel": "amazon",
            "operational_status": "needs_review",
            "condition_disposition": "restricted" if issue_count > 0 else "unknown",
            "listing_status": listing_status,
            "issue_count": issue_count,
            "issue_severity": clean_text(listing.get("issue_severity")),
            "issues_json": listing.get("issues_json"),
        }
        sample = sample_external.get(asin or "")
        severity = "critical" if clean_text(listing.get("issue_severity")) == "ERROR" else "warning"

        items.append(
            reconciliation_item(
                "amazon_stranded_or_suppressed",
                severity,
                None,
                {**(sample or {}), **external},
                amazon=amazon,
            )
        )

    return items


def listing_status_is_buyable(listing_status: str | None) -> bool:
    if not listing_status:
        return False
    return "BUYABLE" in {part.strip().upper() for part in listing_status.split(",")}


def reconciliation_item(
    issue_type: str,
    severity: str,
    internal: dict[str, Any] | None,
    external: dict[str, Any] | None,
    mbop_quantity: int | None = None,
    amazon: dict[str, int] | None = None,
) -> dict[str, Any]:
    amazon = amazon or {}
    source = internal or external or {}
    return {
        "severity": severity,
        "issue_type": issue_type,
        "asin": clean_asin(source.get("asin")),
        "seller_sku": clean_text(source.get("seller_sku")),
        "fnsku": clean_text(source.get("fnsku")),
        "title": clean_text(source.get("title")),
        "system": clean_text(source.get("system")),
        "inventory_position_id": source.get("inventory_position_id"),
        "purchase_item_id": internal.get("purchase_item_id") if internal else None,
        "amazon_sku_id": external.get("amazon_sku_id") if external else None,
        "fba_shipment_id": internal.get("fba_shipment_id") if internal else None,
        "fba_shipment_item_id": internal.get("fba_shipment_item_id") if internal else None,
        "mbop_quantity": mbop_quantity,
        "amazon_total_quantity": amazon.get("total"),
        "amazon_fulfillable_quantity": amazon.get("sellable"),
        "amazon_inbound_quantity": amazon.get("inbound"),
        "amazon_reserved_quantity": amazon.get("reserved"),
        "amazon_unsellable_quantity": amazon.get("unsellable"),
        "expected_inventory_state": internal.get("inventory_state") if internal else None,
        "observed_inventory_state": external.get("inventory_state") if external else None,
        "expected_physical_location": internal.get("physical_location") if internal else None,
        "observed_physical_location": external.get("physical_location") if external else None,
        "expected_marketplace_intent": internal.get("marketplace_intent") if internal else None,
        "observed_marketplace_intent": external.get("marketplace_intent") if external else None,
        "expected_listing_channel": internal.get("listing_channel") if internal else None,
        "observed_listing_channel": external.get("listing_channel") if external else None,
        "expected_operational_status": internal.get("operational_status") if internal else None,
        "observed_operational_status": external.get("operational_status") if external else None,
        "expected_condition_disposition": internal.get("condition_disposition") if internal else None,
        "observed_condition_disposition": external.get("condition_disposition") if external else None,
        "raw_internal_json": internal,
        "raw_external_json": external,
    }


def replace_current_positions(supabase, positions: list[dict[str, Any]]) -> None:
    supabase.table("inventory_reconciliation_event_items").update(
        {"resolution_status": "deferred"}
    ).eq("resolution_status", "open").execute()
    supabase.table("inventory_positions").delete().eq(
        "derivation_version", DERIVATION_VERSION
    ).execute()

    for chunk in chunks(positions, BATCH_SIZE):
        supabase.table("inventory_positions").insert(chunk).execute()


def write_reconciliation_event(supabase, reconciliation: dict[str, Any]) -> None:
    summary = reconciliation["summary"]
    response = (
        supabase.table("inventory_reconciliation_events")
        .insert(summary)
        .execute()
    )
    event_id = response.data[0]["inventory_reconciliation_event_id"]
    items = [
        {"inventory_reconciliation_event_id": event_id, **item}
        for item in reconciliation["items"]
    ]

    for chunk in chunks(items, BATCH_SIZE):
        supabase.table("inventory_reconciliation_event_items").insert(chunk).execute()


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    return text.upper()


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


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def chunks(rows: list[Any], size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


if __name__ == "__main__":
    raise SystemExit(main())
