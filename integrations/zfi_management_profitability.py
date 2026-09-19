"""Conservative calendar-period facts for ZFI; no database writes or cost allocation."""

from __future__ import annotations

import datetime as dt
import os
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def business_timezone():
    return ZoneInfo(os.getenv("MBOP_BUSINESS_TIMEZONE", "America/Los_Angeles"))


def local_date(value):
    if not value:
        return None
    try:
        if len(str(value)) == 10:
            return dt.date.fromisoformat(str(value))
        timestamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return None
        return timestamp.astimezone(business_timezone()).date()
    except ValueError:
        return None


def utc_bounds(start, end):
    zone = business_timezone()
    return tuple(dt.datetime.combine(day, dt.time(), zone).astimezone(dt.timezone.utc).isoformat()
                 for day in (start, end + dt.timedelta(days=1)))


def amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def total(rows, field):
    values = [amount(row.get(field)) for row in rows]
    return None if any(v is None for v in values) else float(sum(values, Decimal(0)).quantize(Decimal(".01")))


def refund_facts(events, start, end):
    """Observed seller revenue reversals, never a claim of complete ingestion."""
    warnings = [
        "Refund coverage is unverified: order-scoped finance sync is not a posted-period ledger; "
        "legacy financial_event_id omits posting date and can collapse repeated equal refunds. "
        "refunds_returns is null; refunds_returns_observed is diagnostic only."
    ]
    selected = []
    seen = set()
    invalid = events is None
    for event in events or []:
        if event.get("event_type") != "RefundEventList":
            continue
        day = local_date(event.get("posted_date"))
        if day is None:
            invalid = True
            continue
        if not start <= day <= end:
            continue
        identity = event.get("financial_event_id")
        if not identity:
            invalid = True
            continue
        if identity in seen:
            continue
        seen.add(identity)
        if event.get("fee_type"):
            continue  # Fee credits are not customer contra-revenue.
        charge = event.get("charge_type")
        if charge and "tax" in charge.lower():
            continue
        if charge not in {"Principal", "ShippingCharge", "GiftWrap"} and not event.get("promotion_type"):
            invalid = True
            continue
        value = amount(event.get("amount"))
        if event.get("currency") != "USD" or value is None:
            invalid = True
            continue
        selected.append({"amount": -value})  # Preserve promotion reversals/credits' signs.
    if invalid:
        warnings.append("Refund source unavailable or contains unsupported currency, amount, type, identity or posting date.")
    return {
        "refunds_returns": None,
        "refunds_returns_observed": None if invalid else total(selected, "amount"),
        "refund_coverage": "unverified",
        "refund_source": "amazon_sales_financial_events:RefundEventList; posted_date; USD; excludes tax and fee credits",
        "completeness_warnings": warnings,
    }


def cost_categories(rows, labels):
    """Separate FBA fees from verified Veeqo costs, counting each order once."""
    fulfillment = []
    merchant_orders = set()
    fulfillment_warnings = []
    label_warnings = []
    for row in rows:
        channel = str(row.get("fulfillment_channel") or "").lower()
        if channel in {"afn", "amazon", "amazonfulfilled"}:
            if row.get("fulfillment_cost_source") == "amazon_fba_fee":
                fulfillment.append(row)
            else:
                fulfillment_warnings.append("FBA fulfillment cost source is missing or ambiguous.")
        elif channel in {"mfn", "merchant", "merchantfulfilled"}:
            merchant_orders.add(row.get("amazon_order_id"))
        else:
            fulfillment_warnings.append("Unknown fulfillment channel prevents a complete FBA fulfillment total.")
            label_warnings.append("Unknown fulfillment channel prevents a complete MFN shipping-label total.")
    fulfillment_cost = total(fulfillment, "fulfillment_cost") if not fulfillment_warnings else None
    label_rows = []
    for order_id in merchant_orders:
        shipments = [r for r in labels or [] if r.get("amazon_order_id") == order_id]
        if not shipments or any(r.get("label_cost_currency") != "USD" or
                                amount(r.get("label_cost_amount")) is None or
                                r.get("label_cost_source_field") not in {"outbound_label_charges", "label_cost"} or
                                not r.get("veeqo_shipment_id") for r in shipments):
            label_warnings.append("MFN shipping labels unavailable or unverified; generic Amazon adjustments/manual costs are not verified labels.")
            continue
        by_id = {r["veeqo_shipment_id"]: r for r in shipments}
        label_rows.extend(by_id.values())
    label_cost = total(label_rows, "label_cost_amount") if not label_warnings else None
    if fulfillment_cost is None:
        fulfillment_warnings.append("Fulfillment costs are incomplete.")
    return fulfillment_cost, label_cost, sorted(set(fulfillment_warnings + label_warnings))


