"""Versioned, deterministic economics for wholesale opportunity evaluation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


EVALUATOR_VERSION = "wholesale-economics-v1"
ASSUMPTION_VERSION = "video-games-2026-10-v1"
ROI_HURDLE = Decimal("0.25")
GAME_INBOUND_ALLOWANCE = Decimal("0.3839")
GAME_RETURN_ALLOWANCE = Decimal("0.21")
GAME_STORAGE_30D_ALLOWANCE = Decimal("0.0153")


@dataclass(frozen=True)
class FeeEvidence:
    total: Decimal | None
    referral: Decimal | None
    fba: Decimal | None
    requested_at: str | None = None


@dataclass(frozen=True)
class EconomicsInput:
    supplier_cost: Decimal | None
    current_buy_box: Decimal | None
    keepa_avg90: Decimal | None
    current_fees: FeeEvidence | None
    avg90_fees: FeeEvidence | None
    is_accessory: bool
    sales_rank_drops90: int | None
    fba_fulfillable_units: int = 0
    inbound_units: int = 0
    draft_commitment_units: int = 0


def evaluate_economics(values: EconomicsInput) -> dict[str, Any]:
    incomplete: list[str] = []
    if values.supplier_cost is None or values.supplier_cost <= 0:
        incomplete.append("supplier_cost_unavailable")
    if values.is_accessory:
        allowances = None
        incomplete.append("accessory_allowances_require_review")
        inbound = returns = storage = None
        allowance_status = "accessory_review_required"
    else:
        inbound, returns, storage = (
            GAME_INBOUND_ALLOWANCE, GAME_RETURN_ALLOWANCE, GAME_STORAGE_30D_ALLOWANCE,
        )
        allowances = inbound + returns + storage
        allowance_status = "complete"

    current = price_case(values.current_buy_box, values.current_fees, values.supplier_cost, allowances)
    avg90 = price_case(values.keepa_avg90, values.avg90_fees, values.supplier_cost, allowances)
    if values.current_buy_box is None:
        incomplete.append("current_buy_box_unavailable")
    elif not current["complete"]:
        incomplete.append("current_fee_estimate_unavailable")
    if values.keepa_avg90 is None:
        incomplete.append("keepa_avg90_unavailable")
    elif not avg90["complete"]:
        incomplete.append("avg90_fee_estimate_unavailable")

    current_qualifies = bool(current["roi"] is not None and current["roi"] >= ROI_HURDLE)
    avg90_qualifies = bool(avg90["roi"] is not None and avg90["roi"] >= ROI_HURDLE)
    if current_qualifies and avg90_qualifies:
        basis = "both"
    elif current_qualifies:
        basis = "current_only"
    elif avg90_qualifies:
        basis = "avg90_only"
    elif current["roi"] is not None and avg90["roi"] is not None:
        basis = "neither"
    else:
        basis = "incomplete"

    monthly_sales = (
        quantize(Decimal(values.sales_rank_drops90) / Decimal(3), "0.0001")
        if values.sales_rank_drops90 is not None else None
    )
    exposure = max(values.fba_fulfillable_units, 0) + max(values.inbound_units, 0) + max(values.draft_commitment_units, 0)
    capacity = max(monthly_sales - Decimal(exposure), Decimal(0)) if monthly_sales is not None else None
    headroom = None
    if values.current_buy_box and current["floor"] is not None and values.current_buy_box > 0:
        headroom = quantize((values.current_buy_box - current["floor"]) / values.current_buy_box, "0.00000001")

    return {
        "evaluator_version": EVALUATOR_VERSION,
        "assumption_version": ASSUMPTION_VERSION,
        "incomplete_reasons": list(dict.fromkeys(incomplete)),
        "allowance_status": allowance_status,
        "inbound_allowance": inbound,
        "return_allowance": returns,
        "storage_allowance": storage,
        "current": current,
        "avg90": avg90,
        "qualification_basis": basis,
        "is_financially_qualified": current_qualifies or avg90_qualifies,
        "expected_monthly_sales": monthly_sales,
        "target_units": monthly_sales,
        "purchase_capacity": quantize(capacity, "0.0001") if capacity is not None else None,
        "current_price_headroom": headroom,
        "exposure_units": exposure,
    }


def price_case(price: Decimal | None, fees: FeeEvidence | None,
               supplier_cost: Decimal | None, allowances: Decimal | None) -> dict[str, Any]:
    if price is None or price <= 0 or supplier_cost is None or supplier_cost <= 0 or allowances is None:
        return {"complete": False, "profit": None, "roi": None, "floor": None}
    if fees is None or fees.total is None or fees.referral is None:
        return {"complete": False, "profit": None, "roi": None, "floor": None}
    profit = price - supplier_cost - fees.total - allowances
    roi = profit / supplier_cost
    referral_rate = fees.referral / price
    fixed_fees = fees.total - fees.referral
    floor = None
    if Decimal(0) <= referral_rate < Decimal(1):
        floor = (supplier_cost * (Decimal(1) + ROI_HURDLE) + fixed_fees + allowances) / (Decimal(1) - referral_rate)
    return {
        "complete": True,
        "profit": quantize(profit, "0.0001"),
        "roi": quantize(roi, "0.00000001"),
        "floor": quantize(floor, "0.0001") if floor is not None else None,
    }


def supplier_price_history(observations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(
        [row for row in observations if row.get("effective_date") and row.get("supplier_price") is not None],
        key=lambda row: (str(row["effective_date"]), int(row.get("revision") or 0)),
    )
    if not rows:
        return {key: None for key in ("current", "previous", "price_30d", "price_90d", "historical_low", "change_30d", "change_90d")}
    current = rows[-1]
    current_date = date.fromisoformat(str(current["effective_date"])[:10])
    current_price = decimal(current["supplier_price"])
    prior_rows = rows[:-1]
    previous = decimal(prior_rows[-1]["supplier_price"]) if prior_rows else None
    price30 = price_at_or_before(prior_rows, current_date - timedelta(days=30))
    price90 = price_at_or_before(prior_rows, current_date - timedelta(days=90))
    return {
        "current": current_price,
        "previous": previous,
        "price_30d": price30,
        "price_90d": price90,
        "historical_low": min(decimal(row["supplier_price"]) for row in rows),
        "change_30d": percent_change(current_price, price30),
        "change_90d": percent_change(current_price, price90),
    }


def informational_risk_signals(*, current_price: Decimal | None, avg30_price: Decimal | None,
                               avg90_price: Decimal | None, supplier_change_30d: Decimal | None,
                               offer_count_current: int | None, fba_seller_count: int | None = None) -> dict[str, Any]:
    amazon30 = percent_change(current_price, avg30_price)
    amazon90 = percent_change(current_price, avg90_price)
    divergence = bool(
        supplier_change_30d is not None and amazon30 is not None
        and supplier_change_30d <= Decimal("-0.15")
        and supplier_change_30d <= amazon30 - Decimal("0.10")
    )
    return {
        "amazon_price_change_30d": amazon30,
        "amazon_price_change_90d": amazon90,
        "amazon_price_trend": trend(amazon30),
        "supplier_amazon_divergence": divergence,
        "supplier_amazon_divergence_message": (
            "Supplier price declining substantially faster than Amazon market price" if divergence else None
        ),
        "offer_count_current": offer_count_current,
        "offer_count_label": "Relevant offers" if offer_count_current is not None else None,
        "fba_seller_count": fba_seller_count,
    }


def input_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def price_at_or_before(rows: list[dict[str, Any]], threshold: date) -> Decimal | None:
    eligible = [row for row in rows if date.fromisoformat(str(row["effective_date"])[:10]) <= threshold]
    return decimal(eligible[-1]["supplier_price"]) if eligible else None


def percent_change(current: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return quantize((current - baseline) / baseline, "0.00000001")


def trend(change: Decimal | None) -> str | None:
    if change is None:
        return None
    if change > Decimal("0.02"):
        return "up"
    if change < Decimal("-0.02"):
        return "down"
    return "stable"


def quantize(value: Decimal | None, precision: str) -> Decimal | None:
    return value.quantize(Decimal(precision), rounding=ROUND_HALF_UP) if value is not None else None


def decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))
