WORKFLOW_LOCKED_STATUSES = {
    "cancelled",
    "listed",
    "received",
    "return_opened",
    "return_pending",
}

INVALID_TRACKING_VALUES = {
    "no tracking",
    "none",
    "n/a",
    "na",
    "not available",
    "refunded",
    "cancelled",
    "canceled",
    "shipped untracked",
    "shipped without tracking",
}


def normalize_status(value):
    if not value:
        return ""

    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def has_usable_tracking_number(value):
    if not value:
        return False

    tracking_number = str(value).strip()

    return bool(tracking_number) and tracking_number.lower() not in INVALID_TRACKING_VALUES


def derive_purchase_item_status(
    current_status=None,
    tracking_number=None,
    carrier_status=None,
    delivered_date=None,
    seller_shipped=False,
    ebay_cancelled=False,
):
    item_status = normalize_status(current_status)
    normalized_carrier_status = normalize_status(carrier_status)

    if item_status in WORKFLOW_LOCKED_STATUSES:
        return item_status

    if ebay_cancelled:
        return "cancelled"

    if normalized_carrier_status == "delivered" or delivered_date:
        return "delivered"

    if normalized_carrier_status in {"exception", "return_to_sender"}:
        return "exception"

    if normalized_carrier_status == "out_for_delivery":
        return "out_for_delivery"

    if normalized_carrier_status == "available_for_pickup":
        return "available_for_pickup"

    if normalized_carrier_status == "in_transit":
        return "in_transit"

    if has_usable_tracking_number(tracking_number):
        return "awaiting_carrier_scan"

    if seller_shipped:
        return "shipped_no_tracking"

    return "no_tracking"
