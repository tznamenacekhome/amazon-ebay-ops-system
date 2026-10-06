"""Build immutable Phase 3 wholesale opportunity evaluations from cached evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sourcing_common import get_supabase_client
from wholesale_economics import (
    EconomicsInput, FeeEvidence, evaluate_economics, informational_risk_signals,
    input_fingerprint, supplier_price_history,
)
from wholesale_repository import WholesaleRepository


def evaluate_product(repository: WholesaleRepository, supplier_product_id: str,
                     marketplace_id: str) -> dict[str, Any]:
    detail = repository.get_matching_detail(supplier_product_id, marketplace_id)
    product = detail.get("product")
    if not product:
        raise ValueError(f"Wholesale product not found: {supplier_product_id}")
    history = repository.observation_history(supplier_product_id)
    observation = history[-1] if history else None
    state = detail.get("match_state") or {}
    candidates = detail.get("candidates") or []
    selected = next((row for row in candidates if row.get("candidate_id") == state.get("selected_candidate_id")), None)
    opportunity = repository.ensure_opportunity(
        supplier_product_id, marketplace_id,
        selected.get("candidate_id") if selected else None,
        observation.get("observation_id") if observation else None,
    )

    base = {
        "opportunity_id": opportunity["opportunity_id"],
        "supplier_product_id": supplier_product_id,
        "candidate_id": selected.get("candidate_id") if selected else None,
        "observation_id": observation.get("observation_id") if observation else None,
        "marketplace_id": marketplace_id,
        "asin": selected.get("asin") if selected else None,
        "evaluator_version": "wholesale-economics-v1",
        "assumption_version": "video-games-2026-10-v1",
        "eligibility_status": selected.get("eligibility_status") if selected else None,
        "eligibility_checked_at": selected.get("eligibility_checked_at") if selected else None,
        "currency": (observation or {}).get("currency") or "USD",
        "evaluated_at": now_iso(),
    }
    if not selected:
        match_status = state.get("match_status")
        status = "restricted" if match_status == "restricted_no_eligible" else (
            "pending_eligibility" if match_status == "eligibility_pending" else "pending_matching"
        )
        row = {**base, "evaluation_status": status, "incomplete_reasons": [match_status or "match_unavailable"],
               "allowance_status": "complete", "qualification_basis": "incomplete",
               "is_financially_qualified": False, "risk_signals_json": {}, "source_evidence_json": {}}
        row["input_fingerprint"] = input_fingerprint(row)
        return repository.save_evaluation(opportunity, row)

    if selected.get("eligibility_status") != "eligible" or not eligibility_fresh(selected):
        row = {**base, "evaluation_status": "pending_eligibility",
               "incomplete_reasons": ["eligibility_not_fresh_and_eligible"],
               "allowance_status": "complete", "qualification_basis": "incomplete",
               "is_financially_qualified": False, "risk_signals_json": {}, "source_evidence_json": {}}
        row["input_fingerprint"] = input_fingerprint(row)
        return repository.save_evaluation(opportunity, row)

    asin = selected["asin"]
    keepa = repository.latest_keepa_snapshot(asin) or {}
    raw_keepa = keepa.get("raw_keepa_json") if isinstance(keepa.get("raw_keepa_json"), dict) else {}
    stats = raw_keepa.get("stats") if isinstance(raw_keepa.get("stats"), dict) else {}
    current_context = keepa_current_price_context(keepa)
    current_price = current_context["price"]
    avg30_price = money_from_cents(keepa.get("buy_box_price_avg30_cents"))
    avg90_price = money_from_cents(keepa.get("buy_box_price_avg90_cents"))
    current_fee_row = repository.fee_estimate(asin, marketplace_id, float(current_price) if current_price else None)
    avg90_fee_row = repository.fee_estimate(asin, marketplace_id, float(avg90_price) if avg90_price else None)
    inventory = repository.inventory_exposure(asin, marketplace_id)
    draft_units = repository.active_draft_units(supplier_product_id, marketplace_id)
    is_accessory = bool((selected.get("compatibility_details") or {}).get("supplier_accessory"))
    economics_input = EconomicsInput(
        supplier_cost=decimal_or_none((observation or {}).get("supplier_price")),
        current_buy_box=current_price,
        keepa_avg90=avg90_price,
        current_fees=fee_evidence(current_fee_row),
        avg90_fees=fee_evidence(avg90_fee_row),
        is_accessory=is_accessory,
        sales_rank_drops90=integer_or_none(keepa.get("sales_rank_drops90")),
        fba_fulfillable_units=inventory["fba_fulfillable_units"],
        inbound_units=inventory["inbound_units"],
        draft_commitment_units=draft_units,
    )
    economics = evaluate_economics(economics_input)
    supplier_history = supplier_price_history(history)
    offer_count = integer_or_none(keepa.get("offer_count_current"))
    fba_count = integer_or_none(stats.get("offerCountFBA"))
    risks = informational_risk_signals(
        current_price=current_price, avg30_price=avg30_price, avg90_price=avg90_price,
        supplier_change_30d=supplier_history["change_30d"],
        offer_count_current=offer_count, fba_seller_count=fba_count,
    )
    catalog = repository.catalog_snapshots([asin]).get(asin) or {}
    relevant = catalog.get("relevant_attributes_json") if isinstance(catalog.get("relevant_attributes_json"), dict) else {}
    source_evidence = {
        "amazon_title": relevant.get("title"),
        "amazon_platform": catalog.get("normalized_platform"),
        "amazon_product_type": catalog.get("product_type"),
        "image_url": first_image_url(catalog.get("raw_catalog_json")),
        "keepa_captured_at": keepa.get("captured_at"),
        "buy_box_is_fba": keepa_boolean(stats.get("buyBoxIsFBA")),
        "current_price_source": current_context["source"],
        "current_price_fulfillment": current_context["fulfillment"],
        "current_price_is_buy_box": current_context["is_buy_box"],
        "current_price_label": current_context["label"],
        "fee_current_requested_at": (current_fee_row or {}).get("requested_at"),
        "fee_avg90_requested_at": (avg90_fee_row or {}).get("requested_at"),
        "fba_seller_count_note": "Keepa stats.offerCountFBA; live retrieved offers may be incomplete" if fba_count is not None else None,
    }
    payload_for_fingerprint = {
        "supplier_product_id": supplier_product_id, "candidate_id": selected["candidate_id"],
        "observation_id": base["observation_id"], "eligibility_checked_at": base["eligibility_checked_at"],
        "supplier_cost": str(economics_input.supplier_cost), "current_price": str(current_price),
        "avg90_price": str(avg90_price), "current_fee": fee_summary(current_fee_row), "avg90_fee": fee_summary(avg90_fee_row),
        "keepa_captured_at": keepa.get("captured_at"), "inventory": inventory,
        "draft_units": draft_units, "risks": risks,
    }
    row = {
        **base,
        "input_fingerprint": input_fingerprint(payload_for_fingerprint),
        "evaluation_status": "complete" if economics["qualification_basis"] != "incomplete" else "incomplete",
        "incomplete_reasons": economics["incomplete_reasons"],
        "supplier_unit_cost": json_value(economics_input.supplier_cost),
        "current_buy_box_price": json_value(current_price),
        "keepa_avg30_price": json_value(avg30_price),
        "keepa_avg90_price": json_value(avg90_price),
        "keepa_captured_at": keepa.get("captured_at"),
        "current_total_amazon_fees": money_value(current_fee_row, "total_fees_estimate"),
        "current_referral_fee": money_value(current_fee_row, "referral_fee_estimate"),
        "current_fba_fee": money_value(current_fee_row, "fba_fee_estimate"),
        "avg90_total_amazon_fees": money_value(avg90_fee_row, "total_fees_estimate"),
        "avg90_referral_fee": money_value(avg90_fee_row, "referral_fee_estimate"),
        "avg90_fba_fee": money_value(avg90_fee_row, "fba_fee_estimate"),
        "fee_evidence_json": {"current": fee_summary(current_fee_row), "avg90": fee_summary(avg90_fee_row)},
        "inbound_allowance": json_value(economics["inbound_allowance"]),
        "return_allowance": json_value(economics["return_allowance"]),
        "storage_allowance": json_value(economics["storage_allowance"]),
        "allowance_status": economics["allowance_status"],
        "current_true_profit": json_value(economics["current"]["profit"]),
        "current_true_roi": json_value(economics["current"]["roi"]),
        "avg90_true_profit": json_value(economics["avg90"]["profit"]),
        "avg90_true_roi": json_value(economics["avg90"]["roi"]),
        "qualification_basis": economics["qualification_basis"],
        "is_financially_qualified": economics["is_financially_qualified"],
        "current_roi_floor_price": json_value(economics["current"]["floor"]),
        "avg90_roi_floor_price": json_value(economics["avg90"]["floor"]),
        "current_price_headroom": json_value(economics["current_price_headroom"]),
        "keepa_sales_rank_drops90": economics_input.sales_rank_drops90,
        "expected_monthly_sales": json_value(economics["expected_monthly_sales"]),
        "fba_fulfillable_units": inventory["fba_fulfillable_units"],
        "inbound_units": inventory["inbound_units"],
        "draft_commitment_units": draft_units,
        "target_units": json_value(economics["target_units"]),
        "purchase_capacity": json_value(economics["purchase_capacity"]),
        "supplier_availability_raw": (observation or {}).get("availability_raw"),
        "supplier_availability_min": (observation or {}).get("availability_min"),
        "supplier_availability_is_exact": (observation or {}).get("availability_is_exact"),
        "previous_supplier_price": json_value(supplier_history["previous"]),
        "supplier_price_30d": json_value(supplier_history["price_30d"]),
        "supplier_price_90d": json_value(supplier_history["price_90d"]),
        "supplier_historical_low": json_value(supplier_history["historical_low"]),
        "supplier_price_change_30d": json_value(supplier_history["change_30d"]),
        "supplier_price_change_90d": json_value(supplier_history["change_90d"]),
        "amazon_price_change_30d": json_value(risks["amazon_price_change_30d"]),
        "amazon_price_change_90d": json_value(risks["amazon_price_change_90d"]),
        "offer_count_current": offer_count,
        "fba_seller_count": fba_count,
        "risk_signals_json": json_safe(risks),
        "source_evidence_json": source_evidence,
    }
    return repository.save_evaluation(opportunity, row)


def fee_evidence(row: dict | None) -> FeeEvidence | None:
    if not row:
        return None
    return FeeEvidence(decimal_or_none(row.get("total_fees_estimate")),
                       decimal_or_none(row.get("referral_fee_estimate")),
                       decimal_or_none(row.get("fba_fee_estimate")), row.get("requested_at"))


def fee_summary(row: dict | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = ("amazon_fee_estimate_id", "asin", "marketplace_id", "listing_price",
            "total_fees_estimate", "referral_fee_estimate", "fba_fee_estimate",
            "variable_closing_fee_estimate", "estimate_status", "requested_at", "updated_at")
    return {key: row.get(key) for key in keys}


def eligibility_fresh(candidate: dict) -> bool:
    value = candidate.get("eligibility_expires_at")
    if not value:
        return False
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed > dt.datetime.now(dt.UTC)


def money_from_cents(value: Any) -> Decimal | None:
    integer = integer_or_none(value)
    return Decimal(integer) / Decimal(100) if integer is not None and integer >= 0 else None


def decimal_or_none(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def integer_or_none(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def keepa_boolean(value: Any) -> bool | None:
    if isinstance(value, list) and value:
        value = value[-1]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        if value.strip().lower() in {"true", "1", "yes"}:
            return True
        if value.strip().lower() in {"false", "0", "no"}:
            return False
    return None


def keepa_current_price_context(keepa: dict[str, Any]) -> dict[str, Any]:
    raw = keepa.get("raw_keepa_json") if isinstance(keepa.get("raw_keepa_json"), dict) else {}
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    buy_box_is_used = keepa_boolean(stats.get("buyBoxIsUsed"))
    buy_box_is_fba = keepa_boolean(stats.get("buyBoxIsFBA"))
    buy_box = None if buy_box_is_used is True else money_from_cents(keepa.get("buy_box_price_current_cents"))
    low_fba = money_from_cents(keepa.get("new_fba_price_current_cents")) or lowest_live_new_offer_price(raw, True)
    low_mf = keepa_stat_money(stats, "current", 7) or lowest_live_new_offer_price(raw, False)
    low_new = money_from_cents(keepa.get("new_price_current_cents"))
    used = keepa_stat_money(stats, "current", 2)
    if buy_box is not None:
        fulfillment = "fba" if buy_box_is_fba is True else "mf" if buy_box_is_fba is False else None
        return {"price": buy_box, "source": "buy_box", "label": "Buy Box",
                "fulfillment": fulfillment, "is_buy_box": True}
    if low_fba is not None:
        return {"price": low_fba, "source": "fba", "label": "Low FBA New",
                "fulfillment": "fba", "is_buy_box": False}
    if low_mf is not None:
        return {"price": low_mf, "source": "mf", "label": "Low MF New",
                "fulfillment": "mf", "is_buy_box": False}
    if low_new is not None:
        return {"price": low_new, "source": "new", "label": "Low New",
                "fulfillment": None, "is_buy_box": False}
    used_only = used is not None or buy_box_is_used is True
    return {"price": None, "source": "used_only" if used_only else "no_data",
            "label": "Used Only" if used_only else "No Data", "fulfillment": None,
            "is_buy_box": False}


def keepa_stat_money(stats: dict[str, Any], period: str, index: int) -> Decimal | None:
    values = stats.get(period)
    if not isinstance(values, list) or index >= len(values):
        return None
    return money_from_cents(values[index])


def lowest_live_new_offer_price(raw_keepa: dict[str, Any], is_fba: bool) -> Decimal | None:
    prices: list[Decimal] = []
    for value in raw_keepa.get("offers") or []:
        if not isinstance(value, dict) or integer_or_none(value.get("condition")) != 1:
            continue
        if keepa_boolean(value.get("isFBA")) is not is_fba or value.get("isShippable") is False:
            continue
        history = value.get("offerCSV")
        if not isinstance(history, list) or len(history) < 3:
            continue
        price = money_from_cents(history[-2])
        shipping = money_from_cents(history[-1])
        if price is not None and shipping is not None:
            prices.append(price + shipping)
    return min(prices) if prices else None


def money_value(row: dict | None, key: str) -> float | None:
    return json_value(decimal_or_none((row or {}).get(key)))


def json_value(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def first_image_url(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for group in payload.get("images") or []:
        if not isinstance(group, dict):
            continue
        for image in group.get("images") or []:
            if isinstance(image, dict) and image.get("link"):
                return str(image["link"])
    return None


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate cached wholesale opportunity economics")
    parser.add_argument("--product-id", action="append", default=[])
    parser.add_argument("--supplier-id")
    parser.add_argument("--pending", action="store_true", help="Evaluate persistently requested opportunities")
    parser.add_argument("--marketplace-id", default="ATVPDKIKX0DER")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    repository = WholesaleRepository(get_supabase_client())
    product_ids = args.product_id[:args.limit]
    if args.pending:
        product_ids.extend(product_id for product_id in repository.pending_evaluation_product_ids(
            args.marketplace_id, args.limit
        ) if product_id not in product_ids)
    if args.supplier_id:
        product_ids.extend(row["supplier_product_id"] for row in repository.list_products(
            args.supplier_id, limit=args.limit, present_only=True
        ) if row["supplier_product_id"] not in product_ids)
    if not product_ids:
        if args.pending:
            print('{"status":"idle","reason":"no_pending_evaluations"}')
            return 0
        parser.error("provide --product-id, --supplier-id, or --pending")
    for product_id in product_ids[:args.limit]:
        result = evaluate_product(repository, product_id, args.marketplace_id)
        evaluation = result["evaluation"]
        print(json.dumps({"supplier_product_id": product_id,
                          "status": evaluation["evaluation_status"],
                          "qualification": evaluation["qualification_basis"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
