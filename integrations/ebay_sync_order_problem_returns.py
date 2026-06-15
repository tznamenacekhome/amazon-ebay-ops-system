"""Read-only eBay Post-Order returns sync for MBOP Order Problems.

This script reads eBay return data and writes only to MBOP local workflow tables:
order_problem_cases and order_problem_events. It does not create returns, send
messages, accept offers, escalate cases, issue refunds, upload files, or call any
other eBay write endpoint.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import logging
import os
import xml.etree.ElementTree as ET
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import create_client


LOGGER = logging.getLogger("ebay_order_problem_returns_sync")
EBAY_POST_ORDER_BASE_URL = "https://api.ebay.com/post-order/v2"
EBAY_TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
EBAY_TRADING_COMPATIBILITY_LEVEL = "1423"
EBAY_SITE_ID = "0"


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
        token = get_access_token()
        purchase_line_index = build_purchase_line_index(supabase, args.lookback_days)
        tracking_status_index = build_tracking_status_index(supabase)
        returns = enrich_returns(token, search_returns(token, lookback_days=args.lookback_days, limit=args.limit))
        inquiries = enrich_inquiries(token, search_inquiries(token, lookback_days=args.lookback_days, limit=args.limit))
        cases = search_cases(token, lookback_days=args.lookback_days, limit=args.limit)
        trading_refunds = search_trading_buyer_order_refunds(token, lookback_days=args.lookback_days)
        LOGGER.info("eBay returns retrieved: %s", len(returns))
        LOGGER.info("eBay inquiries retrieved: %s", len(inquiries))
        LOGGER.info("eBay cases retrieved: %s", len(cases))
        LOGGER.info("eBay buyer order refunds retrieved: %s", len(trading_refunds))

        inserted = 0
        updated = 0
        skipped = 0
        mapped_rows = [
            *[map_return(return_row, supabase) for return_row in returns],
            *[
                map_inquiry(inquiry_row, purchase_line_index, trading_refunds, tracking_status_index)
                for inquiry_row in inquiries
            ],
            *[map_case(case_row, purchase_line_index, trading_refunds) for case_row in cases],
        ]
        for mapped in mapped_rows:
            if not mapped:
                skipped += 1
                continue

            if not args.apply:
                print_summary(mapped, dry_run=True)
                skipped += 1
                continue

            result = upsert_order_problem_case(supabase, mapped)
            if result == "inserted":
                inserted += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

        print("eBay order problem returns sync")
        print("--------------------------------")
        print("Mode:", "write" if args.apply else "dry run")
        print(f"Returns retrieved: {len(returns)}")
        print(f"Inquiries retrieved: {len(inquiries)}")
        print(f"Cases retrieved: {len(cases)}")
        print(f"Inserted: {inserted}")
        print(f"Updated: {updated}")
        print(f"Skipped: {skipped}")
        return 0
    except Exception as error:  # noqa: BLE001 - integration should fail safely
        LOGGER.exception("eBay order problem returns sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only eBay returns sync into MBOP Order Problems.")
    parser.add_argument("--apply", action="store_true", help="Write mapped return cases to Supabase.")
    parser.add_argument("--lookback-days", type=int, default=90, help="Return creation lookback window.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum returns to request from eBay.")
    return parser.parse_args()


def get_supabase_client():
    return create_client(required_env("SUPABASE_URL"), required_env("SUPABASE_SERVICE_ROLE_KEY"))


def get_access_token() -> str:
    credentials = f"{required_env('EBAY_CLIENT_ID')}:{required_env('EBAY_CLIENT_SECRET')}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": required_env("EBAY_REFRESH_TOKEN"),
            "scope": " ".join(
                [
                    "https://api.ebay.com/oauth/api_scope",
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
                    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
                    "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
                ]
            ),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_returns(token: str, *, lookback_days: int, limit: int) -> list[dict[str, Any]]:
    return search_post_order(
        token,
        "return/search",
        lookback_days=lookback_days,
        limit=limit,
        extra_params={"role": "BUYER"},
    )


def search_inquiries(token: str, *, lookback_days: int, limit: int) -> list[dict[str, Any]]:
    return search_post_order(
        token,
        "inquiry/search",
        lookback_days=lookback_days,
        limit=limit,
    )


def search_cases(token: str, *, lookback_days: int, limit: int) -> list[dict[str, Any]]:
    return search_post_order(
        token,
        "casemanagement/search",
        lookback_days=lookback_days,
        limit=limit,
    )


def enrich_returns(token: str, returns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for return_row in returns:
        return_id = clean_text(return_row.get("returnId"))
        if not return_id:
            enriched.append(return_row)
            continue

        detail = get_post_order(token, f"return/{return_id}")
        if detail:
            enriched.append({**return_row, **detail, "_searchSummary": return_row})
        else:
            enriched.append(return_row)
    return enriched


def enrich_inquiries(token: str, inquiries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for inquiry in inquiries:
        inquiry_id = clean_text(inquiry.get("inquiryId"))
        if not inquiry_id:
            enriched.append(inquiry)
            continue

        detail = get_post_order(token, f"inquiry/{inquiry_id}")
        if detail:
            enriched.append({**inquiry, **detail, "_searchSummary": inquiry})
        else:
            enriched.append(inquiry)
    return enriched


def get_post_order(token: str, path: str) -> dict[str, Any] | None:
    response = requests.get(
        f"{EBAY_POST_ORDER_BASE_URL}/{path}",
        headers={
            "Authorization": f"IAF {token}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    if response.status_code == 404:
        LOGGER.warning("eBay Post-Order GET %s returned 404", path)
        return None
    response.raise_for_status()
    return response.json()


def search_post_order(
    token: str,
    path: str,
    *,
    lookback_days: int,
    limit: int,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    end_date = dt.datetime.now(dt.timezone.utc)
    start_date = end_date - dt.timedelta(days=lookback_days)
    response = requests.get(
        f"{EBAY_POST_ORDER_BASE_URL}/{path}",
        headers={
            "Authorization": f"IAF {token}",
            "Content-Type": "application/json",
        },
        params={
            "limit": str(max(1, min(limit, 200))),
            "creation_date_range_from": iso_z(start_date),
            "creation_date_range_to": iso_z(end_date),
            **(extra_params or {}),
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    members = payload.get("members") or []
    return [row for row in members if isinstance(row, dict)]


def search_trading_buyer_order_refunds(
    token: str,
    *,
    lookback_days: int,
) -> dict[str, dict[str, Any]]:
    end_date = dt.datetime.now(dt.timezone.utc)
    start_date = end_date - dt.timedelta(days=lookback_days)
    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": "GetOrders",
        "X-EBAY-API-COMPATIBILITY-LEVEL": EBAY_TRADING_COMPATIBILITY_LEVEL,
        "X-EBAY-API-SITEID": EBAY_SITE_ID,
        "X-EBAY-API-IAF-TOKEN": token,
    }
    refunds: dict[str, dict[str, Any]] = {}
    page_number = 1
    total_pages = 1

    while page_number <= total_pages:
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <CreateTimeFrom>{iso_z(start_date)}</CreateTimeFrom>
  <CreateTimeTo>{iso_z(end_date)}</CreateTimeTo>
  <OrderRole>Buyer</OrderRole>
  <OrderStatus>All</OrderStatus>
  <DetailLevel>ReturnAll</DetailLevel>
  <Pagination>
    <EntriesPerPage>100</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetOrdersRequest>"""
        response = requests.post(
            EBAY_TRADING_ENDPOINT,
            headers=headers,
            data=xml_body,
            timeout=120,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
        ack = first_xml_text(root, "Ack")
        if ack not in {"Success", "Warning"}:
            for message in all_xml_text(root, "LongMessage"):
                LOGGER.warning("eBay Trading GetOrders error: %s", message)
            break

        total_pages_text = first_xml_text(root, "TotalNumberOfPages")
        try:
            total_pages = int(total_pages_text or "1")
        except ValueError:
            total_pages = 1

        for order in xml_children(root, "Order"):
            refund = trading_refund_from_order(order)
            if refund:
                refunds[refund["supplier_order_id"]] = refund

        page_number += 1

    return refunds


def trading_refund_from_order(order: ET.Element) -> dict[str, Any] | None:
    order_id = clean_text(first_xml_text(order, "OrderID"))
    if not order_id:
        return None

    refund_amount = 0.0
    refund_currency = None
    refund_times: list[str] = []
    refund_statuses: list[str] = []
    for refund in xml_children(order, "Refund"):
        amount_elem = first_xml_child(refund, "RefundAmount")
        amount = money_value(amount_elem.text if amount_elem is not None else None)
        if amount is not None:
            refund_amount += abs(amount)
            refund_currency = refund_currency or clean_text(amount_elem.attrib.get("currencyID"))
        refund_time = clean_text(first_xml_text(refund, "RefundTime"))
        if refund_time:
            refund_times.append(refund_time)
        refund_status = clean_text(first_xml_text(refund, "RefundStatus"))
        if refund_status:
            refund_statuses.append(refund_status)

    if refund_amount <= 0:
        return None

    return {
        "supplier_order_id": order_id,
        "actual_refund_amount": round(refund_amount, 2),
        "refund_currency": refund_currency or "USD",
        "refund_time": max(refund_times) if refund_times else None,
        "refund_statuses": refund_statuses,
        "order_status": clean_text(first_xml_text(order, "OrderStatus")),
        "amount_paid": money_value(first_xml_text(order, "AmountPaid")),
        "adjustment_amount": money_value(first_xml_text(order, "AdjustmentAmount")),
    }


def build_purchase_line_index(supabase, lookback_days: int) -> dict[tuple[str, str], dict[str, Any]]:
    start_date = (dt.date.today() - dt.timedelta(days=max(lookback_days, 1))).isoformat()
    purchases = fetch_recent_purchases(supabase, start_date)
    purchase_ids = [purchase["purchase_id"] for purchase in purchases if purchase.get("purchase_id")]
    items_by_purchase_id = fetch_items_by_purchase_id(supabase, purchase_ids)

    index: dict[tuple[str, str], dict[str, Any]] = {}
    for purchase in purchases:
        purchase_item = select_problem_item(items_by_purchase_id.get(purchase["purchase_id"], []))
        if not purchase_item:
            continue
        for line in raw_order_lines(purchase.get("raw_import_json") or {}):
            item_id = clean_text(nested(line, "Item", "Item", "ItemID"))
            transaction_id = clean_text(line.get("TransactionID"))
            if not item_id or not transaction_id:
                continue
            index[(item_id, transaction_id)] = {
                "purchase_id": purchase["purchase_id"],
                "purchase_item_id": purchase_item["item_id"],
                "supplier": purchase.get("supplier") or "eBay",
                "supplier_order_id": purchase.get("supplier_order_id"),
                "raw_order_line": line,
            }
    return index


def fetch_recent_purchases(supabase, start_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table("purchases")
            .select("purchase_id,supplier,supplier_order_id,order_date,raw_import_json")
            .eq("supplier", "eBay")
            .gte("order_date", start_date)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def fetch_items_by_purchase_id(
    supabase,
    purchase_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for chunk in chunks(purchase_ids, 500):
        response = (
            supabase.table("purchase_items")
            .select("item_id,purchase_id,current_status,manual_split_child,received_date")
            .in_("purchase_id", chunk)
            .execute()
        )
        rows.extend(response.data or [])

    items_by_purchase_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        items_by_purchase_id.setdefault(row["purchase_id"], []).append(row)
    return items_by_purchase_id


def build_tracking_status_index(supabase) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table("inbound_shipments")
            .select(
                "tracking_number,normalized_status,carrier_status,shipment_status,"
                "delivered_date,last_checkpoint_time,last_tracking_sync"
            )
            .not_.is_("tracking_number", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        tracking_number = clean_text(row.get("tracking_number"))
        if tracking_number:
            index[tracking_number] = row
    return index


def select_problem_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None

    return sorted(items, key=problem_item_sort_key)[0]


def problem_item_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    status = clean_lower(item.get("current_status"))
    problem_status_rank = {
        "return_opened": 0,
        "return_pending": 1,
        "exception": 2,
        "no_tracking": 3,
        "shipped_no_tracking": 4,
        "awaiting_carrier_scan": 5,
        "in_transit": 6,
        "available_for_pickup": 7,
        "out_for_delivery": 8,
        "cancelled": 9,
        "delivered": 20,
        "received": 21,
        "listed": 22,
    }
    return (
        problem_status_rank.get(status, 10),
        0 if item.get("manual_split_child") else 1,
        0 if not item.get("received_date") else 1,
        clean_text(item.get("item_id")) or "",
    )


def raw_order_lines(raw_import_json: dict[str, Any]) -> list[dict[str, Any]]:
    order = raw_import_json.get("Order") or {}
    transaction_array = order.get("TransactionArray") or {}
    transaction_array = transaction_array.get("TransactionArray") or transaction_array
    transaction = transaction_array.get("Transaction") or {}
    if isinstance(transaction, dict):
        transaction = transaction.get("Transaction") or transaction
    if isinstance(transaction, list):
        return [row for row in transaction if isinstance(row, dict)]
    if isinstance(transaction, dict):
        return [transaction]
    return []


def map_return(return_row: dict[str, Any], supabase) -> dict[str, Any] | None:
    return_id = clean_text(return_row.get("returnId"))
    order_id = clean_text(return_row.get("orderId"))
    purchase = find_purchase_for_order(supabase, order_id)
    if not purchase:
        LOGGER.warning("Skipping eBay return %s; no purchase matched order %s", return_id, order_id)
        return None

    item = find_purchase_item_for_return(supabase, purchase["purchase_id"], return_row)
    if not item:
        LOGGER.warning("Skipping eBay return %s; no purchase item matched order %s", return_id, order_id)
        return None

    creation_info = return_row.get("creationInfo") or {}
    buyer_refund = return_row.get("buyerTotalRefund") or {}
    seller_due = return_row.get("sellerResponseDue") or {}
    buyer_due = return_row.get("buyerResponseDue") or {}
    escalation_info = return_row.get("escalationInfo") or {}
    buyer_escalation = escalation_info.get("buyerEscalationEligibilityInfo") or {}
    seller_escalation = escalation_info.get("sellerEscalationEligibilityInfo") or {}
    escalation_available_at = escalation_start_time(buyer_escalation, seller_escalation, buyer_due)
    return_tracking = return_tracking_details(return_row)
    return_tracking_number = clean_text(return_tracking.get("trackingNumber"))
    return_tracking_carrier = (
        clean_text(return_tracking.get("carrierName"))
        or clean_text(return_tracking.get("carrierEnum"))
        or clean_text(return_tracking.get("carrierUsed"))
    )
    return_tracking_status = clean_text(return_tracking.get("deliveryStatus"))
    return_label_date = unwrap_value(return_tracking.get("labelDate"))

    workflow_state = map_workflow_state(return_row)
    if workflow_state == "escalated" and return_tracking_number:
        workflow_state = "label_received"
    problem_type = map_problem_type(creation_info.get("reason"), return_row.get("currentType"))
    needs_response = workflow_state == "seller_message_needs_response" or buyer_response_due(return_row)
    estimated_refund = money_value(buyer_refund.get("estimatedRefundAmount"))
    actual_refund = money_value(buyer_refund.get("actualRefundAmount"))
    currency = (
        money_currency(buyer_refund.get("estimatedRefundAmount"))
        or money_currency(buyer_refund.get("actualRefundAmount"))
        or "USD"
    )

    return {
        "purchase_item_id": item["item_id"],
        "purchase_id": purchase["purchase_id"],
        "supplier": purchase.get("supplier") or "eBay",
        "supplier_order_id": order_id,
        "problem_source": "ebay_return_sync",
        "problem_type": problem_type,
        "workflow_state": workflow_state,
        "episode_kind": episode_kind_for_return(problem_type, return_row),
        "opened_reason": "ebay_return",
        "source_artifact_type": "ebay_return",
        "priority": "urgent" if needs_response else "normal",
        "is_open": not is_confidently_closed(return_row),
        "needs_response": needs_response,
        "next_action": next_action_for_state(workflow_state),
        "next_action_due_at": unwrap_value(
            seller_due.get("respondByDate")
            or buyer_due.get("respondByDate")
            or nested(return_row, "timeoutDate", "value")
        ),
        "last_detected_at": iso_z(dt.datetime.now(dt.timezone.utc)),
        "return_needed_at": unwrap_value(creation_info.get("creationDate")),
        "ebay_return_opened_at": unwrap_value(creation_info.get("creationDate")),
        "seller_message_last_at": unwrap_value(seller_due.get("respondByDate")) if needs_response else None,
        "partial_refund_offered_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "partial_refund_offered"
        else None,
        "label_available_at": return_label_date or (iso_z(dt.datetime.now(dt.timezone.utc)) if workflow_state == "label_received" else None),
        "return_shipped_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "return_shipped"
        else None,
        "return_tracking_number": return_tracking_number,
        "return_tracking_carrier": return_tracking_carrier,
        "return_tracking_status": return_tracking_status,
        "return_label_printed_at": return_label_date,
        "seller_received_return_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if workflow_state == "seller_received_return"
        else None,
        "refund_received_at": iso_z(dt.datetime.now(dt.timezone.utc))
        if actual_refund is not None and is_confidently_closed(return_row)
        else None,
        "escalation_available_at": escalation_available_at,
        "closed_at": iso_z(dt.datetime.now(dt.timezone.utc)) if is_confidently_closed(return_row) else None,
        "ebay_return_id": return_id,
        "ebay_case_id": return_id,
        "ebay_return_state": clean_text(return_row.get("state")),
        "ebay_return_status": clean_text(return_row.get("status")),
        "ebay_current_type": clean_text(return_row.get("currentType")),
        "ebay_action_url": return_action_url(return_row, return_id),
        "expected_refund_amount": estimated_refund,
        "actual_refund_amount": actual_refund,
        "partial_refund_amount": estimated_refund if workflow_state == "partial_refund_offered" else None,
        "refund_currency": currency,
        "purchase_item_status": "return_opened" if workflow_state not in {"resolved_refunded"} else "return_opened",
        "raw_ebay_json": return_row,
    }


def map_inquiry(
    inquiry_row: dict[str, Any],
    purchase_line_index: dict[tuple[str, str], dict[str, Any]],
    trading_refunds: dict[str, dict[str, Any]],
    tracking_status_index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    match = match_purchase_line(inquiry_row, purchase_line_index)
    if not match:
        LOGGER.warning(
            "Skipping eBay inquiry %s; no purchase matched item=%s transaction=%s",
            inquiry_row.get("inquiryId"),
            inquiry_row.get("itemId"),
            inquiry_row.get("transactionId"),
        )
        return None

    status = clean_upper(inquiry_row.get("inquiryStatusEnum") or inquiry_row.get("status"))
    replacement_tracking = clean_text(nested(inquiry_row, "inquiryHistoryDetails", "shipmentTrackingDetails", "trackingNumber"))
    tracking_status = tracking_status_index.get(replacement_tracking or "", {})
    replacement_delivered_at = replacement_tracking_delivered_at(inquiry_row, tracking_status)
    replacement_has_progress = replacement_tracking_has_progress(inquiry_row, tracking_status)
    order_refund = trading_refunds.get(clean_text(match.get("supplier_order_id")) or "")
    if order_refund:
        workflow_state = "resolved_refunded"
    elif replacement_delivered_at:
        workflow_state = "resolved_received_item"
    elif replacement_tracking and replacement_has_progress:
        workflow_state = "replacement_shipped"
    else:
        workflow_state = inquiry_workflow_state(status, replacement_tracking)
    needs_response = workflow_state == "seller_message_needs_response" or "BUYER_RESPONSE" in status
    claim_amount = money_value(inquiry_row.get("claimAmount"))
    inquiry_id = clean_text(inquiry_row.get("inquiryId"))
    escalation_available_at = unwrap_value(
        inquiry_row.get("sellerMakeItRightByDate")
        or nested(inquiry_row, "inquiryDetails", "expirationDate")
    )
    next_action_due_at = (
        escalation_available_at
        or unwrap_value(inquiry_row.get("respondByDate"))
        or unwrap_value(nested(inquiry_row, "inquiryDetails", "refundDeadlineDate"))
    )

    return {
        "purchase_item_id": match["purchase_item_id"],
        "purchase_id": match["purchase_id"],
        "supplier": match.get("supplier") or "eBay",
        "supplier_order_id": match.get("supplier_order_id"),
        "problem_source": "ebay_inquiry_sync",
        "problem_type": "missing_items",
        "workflow_state": workflow_state,
        "episode_kind": "item_not_received",
        "opened_reason": "ebay_inquiry",
        "source_artifact_type": "ebay_inquiry",
        "priority": "urgent" if needs_response else "normal",
        "is_open": workflow_state not in {"resolved_refunded", "resolved_received_item"},
        "needs_response": needs_response,
        "next_action": next_action_for_state(workflow_state),
        "next_action_due_at": next_action_due_at,
        "last_detected_at": iso_z(dt.datetime.now(dt.timezone.utc)),
        "return_needed_at": unwrap_value(
            inquiry_row.get("creationDate") or nested(inquiry_row, "inquiryDetails", "creationDate")
        ),
        "escalation_available_at": escalation_available_at,
        "ebay_inquiry_id": inquiry_id,
        "ebay_return_status": status or clean_text(inquiry_row.get("inquiryStatusEnum")),
        "ebay_current_type": "ITEM_NOT_RECEIVED_INQUIRY",
        "ebay_action_url": f"https://www.ebay.com/ItemNotReceived/{inquiry_id}" if inquiry_id else None,
        "expected_refund_amount": claim_amount,
        "actual_refund_amount": order_refund.get("actual_refund_amount") if order_refund else None,
        "refund_currency": (
            (order_refund.get("refund_currency") if order_refund else None)
            or money_currency(inquiry_row.get("claimAmount"))
            or "USD"
        ),
        "replacement_tracking_number": replacement_tracking,
        "replacement_shipped_at": replacement_shipped_at(match.get("raw_order_line") or {}, tracking_status)
        if workflow_state in {"replacement_shipped", "resolved_received_item"}
        else None,
        "replacement_received_at": replacement_delivered_at if workflow_state == "resolved_received_item" else None,
        "purchase_item_status": replacement_purchase_item_status(workflow_state, inquiry_row, tracking_status),
        "refund_received_at": order_refund.get("refund_time") if order_refund else None,
        "closed_at": (
            order_refund.get("refund_time")
            if order_refund
            else replacement_delivered_at
            if workflow_state == "resolved_received_item"
            else iso_z(dt.datetime.now(dt.timezone.utc))
            if inquiry_is_closed(status) and workflow_state != "replacement_shipped"
            else None
        ),
        "raw_ebay_json": {**inquiry_row, "_tradingRefund": order_refund} if order_refund else inquiry_row,
    }


def map_case(
    case_row: dict[str, Any],
    purchase_line_index: dict[tuple[str, str], dict[str, Any]],
    trading_refunds: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    status = clean_upper(case_row.get("caseStatusEnum"))
    match = match_purchase_line(case_row, purchase_line_index)
    if not match:
        LOGGER.warning(
            "Skipping eBay case %s; no purchase matched item=%s transaction=%s",
            case_row.get("caseId"),
            case_row.get("itemId"),
            case_row.get("transactionId"),
        )
        return None

    order_refund = trading_refunds.get(clean_text(match.get("supplier_order_id")) or "")
    if status == "CLOSED" and not order_refund:
        return None

    claim_amount = money_value(case_row.get("claimAmount"))
    workflow_state = "resolved_refunded" if order_refund else "escalated"
    return {
        "purchase_item_id": match["purchase_item_id"],
        "purchase_id": match["purchase_id"],
        "supplier": match.get("supplier") or "eBay",
        "supplier_order_id": match.get("supplier_order_id"),
        "problem_source": "ebay_inquiry_sync",
        "problem_type": "missing_items",
        "workflow_state": workflow_state,
        "episode_kind": "item_not_received",
        "opened_reason": "ebay_case",
        "source_artifact_type": "ebay_case",
        "priority": "normal" if order_refund else "high",
        "is_open": not order_refund,
        "needs_response": False,
        "next_action": next_action_for_state(workflow_state),
        "next_action_due_at": unwrap_value(case_row.get("respondByDate")),
        "last_detected_at": iso_z(dt.datetime.now(dt.timezone.utc)),
        "return_needed_at": unwrap_value(case_row.get("creationDate")),
        "ebay_case_id": clean_text(case_row.get("caseId")),
        "ebay_return_status": status or clean_text(case_row.get("caseStatusEnum")),
        "ebay_current_type": "ITEM_NOT_RECEIVED_CASE",
        "expected_refund_amount": claim_amount,
        "actual_refund_amount": order_refund.get("actual_refund_amount") if order_refund else None,
        "refund_currency": (
            (order_refund.get("refund_currency") if order_refund else None)
            or money_currency(case_row.get("claimAmount"))
            or "USD"
        ),
        "refund_received_at": order_refund.get("refund_time") if order_refund else None,
        "closed_at": order_refund.get("refund_time") if order_refund else None,
        "raw_ebay_json": {**case_row, "_tradingRefund": order_refund} if order_refund else case_row,
    }


def upsert_order_problem_case(supabase, mapped: dict[str, Any]) -> str:
    existing = find_existing_case(supabase, mapped)
    now = iso_z(dt.datetime.now(dt.timezone.utc))
    if existing:
        if should_preserve_operator_terminal_state(existing, mapped):
            append_event(supabase, existing["problem_case_id"], "ebay_return_sync_skipped_terminal", mapped)
            return "skipped"

        case_id = existing["problem_case_id"]
        updates = {key: value for key, value in mapped.items() if value is not None and key != "purchase_item_status"}
        preserve_active_return = should_preserve_active_return_state(existing, mapped)
        if should_preserve_operator_replacement_state(existing, mapped):
            updates.pop("workflow_state", None)
            updates.pop("next_action", None)
            updates.pop("needs_response", None)
        if preserve_active_return:
            updates.pop("workflow_state", None)
            updates.pop("is_open", None)
            updates.pop("needs_response", None)
            updates.pop("next_action", None)
            updates.pop("next_action_due_at", None)
            updates.pop("closed_at", None)
            updates.pop("refund_received_at", None)
            updates.pop("problem_source", None)
            updates.pop("problem_type", None)
            updates.pop("ebay_inquiry_id", None)
            updates.pop("ebay_action_url", None)
            updates.pop("ebay_return_state", None)
            updates.pop("ebay_current_type", None)
            updates.pop("ebay_return_status", None)
            updates.pop("escalation_available_at", None)
            updates.pop("episode_kind", None)
            updates.pop("opened_reason", None)
            updates.pop("source_artifact_type", None)
            updates.pop("resolved_reason", None)
            updates.pop("raw_ebay_json", None)
        if should_require_operator_refund_confirmation(existing, mapped):
            refund_issued_at = mapped.get("refund_received_at") or mapped.get("closed_at") or now
            updates["workflow_state"] = "refund_pending"
            updates["is_open"] = True
            updates["next_action"] = "Confirm refund received."
            updates["refund_due_at"] = refund_issued_at
            updates["closed_at"] = None
            updates["refund_received_at"] = None
            updates["resolved_reason"] = None
        if mapped.get("workflow_state") == "resolved_received_item" and not preserve_active_return:
            updates["is_open"] = False
            updates["needs_response"] = False
            updates["next_action"] = None
            updates["next_action_due_at"] = None
            updates["refund_due_at"] = None
            updates["resolved_reason"] = "replacement_received"
        if is_active_return_mapping(mapped):
            updates["is_open"] = True
            updates["closed_at"] = None
            updates["refund_received_at"] = None
            updates["resolved_reason"] = None
            updates["next_action"] = mapped.get("next_action") or next_action_for_state(mapped.get("workflow_state") or "")
            updates["ebay_inquiry_id"] = None
        updates["updated_at"] = now
        supabase.table("order_problem_cases").update(updates).eq("problem_case_id", case_id).execute()
        ensure_replacement_tracking_shipment(supabase, mapped)
        if not preserve_active_return:
            update_purchase_item_status_from_problem(supabase, mapped)
        close_duplicate_ebay_cases(supabase, case_id, mapped, now)
        append_event(supabase, case_id, "ebay_return_sync_updated", mapped)
        return "updated"

    payload = {key: value for key, value in mapped.items() if key != "purchase_item_status"}
    if should_insert_as_refund_pending(payload):
        refund_issued_at = payload.get("refund_received_at") or payload.get("closed_at") or now
        payload["workflow_state"] = "refund_pending"
        payload["is_open"] = True
        payload["next_action"] = "Confirm refund received."
        payload["refund_due_at"] = refund_issued_at
        payload.pop("closed_at", None)
        payload.pop("refund_received_at", None)
        payload.pop("resolved_reason", None)
    payload["episode_sequence"] = next_episode_sequence(supabase, mapped["purchase_item_id"])
    payload["created_at"] = now
    payload["updated_at"] = now
    response = supabase.table("order_problem_cases").insert(payload).execute()
    case_id = response.data[0]["problem_case_id"]
    ensure_replacement_tracking_shipment(supabase, mapped)
    update_purchase_item_status_from_problem(supabase, mapped)
    close_duplicate_ebay_cases(supabase, case_id, mapped, now)
    append_event(supabase, case_id, "ebay_return_sync_inserted", mapped)
    return "inserted"


def close_duplicate_ebay_cases(
    supabase,
    keep_case_id: str,
    mapped: dict[str, Any],
    now: str,
) -> None:
    duplicate_filters = [
        ("ebay_return_id", mapped.get("ebay_return_id")),
        ("ebay_inquiry_id", mapped.get("ebay_inquiry_id")),
        ("ebay_case_id", mapped.get("ebay_case_id")),
    ]
    for column, value in duplicate_filters:
        if not value:
            continue
        supabase.table("order_problem_cases").update(
            {
                "is_open": False,
                "workflow_state": "closed_no_action",
                "closed_at": now,
                "updated_at": now,
                "resolved_reason": "superseded",
                "superseded_by_case_id": keep_case_id,
                "notes": "Closed automatically because this eBay artifact was remapped to the active split/problem item.",
            }
        ).eq(column, value).neq("problem_case_id", keep_case_id).eq("is_open", True).execute()


def next_episode_sequence(supabase, item_id: str) -> int:
    response = (
        supabase.table("order_problem_cases")
        .select("episode_sequence")
        .eq("purchase_item_id", item_id)
        .order("episode_sequence", desc=True)
        .limit(1)
        .execute()
    )
    current = (response.data or [{}])[0].get("episode_sequence")
    try:
        return int(current or 0) + 1
    except (TypeError, ValueError):
        return 1


def append_event(supabase, case_id: str, event_type: str, mapped: dict[str, Any]) -> None:
    supabase.table("order_problem_events").insert(
        {
            "problem_case_id": case_id,
            "event_type": event_type,
            "event_source": "ebay_api",
            "message": (
                f"Read-only eBay order-problem sync mapped "
                f"{mapped.get('ebay_current_type') or 'return'} "
                f"state {mapped.get('workflow_state')}."
            ),
            "amount": mapped.get("actual_refund_amount") or mapped.get("expected_refund_amount"),
            "currency": mapped.get("refund_currency"),
            "raw_json": mapped.get("raw_ebay_json"),
        }
    ).execute()


def ensure_replacement_tracking_shipment(supabase, mapped: dict[str, Any]) -> None:
    tracking_number = clean_text(mapped.get("replacement_tracking_number"))
    purchase_id = clean_text(mapped.get("purchase_id"))
    item_id = clean_text(mapped.get("purchase_item_id"))
    if not tracking_number or not purchase_id or not item_id:
        return

    carrier = clean_text(
        nested(
            mapped.get("raw_ebay_json") or {},
            "inquiryHistoryDetails",
            "shipmentTrackingDetails",
            "carrier",
        )
    )
    now = iso_z(dt.datetime.now(dt.timezone.utc))
    existing = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id")
        .eq("purchase_id", purchase_id)
        .eq("tracking_number", tracking_number)
        .limit(1)
        .execute()
    )

    if existing.data:
        shipment_id = existing.data[0]["inbound_shipment_id"]
        supabase.table("inbound_shipments").update(
            {
                "carrier": carrier,
                "updated_at": now,
            }
        ).eq("inbound_shipment_id", shipment_id).execute()
    else:
        inserted = supabase.table("inbound_shipments").insert(
            {
                "purchase_id": purchase_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
                "shipment_status": "unknown",
                "normalized_status": "unknown",
                "updated_at": now,
            }
        ).execute()
        shipment_id = inserted.data[0]["inbound_shipment_id"]

    link = (
        supabase.table("inbound_shipment_items")
        .select("inbound_shipment_item_id")
        .eq("inbound_shipment_id", shipment_id)
        .eq("item_id", item_id)
        .limit(1)
        .execute()
    )
    if not link.data:
        supabase.table("inbound_shipment_items").insert(
            {
                "inbound_shipment_id": shipment_id,
                "item_id": item_id,
                "quantity_expected_in_package": 1,
                "notes": "Linked from eBay replacement tracking.",
            }
        ).execute()


def update_purchase_item_status_from_problem(supabase, mapped: dict[str, Any]) -> None:
    item_id = clean_text(mapped.get("purchase_item_id"))
    purchase_status = clean_text(mapped.get("purchase_item_status"))
    if not item_id or not purchase_status:
        return

    response = (
        supabase.table("purchase_items")
        .select("current_status")
        .eq("item_id", item_id)
        .limit(1)
        .execute()
    )
    current_status = clean_lower((response.data or [{}])[0].get("current_status"))
    if current_status in {"listed", "cancelled"}:
        return
    if current_status == "received" and purchase_status != "return_opened":
        return

    supabase.table("purchase_items").update({"current_status": purchase_status}).eq("item_id", item_id).execute()


def find_existing_case(supabase, mapped: dict[str, Any]) -> dict[str, Any] | None:
    select_fields = (
        "problem_case_id,workflow_state,problem_source,is_open,closed_at,refund_received_at,"
        "ebay_return_id,ebay_case_id,return_tracking_number,label_available_at,"
        "return_tracking_status,seller_received_return_at"
    )
    response = (
        supabase.table("order_problem_cases")
        .select(select_fields)
        .eq("purchase_item_id", mapped["purchase_item_id"])
        .eq("is_open", True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]

    supplier_order_id = mapped.get("supplier_order_id")
    if supplier_order_id:
        response = (
            supabase.table("order_problem_cases")
            .select(select_fields)
            .eq("supplier_order_id", supplier_order_id)
            .eq("is_open", True)
            .in_("workflow_state", ["return_opened", "return_needed", "refund_pending"])
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    return_id = mapped.get("ebay_return_id")
    if return_id:
        response = (
            supabase.table("order_problem_cases")
            .select(select_fields)
            .eq("ebay_return_id", return_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    inquiry_id = mapped.get("ebay_inquiry_id")
    if inquiry_id:
        response = (
            supabase.table("order_problem_cases")
            .select(select_fields)
            .eq("ebay_inquiry_id", inquiry_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    case_id = mapped.get("ebay_case_id")
    if case_id:
        response = (
            supabase.table("order_problem_cases")
            .select(select_fields)
            .eq("ebay_case_id", case_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]

    return None


def should_preserve_operator_terminal_state(existing: dict[str, Any], mapped: dict[str, Any]) -> bool:
    if mapped.get("problem_source") == "ebay_return_sync" and mapped.get("workflow_state") not in {
        "resolved_refunded",
        "closed_no_action",
        "closed_no_refund",
    }:
        return False
    if existing.get("problem_source") == "ebay_return_sync":
        return False
    if existing.get("ebay_return_id") and existing.get("ebay_return_id") == existing.get("ebay_case_id"):
        return False

    workflow_state = existing.get("workflow_state")
    if workflow_state not in {
        "resolved_refunded",
        "resolved_received_item",
        "closed_no_action",
        "closed_no_refund",
    }:
        return False

    return existing.get("is_open") is False or bool(existing.get("closed_at") or existing.get("refund_received_at"))


def should_preserve_operator_replacement_state(
    existing: dict[str, Any],
    mapped: dict[str, Any],
) -> bool:
    if mapped.get("problem_source") != "ebay_inquiry_sync":
        return False
    if mapped.get("is_open") is False:
        return False
    return existing.get("workflow_state") in {"replacement_pending", "replacement_shipped"}


def should_preserve_active_return_state(
    existing: dict[str, Any],
    mapped: dict[str, Any],
) -> bool:
    if mapped.get("problem_source") != "ebay_inquiry_sync":
        return False
    if existing.get("problem_source") != "ebay_return_sync" and not existing.get("return_tracking_number"):
        return False
    if existing.get("workflow_state") not in {
        "return_opened",
        "seller_message_needs_response",
        "waiting_on_seller",
        "partial_refund_offered",
        "label_pending",
        "label_received",
        "return_shipped",
        "seller_received_return",
        "refund_pending",
        "escalation_available",
        "escalated",
    }:
        return False
    if mapped.get("workflow_state") in {"resolved_received_item", "closed_no_action"}:
        return True
    if mapped.get("workflow_state") == "escalated" and existing.get("workflow_state") in {
        "return_opened",
        "seller_message_needs_response",
        "waiting_on_seller",
        "partial_refund_offered",
        "label_pending",
        "label_received",
        "return_shipped",
        "seller_received_return",
        "refund_pending",
    }:
        return True
    return False


def is_active_return_mapping(mapped: dict[str, Any]) -> bool:
    return mapped.get("problem_source") == "ebay_return_sync" and mapped.get("workflow_state") not in {
        "resolved_refunded",
        "closed_no_action",
        "closed_no_refund",
    }


def should_require_operator_refund_confirmation(
    existing: dict[str, Any],
    mapped: dict[str, Any],
) -> bool:
    if mapped.get("workflow_state") != "resolved_refunded":
        return False
    return existing.get("workflow_state") != "resolved_refunded"


def should_insert_as_refund_pending(mapped: dict[str, Any]) -> bool:
    return mapped.get("workflow_state") == "resolved_refunded"


def find_purchase_for_order(supabase, order_id: str | None) -> dict[str, Any] | None:
    if not order_id:
        return None
    response = (
        supabase.table("purchases")
        .select("purchase_id,supplier,supplier_order_id")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def find_purchase_item_for_purchase(supabase, purchase_id: str) -> dict[str, Any] | None:
    response = (
        supabase.table("purchase_items")
        .select("item_id")
        .eq("purchase_id", purchase_id)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def find_purchase_item_for_return(
    supabase,
    purchase_id: str,
    return_row: dict[str, Any],
) -> dict[str, Any] | None:
    rows = (
        supabase.table("purchase_items")
        .select("item_id,current_status,received_date,manual_split_child")
        .eq("purchase_id", purchase_id)
        .execute()
    ).data or []
    if not rows:
        return None

    active_problem_items = fetch_open_problem_item_ids(supabase, purchase_id)
    if active_problem_items:
        for row in rows:
            if row.get("item_id") in active_problem_items:
                return row

    return select_problem_item(rows)


def fetch_open_problem_item_ids(supabase, purchase_id: str) -> set[str]:
    rows = (
        supabase.table("order_problem_cases")
        .select("purchase_item_id,workflow_state,problem_source")
        .eq("purchase_id", purchase_id)
        .eq("is_open", True)
        .in_("workflow_state", ["return_needed", "return_opened", "waiting_on_seller", "label_pending", "label_received", "return_shipped", "refund_pending"])
        .execute()
    ).data or []
    return {clean_text(row.get("purchase_item_id")) for row in rows if clean_text(row.get("purchase_item_id"))}


def map_workflow_state(return_row: dict[str, Any]) -> str:
    status = clean_upper(return_row.get("status"))
    state = clean_upper(return_row.get("state"))
    current_type = clean_upper(return_row.get("currentType"))
    combined = {status, state, current_type}

    if "ESCALATED" in combined:
        return "escalated"
    if combined & {"PARTIAL_REFUND_REQUESTED", "PARTIAL_REFUND_INITIATED", "LESS_THAN_A_FULL_REFUND_ISSUED"}:
        return "partial_refund_offered"
    if combined & {"WAITING_FOR_RETURN_LABEL", "RETURN_LABEL_REQUESTED"}:
        return "label_pending"
    if "READY_FOR_SHIPPING" in combined:
        return "label_received"
    if "ITEM_SHIPPED" in combined:
        return "return_shipped"
    if "ITEM_DELIVERED" in combined:
        return "seller_received_return"
    if "CLOSED" in combined and is_confidently_closed(return_row):
        return "resolved_refunded"
    if "RETURN_REQUESTED" in combined:
        return "return_opened"
    if "BUYER_ACTION" in combined or "SELLER_MESSAGE" in combined:
        return "seller_message_needs_response"
    return "waiting_on_seller" if "CLOSED" not in combined else "return_opened"


def map_problem_type(reason: Any, current_type: Any) -> str:
    text = f"{reason or ''} {current_type or ''}".upper()
    if "MISSING" in text or "INCOMPLETE" in text:
        return "missing_items"
    if "CHANGED" in text or "BUYER" in text:
        return "buyer_choice"
    return "not_as_listed"


def episode_kind_for_return(problem_type: str, return_row: dict[str, Any]) -> str:
    reason_text = " ".join(
        clean_upper(value)
        for value in (
            nested(return_row, "creationInfo", "reason"),
            return_row.get("currentType"),
            return_row.get("state"),
            return_row.get("status"),
        )
    )
    if problem_type == "missing_items" or "MISSING" in reason_text or "INCOMPLETE" in reason_text:
        return "incomplete_item"
    if "DAMAGED" in reason_text or "NOT_AS_DESCRIBED" in reason_text or "SIGNIFICANTLY_NOT_AS_DESCRIBED" in reason_text:
        return "damaged_item"
    return "return_request"


def return_action_url(return_row: dict[str, Any], return_id: str | None) -> str | None:
    for option_group in ("buyerAvailableOptions", "sellerAvailableOptions"):
        options = return_row.get(option_group) or []
        if isinstance(options, dict):
            options = [options]
        if not isinstance(options, list):
            continue
        for option in options:
            if not isinstance(option, dict):
                continue
            action_url = clean_text(option.get("actionURL"))
            if action_url:
                return action_url

    if return_id:
        return f"https://www.ebay.com/rtn/Return/ReturnsDetail?returnId={return_id}"

    return None


def return_tracking_details(return_row: dict[str, Any]) -> dict[str, Any]:
    shipment_info = nested(return_row, "detail", "returnShipmentInfo")
    if not isinstance(shipment_info, dict):
        return {}

    tracking = shipment_info.get("shipmentTracking")
    if isinstance(tracking, dict) and clean_text(tracking.get("trackingNumber")):
        return tracking

    all_trackings = shipment_info.get("allShipmentTrackings")
    if isinstance(all_trackings, dict):
        all_trackings = [all_trackings]
    if isinstance(all_trackings, list):
        for row in all_trackings:
            if isinstance(row, dict) and clean_text(row.get("trackingNumber")):
                return row

    return {}


def inquiry_workflow_state(status: str, replacement_tracking: str | None) -> str:
    if status in {"CLOSED", "CLOSED_WITH_REFUND", "CLOSED_WITHOUT_REFUND"}:
        return "resolved_refunded"
    if replacement_tracking and status in {
        "WAITING_BUYER_RESPONSE",
        "PENDING_BUYER_RESPONSE",
        "TRACK_INQUIRY_PENDING_BUYER_RESPONSE",
    }:
        return "replacement_shipped"
    if status in {"WAITING_BUYER_RESPONSE", "PENDING_BUYER_RESPONSE"}:
        return "seller_message_needs_response"
    if status in {"OPEN", "WAITING_SELLER_RESPONSE", "PENDING_SELLER_RESPONSE"}:
        return "waiting_on_seller"
    return "waiting_on_seller"


def replacement_tracking_delivered_at(
    inquiry_row: dict[str, Any],
    tracking_status: dict[str, Any],
) -> str | None:
    local_delivered_at = clean_text(tracking_status.get("delivered_date"))
    if local_delivered_at:
        return local_delivered_at

    if tracking_status_is_delivered(inquiry_tracking_status(inquiry_row)):
        return (
            inquiry_history_time_for_text(inquiry_row, "DELIVER")
            or clean_text(tracking_status.get("last_checkpoint_time"))
            or clean_text(tracking_status.get("last_tracking_sync"))
            or iso_z(dt.datetime.now(dt.timezone.utc))
        )

    return None


def replacement_tracking_has_progress(
    inquiry_row: dict[str, Any],
    tracking_status: dict[str, Any],
) -> bool:
    if replacement_tracking_delivered_at(inquiry_row, tracking_status):
        return True

    local_statuses = [
        normalize_status_text(tracking_status.get("normalized_status")),
        normalize_status_text(tracking_status.get("carrier_status")),
        normalize_status_text(tracking_status.get("shipment_status")),
    ]
    if any(status in PROGRESS_TRACKING_STATUSES for status in local_statuses):
        return True

    ebay_status = normalize_status_text(inquiry_tracking_status(inquiry_row))
    if ebay_status in PROGRESS_TRACKING_STATUSES:
        return True

    return bool(clean_text(tracking_status.get("last_checkpoint_time")))


def replacement_purchase_item_status(
    workflow_state: str,
    inquiry_row: dict[str, Any],
    tracking_status: dict[str, Any],
) -> str | None:
    if workflow_state == "resolved_received_item":
        return "delivered"
    if workflow_state != "replacement_shipped":
        return None

    statuses = [
        normalize_status_text(tracking_status.get("normalized_status")),
        normalize_status_text(tracking_status.get("carrier_status")),
        normalize_status_text(tracking_status.get("shipment_status")),
        normalize_status_text(inquiry_tracking_status(inquiry_row)),
    ]
    if any(status in {"exception", "failure", "return_to_sender", "returned_to_sender"} for status in statuses):
        return "exception"
    if "out_for_delivery" in statuses:
        return "out_for_delivery"
    if "available_for_pickup" in statuses:
        return "available_for_pickup"
    if any(status in PROGRESS_TRACKING_STATUSES for status in statuses):
        return "in_transit"
    return "awaiting_carrier_scan"


def replacement_shipped_at(raw_line: dict[str, Any], tracking_status: dict[str, Any]) -> str | None:
    return (
        shipment_tracking_date(raw_line)
        or clean_text(tracking_status.get("last_checkpoint_time"))
        or clean_text(tracking_status.get("last_tracking_sync"))
    )


def inquiry_tracking_status(inquiry_row: dict[str, Any]) -> str | None:
    return clean_text(nested(inquiry_row, "inquiryHistoryDetails", "shipmentTrackingDetails", "currentStatus"))


def tracking_status_is_delivered(value: Any) -> bool:
    return normalize_status_text(value) == "delivered"


PROGRESS_TRACKING_STATUSES = {
    "accepted",
    "available_for_pickup",
    "delivered",
    "in_transit",
    "out_for_delivery",
    "return_to_sender",
    "returned_to_sender",
    "transit",
}


def normalize_status_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized_chars: list[str] = []
    previous_was_lower = False
    for char in text:
        if char.isupper() and previous_was_lower:
            normalized_chars.append("_")
        if char.isalnum():
            normalized_chars.append(char.lower())
            previous_was_lower = char.islower() or char.isdigit()
        else:
            if normalized_chars and normalized_chars[-1] != "_":
                normalized_chars.append("_")
            previous_was_lower = False
    return "".join(normalized_chars).strip("_")


def inquiry_history_time_for_text(inquiry_row: dict[str, Any], text_fragment: str) -> str | None:
    fragment = text_fragment.upper()
    history = nested(inquiry_row, "inquiryHistoryDetails", "history")
    if isinstance(history, dict):
        history = [history]
    if not isinstance(history, list):
        return None

    matches: list[str] = []
    for event in history:
        if not isinstance(event, dict):
            continue
        event_text = " ".join(str(value or "") for value in event.values()).upper()
        if fragment not in event_text:
            continue
        timestamp = clean_text(
            unwrap_value(event.get("creationDate"))
            or unwrap_value(event.get("date"))
            or unwrap_value(event.get("activityDate"))
        )
        if timestamp:
            matches.append(timestamp)
    return max(matches) if matches else None


def inquiry_is_closed(status: str) -> bool:
    return status in {"CLOSED", "CLOSED_WITH_REFUND", "CLOSED_WITHOUT_REFUND"}


def buyer_response_due(return_row: dict[str, Any]) -> bool:
    status_text = " ".join(
        clean_upper(value)
        for value in (
            return_row.get("status"),
            return_row.get("state"),
            return_row.get("currentType"),
            nested(return_row, "buyerResponseDue", "activityDue"),
        )
    )
    return "BUYER_RESPONSE" in status_text or "BUYER_ACTION" in status_text


def next_action_for_state(state: str) -> str | None:
    return {
        "return_opened": "Wait for seller response.",
        "seller_message_needs_response": "Respond to seller in eBay.",
        "waiting_on_seller": "Wait for seller response.",
        "partial_refund_offered": "Review partial refund offer.",
        "label_pending": "Wait for return label.",
        "label_received": "Ship item back to seller.",
        "return_shipped": "Wait for seller to receive return.",
        "seller_received_return": "Wait for refund.",
        "replacement_shipped": "Monitor replacement tracking and confirm receipt.",
        "escalated": "Wait for eBay case decision.",
    }.get(state)


def escalation_start_time(
    buyer_escalation: dict[str, Any],
    seller_escalation: dict[str, Any],
    buyer_due: dict[str, Any],
) -> str | None:
    explicit_start = unwrap_value(
        buyer_escalation.get("startTime") or seller_escalation.get("startTime")
    )
    if explicit_start:
        return explicit_start

    if clean_upper(buyer_due.get("activityDue")) == "BUYER_ESCALATE":
        return unwrap_value(buyer_due.get("respondByDate"))

    return None


def is_confidently_closed(return_row: dict[str, Any]) -> bool:
    status = clean_upper(return_row.get("status"))
    state = clean_upper(return_row.get("state"))
    actual_refund = money_value(nested(return_row, "buyerTotalRefund", "actualRefundAmount"))
    return "CLOSED" in {status, state} and actual_refund is not None


def print_summary(mapped: dict[str, Any], *, dry_run: bool) -> None:
    prefix = "DRY RUN" if dry_run else "WRITE"
    print(
        f"{prefix}: order={mapped.get('supplier_order_id')} return={mapped.get('ebay_return_id')} "
        f"state={mapped.get('workflow_state')} expected={mapped.get('expected_refund_amount')}"
    )


def nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def match_purchase_line(
    row: dict[str, Any],
    purchase_line_index: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    item_id = clean_text(row.get("itemId"))
    transaction_id = clean_text(row.get("transactionId"))
    if not item_id or not transaction_id:
        return None
    return purchase_line_index.get((item_id, transaction_id))


def shipment_tracking_number(raw_line: dict[str, Any]) -> str | None:
    details = raw_line.get("ShippingDetails") or {}
    details = details.get("ShippingDetails") or details
    tracking = details.get("ShipmentTrackingDetails") or {}
    tracking = tracking.get("ShipmentTrackingDetails") or tracking
    return clean_text(tracking.get("ShipmentTrackingNumber"))


def shipment_tracking_date(raw_line: dict[str, Any]) -> str | None:
    return unwrap_value(raw_line.get("ShippedTime"))


def chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def unwrap_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("Value")
    return value


def strip_xml_namespace(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def xml_children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [elem for elem in parent.iter() if strip_xml_namespace(elem.tag) == name]


def first_xml_child(parent: ET.Element, name: str) -> ET.Element | None:
    for elem in parent.iter():
        if strip_xml_namespace(elem.tag) == name:
            return elem
    return None


def first_xml_text(parent: ET.Element, name: str) -> str | None:
    elem = first_xml_child(parent, name)
    return elem.text if elem is not None else None


def all_xml_text(parent: ET.Element, name: str) -> list[str]:
    return [elem.text for elem in xml_children(parent, name) if elem.text]


def money_value(value: Any) -> float | None:
    value = unwrap_value(value)
    if isinstance(value, dict):
        value = value.get("value")
    try:
        if value is None or value == "":
            return None
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def money_currency(value: Any) -> str | None:
    if isinstance(value, dict):
        return clean_text(value.get("currency") or value.get("currencyId"))
    return None


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def clean_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def clean_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
