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


def derive_purchase_item_status_from_shipments(current_status=None, shipments=None, seller_shipped=False, ebay_cancelled=False):
    item_status = normalize_status(current_status)
    if item_status in WORKFLOW_LOCKED_STATUSES:
        return item_status
    if ebay_cancelled:
        return "cancelled"

    active_shipments = []
    for shipment in shipments or []:
        resolution_status = normalize_status(shipment.get("resolution_status"))
        if resolution_status in {"closed_fully_received_elsewhere", "received", "return_pending"}:
            continue
        tracking_number = shipment.get("tracking_number")
        if not has_usable_tracking_number(tracking_number):
            continue
        active_shipments.append(shipment)

    if not active_shipments:
        return "shipped_no_tracking" if seller_shipped else "no_tracking"

    statuses = {
        normalize_status(
            shipment.get("normalized_status")
            or shipment.get("carrier_status")
            or shipment.get("shipment_status")
        )
        for shipment in active_shipments
    }
    delivered_count = sum(
        1
        for shipment in active_shipments
        if normalize_status(shipment.get("normalized_status") or shipment.get("carrier_status") or shipment.get("shipment_status")) == "delivered"
        or shipment.get("delivered_date")
    )

    if delivered_count == len(active_shipments):
        return "delivered"
    if delivered_count > 0:
        return "partially_delivered"
    if statuses & {"exception", "return_to_sender"}:
        return "exception"
    if "out_for_delivery" in statuses:
        return "out_for_delivery"
    if "available_for_pickup" in statuses:
        return "available_for_pickup"
    if "in_transit" in statuses:
        return "multi_package_in_transit" if len(active_shipments) > 1 else "in_transit"
    return "awaiting_carrier_scan"
