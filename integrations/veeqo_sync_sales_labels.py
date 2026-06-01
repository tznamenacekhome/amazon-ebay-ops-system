"""Sync Veeqo label costs for Merchant Fulfilled Amazon sales orders.

This integration reads Veeqo order/shipment data and writes only Veeqo-specific
sales tables. It does not buy labels, create shipments, or update remote orders.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from supabase import create_client
import requests

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
    load_dotenv()

    api_key = (
        os.getenv("VEEQO_KEY")
        or os.getenv("VEEQO_API_KEY")
        or os.getenv("VEEQO_ACCESS_TOKEN")
    )
    if not api_key:
        LOGGER.warning(
            "Skipping Veeqo label sync for %s because no Veeqo API key is configured.",
            args.amazon_order_id or "eligible MF orders",
        )
        print("Veeqo label sync skipped: VEEQO_KEY is not configured.")
        return 0

    try:
        client = VeeqoClient(api_key)
        supabase = get_supabase_client()
        amazon_order_ids = (
            [args.amazon_order_id]
            if args.amazon_order_id
            else fetch_mf_order_ids(
                supabase,
                limit=args.limit,
                purchase_date_start=args.purchase_date_start,
                purchase_date_end=args.purchase_date_end,
                missing_only=args.missing_only,
            )
        )
        veeqo_order_rows: list[dict[str, Any]] = []
        shipment_rows: list[dict[str, Any]] = []
        missing_matches: list[str] = []

        for amazon_order_id in amazon_order_ids:
            veeqo_order = client.find_order_by_amazon_order_id(amazon_order_id)
            if not veeqo_order:
                missing_matches.append(amazon_order_id)
                continue

            veeqo_order_rows.append(build_veeqo_order_row(amazon_order_id, veeqo_order))
            shipment_rows.extend(build_shipment_rows(amazon_order_id, veeqo_order))

        print_summary(
            amazon_order_ids,
            veeqo_order_rows,
            shipment_rows,
            missing_matches,
            apply=args.apply,
        )

        if not args.apply:
            LOGGER.info("Dry run complete. No Supabase writes performed.")
            return 0

        upsert_rows(supabase, "veeqo_sales_orders", veeqo_order_rows, "veeqo_order_id")
        upsert_rows(
            supabase,
            "veeqo_sales_shipments",
            shipment_rows,
            "veeqo_shipment_id",
        )
        LOGGER.info(
            "Veeqo sales label sync complete. orders=%s shipments=%s missing=%s",
            len(veeqo_order_rows),
            len(shipment_rows),
            len(missing_matches),
        )
        return 0
    except Exception as error:  # noqa: BLE001 - top-level integration guard
        LOGGER.exception("Veeqo sales label sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Veeqo label costs for Amazon MF sales orders."
    )
    parser.add_argument("--amazon-order-id", help="Target one Amazon order ID.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum MF Amazon sales orders to process. Defaults to 100 for recent-order mode.",
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
        help="Only process MF orders that do not already have a Veeqo order row.",
    )
    parser.add_argument("--apply", action="store_true", help="Write to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Dry run; default mode.")
    return parser.parse_args()


class VeeqoClient:
    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()

    def find_order_by_amazon_order_id(self, amazon_order_id: str) -> dict[str, Any] | None:
        rows = self.list_orders(
            {
                "query": amazon_order_id,
                "page_size": 25,
                "page": 1,
            }
        )
        candidates = normalize_order_list(rows)
        for candidate in candidates:
            if order_matches_amazon_id(candidate, amazon_order_id):
                order_id = candidate.get("id")
                return self.get_order(order_id) if order_id else candidate

        if len(candidates) == 1 and candidates[0].get("id"):
            detail = self.get_order(candidates[0]["id"])
            if order_matches_amazon_id(detail, amazon_order_id):
                return detail

        return None

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
            response = self.session.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
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
            time.sleep(delay)

        if response is None:
            raise RuntimeError(f"Veeqo {method} {path} was not attempted")
        if not response.ok:
            raise RuntimeError(
                f"Veeqo {method} {path} failed with HTTP {response.status_code}: "
                f"{response.text[:1000]}"
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


def fetch_mf_order_ids(
    supabase,
    *,
    limit: int | None,
    purchase_date_start: str | None,
    purchase_date_end: str | None,
    missing_only: bool,
) -> list[str]:
    request = (
        supabase.table("amazon_sales_orders")
        .select("amazon_order_id")
        .in_("fulfillment_channel", ["MFN", "Merchant", "MerchantFulfilled"])
    )
    effective_start = max_iso(purchase_date_start, MIN_PURCHASE_DATE)
    if effective_start:
        request = request.gte("purchase_date", effective_start)
    if purchase_date_end:
        request = request.lt("purchase_date", purchase_date_end)
    if purchase_date_start or purchase_date_end:
        request = request.order("purchase_date", desc=False)
        if limit:
            request = request.limit(max(limit, 1))
    else:
        request = request.order("purchase_date", desc=True).limit(max(limit or 100, 1))
    result = request.execute()
    order_ids = [row["amazon_order_id"] for row in result.data or [] if row.get("amazon_order_id")]
    if missing_only and order_ids:
        existing_result = (
            supabase.table("veeqo_sales_orders")
            .select("amazon_order_id")
            .in_("amazon_order_id", order_ids)
            .execute()
        )
        existing_ids = {
            row["amazon_order_id"]
            for row in existing_result.data or []
            if row.get("amazon_order_id")
        }
        order_ids = [order_id for order_id in order_ids if order_id not in existing_ids]
    return order_ids


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

    raw_text = str(order)
    return amazon_order_id in raw_text


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
        label_cost = extract_label_cost(shipment)
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
            }
        )
    return rows


def extract_shipments(order: dict[str, Any]) -> list[dict[str, Any]]:
    shipments: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("outbound_label_charges") or value.get("tracking_number"):
                shipments.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for key in ("allocations", "shipments"):
        visit(order.get(key))

    seen: set[str] = set()
    unique_shipments: list[dict[str, Any]] = []
    for index, shipment in enumerate(shipments):
        key = str(shipment.get("id") or shipment.get("shipment_id") or index)
        if key in seen:
            continue
        seen.add(key)
        unique_shipments.append(shipment)
    return unique_shipments


def extract_label_cost(shipment: dict[str, Any]) -> dict[str, Any]:
    for field in ("outbound_label_charges", "label_cost", "charge", "cost"):
        charge = shipment.get(field)
        if isinstance(charge, dict):
            amount = to_float(
                charge.get("value")
                or charge.get("amount")
                or charge.get("CurrencyAmount")
            )
            currency = clean_text(
                charge.get("unit")
                or charge.get("currency")
                or charge.get("CurrencyCode")
            )
            if amount is not None:
                return {
                    "amount": round(amount, 2),
                    "currency": currency,
                    "source_field": field,
                }
        else:
            amount = to_float(charge)
            if amount is not None:
                return {
                    "amount": round(amount, 2),
                    "currency": None,
                    "source_field": field,
                }

    return {"amount": None, "currency": None, "source_field": None}


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


def print_summary(
    amazon_order_ids: list[str],
    veeqo_order_rows: list[dict[str, Any]],
    shipment_rows: list[dict[str, Any]],
    missing_matches: list[str],
    *,
    apply: bool,
) -> None:
    mode = "write" if apply else "dry run"
    print(f"Veeqo sales label {mode}")
    print("----------------------")
    print(f"Amazon orders checked: {len(amazon_order_ids)}")
    print(f"Veeqo orders matched: {len(veeqo_order_rows)}")
    print(f"Shipments found: {len(shipment_rows)}")
    print(f"Missing Veeqo matches: {len(missing_matches)}")
    for row in shipment_rows[:10]:
        print(
            f"- order={row['amazon_order_id']} shipment={row['veeqo_shipment_id']} "
            f"label={row.get('label_cost_amount')} {row.get('label_cost_currency') or ''} "
            f"tracking={row.get('tracking_number') or '--'}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
