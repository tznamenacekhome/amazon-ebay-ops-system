"""Cache Amazon Product Fees estimates for FBA prep pricing.

This integration is read-only against Amazon SP-API and writes normalized fee
estimates to Supabase. It intentionally runs on demand or as a small targeted
job because Product Fees v0 is rate-limited and fees vary by listing price.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from supabase import create_client

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError
from wholesale_evaluate_opportunities import keepa_current_price_context
from wholesale_repository import request_wholesale_evaluation_for_asins

LOGGER = logging.getLogger("amazon_fee_estimates")
DEFAULT_MARKETPLACE_ID = "ATVPDKIKX0DER"


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(".env")
    load_dotenv(".env.local")

    try:
        supabase = get_supabase_client()
        client = AmazonSPAPIClient.from_env()
        selected = collect_price_requests(supabase, args)
        if args.missing_only:
            selected = exclude_cached_requests(supabase, selected)
        if args.limit is not None:
            selected = selected[: args.limit]

        print("Amazon fee estimate sync")
        print("------------------------")
        print(f"Selected price points: {len(selected)}")
        if not selected:
            return 0

        if args.plan_only:
            for row in selected[:10]:
                print(f"- {row['asin']} ${row['listing_price']:.2f}")
            return 0

        rows: list[dict[str, Any]] = []
        failures = 0
        requested_at = utc_now_iso()

        for index, request_row in enumerate(selected):
            if index > 0 and args.delay_seconds > 0:
                time.sleep(args.delay_seconds)

            try:
                payload = client.get_my_fees_estimate_for_asin(
                    request_row["asin"],
                    listing_price=request_row["listing_price"],
                    shipping_price=request_row["shipping_price"],
                    currency=request_row["currency"],
                    is_amazon_fulfilled=True,
                )
                rows.append(
                    build_fee_estimate_row(
                        payload=payload,
                        request_row=request_row,
                        marketplace_id=client.config.marketplace_id,
                        requested_at=requested_at,
                    )
                )
            except AmazonSPAPIError as error:
                failures += 1
                LOGGER.warning("Fee estimate failed for %s: %s", request_row["asin"], error)
                rows.append(
                    {
                        **request_row,
                        "marketplace_id": client.config.marketplace_id,
                        "fulfillment_channel": "AFN",
                        "estimate_status": "error",
                        "status_message": str(error)[:500],
                        "requested_at": requested_at,
                        "updated_at": requested_at,
                    }
                )

        if rows:
            response = (
                supabase.table("amazon_fee_estimates")
                .upsert(
                    rows,
                    on_conflict=(
                        "asin,marketplace_id,fulfillment_channel,"
                        "listing_price,shipping_price,currency"
                    ),
                )
                .execute()
            )
            LOGGER.info("Upserted fee estimate rows: %s", len(response.data or rows))
            reevaluation_count = request_wholesale_evaluation_for_asins(
                supabase, [row.get("asin") for row in rows]
            )
            LOGGER.info("Wholesale reevaluations requested: %s", reevaluation_count)

        print(f"Cached fee estimates: {len(rows)}")
        print(f"Failures: {failures}")
        for row in rows[:10]:
            print(
                f"- {row['asin']} ${row['listing_price']:.2f} "
                f"fees={row.get('total_fees_estimate')} status={row['estimate_status']}"
            )
        return 0 if failures == 0 else 1
    except Exception as error:  # noqa: BLE001 - integration guard
        LOGGER.exception("Amazon fee estimate sync failed safely: %s", error)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache Amazon Product Fees estimates.")
    parser.add_argument("--asin", action="append", default=[], help="ASIN to refresh.")
    parser.add_argument(
        "--source",
        choices=["received_fba_prep", "wholesale_selected", "explicit"],
        default="received_fba_prep",
    )
    parser.add_argument("--listing-price", type=float, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--missing-only", action="store_true",
                        help="Skip exact ASIN/price points already cached successfully.")
    parser.add_argument("--delay-seconds", type=float, default=1.1)
    return parser.parse_args()


def collect_price_requests(supabase, args: argparse.Namespace) -> list[dict[str, Any]]:
    requests: dict[tuple[str, float], dict[str, Any]] = {}

    if args.source == "received_fba_prep":
        for row in fetch_all(
            supabase,
            "purchase_items",
            "item_id,asin,target_price,current_status,marketplace,exclude_from_purchase_reporting",
        ):
            asin = clean_asin(row.get("asin"))
            price = to_float(row.get("target_price"))
            if (
                not asin
                or price is None
                or price <= 0
                or clean_text(row.get("current_status")) != "received"
                or clean_text(row.get("marketplace")) == "ebay"
                or row.get("exclude_from_purchase_reporting") is True
            ):
                continue
            requests[(asin, round(price, 2))] = fee_request(asin, price)

    if args.source == "wholesale_selected":
        states = fetch_all(
            supabase, "wholesale_match_states",
            "selected_candidate_id,match_status",
        )
        candidate_ids = [row["selected_candidate_id"] for row in states
                         if row.get("match_status") == "matched" and row.get("selected_candidate_id")]
        candidates: list[dict[str, Any]] = []
        for index in range(0, len(candidate_ids), 200):
            response = (supabase.table("wholesale_amazon_candidates").select("candidate_id,asin,eligibility_status")
                        .in_("candidate_id", candidate_ids[index:index + 200]).execute())
            candidates.extend(response.data or [])
        asins = sorted({clean_asin(row.get("asin")) for row in candidates
                        if row.get("eligibility_status") == "eligible" and clean_asin(row.get("asin"))})
        for index in range(0, len(asins), 200):
            response = (supabase.table("vw_latest_keepa_product_snapshot")
                        .select("asin,captured_at,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,keepa_stats:raw_keepa_json->stats")
                        .in_("asin", asins[index:index + 200]).eq("domain_id", 1).execute())
            for row in response.data or []:
                asin = clean_asin(row.get("asin"))
                if not asin:
                    continue
                price_row = {**row, "raw_keepa_json": {"stats": row.get("keepa_stats") or {}}}
                current_price = keepa_current_price_context(price_row)["price"]
                avg90_cents = to_float(row.get("buy_box_price_avg90_cents"))
                price_points = [to_float(current_price), avg90_cents / 100 if avg90_cents is not None else None]
                for price in price_points:
                    if price is None or price <= 0:
                        continue
                    dollars = round(price, 2)
                    requests[(asin, dollars)] = fee_request(asin, dollars)

        for row in fetch_all(
            supabase,
            "amazon_return_recovery_cases",
            "amazon_return_recovery_case_id,asin,target_price,workflow_state,decision",
        ):
            asin = clean_asin(row.get("asin"))
            price = to_float(row.get("target_price"))
            if (
                not asin
                or price is None
                or price <= 0
                or clean_text(row.get("workflow_state")) != "ready_to_send_back_to_amazon"
                or clean_text(row.get("decision")) != "send_back_to_amazon"
            ):
                continue
            requests[(asin, round(price, 2))] = fee_request(asin, price)

    for asin_value in args.asin:
        asin = clean_asin(asin_value)
        if not asin:
            continue
        price = args.listing_price
        if price is None:
            price = latest_received_target_price(supabase, asin)
        if price is None or price <= 0:
            LOGGER.warning("Skipping %s because no listing price was available.", asin)
            continue
        requests[(asin, round(price, 2))] = fee_request(asin, price)

    return sorted(requests.values(), key=lambda row: (row["asin"], row["listing_price"]))


def fee_request(asin: str, price: float) -> dict[str, Any]:
    return {
        "asin": asin,
        "listing_price": round(float(price), 2),
        "shipping_price": 0.0,
        "currency": "USD",
    }


def exclude_cached_requests(supabase, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asins = sorted({row["asin"] for row in requests})
    cached: set[tuple[str, float]] = set()
    for index in range(0, len(asins), 200):
        response = (supabase.table("amazon_fee_estimates")
                    .select("asin,listing_price,estimate_status,fulfillment_channel,shipping_price,currency")
                    .in_("asin", asins[index:index + 200]).execute())
        for row in response.data or []:
            if (row.get("estimate_status") == "ok" and row.get("fulfillment_channel") == "AFN"
                    and to_float(row.get("shipping_price")) == 0
                    and row.get("currency") == "USD"):
                cached.add((clean_asin(row.get("asin")) or "", round(to_float(row.get("listing_price")) or 0, 2)))
    return [row for row in requests if (row["asin"], round(row["listing_price"], 2)) not in cached]


def latest_received_target_price(supabase, asin: str) -> float | None:
    response = (
        supabase.table("purchase_items")
        .select("target_price,created_at")
        .eq("asin", asin)
        .eq("current_status", "received")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return to_float(rows[0].get("target_price")) if rows else None


def build_fee_estimate_row(
    *,
    payload: dict[str, Any],
    request_row: dict[str, Any],
    marketplace_id: str,
    requested_at: str,
) -> dict[str, Any]:
    result = payload.get("payload") or payload
    result = result.get("FeesEstimateResult") if isinstance(result, dict) else None
    result = result if isinstance(result, dict) else {}
    estimate = result.get("FeesEstimate") if isinstance(result.get("FeesEstimate"), dict) else {}
    status = result.get("Status") or "Success"
    fees = estimate.get("FeeDetailList") if isinstance(estimate.get("FeeDetailList"), list) else []

    return {
        **request_row,
        "marketplace_id": marketplace_id or DEFAULT_MARKETPLACE_ID,
        "fulfillment_channel": "AFN",
        "total_fees_estimate": money_amount(estimate.get("TotalFeesEstimate")),
        "referral_fee_estimate": fee_amount(fees, "ReferralFee"),
        "fba_fee_estimate": fee_amount(fees, "FBAFees"),
        "variable_closing_fee_estimate": fee_amount(fees, "VariableClosingFee"),
        "fee_breakdown_json": fees,
        "raw_fee_estimate_json": payload,
        "estimate_status": "ok" if str(status).lower() == "success" else "not_available",
        "status_message": result.get("Error", {}).get("Message")
        if isinstance(result.get("Error"), dict)
        else None,
        "requested_at": requested_at,
        "updated_at": requested_at,
    }


def fee_amount(fees: list[dict[str, Any]], fee_type: str) -> float | None:
    for fee in fees:
        if clean_text(fee.get("FeeType")) == clean_text(fee_type):
            return money_amount(fee.get("FinalFee"))
    return None


def money_amount(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    amount = to_float(value.get("Amount"))
    return round(amount, 2) if amount is not None else None


def fetch_all(supabase, table: str, select: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        response = (
            supabase.table(table)
            .select(select)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        data = response.data or []
        rows.extend(data)
        if len(data) < page_size:
            return rows
        offset += page_size


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(supabase_url, supabase_key)


def clean_asin(value: Any) -> str | None:
    cleaned = str(value or "").strip().upper()
    return cleaned or None


def clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