def management_sale_rows(rows, start, end):
    """Return economically recognized sale rows for a purchase-date cohort."""
    selected = []
    for row in rows:
        day = local_date(row.get("sold_at"))
        if day is None or not start <= day <= end:
            continue
        if row.get("data_status") == "cancelled" or row.get("is_replacement_order") is True:
            continue
        status = str(row.get("order_status") or "").lower()
        if status and status != "shipped":
            continue
        selected.append(row)
    return selected


def summarize_management_window(rows, start, end, timestamps, refunds, labels):
    selected = management_sale_rows(rows, start, end)
    warnings = [
        "Sales and cost facts cover shipped, non-replacement stored profitability rows by original purchase date; source timestamps do not certify ingestion completeness."
    ]
    revenue = total(selected, "sale_price")
    cogs = total(selected, "cogs")
    fees = total(selected, "amazon_fees_excluding_fulfillment")
    # Stored fee sums use absolute amounts, including refund fees/credits. Do not
    # advertise these as a refund-adjusted management expense ledger.
    warnings.append("Marketplace fees are sale-cohort operational aggregates excluding FBA fulfillment; refund fee credits are not reconciled by posting period.")
    if any(r.get("data_status") == "missing_fees" for r in selected):
        fees = None
        warnings.append("Marketplace fees unavailable because applicable shipped rows are missing fee data.")
    fulfillment, shipping, cost_warnings = cost_categories(selected, labels)
    refund = refund_facts(refunds, start, end)
    warnings.extend(cost_warnings + refund.pop("completeness_warnings"))
    if revenue is None or cogs is None:
        warnings.append("Sales or acquisition COGS are incomplete; totals are null, not partial sums.")
    lower, upper = utc_bounds(start, end)
    return {
        "gross_sales": revenue, "revenue": revenue, "cogs": cogs,
        "marketplace_fees": fees, "fulfillment_costs": fulfillment,
        "shipping_label_costs": shipping, **refund,
        "gross_profit": None if revenue is None or cogs is None else round(revenue - cogs, 2),
        "net_profit": None,
        "units_sold": int(sum(r.get("quantity") or 0 for r in selected)),
        "source_start_date": start.isoformat(), "source_end_date": end.isoformat(),
        "source_start_at": lower, "source_end_at_exclusive": upper,
        "timezone": str(business_timezone()), "currency": "USD",
        "marketplace_fee_basis": "amazon_sales_profitability.amazon_fees_excluding_fulfillment; sale cohort; not a posted fee ledger",
        "fulfillment_cost_basis": "amazon_sales_profitability.fulfillment_cost where source=amazon_fba_fee and channel=AFN",
        "shipping_label_cost_basis": "verified USD Veeqo labels once per shipment; attributed to original order purchase period",
        "cogs_basis": "stored vendor-paid acquisition cost of units sold; excludes inbound freight, prep, labels and Amazon fees",
        "gross_profit_basis": "gross_sales minus acquisition cogs; before refunds, marketplace fees, fulfillment and labels",
        "source_timestamps": dict(timestamps),
        "completeness_warnings": warnings,
    }
