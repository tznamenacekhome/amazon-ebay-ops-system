"""Sync Veeqo label costs for Merchant Fulfilled Amazon sales orders.

This integration reads Veeqo order/shipment data, stores actual cost evidence and
repairs shipping profitability. It never buys labels or updates remote orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from collections import Counter
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from supabase import create_client
import requests

try:
    from .sales_shipping_costs import extract_shipments, label_evidence, order_label_cost, allocate_cost
    from .amazon_sales_profitability import refresh_shipping_profitability, amazon_shipping_label_cost, fulfillment_cost_for_order
except ImportError:
    from sales_shipping_costs import extract_shipments, label_evidence, order_label_cost, allocate_cost
    from amazon_sales_profitability import refresh_shipping_profitability, amazon_shipping_label_cost, fulfillment_cost_for_order

LOGGER = logging.getLogger("veeqo_sales_label_sync")
VEEQO_BASE_URL = "https://api.veeqo.com"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 4
BATCH_LIMIT = 100
MIN_PURCHASE_DATE = "2025-01-01T00:00:00Z"


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
        if args.apply:
            try:
                from .sourcing_database_guard import wait_for_database
            except ImportError:
                from sourcing_database_guard import wait_for_database
            wait_for_database(supabase, attempts=1)
        orders = load_mf_orders(supabase)
        known = load_pages(supabase, "veeqo_sales_orders", "veeqo_order_id,amazon_order_id,raw_veeqo_order_json")
        by_order = {r["amazon_order_id"]: r for r in known}
        previous = (supabase.table("scheduler_run_jobs").select("metadata")
                    .eq("job_name", "Veeqo MF label costs").neq("status", "running")
                    .order("started_at", desc=True).limit(10).execute().data or [])
        cursor = next((r["metadata"]["shipping_reconciliation"].get("cursors", {})
                       for r in previous if (r.get("metadata") or {}).get("shipping_reconciliation", {}).get("cursors")), {})
        eligible = [o for o in orders if shipping_required(o)]
        pending = [o for o in orders if str(o.get("order_status", "")).lower() in {"unshipped", "pending", "pendingavailability"}]
        profits, events, overrides = {}, {}, {}
        for offset in range(0, len(eligible), 100):
            ids = [o["amazon_order_id"] for o in eligible[offset:offset + 100]]
            rows = supabase.table("amazon_sales_profitability").select("amazon_order_id,amazon_order_item_id,quantity,fulfillment_cost,fulfillment_cost_source,data_status").in_("amazon_order_id", ids).execute().data or []
            for row in rows:
                profits.setdefault(row["amazon_order_id"], []).append(row)
            for row in load_pages(supabase, "amazon_sales_financial_events", "amazon_order_id,financial_event_id,event_type,currency,amount,raw_financial_event_json",
                    lambda q: q.in_("amazon_order_id", ids).eq("event_type", "AdjustmentEventList")):
                events.setdefault(row["amazon_order_id"], []).append(row)
            for row in load_pages(supabase, "amazon_sales_fulfillment_cost_overrides", "amazon_order_id,amazon_order_item_id,fulfillment_cost,fulfillment_cost_source,currency",
                    lambda q: q.in_("amazon_order_id", ids).eq("active", True)):
                if row.get("currency") == "USD":
                    overrides.setdefault(row["amazon_order_id"], {})[row.get("amazon_order_item_id")] = row
        eligible = [o for o in eligible if not profits.get(o["amazon_order_id"]) or not all(
            p.get("data_status") in {"cancelled", "refunded"} for p in profits[o["amazon_order_id"]])]
        verified = {}
        for order in eligible:
            oid = order["amazon_order_id"]
            amount, source = fulfillment_cost_for_order(order, 0,
                order_label_cost((by_order.get(oid) or {}).get("raw_veeqo_order_json") or {})[0],
                amazon_shipping_label_cost(events.get(oid, [])), overrides.get(oid, {}).get(None))
            verified[oid] = (amount, source, overrides.get(oid, {}))
        unresolved = [o for o in eligible if needs_reconciliation(o, by_order, profits, verified)]
        candidates = unresolved if args.missing_only else eligible
        if args.amazon_order_id:
            selected = [o for o in eligible if o["amazon_order_id"] == args.amazon_order_id]
            if not selected:
                raise RuntimeError("Target order is absent or does not require outbound shipping")
        elif args.asin:
            target = recent_asin_orders(supabase, args.asin, args.last_units)
            selected = [o for o in eligible if o["amazon_order_id"] in target]
            if len(selected) > args.limit:
                raise RuntimeError("ASIN cohort exceeds --limit; increase the explicit bounded limit")
        else:
            selected, cursor = select_work(candidates, args.purchase_date_start, args.purchase_date_end,
                                           args.limit, args.backlog_limit, cursor)
        stats = {"eligible_orders": len(eligible), "selected_orders": len(selected), "attempted_orders": 0,
                 "matched_orders": 0, "reconciled_costs": 0, "pending_orders": len(pending),
                 "unresolved_shipped_orders": len(unresolved), "api_failures": 0, "write_failures": 0,
                 "oldest_unresolved_purchase_date": min((o["purchase_date"] for o in unresolved), default=None),
                 "backlog_age_days": max((datetime.now(timezone.utc) - datetime.fromisoformat(o["purchase_date"].replace("Z", "+00:00"))).days for o in unresolved) if unresolved else 0,
                 "cursors": cursor, "queue_status": "empty" if not unresolved else "planned",
                 "expected_api_requests_max": sum(4 if by_order.get(o["amazon_order_id"]) else 28 for o in selected)}
        api_key = os.getenv("VEEQO_KEY") or os.getenv("VEEQO_API_KEY") or os.getenv("VEEQO_ACCESS_TOKEN")
        if not api_key:
            stats["queue_status"] = "missing_credentials"
            emit_summary(stats)
            if args.apply:
                notify_backlog(supabase, stats)
            return 1
        if not args.apply:
            emit_summary(stats)
            return 0
        client = VeeqoClient(api_key)
        outcomes = Counter()
        resolved_orders = set()
        stats["order_outcomes"] = {}
        stats["queue_status"] = "incomplete"
        # Preserve continuation even if ECS times out during a slow provider call.
        # The scheduler streams these checkpoints into failed-run metadata too.
        print("METADATA_JSON: " + json.dumps({"shipping_reconciliation": stats}), flush=True)
        for order in selected:
            order_id = order["amazon_order_id"]
            stats["attempted_orders"] += 1
            print("METADATA_JSON: " + json.dumps({"shipping_reconciliation": stats}), flush=True)
            stage = "api"
            try:
                old = by_order.get(order_id)
                payload = (client.get_order(old["veeqo_order_id"]) if old
                           else client.find_order_by_amazon_order_id(order_id))
                if not payload:
                    outcomes["missing_veeqo_match"] += 1
                    stats["order_outcomes"][order_id] = "missing_veeqo_match"
                    continue
                if not order_matches_amazon_id(payload, order_id):
                    outcomes["source_identity_mismatch"] += 1
                    stats["order_outcomes"][order_id] = "source_identity_mismatch"
                    continue
                stats["matched_orders"] += 1
                payload = preserve_cost_evidence((old or {}).get("raw_veeqo_order_json") or {}, payload)
                amount, reason = order_label_cost(payload)
                payload["_mbop_shipping_reconciliation"] = {
                    "checked_at": datetime.now(timezone.utc).isoformat(), "reason": reason,
                    "allocation_rule": "ordered_quantity_stable_item_id_cents",
                }
                outcomes[reason] += 1
                stats["order_outcomes"][order_id] = reason
                stage = "write"
                upsert_rows(supabase, "veeqo_sales_orders", [build_veeqo_order_row(order_id, payload)], "veeqo_order_id")
                persist_shipments(supabase, order_id, build_shipment_rows(order_id, payload))
                # Always repair this order, including old dates and stale adjustment-derived costs.
                repaired = refresh_shipping_profitability(supabase, order)
                if repaired:
                    resolved_orders.add(order_id)
                    stats["reconciled_costs"] += 1
                    if order in unresolved:
                        stats["unresolved_shipped_orders"] -= 1
            except Exception as error:
                # Continue to other orders; never print source bodies/customer data.
                stats[stage + "_failures"] += 1
                stats["order_outcomes"][order_id] = stage + "_failure"
                LOGGER.error("Shipping reconciliation failed (%s)", type(error).__name__)
        stats.update(outcomes)
        stats.update(external_api_calls=client.api_calls, retry_count=client.retries, rate_limit_count=client.rate_limits)
        remaining = [o for o in unresolved if o["amazon_order_id"] not in resolved_orders]
        stats["oldest_unresolved_purchase_date"] = min((o["purchase_date"] for o in remaining), default=None)
        stats["backlog_age_days"] = max((datetime.now(timezone.utc) - datetime.fromisoformat(o["purchase_date"].replace("Z", "+00:00"))).days for o in remaining) if remaining else 0
        failures = stats["api_failures"] + stats["write_failures"]
        stats["queue_status"] = "incomplete" if failures else "backlog" if stats["unresolved_shipped_orders"] else "empty"
        emit_summary(stats)
        notify_backlog(supabase, stats)
        return 1 if failures else 0
    except Exception as error:
        LOGGER.error("Veeqo reconciliation failed (%s)", type(error).__name__)
        print('METADATA_JSON: {"shipping_reconciliation":{"queue_status":"failed"}}')
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Veeqo label costs for Amazon MF sales orders."
    )
    parser.add_argument("--amazon-order-id", help="Target one Amazon order ID.")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum MF Amazon sales orders to process (1..200, default 50).",
    )
    parser.add_argument(
        "--purchase-date-start",
        help="Stored order purchase_date lower bound as ISO timestamp.",
    )
    parser.add_argument(
        "--purchase-date-end",
        help="Stored order purchase_date upper bound as ISO timestamp.",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only process MF orders without complete actual label evidence.",
    )
    parser.add_argument("--backlog-limit", type=int, default=20, help="Reserved older-order slots within --limit.")
    parser.add_argument("--asin", help="Bounded last-shipped-unit recovery cohort.")
    parser.add_argument("--last-units", type=int, default=25)
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run; default mode.")
    args = parser.parse_args()
    if not 1 <= args.limit <= 200 or not 0 <= args.backlog_limit <= args.limit or args.last_units < 1:
        parser.error("Require limit 1..200, backlog-limit 0..limit and positive last-units")
    return args


class VeeqoClient:
    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()
        self.api_calls = self.retries = self.rate_limits = 0

    def find_order_by_amazon_order_id(self, amazon_order_id: str) -> dict[str, Any] | None:
        for page in range(1, 7):
            candidates = normalize_order_list(self.list_orders({"query": amazon_order_id, "page_size": 25, "page": page}))
            for candidate in candidates:
                if order_matches_amazon_id(candidate, amazon_order_id):
                    detail = self.get_order(candidate["id"]) if candidate.get("id") else candidate
                    if order_matches_amazon_id(detail, amazon_order_id):
                        return detail
            if len(candidates) < 25:
                return None
        raise RuntimeError("Veeqo search pagination limit reached")

    def list_orders(self, params: dict[str, Any]) -> Any:
        return self.request("GET", "/orders", params=params)

    def get_order(self, order_id: Any) -> dict[str, Any]:
        payload = self.request("GET", f"/orders/{order_id}")
        if isinstance(payload, dict) and isinstance(payload.get("order"), dict):
            return payload["order"]
        return payload if isinstance(payload, dict) else {}

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{VEEQO_BASE_URL}{path}"
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "MBOP/0.1 (Language=Python)",
        }

        response: requests.Response | None = None
        for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
            self.api_calls += 1
            time.sleep(0.25)
            try:
                response = self.session.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            except requests.RequestException:
                if attempt == DEFAULT_MAX_ATTEMPTS:
                    raise RuntimeError("Veeqo transport failure") from None
                self.retries += 1
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 429:
                self.rate_limits += 1
            if response.ok:
                break
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt >= DEFAULT_MAX_ATTEMPTS:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else attempt * 2.0
            except ValueError:
                delay = attempt * 2.0
            LOGGER.warning(
                "Veeqo %s %s returned HTTP %s; retrying in %.1fs",
                method,
                path,
                response.status_code,
                delay,
            )
            self.retries += 1
            time.sleep(min(max(delay, 0), 60))

        if response is None:
            raise RuntimeError(f"Veeqo {method} {path} was not attempted")
        if not response.ok:
            raise RuntimeError(
                f"Veeqo request failed with HTTP {response.status_code}"
            )
        if not response.text.strip():
            return {}
        return response.json()


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")
    return create_client(supabase_url, supabase_key)


def load_pages(supabase, table, columns, configure=lambda q: q):
    rows = []
    for page in range(100):
        query = configure(supabase.table(table).select(columns)).order("amazon_order_id")
        stable_key = {"amazon_sales_order_items": "amazon_order_item_id", "veeqo_sales_orders": "veeqo_order_id",
                      "amazon_sales_financial_events": "financial_event_id", "amazon_sales_fulfillment_cost_overrides": "amazon_order_item_id"}.get(table)
        if stable_key:
            query = query.order(stable_key)
        batch = query.range(page * 100, page * 100 + 99).execute().data or []
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise RuntimeError("Database scan bound reached; queue is incomplete")


def load_mf_orders(supabase):
    return load_pages(supabase, "amazon_sales_orders",
        "amazon_order_id,purchase_date,order_status,fulfillment_channel,number_of_items_shipped",
        lambda q: q.in_("fulfillment_channel", ["MFN", "Merchant", "MerchantFulfilled"]).gte("purchase_date", MIN_PURCHASE_DATE))


def shipping_required(order):
    return str(order.get("order_status", "")).lower() in {
        "shipped", "partiallyshipped", "shipped - delivered to buyer", "delivered",
    }


def needs_reconciliation(order, by_order, profits, verified=None):
    order_id = order["amazon_order_id"]
    cost, _ = order_label_cost((by_order.get(order_id) or {}).get("raw_veeqo_order_json") or {})
    rows = profits.get(order_id) or []
    if verified is not None:
        total, source, overrides = verified[order_id]
        items = [{"amazon_order_item_id": r["amazon_order_item_id"], "quantity_ordered": r.get("quantity")} for r in rows]
        allocated = allocate_cost(total, items)
        for row in rows:
            iid = row["amazon_order_item_id"]
            override = overrides.get(iid)
            expected, expected_source = (fulfillment_cost_for_order(order, 0, None, None, override)
                                         if override else (allocated[iid], source))
            if expected is None or row.get("fulfillment_cost") is None or round(float(row["fulfillment_cost"]), 2) != expected or row.get("fulfillment_cost_source") != expected_source:
                return True
        return not rows
    if cost is None or not rows or any(r.get("fulfillment_cost") is None for r in rows):
        return True
    if all(r.get("fulfillment_cost_source") in {"veeqo_label", "amazon_shipping_label", "missing"} for r in rows):
        return round(sum(float(r["fulfillment_cost"]) for r in rows), 2) != cost or any(r.get("fulfillment_cost_source") != "veeqo_label" for r in rows)
    return False


def rotate_select(rows, limit, cursor):
    rows = sorted(rows, key=lambda o: o["amazon_order_id"])
    after = [o for o in rows if o["amazon_order_id"] > (cursor or "")]
    before = [o for o in rows if o["amazon_order_id"] <= (cursor or "")]
    selected = (after + before)[:limit]
    return selected, selected[-1]["amazon_order_id"] if selected else cursor


def select_work(orders, start, end, limit, backlog_limit, cursors):
    recent = [o for o in orders if (not start or o["purchase_date"] >= start) and (not end or o["purchase_date"] < end)]
    backlog = [o for o in orders if start and o["purchase_date"] < start]
    older, old_cursor = rotate_select(backlog, backlog_limit, cursors.get("backlog"))
    newer, new_cursor = rotate_select(recent, limit - len(older), cursors.get("recent"))
    if len(newer) + len(older) < limit:
        older, old_cursor = rotate_select(backlog, limit - len(newer), cursors.get("backlog"))
    return newer + older, {"recent": new_cursor, "backlog": old_cursor}


def recent_asin_orders(supabase, asin, units):
    items = load_pages(supabase, "amazon_sales_order_items", "amazon_order_id,quantity_shipped", lambda q: q.eq("asin", asin))
    quantities = Counter()
    for item in items:
        quantities[item["amazon_order_id"]] += int(item.get("quantity_shipped") or 0)
    orders = sorted((o for o in load_mf_orders(supabase) if o["amazon_order_id"] in quantities and shipping_required(o)),
                    key=lambda o: (o["purchase_date"], o["amazon_order_id"]), reverse=True)
    selected, count = [], 0
    for order in orders:
        if count >= units:
            break
        selected.append(order["amazon_order_id"])
        count += quantities[order["amazon_order_id"]]
    return selected


def preserve_cost_evidence(old, new):
    previous = {str(s.get("id") or s.get("shipment_id")): s for s in extract_shipments(old)}
    current = extract_shipments(new)
    for shipment in current:
        key = str(shipment.get("id") or shipment.get("shipment_id"))
        prior = previous.get(key)
        if prior and label_evidence(shipment, new.get("currency_code"))[0] is None and label_evidence(prior, old.get("currency_code"))[0] is not None:
            # Preserve amount evidence, but keep new void/refund/status flags for review.
            shipment["outbound_label_charges"] = prior["outbound_label_charges"]
            shipment["_mbop_preserved_charge"] = True
        previous[key] = shipment
    merged = dict(new)
    merged["shipments"] = list(previous.values())
    merged["currency_code"] = new.get("currency_code") or old.get("currency_code")
    return merged


def emit_summary(stats):
    print("METADATA_JSON: " + json.dumps({"shipping_reconciliation": stats}, sort_keys=True))
    for key, value in stats.items():
        if isinstance(value, int):
            print(f"{key.replace('_', ' ').title()}: {value}")


def notify_backlog(supabase, stats):
    key = "sales-shipping:unresolved"
    existing = supabase.table("mbop_notifications").select("notification_id,resolved_at").eq("dedupe_key", key).limit(1).execute().data or []
    now = datetime.now(timezone.utc).isoformat()
    problem = stats["unresolved_shipped_orders"] or stats["api_failures"] or stats["queue_status"] == "missing_credentials"
    if not problem:
        if existing:
            supabase.table("mbop_notifications").update({"resolved_at": now}).eq("dedupe_key", key).execute()
        return
    row = {"last_seen_at": now, "resolved_at": None, "message":
        f"Unresolved shipped orders: {stats['unresolved_shipped_orders']}; failures: {stats['api_failures']}; "
        f"oldest purchase: {stats['oldest_unresolved_purchase_date']}; state: {stats['queue_status']}"}
    if existing:
        # Preserve read_at: the same persistent backlog must not re-alert every run.
        if existing[0].get("resolved_at"):
            row["read_at"] = None
        supabase.table("mbop_notifications").update(row).eq("dedupe_key", key).execute()
    else:
        supabase.table("mbop_notifications").insert({**row, "dedupe_key": key, "category": "sales_shipping",
            "severity": "warning", "title": "Amazon shipping costs need reconciliation", "href": "/system-health"}).execute()


def normalize_order_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("orders", "data", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if payload.get("id"):
            return [payload]
    return []


def max_iso(left: str | None, right: str | None) -> str | None:
    values = [value for value in (left, right) if value]
    return max(values) if values else None


def order_matches_amazon_id(order: dict[str, Any], amazon_order_id: str) -> bool:
    searchable_values = [
        order.get("reference_number"),
        order.get("channel_order_id"),
        order.get("remote_order_id"),
        order.get("number"),
        order.get("id"),
    ]
    for key in ("additional_options", "metadata", "channel", "store"):
        nested = order.get(key)
        if isinstance(nested, dict):
            searchable_values.extend(nested.values())

    if any(str(value).strip() == amazon_order_id for value in searchable_values if value):
        return True

    return False


def build_veeqo_order_row(
    amazon_order_id: str,
    veeqo_order: dict[str, Any],
) -> dict[str, Any]:
    return {
        "veeqo_order_id": str(veeqo_order["id"]),
        "amazon_order_id": amazon_order_id,
        "status": clean_text(veeqo_order.get("status")),
        "channel": channel_name(veeqo_order),
        "raw_veeqo_order_json": veeqo_order,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_shipment_rows(
    amazon_order_id: str,
    veeqo_order: dict[str, Any],
) -> list[dict[str, Any]]:
    veeqo_order_id = str(veeqo_order["id"])
    shipments = extract_shipments(veeqo_order)
    rows: list[dict[str, Any]] = []
    for index, shipment in enumerate(shipments):
        shipment_id = shipment.get("id") or shipment.get("shipment_id") or f"{veeqo_order_id}-{index}"
        amount, reason = label_evidence(shipment, veeqo_order.get("currency_code"))
        label_cost = {"amount": amount, "currency": (shipment.get("outbound_label_charges") or {}).get("unit") or veeqo_order.get("currency_code"), "source_field": "outbound_label_charges" if amount is not None else None}
        tracking = shipment.get("tracking_number")
        if isinstance(tracking, dict):
            tracking_number = tracking.get("tracking_number")
        else:
            tracking_number = tracking

        rows.append(
            {
                "veeqo_shipment_id": str(shipment_id),
                "veeqo_order_id": veeqo_order_id,
                "amazon_order_id": amazon_order_id,
                "carrier": carrier_name(shipment),
                "service": clean_text(
                    shipment.get("service")
                    or shipment.get("service_type")
                    or shipment.get("service_name")
                ),
                "tracking_number": clean_text(tracking_number),
                "label_cost_amount": label_cost["amount"],
                "label_cost_currency": label_cost["currency"],
                "label_cost_source_field": label_cost["source_field"],
                "raw_veeqo_shipment_json": shipment,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows



def carrier_name(shipment: dict[str, Any]) -> str | None:
    carrier = shipment.get("carrier")
    if isinstance(carrier, dict):
        return clean_text(carrier.get("name") or carrier.get("display_name"))
    return clean_text(carrier or shipment.get("carrier_name") or shipment.get("service_carrier"))


def channel_name(order: dict[str, Any]) -> str | None:
    channel = order.get("channel") or order.get("store")
    if isinstance(channel, dict):
        return clean_text(channel.get("name") or channel.get("type"))
    return clean_text(channel)


def upsert_rows(supabase, table: str, rows: list[dict[str, Any]], on_conflict: str) -> None:
    usable_rows = [row for row in rows if row.get(on_conflict)]
    for index in range(0, len(usable_rows), BATCH_LIMIT):
        chunk = usable_rows[index : index + BATCH_LIMIT]
        supabase.table(table).upsert(chunk, on_conflict=on_conflict).execute()


def persist_shipments(supabase, order_id, rows):
    existing = supabase.table("veeqo_sales_shipments").select(
        "veeqo_shipment_id,label_cost_amount,label_cost_currency,label_cost_source_field"
    ).eq("amazon_order_id", order_id).execute().data or []
    by_id = {r["veeqo_shipment_id"]: r for r in existing}
    for row in rows:
        old = by_id.get(row["veeqo_shipment_id"])
        if row.get("label_cost_amount") is None and old and old.get("label_cost_amount") is not None:
            for key in ("label_cost_amount", "label_cost_currency", "label_cost_source_field"):
                row[key] = old[key]
    upsert_rows(supabase, "veeqo_sales_shipments", rows, "veeqo_shipment_id")


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None



if __name__ == "__main__":
    raise SystemExit(main())
