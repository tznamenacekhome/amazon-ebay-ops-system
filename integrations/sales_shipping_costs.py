"""Actual outbound label evidence. No quotes, customer delivery charges or estimates."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def money(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def shipment_candidates(order):
    """Only shipment containers: tracking records have their own unrelated IDs."""
    candidates = list(order.get("shipments") or [])
    for allocation in order.get("allocations") or []:
        if isinstance(allocation, dict):
            if isinstance(allocation.get("shipment"), dict):
                candidates.append(allocation["shipment"])
            candidates.extend(allocation.get("shipments") or [])
    return [s for s in candidates if isinstance(s, dict)]


def extract_shipments(order):
    candidates = shipment_candidates(order)
    unique = {}
    for shipment in candidates:
        if not isinstance(shipment, dict):
            continue
        key = shipment.get("id") or shipment.get("shipment_id")
        if key is None:
            # No stable source ID means no auditable cost, never invent an index ID.
            continue
        key = str(key)
        if key not in unique or shipment.get("outbound_label_charges") is not None:
            unique[key] = shipment
    return list(unique.values())


def label_evidence(shipment, order_currency=None):
    charge = shipment.get("outbound_label_charges")
    tracking = shipment.get("tracking_number")
    tracking = tracking if isinstance(tracking, dict) else {}
    if any(shipment.get(k) for k in ("voided_at", "cancelled_at", "refunded_at", "cancelled")) or tracking.get("cancelled") or tracking.get("cancelled_at") or str(shipment.get("status", "")).lower() in {"voided", "cancelled", "refunded"}:
        return None, "void_or_refund_requires_review"
    # The documented field is a total label charge, including explicit source zero.
    if not isinstance(charge, dict):
        return None, "missing_label_amount"
    amount = money(charge.get("value"))
    if amount is None or amount < 0:
        return None, "missing_label_amount"
    if (charge.get("unit") or order_currency) != "USD":
        return None, "unsupported_currency"
    # Undocumented adjustment/refund structures must be reviewed, never guessed.
    if any(shipment.get(k) for k in ("adjustments", "refunds", "label_refund", "label_adjustments")):
        return None, "label_adjustment_requires_review"
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "reconciled"


def order_label_cost(order):
    if str(order.get("status", "")).lower() in {"partially_shipped", "partiallyshipped"}:
        return None, "pending_shipment"
    if any(not (s.get("id") or s.get("shipment_id")) for s in shipment_candidates(order)):
        return None, "missing_shipment_identifier"
    shipments = extract_shipments(order)
    if not shipments:
        return None, "missing_shipment"
    values = []
    for shipment in shipments:
        amount, reason = label_evidence(shipment, order.get("currency_code"))
        if amount is None:
            return None, reason
        values.append(Decimal(str(amount)))
    return float(sum(values)), "reconciled"


def allocate_cost(total, items):
    """Allocate once by ordered unit quantity; stable item-ID order receives rounding cents."""
    if total is None:
        return {i["amazon_order_item_id"]: None for i in items}
    ordered = sorted(items, key=lambda i: i["amazon_order_item_id"])
    weights = [max(int(i.get("quantity_ordered") or i.get("quantity_shipped") or 0), 0) for i in ordered]
    units = sum(weights)
    if not units:
        return {i["amazon_order_item_id"]: None for i in items}
    cents = int((Decimal(str(total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    shares = [cents * w // units for w in weights]
    for index in range(cents - sum(shares)):
        shares[index] += 1
    return {i["amazon_order_item_id"]: share / 100 for i, share in zip(ordered, shares)}
