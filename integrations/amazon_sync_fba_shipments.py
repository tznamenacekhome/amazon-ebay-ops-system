"""Sync Amazon FBA inbound shipment status into MBOP shipment workflow tables.

Reads Amazon SP-API Fulfillment Inbound and latest FBA inventory snapshots.
Writes only FBA shipment workflow tables:
- fba_shipments
- fba_shipment_items
- fba_shipment_events

This integration does not write to purchases, purchase_items, receiving rows, or
Amazon inventory snapshot tables.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError

LOGGER = logging.getLogger("amazon_fba_shipment_sync")
BATCH_SIZE = 500


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
        client = AmazonSPAPIClient.from_env()
        if args.discover_limit:
            discover_recent_shipments(supabase, client, args)
        shipments = fetch_mbop_shipments(supabase, args)
        if not shipments:
            LOGGER.info("No MBOP FBA shipments selected for sync.")
            return 0

        sku_index = fetch_amazon_sku_index(supabase)
        latest_inventory = fetch_latest_inventory(supabase)
        shipment_items = fetch_shipment_items(supabase, shipments)

        LOGGER.info("Selected MBOP FBA shipments: %s", len(shipments))
        synced = 0
        for shipment in shipments:
            shipment_code = clean_text(shipment.get("shipment_code"))
            if not shipment_code:
                continue
            amazon_shipments = list(client.iter_inbound_shipments([shipment_code]))
            amazon_items = list(
                client.iter_inbound_shipment_items(
                    shipment_code,
                    max_pages=args.amazon_item_max_pages,
                )
            )
            amazon_shipment = amazon_shipments[0] if amazon_shipments else {}
            transport_details = fetch_transport_details(client, shipment_code)
            if not amazon_shipment and not amazon_items:
                LOGGER.warning("No Amazon shipment data returned for %s", shipment_code)

            planned = build_plan(
                shipment,
                amazon_shipment,
                transport_details,
                amazon_items,
                shipment_items.get(shipment["fba_shipment_id"], []),
                sku_index,
                latest_inventory,
            )
            if args.dry_run:
                print_plan(shipment_code, planned)
            else:
                apply_plan(supabase, shipment["fba_shipment_id"], planned)
            synced += 1

        LOGGER.info("Amazon FBA shipment sync complete. shipments=%s", synced)
        return 0
    except AmazonSPAPIError as error:
        LOGGER.error("Amazon SP-API shipment sync failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("Unexpected Amazon FBA shipment sync failure: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Amazon FBA inbound shipment status.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize without writing.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum shipments to sync.")
    parser.add_argument("--shipment-code", help="Sync one Amazon shipment ID.")
    parser.add_argument(
        "--include-closed",
        action="store_true",
        help="Include shipments already normalized as closed.",
    )
    parser.add_argument(
        "--discover-days-back",
        type=int,
        default=365,
        help="Look this far back when discovering recent Amazon shipments.",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=0,
        help="Backfill this many recent Amazon shipment headers before syncing.",
    )
    parser.add_argument(
        "--discover-max-pages",
        type=int,
        default=20,
        help="Maximum Amazon shipment discovery pages to scan.",
    )
    parser.add_argument(
        "--amazon-item-max-pages",
        type=int,
        default=20,
        help="Maximum Amazon item pages to scan per shipment.",
    )
    return parser.parse_args()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def fetch_mbop_shipments(supabase, args: argparse.Namespace) -> list[dict[str, Any]]:
    query = (
        supabase.table("fba_shipments")
        .select("*")
        .neq("shipment_code", "legacy_listed_no_shipment_id")
        .neq("workflow_status", "historical")
        .order("finalized_at", desc=True)
        .limit(args.limit)
    )
    if args.shipment_code:
        query = query.eq("shipment_code", args.shipment_code.strip())
    rows = query.execute().data or []
    if args.include_closed or args.shipment_code:
        return rows
    return [
        row
        for row in rows
        if normalize_status(row.get("amazon_status_normalized")) not in {"closed", "closed_with_shortage"}
    ]


def discover_recent_shipments(
    supabase,
    client: AmazonSPAPIClient,
    args: argparse.Namespace,
) -> None:
    started_after = (
        datetime.now(timezone.utc) - timedelta(days=max(args.discover_days_back, 1))
    ).replace(microsecond=0)
    discovered = list(
        client.iter_inbound_shipments_by_date_range(
            last_updated_after=started_after.isoformat().replace("+00:00", "Z"),
            max_pages=args.discover_max_pages,
        )
    )
    discovered.sort(
        key=lambda row: (
            clean_text(row.get("LastUpdatedDate"))
            or clean_text(row.get("ShipmentCreatedDate"))
            or ""
        ),
        reverse=True,
    )
    selected = discovered[: args.discover_limit]
    LOGGER.info(
        "Discovered Amazon FBA shipment headers: fetched=%s selected=%s",
        len(discovered),
        len(selected),
    )
    now = utc_now_iso()
    for shipment in selected:
        shipment_code = clean_text(shipment.get("ShipmentId"))
        if not shipment_code:
            continue
        status_raw = clean_text(shipment.get("ShipmentStatus"))
        status_normalized = normalize_amazon_status(status_raw, 0, 0)
        finalized_at = parse_timestamp(
            shipment.get("ShipmentCreatedDate") or shipment.get("LastUpdatedDate")
        )
        row = {
            "shipment_code": shipment_code,
            "workflow_status": status_normalized,
            "amazon_status_raw": status_raw,
            "amazon_status_normalized": status_normalized,
            "fulfillment_center_id": clean_text(
                shipment.get("DestinationFulfillmentCenterId")
                or shipment.get("FulfillmentCenterId")
            ),
            "destination_fulfillment_center_id": clean_text(
                shipment.get("DestinationFulfillmentCenterId")
            ),
            "raw_amazon_shipment_json": shipment,
            "last_amazon_sync_at": now,
            "updated_at": now,
        }
        if finalized_at:
            row["finalized_at"] = finalized_at
        supabase.table("fba_shipments").upsert(
            row,
            on_conflict="shipment_code",
        ).execute()


def fetch_transport_details(
    client: AmazonSPAPIClient,
    shipment_code: str,
) -> dict[str, Any]:
    try:
        payload = client.get_inbound_transport_details(shipment_code)
    except AmazonSPAPIError as error:
        LOGGER.warning(
            "Transport details unavailable for %s: %s",
            shipment_code,
            error,
        )
        return {}
    return payload.get("payload") or payload or {}


def fetch_shipment_items(
    supabase,
    shipments: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    shipment_ids = [row["fba_shipment_id"] for row in shipments if row.get("fba_shipment_id")]
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks(shipment_ids, 100):
        response = (
            supabase.table("fba_shipment_items")
            .select("*")
            .in_("fba_shipment_id", chunk)
            .eq("included", True)
            .execute()
        )
        for row in response.data or []:
            rows[row["fba_shipment_id"]].append(row)
    return rows


def fetch_amazon_sku_index(supabase) -> dict[str, dict[str, Any]]:
    rows = fetch_all(supabase, "amazon_skus", "seller_sku,asin,fnsku,product_name")
    return {
        clean_text(row.get("seller_sku")) or "": row
        for row in rows
        if clean_text(row.get("seller_sku"))
    }


def fetch_latest_inventory(supabase) -> dict[str, dict[str, int]]:
    rows = fetch_all(
        supabase,
        "vw_latest_amazon_fba_inventory_snapshot",
        "seller_sku,asin,fulfillable_quantity,reserved_quantity,unfulfillable_quantity,total_quantity",
    )
    inventory: dict[str, dict[str, int]] = {}
    for row in rows:
        seller_sku = clean_text(row.get("seller_sku"))
        if not seller_sku:
            continue
        inventory[seller_sku] = {
            "available": to_int(row.get("fulfillable_quantity")),
            "reserved": to_int(row.get("reserved_quantity")),
            "unfulfillable": to_int(row.get("unfulfillable_quantity")),
            "total": to_int(row.get("total_quantity")),
        }
    return inventory


def fetch_all(supabase, table: str, columns: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = (
            supabase.table(table)
            .select(columns)
            .range(offset, offset + BATCH_SIZE - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < BATCH_SIZE:
            return rows
        offset += BATCH_SIZE


def build_plan(
    shipment: dict[str, Any],
    amazon_shipment: dict[str, Any],
    transport_details: dict[str, Any],
    amazon_items: list[dict[str, Any]],
    mbop_items: list[dict[str, Any]],
    sku_index: dict[str, dict[str, Any]],
    latest_inventory: dict[str, dict[str, int]],
) -> dict[str, Any]:
    now = utc_now_iso()
    amazon_by_asin = summarize_amazon_items_by_asin(amazon_items, sku_index)
    mbop_by_asin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in mbop_items:
        asin = clean_asin(row.get("asin"))
        if asin:
            mbop_by_asin[asin].append(row)

    item_updates: list[dict[str, Any]] = []
    totals = {
        "sent": 0,
        "expected": 0,
        "received": 0,
        "available": 0,
        "reserved": 0,
        "unfulfillable": 0,
        "missing": 0,
        "cost_sent": 0.0,
        "outbound_remaining_cost": 0.0,
        "amazon_received_cost": 0.0,
        "amazon_available_cost": 0.0,
    }

    for asin, rows in mbop_by_asin.items():
        amazon_summary = amazon_by_asin.get(asin, {})
        seller_skus = amazon_summary.get("seller_skus") or []
        seller_sku = seller_skus[0] if seller_skus else None
        sku_inventory = aggregate_inventory(seller_skus, latest_inventory)
        asin_sent = sum(to_int(row.get("quantity")) for row in rows)
        expected_total = amazon_summary.get("expected", asin_sent)
        received_total = amazon_summary.get("received", 0)
        available_total = min(sku_inventory["available"], asin_sent)
        reserved_total = min(sku_inventory["reserved"], asin_sent)
        unfulfillable_total = min(sku_inventory["unfulfillable"], asin_sent)
        missing_total = max(asin_sent - max(received_total, available_total), 0)
        outbound_total = max(asin_sent - max(received_total, available_total), 0)

        distributed = distribute_quantities(
            rows,
            {
                "expected_quantity": expected_total,
                "received_quantity": received_total,
                "available_quantity": available_total,
                "reserved_quantity": reserved_total,
                "unfulfillable_quantity": unfulfillable_total,
                "missing_quantity": missing_total,
                "outbound_remaining_quantity": outbound_total,
            },
        )

        for row, quantities in distributed:
            quantity = to_int(row.get("quantity"))
            unit_cost = to_float(row.get("unit_cost")) or 0.0
            cost_sent = quantity * unit_cost
            outbound_cost = quantities["outbound_remaining_quantity"] * unit_cost
            received_cost = quantities["received_quantity"] * unit_cost
            available_cost = quantities["available_quantity"] * unit_cost
            totals["sent"] += quantity
            totals["expected"] += quantities["expected_quantity"]
            totals["received"] += quantities["received_quantity"]
            totals["available"] += quantities["available_quantity"]
            totals["reserved"] += quantities["reserved_quantity"]
            totals["unfulfillable"] += quantities["unfulfillable_quantity"]
            totals["missing"] += quantities["missing_quantity"]
            totals["cost_sent"] += cost_sent
            totals["outbound_remaining_cost"] += outbound_cost
            totals["amazon_received_cost"] += received_cost
            totals["amazon_available_cost"] += available_cost

            item_updates.append(
                {
                    "fba_shipment_item_id": row["fba_shipment_item_id"],
                    "seller_sku": seller_sku or row.get("seller_sku"),
                    "fnsku": amazon_summary.get("fnsku") or row.get("fnsku"),
                    **quantities,
                    "cost_sent": round(cost_sent, 2),
                    "outbound_remaining_cost": round(outbound_cost, 2),
                    "amazon_received_cost": round(received_cost, 2),
                    "amazon_available_cost": round(available_cost, 2),
                    "raw_amazon_item_json": amazon_summary.get("raw_items") or None,
                    "availability_last_checked_at": now,
                    "updated_at": now,
                }
            )

    if not mbop_by_asin:
        for amazon_summary in amazon_by_asin.values():
            seller_skus = amazon_summary.get("seller_skus") or []
            sku_inventory = aggregate_inventory(seller_skus, latest_inventory)
            sent = to_int(amazon_summary.get("expected"))
            received = to_int(amazon_summary.get("received"))
            totals["sent"] += sent
            totals["expected"] += sent
            totals["received"] += received
            totals["available"] += min(sku_inventory["available"], sent)
            totals["reserved"] += min(sku_inventory["reserved"], sent)
            totals["unfulfillable"] += min(sku_inventory["unfulfillable"], sent)
        totals["missing"] = max(totals["sent"] - totals["received"], 0)

    tracking_payload = merge_payloads(amazon_shipment, transport_details)
    status_raw = clean_text(amazon_shipment.get("ShipmentStatus")) or shipment.get("amazon_status_raw")
    status_normalized = normalize_amazon_status(status_raw, totals["sent"], totals["received"])
    all_available_at = (
        shipment.get("all_units_available_at")
        if totals["sent"] > 0 and totals["available"] >= totals["sent"]
        else None
    )
    if totals["sent"] > 0 and totals["available"] >= totals["sent"] and not all_available_at:
        all_available_at = now

    shipment_update = {
        "amazon_status_raw": status_raw,
        "amazon_status_normalized": status_normalized,
        "fulfillment_center_id": clean_text(
            amazon_shipment.get("DestinationFulfillmentCenterId")
            or amazon_shipment.get("FulfillmentCenterId")
        ),
        "destination_fulfillment_center_id": clean_text(
            amazon_shipment.get("DestinationFulfillmentCenterId")
        ),
        "carrier_name": extract_carrier(tracking_payload),
        "tracking_number": extract_tracking_number(tracking_payload),
        "carrier_tracking_url": extract_tracking_url(tracking_payload),
        "carrier_pickup_at": parse_event_timestamp(
            tracking_payload,
            ("PickupDate", "ShipmentPickupDate", "CarrierPickupDate", "DepartureDate"),
        ),
        "carrier_delivery_eta": parse_date(extract_delivery_eta(tracking_payload)),
        "carrier_delivered_at": parse_event_timestamp(
            tracking_payload,
            ("DeliveredDate", "DeliveryDate", "ActualDeliveryDate", "CarrierDeliveredDate"),
        ),
        "amazon_checked_in_at": milestone_from_status(status_raw, "CHECKED_IN", shipment),
        "amazon_receiving_started_at": milestone_from_status(status_raw, "RECEIVING", shipment),
        "amazon_closed_at": milestone_from_status(status_raw, "CLOSED", shipment),
        "all_units_available_at": all_available_at,
        "units_sent": totals["sent"],
        "units_expected": totals["expected"],
        "units_received": totals["received"],
        "units_available": totals["available"],
        "units_reserved": totals["reserved"],
        "units_unfulfillable": totals["unfulfillable"],
        "units_missing": totals["missing"],
        "fba_availability_pct": (
            round((totals["available"] / totals["sent"]) * 100, 1)
            if totals["sent"] > 0
            else None
        ),
        "cost_sent": round(totals["cost_sent"], 2),
        "outbound_remaining_cost": round(totals["outbound_remaining_cost"], 2),
        "amazon_received_cost": round(totals["amazon_received_cost"], 2),
        "amazon_available_cost": round(totals["amazon_available_cost"], 2),
        "attention_flags": attention_flags(status_normalized, totals),
        "raw_amazon_shipment_json": amazon_shipment or None,
        "raw_tracking_json": transport_details or extract_tracking_payload(amazon_shipment),
        "last_amazon_sync_at": now,
        "last_inventory_availability_sync_at": now,
        "updated_at": now,
    }
    if status_normalized and status_normalized not in {"created", "finalized"}:
        shipment_update["workflow_status"] = status_normalized

    events = build_events(shipment["fba_shipment_id"], shipment_update)
    return {
        "shipment_update": shipment_update,
        "item_updates": item_updates,
        "events": events,
    }


def summarize_amazon_items_by_asin(
    amazon_items: list[dict[str, Any]],
    sku_index: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for item in amazon_items:
        seller_sku = clean_text(item.get("SellerSKU") or item.get("SellerSku"))
        sku = sku_index.get(seller_sku or "", {})
        asin = clean_asin(item.get("ASIN") or sku.get("asin"))
        if not asin:
            continue
        summary = summaries.setdefault(
            asin,
            {
                "expected": 0,
                "received": 0,
                "seller_skus": [],
                "fnsku": None,
                "raw_items": [],
            },
        )
        expected = to_int(
            item.get("QuantityShipped")
            if item.get("QuantityShipped") is not None
            else item.get("Quantity")
        )
        received = to_int(item.get("QuantityReceived"))
        summary["expected"] += expected
        summary["received"] += received
        if seller_sku and seller_sku not in summary["seller_skus"]:
            summary["seller_skus"].append(seller_sku)
        summary["fnsku"] = summary["fnsku"] or clean_text(
            item.get("FulfillmentNetworkSKU")
            or item.get("FulfillmentNetworkSku")
            or sku.get("fnsku")
        )
        summary["raw_items"].append(item)
    return summaries


def aggregate_inventory(
    seller_skus: list[str],
    latest_inventory: dict[str, dict[str, int]],
) -> dict[str, int]:
    totals = {"available": 0, "reserved": 0, "unfulfillable": 0, "total": 0}
    for seller_sku in seller_skus:
        row = latest_inventory.get(seller_sku) or {}
        for key in totals:
            totals[key] += to_int(row.get(key))
    return totals


def distribute_quantities(
    rows: list[dict[str, Any]],
    totals: dict[str, int],
) -> list[tuple[dict[str, Any], dict[str, int]]]:
    remaining = dict(totals)
    distributed: list[tuple[dict[str, Any], dict[str, int]]] = []
    sorted_rows = sorted(rows, key=lambda row: clean_text(row.get("fba_shipment_item_id")) or "")
    for row in sorted_rows:
        quantity = to_int(row.get("quantity"))
        values: dict[str, int] = {}
        for key in totals:
            value = min(quantity, max(remaining.get(key, 0), 0))
            values[key] = value
            remaining[key] = max(remaining.get(key, 0) - value, 0)
        distributed.append((row, values))
    return distributed


def normalize_amazon_status(status: str | None, sent: int, received: int) -> str:
    normalized = normalize_status(status)
    mapping = {
        "working": "working",
        "ready_to_ship": "ready_to_ship",
        "shipped": "shipped",
        "in_transit": "in_transit",
        "delivered": "delivered_to_fc",
        "checked_in": "checked_in",
        "receiving": "receiving",
        "closed": "closed",
        "cancelled": "cancelled",
        "deleted": "cancelled",
        "error": "discrepancy",
    }
    value = mapping.get(normalized, normalized or "finalized")
    if value == "closed" and sent > received:
        return "closed_with_shortage"
    return value


def attention_flags(status: str, totals: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if totals["sent"] and totals["received"] < totals["sent"] and status in {"closed", "closed_with_shortage"}:
        flags.append("closed_short")
    if totals["unfulfillable"] > 0:
        flags.append("unfulfillable_units")
    if totals["sent"] and totals["available"] < totals["sent"] and status == "closed":
        flags.append("not_fully_available")
    return flags


def build_events(fba_shipment_id: str, shipment_update: dict[str, Any]) -> list[dict[str, Any]]:
    event_fields = {
        "carrier_pickup": shipment_update.get("carrier_pickup_at"),
        "carrier_delivered": shipment_update.get("carrier_delivered_at"),
        "amazon_checked_in": shipment_update.get("amazon_checked_in_at"),
        "amazon_receiving_started": shipment_update.get("amazon_receiving_started_at"),
        "amazon_closed": shipment_update.get("amazon_closed_at"),
        "all_units_available": shipment_update.get("all_units_available_at"),
    }
    rows = []
    for event_type, event_at in event_fields.items():
        if not event_at:
            continue
        rows.append(
            {
                "fba_shipment_id": fba_shipment_id,
                "event_type": event_type,
                "event_source": "amazon_fba_shipment_sync",
                "event_at": event_at,
                "fulfillment_center_id": shipment_update.get("fulfillment_center_id"),
                "raw_event_json": {"shipment_status": shipment_update.get("amazon_status_raw")},
            }
        )
    return rows


def apply_plan(supabase, fba_shipment_id: str, plan: dict[str, Any]) -> None:
    supabase.table("fba_shipments").update(plan["shipment_update"]).eq(
        "fba_shipment_id",
        fba_shipment_id,
    ).execute()

    for item in plan["item_updates"]:
        item_id = item.pop("fba_shipment_item_id")
        supabase.table("fba_shipment_items").update(item).eq(
            "fba_shipment_item_id",
            item_id,
        ).execute()

    for event in plan["events"]:
        supabase.table("fba_shipment_events").upsert(
            event,
            on_conflict="fba_shipment_id,event_type,event_source,event_at",
        ).execute()


def print_plan(shipment_code: str, plan: dict[str, Any]) -> None:
    update = plan["shipment_update"]
    print(
        f"{shipment_code}: status={update.get('amazon_status_normalized')} "
        f"sent={update.get('units_sent')} received={update.get('units_received')} "
        f"available={update.get('units_available')} "
        f"outbound=${update.get('outbound_remaining_cost')}"
    )


def extract_carrier(payload: dict[str, Any]) -> str | None:
    return find_first_key(payload, {"carriername", "carrier", "transportationcarrier"})


def extract_tracking_number(payload: dict[str, Any]) -> str | None:
    return find_first_key(payload, {"trackingid", "trackingnumber", "trackingnumberid"})


def extract_tracking_url(payload: dict[str, Any]) -> str | None:
    return find_first_key(payload, {"trackingurl", "carriertrackingurl"})


def extract_delivery_eta(payload: dict[str, Any]) -> str | None:
    return find_first_key(
        payload,
        {"estimateddeliverydate", "deliveryeta", "estimatedarrivaldate"},
    )


def extract_tracking_payload(payload: dict[str, Any]) -> Any:
    transport = payload.get("TransportDetails")
    return transport if transport else None


def merge_payloads(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for index, payload in enumerate(payloads):
        if payload:
            merged[f"payload_{index}"] = payload
    return merged


def find_first_key(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in keys:
                text = clean_text(item)
                if text:
                    return text
            found = find_first_key(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_first_key(item, keys)
            if found:
                return found
    return None


def parse_event_timestamp(
    payload: dict[str, Any],
    keys: tuple[str, ...],
) -> str | None:
    lowered = {key.lower() for key in keys}
    value = find_first_key(payload, lowered)
    return parse_timestamp(value)


def milestone_from_status(
    status_raw: str | None,
    milestone: str,
    existing_shipment: dict[str, Any],
) -> str | None:
    field_by_milestone = {
        "CHECKED_IN": "amazon_checked_in_at",
        "RECEIVING": "amazon_receiving_started_at",
        "CLOSED": "amazon_closed_at",
    }
    existing = existing_shipment.get(field_by_milestone[milestone])
    if existing:
        return existing
    status_order = [
        "WORKING",
        "READY_TO_SHIP",
        "SHIPPED",
        "IN_TRANSIT",
        "DELIVERED",
        "CHECKED_IN",
        "RECEIVING",
        "CLOSED",
    ]
    current = (status_raw or "").upper()
    if current in status_order and status_order.index(current) >= status_order.index(milestone):
        return utc_now_iso()
    return None


def parse_timestamp(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date(value: Any) -> str | None:
    timestamp = parse_timestamp(value)
    if timestamp:
        return timestamp[:10]
    text = clean_text(value)
    if text and len(text) >= 10:
        return text[:10]
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def clean_asin(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return text.upper()


def normalize_status(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def to_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
