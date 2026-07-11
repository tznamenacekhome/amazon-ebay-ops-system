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
SHIPMENT_UNIT_FIELDS = {
    "units_sent",
    "units_expected",
    "units_received",
    "units_available",
    "units_reserved",
    "units_unfulfillable",
    "units_missing",
    "cost_sent",
    "outbound_remaining_cost",
    "amazon_received_cost",
    "amazon_available_cost",
    "all_units_available_at",
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
        supabase = get_supabase_client()
        client = AmazonSPAPIClient.from_env()
        if args.discover_limit:
            discover_recent_shipments(supabase, client, args)
        shipments = fetch_mbop_shipments(supabase, args)
        if not shipments:
            LOGGER.info("No MBOP FBA shipments selected for sync.")
            return 0

        shipment_items = fetch_shipment_items(supabase, shipments)
        sku_index = fetch_amazon_sku_index(supabase)

        LOGGER.info("Selected MBOP FBA shipments: %s", len(shipments))
        synced = 0
        for shipment in shipments:
            shipment_code = clean_text(shipment.get("shipment_code"))
            if not shipment_code:
                continue
            mbop_rows = shipment_items.get(shipment["fba_shipment_id"], [])
            try:
                amazon_shipments = list(client.iter_inbound_shipments([shipment_code]))
            except AmazonSPAPIError as error:
                LOGGER.info("v0 shipment status unavailable for %s: %s", shipment_code, error)
                amazon_shipments = []
            if should_fetch_v0_shipment_items(shipment, mbop_rows):
                try:
                    amazon_items = list(
                        client.iter_inbound_shipment_items(
                            shipment_code,
                            max_pages=args.amazon_item_max_pages,
                        )
                    )
                except AmazonSPAPIError as error:
                    LOGGER.info("v0 shipment items unavailable for %s: %s", shipment_code, error)
                    amazon_items = []
            else:
                LOGGER.info(
                    "Skipping v0 shipment item refresh for v2024-only shipment %s",
                    shipment_code,
                )
                amazon_items = []
            amazon_shipment = amazon_shipments[0] if amazon_shipments else {}
            bridge_payload = fetch_v2024_identity_bridge(client, shipment, shipment_code, args)
            if not amazon_shipment and not amazon_items:
                LOGGER.warning("No Amazon shipment data returned for %s", shipment_code)

            latest_inventory = fetch_latest_inventory(
                supabase,
                seller_skus_for_amazon_items(amazon_items, sku_index),
            )
            planned = build_plan(
                shipment,
                amazon_shipment,
                bridge_payload,
                amazon_items,
                mbop_rows,
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
    parser.add_argument(
        "--v2024-bridge-max-pages",
        type=int,
        default=1,
        help="Maximum v2024 inbound-plan pages to scan for a shipment identity bridge.",
    )
    parser.add_argument(
        "--skip-v2024-bridge",
        action="store_true",
        help="Skip best-effort v2024 shipment identity and transport lookup.",
    )
    parser.add_argument(
        "--force-v2024-bridge",
        action="store_true",
        help="Ignore the cached v2024 bridge payload and rescan inbound plans.",
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
    v2024_rows = discover_recent_v2024_shipments(client, args.discover_limit)
    if v2024_rows:
        LOGGER.info(
            "Discovered Amazon FBA v2024 shipments: selected=%s",
            len(v2024_rows),
        )
        upsert_discovered_shipments(supabase, v2024_rows)
        return

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
    upsert_discovered_shipments(
        supabase,
        [normalize_v0_discovered_shipment(row) for row in selected],
    )


def discover_recent_v2024_shipments(
    client: AmazonSPAPIClient,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    payload = client.list_inbound_plans(page_size=min(max(limit, 1), 30), status="SHIPPED")
    plans = payload.get("inboundPlans") or []
    for plan in plans:
        inbound_plan_id = clean_text(plan.get("inboundPlanId"))
        if not inbound_plan_id:
            continue
        try:
            plan_detail = client.get_inbound_plan(inbound_plan_id)
        except AmazonSPAPIError as error:
            LOGGER.info(
                "Skipping unreadable v2024 inbound plan %s during discovery: %s",
                inbound_plan_id,
                error,
            )
            continue
        for shipment_summary in plan_detail.get("shipments") or []:
            shipment_id = clean_text(shipment_summary.get("shipmentId"))
            if not shipment_id:
                continue
            try:
                shipment_payload = client.get_inbound_plan_shipment(
                    inbound_plan_id,
                    shipment_id,
                )
            except AmazonSPAPIError as error:
                LOGGER.info(
                    "Skipping unreadable v2024 shipment %s/%s during discovery: %s",
                    inbound_plan_id,
                    shipment_id,
                    error,
                )
                continue
            boxes = fetch_v2024_boxes(client, inbound_plan_id, shipment_id)
            transportation_options = fetch_v2024_transportation_options(
                client,
                inbound_plan_id,
                shipment_id,
            )
            row = normalize_v2024_discovered_shipment(
                plan,
                shipment_payload,
                boxes,
                transportation_options,
            )
            if row:
                rows.append(row)
                if len(rows) >= limit:
                    return rows
    return rows


def fetch_v2024_boxes(
    client: AmazonSPAPIClient,
    inbound_plan_id: str,
    shipment_id: str,
) -> list[dict[str, Any]]:
    try:
        return list(
            client.iter_inbound_plan_shipment_boxes(
                inbound_plan_id,
                shipment_id,
                max_pages=5,
            )
        )
    except AmazonSPAPIError as error:
        LOGGER.info(
            "v2024 listShipmentBoxes unavailable for %s/%s: %s",
            inbound_plan_id,
            shipment_id,
            error,
        )
        return []


def fetch_v2024_transportation_options(
    client: AmazonSPAPIClient,
    inbound_plan_id: str,
    shipment_id: str,
) -> list[dict[str, Any]]:
    try:
        return list(
            client.iter_inbound_transportation_options(
                inbound_plan_id,
                shipment_id=shipment_id,
                max_pages=5,
            )
        )
    except AmazonSPAPIError as error:
        LOGGER.info(
            "v2024 listTransportationOptions unavailable for %s/%s: %s",
            inbound_plan_id,
            shipment_id,
            error,
        )
        return []


def normalize_v2024_discovered_shipment(
    plan: dict[str, Any],
    shipment_payload: dict[str, Any],
    boxes: list[dict[str, Any]],
    transportation_options: list[dict[str, Any]],
) -> dict[str, Any] | None:
    shipment_code = clean_text(shipment_payload.get("shipmentConfirmationId"))
    shipment_id = clean_text(shipment_payload.get("shipmentId"))
    inbound_plan_id = clean_text(plan.get("inboundPlanId"))
    if not shipment_code or not shipment_id or not inbound_plan_id:
        return None
    status_raw = clean_text(shipment_payload.get("status"))
    status_normalized = normalize_amazon_status(status_raw, 0, 0)
    tracking_details = collect_tracking_details(
        {
            "shipment": shipment_payload,
            "boxes": boxes,
            "transportationOptions": transportation_options,
        }
    )
    bridge_payload = {
        "source": "fulfillment_inbound_v2024_03_20",
        "shipmentConfirmationId": shipment_code,
        "checkedAt": utc_now_iso(),
        "match": {
            "inboundPlanId": inbound_plan_id,
            "shipmentId": shipment_id,
            "shipmentConfirmationId": shipment_code,
            "matchedField": "shipmentConfirmationId",
        },
        "inboundPlanId": inbound_plan_id,
        "v2024ShipmentId": shipment_id,
        "transportationOptionIds": unique_texts(
            find_all_keys(shipment_payload, {"transportationoptionid"})
            + find_all_keys(transportation_options, {"transportationoptionid"})
        ),
        "trackingDetails": tracking_details,
        "raw": {
            "plan": plan,
            "shipment": shipment_payload,
            "boxes": boxes,
            "transportationOptions": transportation_options,
        },
        "errors": [],
    }
    tracking = first_tracking_detail(tracking_details)
    destination = shipment_payload.get("destination") or {}
    destination_address = destination.get("address") or {}
    delivery_window = shipment_payload.get("selectedDeliveryWindow") or {}
    units = sum_box_units(boxes)
    return {
        "shipment_code": shipment_code,
        "workflow_status": status_normalized,
        "amazon_status_raw": status_raw,
        "amazon_status_normalized": status_normalized,
        "fulfillment_center_id": clean_text(
            destination.get("warehouseId")
            or destination_address.get("name")
        ),
        "destination_fulfillment_center_id": clean_text(
            destination.get("warehouseId")
            or destination_address.get("name")
        ),
        "tracking_number": tracking.get("tracking_number") if tracking else None,
        "carrier_name": infer_carrier(tracking.get("tracking_number") if tracking else None)
        or (tracking.get("carrier_name") if tracking else None),
        "carrier_tracking_url": tracking.get("tracking_url") if tracking else None,
        "carrier_pickup_at": tracking.get("pickup_at") if tracking else None,
        "carrier_delivery_eta": (
            parse_date(delivery_window.get("endDate"))
            or (tracking.get("delivery_eta") if tracking else None)
        ),
        "carrier_delivered_at": tracking.get("delivered_at") if tracking else None,
        "units_sent": units or None,
        "units_expected": units or None,
        "raw_amazon_shipment_json": shipment_payload,
        "raw_tracking_json": bridge_payload,
        "finalized_at": parse_timestamp(plan.get("createdAt")),
        "last_amazon_sync_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }


def normalize_v0_discovered_shipment(shipment: dict[str, Any]) -> dict[str, Any]:
    shipment_code = clean_text(shipment.get("ShipmentId"))
    status_raw = clean_text(shipment.get("ShipmentStatus"))
    status_normalized = normalize_amazon_status(status_raw, 0, 0)
    return {
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
        "finalized_at": parse_timestamp(
            shipment.get("ShipmentCreatedDate") or shipment.get("LastUpdatedDate")
        ),
        "last_amazon_sync_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }


def upsert_discovered_shipments(
    supabase,
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        shipment_code = clean_text(row.get("shipment_code"))
        if not shipment_code:
            continue
        payload = {key: value for key, value in row.items() if value is not None}
        existing = (
            supabase.table("fba_shipments")
            .select("fba_shipment_id")
            .eq("shipment_code", shipment_code)
            .limit(1)
            .execute()
            .data
            or []
        )
        existing_row = existing[0] if existing else None
        if existing_row and shipment_has_mbop_items(supabase, existing_row["fba_shipment_id"]):
            for field in SHIPMENT_UNIT_FIELDS:
                payload.pop(field, None)
            supabase.table("fba_shipments").update(payload).eq(
                "shipment_code",
                shipment_code,
            ).execute()
            continue
        supabase.table("fba_shipments").upsert(payload, on_conflict="shipment_code").execute()


def shipment_has_mbop_items(supabase, fba_shipment_id: str) -> bool:
    response = (
        supabase.table("fba_shipment_items")
        .select("fba_shipment_item_id")
        .eq("fba_shipment_id", fba_shipment_id)
        .limit(1)
        .execute()
    )
    return bool(response.data)


def fetch_v2024_identity_bridge(
    client: AmazonSPAPIClient,
    shipment: dict[str, Any],
    shipment_confirmation_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if args.skip_v2024_bridge:
        return {}
    cached = shipment.get("raw_tracking_json")
    if not args.force_v2024_bridge and fresh_cached_v2024_bridge(cached):
        LOGGER.info("Using cached v2024 identity bridge for %s", shipment_confirmation_id)
        return cached

    bridge: dict[str, Any] = {
        "source": "fulfillment_inbound_v2024_03_20",
        "shipmentConfirmationId": shipment_confirmation_id,
        "checkedAt": utc_now_iso(),
        "match": None,
        "inboundPlanId": None,
        "v2024ShipmentId": None,
        "transportationOptionIds": [],
        "trackingDetails": [],
        "raw": {},
        "errors": [],
    }
    try:
        candidates = find_v2024_shipment_candidates(
            client,
            shipment_confirmation_id,
            max_pages=args.v2024_bridge_max_pages,
        )
    except AmazonSPAPIError as error:
        bridge["errors"].append(f"listInboundPlans/getInboundPlan failed: {error}")
        LOGGER.info(
            "v2024 identity bridge unavailable for %s: %s",
            shipment_confirmation_id,
            error,
        )
        return bridge

    if not candidates:
        LOGGER.info(
            "No v2024 inbound shipment identity found for %s",
            shipment_confirmation_id,
        )
        return bridge

    candidate = candidates[0]
    inbound_plan_id = clean_text(candidate.get("inboundPlanId"))
    shipment_id = clean_text(candidate.get("shipmentId"))
    bridge["match"] = candidate
    bridge["inboundPlanId"] = inbound_plan_id
    bridge["v2024ShipmentId"] = shipment_id

    if not inbound_plan_id or not shipment_id:
        return bridge

    try:
        shipment_payload = client.get_inbound_plan_shipment(inbound_plan_id, shipment_id)
        bridge["raw"]["shipment"] = shipment_payload
        bridge["transportationOptionIds"] = unique_texts(
            bridge["transportationOptionIds"]
            + find_all_keys(shipment_payload, {"transportationoptionid"})
        )
        bridge["trackingDetails"] = collect_tracking_details(shipment_payload)
    except AmazonSPAPIError as error:
        bridge["errors"].append(f"getShipment failed: {error}")
        LOGGER.info("v2024 getShipment failed for %s: %s", shipment_confirmation_id, error)

    try:
        boxes = list(
            client.iter_inbound_plan_shipment_boxes(
                inbound_plan_id,
                shipment_id,
                max_pages=5,
            )
        )
        bridge["raw"]["boxes"] = boxes
        bridge["trackingDetails"] = collect_tracking_details(
            {"existing": bridge["trackingDetails"], "boxes": boxes}
        )
    except AmazonSPAPIError as error:
        bridge["errors"].append(f"listShipmentBoxes failed: {error}")
        LOGGER.info(
            "v2024 listShipmentBoxes failed for %s: %s",
            shipment_confirmation_id,
            error,
        )

    try:
        transportation_options = list(
            client.iter_inbound_transportation_options(
                inbound_plan_id,
                shipment_id=shipment_id,
                max_pages=5,
            )
        )
        bridge["raw"]["transportationOptions"] = transportation_options
        bridge["transportationOptionIds"] = unique_texts(
            bridge["transportationOptionIds"]
            + find_all_keys(transportation_options, {"transportationoptionid"})
        )
        bridge["trackingDetails"] = collect_tracking_details(
            {
                "existing": bridge["trackingDetails"],
                "transportationOptions": transportation_options,
            }
        )
    except AmazonSPAPIError as error:
        bridge["errors"].append(f"listTransportationOptions failed: {error}")
        LOGGER.info(
            "v2024 listTransportationOptions failed for %s: %s",
            shipment_confirmation_id,
            error,
        )

    bridge["trackingDetails"] = dedupe_tracking_details(bridge["trackingDetails"])
    LOGGER.info(
        "v2024 identity bridge for %s: inboundPlanId=%s shipmentId=%s tracking=%s",
        shipment_confirmation_id,
        inbound_plan_id,
        shipment_id,
        len(bridge["trackingDetails"]),
    )
    return bridge


def fresh_cached_v2024_bridge(value: Any, *, max_age_hours: int = 12) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("source") != "fulfillment_inbound_v2024_03_20":
        return False
    checked_at = parse_timestamp(value.get("checkedAt"))
    if not checked_at:
        return False
    parsed = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - parsed
    return age.total_seconds() <= max_age_hours * 3600


def find_v2024_shipment_candidates(
    client: AmazonSPAPIClient,
    shipment_confirmation_id: str,
    *,
    max_pages: int,
) -> list[dict[str, Any]]:
    statuses = [None, "ACTIVE", "SHIPPED", "VOIDED"]
    candidates: list[dict[str, Any]] = []
    seen_plan_ids: set[str] = set()
    for status in statuses:
        pagination_token: str | None = None
        pages_seen = 0
        while True:
            payload = client.list_inbound_plans(
                page_size=30,
                pagination_token=pagination_token,
                status=status,
            )
            pages_seen += 1
            for plan_summary in payload.get("inboundPlans") or []:
                inbound_plan_id = clean_text(plan_summary.get("inboundPlanId"))
                if not inbound_plan_id or inbound_plan_id in seen_plan_ids:
                    continue
                seen_plan_ids.add(inbound_plan_id)
                try:
                    plan_detail = client.get_inbound_plan(inbound_plan_id)
                except AmazonSPAPIError as error:
                    LOGGER.info(
                        "Skipping unreadable v2024 inbound plan %s while bridging %s: %s",
                        inbound_plan_id,
                        shipment_confirmation_id,
                        error,
                    )
                    continue
                matches = find_matching_v2024_shipments(
                    plan_detail,
                    shipment_confirmation_id,
                )
                for match in matches:
                    candidates.append(
                        {
                            "inboundPlanId": inbound_plan_id,
                            "shipmentId": match.get("shipmentId"),
                            "shipmentConfirmationId": match.get("shipmentConfirmationId"),
                            "plan": plan_summary,
                            "rawShipment": match.get("rawShipment"),
                            "matchedField": match.get("matchedField"),
                        }
                    )
            pagination_token = (payload.get("pagination") or {}).get("nextToken")
            if not pagination_token or pages_seen >= max_pages:
                break
    return candidates


def find_matching_v2024_shipments(
    payload: Any,
    shipment_confirmation_id: str,
) -> list[dict[str, Any]]:
    needle = shipment_confirmation_id.strip().upper()
    matches: list[dict[str, Any]] = []
    for shipment in find_shipment_like_dicts(payload):
        field_values = {
            "shipmentConfirmationId": clean_text(shipment.get("shipmentConfirmationId")),
            "shipmentId": clean_text(shipment.get("shipmentId")),
            "amazonReferenceId": clean_text(shipment.get("amazonReferenceId")),
        }
        for field, value in field_values.items():
            if value and value.upper() == needle:
                matches.append(
                    {
                        "shipmentId": clean_text(shipment.get("shipmentId")),
                        "shipmentConfirmationId": clean_text(
                            shipment.get("shipmentConfirmationId")
                        ),
                        "matchedField": field,
                        "rawShipment": shipment,
                    }
                )
                break
    return matches


def find_shipment_like_dicts(value: Any) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = {key.lower() for key in value}
        if "shipmentid" in keys or "shipmentconfirmationid" in keys:
            matches.append(value)
        for item in value.values():
            matches.extend(find_shipment_like_dicts(item))
    elif isinstance(value, list):
        for item in value:
            matches.extend(find_shipment_like_dicts(item))
    return matches


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


def has_v2024_bridge_payload(shipment: dict[str, Any]) -> bool:
    raw_payload = shipment.get("raw_tracking_json")
    return (
        isinstance(raw_payload, dict)
        and raw_payload.get("source") == "fulfillment_inbound_v2024_03_20"
    )


def should_fetch_v0_shipment_items(
    shipment: dict[str, Any],
    mbop_items: list[dict[str, Any]],
) -> bool:
    if mbop_items:
        return True
    return not has_v2024_bridge_payload(shipment)


def fetch_amazon_sku_index(supabase) -> dict[str, dict[str, Any]]:
    rows = fetch_all(supabase, "amazon_skus", "seller_sku,asin,fnsku,product_name")
    return {
        clean_text(row.get("seller_sku")) or "": row
        for row in rows
        if clean_text(row.get("seller_sku"))
    }


def seller_skus_for_amazon_items(
    amazon_items: list[dict[str, Any]],
    sku_index: dict[str, dict[str, Any]],
) -> list[str]:
    seller_skus: list[str] = []
    seen: set[str] = set()
    for item in amazon_items:
        seller_sku = clean_text(item.get("SellerSKU") or item.get("SellerSku"))
        if seller_sku:
            value = seller_sku
        else:
            asin = clean_asin(item.get("ASIN"))
            value = next(
                (
                    sku
                    for sku, row in sku_index.items()
                    if clean_asin(row.get("asin")) == asin
                ),
                None,
            )
        if value and value not in seen:
            seen.add(value)
            seller_skus.append(value)
    return seller_skus


def fetch_latest_inventory(
    supabase,
    seller_skus: list[str],
) -> dict[str, dict[str, int]]:
    inventory: dict[str, dict[str, int]] = {}
    if not seller_skus:
        return inventory

    columns = (
        "seller_sku,asin,fulfillable_quantity,reserved_quantity,"
        "unfulfillable_quantity,total_quantity"
    )
    rows: list[dict[str, Any]] = []
    for chunk in chunks(seller_skus, 100):
        response = (
            supabase.table("vw_latest_amazon_fba_inventory_snapshot")
            .select(columns)
            .in_("seller_sku", chunk)
            .execute()
        )
        rows.extend(response.data or [])

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
    is_v2024_only = has_v2024_bridge_payload(shipment) and not mbop_items
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

    if not mbop_by_asin and not is_v2024_only:
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

    if totals["sent"] == 0:
        totals["sent"] = to_int(shipment.get("units_sent"))
        totals["expected"] = to_int(shipment.get("units_expected")) or totals["sent"]
        totals["received"] = to_int(shipment.get("units_received"))
        totals["available"] = to_int(shipment.get("units_available"))
        totals["reserved"] = to_int(shipment.get("units_reserved"))
        totals["unfulfillable"] = to_int(shipment.get("units_unfulfillable"))
        totals["missing"] = to_int(shipment.get("units_missing"))

    tracking_payload = merge_payloads(amazon_shipment, transport_details)
    tracking_number = extract_tracking_number(tracking_payload) or shipment.get("tracking_number")
    carrier_name = shipment.get("carrier_name") or extract_carrier(tracking_payload)
    carrier_tracking_url = shipment.get("carrier_tracking_url") or extract_tracking_url(
        tracking_payload
    )
    carrier_pickup_at = shipment.get("carrier_pickup_at") or parse_event_timestamp(
        tracking_payload,
        ("PickupDate", "ShipmentPickupDate", "CarrierPickupDate", "DepartureDate"),
    )
    carrier_delivery_eta = shipment.get("carrier_delivery_eta") or parse_date(
        extract_delivery_eta(tracking_payload)
    )
    carrier_delivered_at = shipment.get("carrier_delivered_at") or parse_event_timestamp(
        tracking_payload,
        ("DeliveredDate", "DeliveryDate", "ActualDeliveryDate", "CarrierDeliveredDate"),
    )
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
        )
        or shipment.get("fulfillment_center_id"),
        "destination_fulfillment_center_id": clean_text(
            amazon_shipment.get("DestinationFulfillmentCenterId")
        )
        or shipment.get("destination_fulfillment_center_id"),
        "carrier_name": carrier_name,
        "tracking_number": tracking_number,
        "carrier_tracking_url": carrier_tracking_url,
        "carrier_pickup_at": carrier_pickup_at,
        "carrier_delivery_eta": carrier_delivery_eta,
        "carrier_delivered_at": carrier_delivered_at,
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
        "raw_amazon_shipment_json": amazon_shipment or shipment.get("raw_amazon_shipment_json"),
        "raw_tracking_json": merge_tracking_context(
            shipment.get("raw_tracking_json"),
            transport_details or extract_tracking_payload(amazon_shipment),
        ),
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
    return find_first_key(
        payload,
        {
            "trackingid",
            "trackingnumber",
            "trackingnumberid",
            "protrackingnumber",
        },
    )


def extract_tracking_url(payload: dict[str, Any]) -> str | None:
    return find_first_key(payload, {"trackingurl", "carriertrackingurl"})


def extract_delivery_eta(payload: dict[str, Any]) -> str | None:
    return find_first_key(
        payload,
        {
            "estimateddeliverydate",
            "deliveryeta",
            "estimatedarrivaldate",
            "estimateddeliverytime",
            "estimatedarrivaltime",
        },
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


def merge_tracking_context(
    existing: Any,
    amazon_context: Any,
) -> dict[str, Any] | None:
    if isinstance(existing, dict):
        merged = dict(existing)
    else:
        merged = {}

    if amazon_context:
        if isinstance(amazon_context, dict) and amazon_context.get("source"):
            for key, value in amazon_context.items():
                if key == "easypost" and "easypost" in merged:
                    continue
                merged[key] = value
        else:
            merged["amazon_tracking_context"] = amazon_context

    return merged or None


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


def find_all_keys(value: Any, keys: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in keys:
                text = clean_text(item)
                if text:
                    found.append(text)
            found.extend(find_all_keys(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_all_keys(item, keys))
    return unique_texts(found)


def collect_tracking_details(payload: Any) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for node in find_tracking_like_dicts(payload):
        tracking_number = extract_tracking_number(node)
        carrier_name = extract_carrier(node)
        tracking_url = extract_tracking_url(node)
        eta = parse_date(extract_delivery_eta(node))
        pickup_at = parse_event_timestamp(
            node,
            ("PickupDate", "ShipmentPickupDate", "CarrierPickupDate", "DepartureDate"),
        )
        delivered_at = parse_event_timestamp(
            node,
            ("DeliveredDate", "DeliveryDate", "ActualDeliveryDate", "CarrierDeliveredDate"),
        )
        if not any([tracking_number, carrier_name, tracking_url, eta, pickup_at, delivered_at]):
            continue
        details.append(
            {
                "tracking_number": tracking_number,
                "carrier_name": carrier_name,
                "tracking_url": tracking_url,
                "delivery_eta": eta,
                "pickup_at": pickup_at,
                "delivered_at": delivered_at,
                "raw": node,
            }
        )
    return dedupe_tracking_details(details)


def find_tracking_like_dicts(value: Any) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(value, dict):
        keys = {key.lower() for key in value}
        if keys.intersection(
            {
                "trackingid",
                "trackingnumber",
                "trackingnumberid",
                "protrackingnumber",
                "carriername",
                "transportationcarrier",
                "estimateddeliverydate",
                "actualdeliverydate",
            }
        ):
            matches.append(value)
        for item in value.values():
            matches.extend(find_tracking_like_dicts(item))
    elif isinstance(value, list):
        for item in value:
            matches.extend(find_tracking_like_dicts(item))
    return matches


def dedupe_tracking_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for detail in details:
        key = (
            clean_text(detail.get("tracking_number")) or "",
            clean_text(detail.get("carrier_name")) or "",
            clean_text(detail.get("tracking_url")) or "",
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(detail)
    return deduped


def first_tracking_detail(details: list[dict[str, Any]]) -> dict[str, Any] | None:
    return details[0] if details else None


def sum_box_units(boxes: list[dict[str, Any]]) -> int:
    total = 0
    for box in boxes:
        for item in box.get("items") or []:
            total += to_int(item.get("quantity"))
    return total


def infer_carrier(tracking_number: Any) -> str | None:
    text = clean_text(tracking_number)
    if not text:
        return None
    if text.upper().startswith("1Z"):
        return "UPS"
    return None


def unique_texts(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


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
