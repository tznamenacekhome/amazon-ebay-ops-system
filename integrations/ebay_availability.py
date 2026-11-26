"""Quantity evidence shared by Browse/Trading enrichment and candidate mapping."""
from decimal import Decimal, InvalidOperation


def quantity_evidence(payload):
    quantities = []
    for row in payload.get('estimatedAvailabilities') or []:
        if not isinstance(row, dict):
            return None, 'unknown_availability'
        status = str(row.get('estimatedAvailabilityStatus') or '').upper()
        if status in {'OUT_OF_STOCK', 'SOLD_OUT', 'UNAVAILABLE'}:
            return 0, 'unavailable'
        if status == 'UNKNOWN':
            return None, 'unknown_availability'
        values = []
        for key in ('estimatedAvailableQuantity', 'estimatedRemainingQuantity'):
            value = row.get(key)
            if value is None:
                continue
            try:
                number = Decimal(str(value))
                if isinstance(value, bool) or not number.is_finite() or number < 0 or number != number.to_integral_value():
                    return None, 'invalid_quantity'
            except (InvalidOperation, ValueError):
                return None, 'invalid_quantity'
            if key == 'estimatedRemainingQuantity' and status != 'IN_STOCK':
                return None, 'unknown_availability'
            values.append(int(number))
        if len(set(values)) > 1:
            return None, 'conflicting_quantity'
        if values:
            quantities.append(values[0])
    if not quantities:
        return None, 'unknown_quantity'
    if len(set(quantities)) > 1:
        return None, 'conflicting_quantity'
    return quantities[0], 'available' if quantities[0] > 0 else 'unavailable'
