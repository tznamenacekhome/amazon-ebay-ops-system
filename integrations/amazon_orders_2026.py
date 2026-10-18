"""Project Orders 2026 operational data into MBOP's existing non-PII contract."""
from decimal import Decimal
from datetime import datetime

STATUSES = {
    "PENDING_AVAILABILITY": "PendingAvailability", "PENDING": "Pending",
    "UNSHIPPED": "Unshipped", "PARTIALLY_SHIPPED": "PartiallyShipped",
    "SHIPPED": "Shipped", "CANCELLED": "Canceled", "UNFULFILLABLE": "Unfulfillable",
}
CHANNELS = {"AMAZON": "AFN", "MERCHANT": "MFN"}
CONDITIONS = {"NEW": "New", "USED": "Used", "COLLECTIBLE": "Collectible", "REFURBISHED": "Refurbished"}
SUBTYPES = {"NEW": "New", "MINT": "Mint", "VERY_GOOD": "VeryGood", "GOOD": "Good", "ACCEPTABLE": "Acceptable"}


def money(value):
    if not isinstance(value, dict) or value.get("amount") is None:
        return None
    return {"Amount": str(value["amount"]), "CurrencyCode": value.get("currencyCode")}


def proceeds_money(breakdowns, kind, subtype=None, *, discount=False):
    values = []
    for part in breakdowns:
        if part.get("type") != kind:
            continue
        if subtype is None:
            values.append(part.get("subtotal"))
        else:
            values.extend(x.get("value") for x in part.get("detailedBreakdowns", []) if x.get("subtype") == subtype)
    values = [v for v in values if isinstance(v, dict) and v.get("amount") is not None]
    if not values:
        parent = next((x.get("subtotal") for x in breakdowns if x.get("type") == kind), None)
        if subtype and isinstance(parent, dict):
            return {"Amount": "0", "CurrencyCode": parent.get("currencyCode")}
        return None
    currencies = {v.get("currencyCode") for v in values}
    if len(currencies) != 1:
        raise ValueError("Mixed currencies in order item proceeds")
    amount = sum((Decimal(str(v["amount"])) for v in values), Decimal(0))
    return {"Amount": str(abs(amount) if discount else amount), "CurrencyCode": values[0].get("currencyCode")}


def timestamp(value):
    if not value:
        return None
    # v0 emitted second precision. Retain that contract for unchanged-item checks.
    return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_item(item):
    product = item.get("product") or {}
    condition = product.get("condition") or {}
    parts = (item.get("proceeds") or {}).get("breakdowns") or []
    result = {
        "OrderItemId": item["orderItemId"], "ASIN": product.get("asin"),
        "SellerSKU": product.get("sellerSku"), "Title": product.get("title"),
        "QuantityOrdered": item.get("quantityOrdered"),
        "QuantityShipped": (item.get("fulfillment") or {}).get("quantityFulfilled"),
        "ConditionId": CONDITIONS.get(condition.get("conditionType"), condition.get("conditionType")),
        "ConditionSubtypeId": SUBTYPES.get(condition.get("conditionSubtype"), condition.get("conditionSubtype")),
    }
    for field, kind, subtype in [
        ("ItemPrice", "ITEM", None), ("ShippingPrice", "SHIPPING", None),
        ("GiftWrapPrice", "GIFT_WRAP", None), ("ItemTax", "TAX", "ITEM"),
        ("ShippingTax", "TAX", "SHIPPING"), ("GiftWrapTax", "TAX", "GIFT_WRAP"),
        ("PromotionDiscount", "DISCOUNT", None), ("ShippingDiscount", "DISCOUNT", "SHIPPING"),
    ]:
        result[field] = proceeds_money(parts, kind, subtype, discount=kind == "DISCOUNT")
    if result["PromotionDiscount"] and result["ShippingDiscount"]:
        # 2026 DISCOUNT subtotal contains SHIPPING; v0's PromotionDiscount excludes it.
        total = Decimal(result["PromotionDiscount"]["Amount"])
        shipping = Decimal(result["ShippingDiscount"]["Amount"])
        if shipping > total:
            raise ValueError("Shipping discount exceeds total discount")
        result["PromotionDiscount"]["Amount"] = str(total - shipping)
    if result["GiftWrapPrice"] is None:
        result["GiftWrapTax"] = None
    # Keep only operational fields, even if Amazon adds unsolicited PII members.
    return result


def normalize_order(order):
    items = order.get("orderItems")
    if not isinstance(items, list):
        raise ValueError("Orders 2026 response is missing orderItems")
    fulfillment = order.get("fulfillment") or {}
    channel = order.get("salesChannel") or {}
    programs = order.get("programs")
    normalized_items = [normalize_item(item) for item in items]
    quantities = [item.get("QuantityShipped") for item in normalized_items]
    unfulfilled = [(item.get("fulfillment") or {}).get("quantityUnfulfilled") for item in items]
    cancellation_requests = [(item.get("cancellation") or {}).get("cancellationRequest") or {} for item in items]
    result = {
        "AmazonOrderId": order["orderId"], "PurchaseDate": timestamp(order["createdTime"]),
        "LastUpdateDate": timestamp(order["lastUpdatedTime"]),
        "OrderStatus": STATUSES.get(fulfillment.get("fulfillmentStatus"), fulfillment.get("fulfillmentStatus")),
        "FulfillmentChannel": CHANNELS.get(fulfillment.get("fulfilledBy"), fulfillment.get("fulfilledBy")),
        "SalesChannel": channel.get("marketplaceName"), "MarketplaceId": channel.get("marketplaceId"),
        "OrderTotal": money((order.get("proceeds") or {}).get("grandTotal")),
        "BuyerRequestedCancel": {"IsBuyerRequestedCancel": any(x.get("requester") == "BUYER" for x in cancellation_requests) if any(cancellation_requests) else None},
        "IsReplacementOrder": any(x.get("associationType") in {"REPLACEMENT_ORIGINAL_ID", "EXCHANGE_ORIGINAL_ID"} for x in order.get("associatedOrders") or []),
        "IsBusinessOrder": "AMAZON_BUSINESS" in programs if programs is not None else None,
        "IsPrime": "PRIME" in programs if programs is not None else None,
        "NumberOfItemsShipped": sum(quantities) if quantities and all(x is not None for x in quantities) else None,
        "NumberOfItemsUnshipped": sum(unfulfilled) if unfulfilled and all(x is not None for x in unfulfilled) else None,
        "ShipmentServiceLevelCategory": (fulfillment.get("fulfillmentServiceLevel") or "").title().replace("_", "") or None,
        "_orders_api_version": "2026-01-01", "_order_items": normalized_items,
    }
    for prefix, window_name in [("Ship", "shipByWindow"), ("Delivery", "deliverByWindow")]:
        window = fulfillment.get(window_name) or {}
        result[f"Earliest{prefix}Date"] = timestamp(window.get("earliestDateTime"))
        result[f"Latest{prefix}Date"] = timestamp(window.get("latestDateTime"))
    return result


def preserve_missing_fields(row, existing):
    """Omitted provider values must not erase known historical normalized data."""
    return {key: existing.get(key) if value is None and key in existing else value for key, value in row.items()}
