import os
import base64
import requests
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from supabase import create_client

try:
    from system_detection import detect_system_from_title, normalize_system
except ImportError:
    from integrations.system_detection import detect_system_from_title, normalize_system

try:
    from status_logic import derive_purchase_item_status
except ImportError:
    from integrations.status_logic import derive_purchase_item_status


DAYS_BACK = 90
LOCAL_TIMEZONE = "America/Los_Angeles"
SKIP_EXISTING_ORDERS_WITH_TRACKING = True
WORKFLOW_LOCKED_STATUSES = {
    "cancelled",
    "listed",
    "received",
    "return_opened",
    "return_pending",
}

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
COMPATIBILITY_LEVEL = "1423"
SITE_ID = "0"


def iso(dt):
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def strip_namespace(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def child_text(parent, name):
    if parent is None or name is None:
        return None

    for child in list(parent):
        if strip_namespace(child.tag) == name:
            return child.text

    return None


def find_first(parent, name):
    if parent is None:
        return None

    for elem in parent.iter():
        if strip_namespace(elem.tag) == name:
            return elem

    return None


def find_all(parent, name):
    if parent is None:
        return []

    return [
        elem
        for elem in parent.iter()
        if strip_namespace(elem.tag) == name
    ]


def element_to_dict(elem):
    tag = strip_namespace(elem.tag)
    children = list(elem)

    if not children:
        return elem.text

    result = {}

    for child in children:
        child_tag = strip_namespace(child.tag)
        child_value = element_to_dict(child)

        if child_tag in result:
            if not isinstance(result[child_tag], list):
                result[child_tag] = [result[child_tag]]
            result[child_tag].append(child_value)
        else:
            result[child_tag] = child_value

    return {tag: result}


def parse_money(value):
    if value is None:
        return Decimal("0.00")

    try:
        return Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except Exception:
        return Decimal("0.00")


def decimal_to_float(value):
    if value is None:
        return None

    return float(
        Decimal(value).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    )


def get_access_token():
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("utf-8")

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=120,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def get_buyer_orders(access_token, days_back=DAYS_BACK):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": "GetOrders",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPATIBILITY_LEVEL,
        "X-EBAY-API-SITEID": SITE_ID,
        "X-EBAY-API-IAF-TOKEN": access_token,
    }

    all_orders = []
    page_number = 1
    total_pages = 1

    while page_number <= total_pages:
        print(f"Fetching eBay orders page {page_number} of {total_pages}...")

        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <CreateTimeFrom>{iso(start)}</CreateTimeFrom>
  <CreateTimeTo>{iso(end)}</CreateTimeTo>
  <OrderRole>Buyer</OrderRole>
  <OrderStatus>All</OrderStatus>
  <DetailLevel>ReturnAll</DetailLevel>
  <Pagination>
    <EntriesPerPage>100</EntriesPerPage>
    <PageNumber>{page_number}</PageNumber>
  </Pagination>
</GetOrdersRequest>"""

        response = requests.post(
            TRADING_ENDPOINT,
            headers=headers,
            data=xml_body,
            timeout=120,
        )

        response.raise_for_status()
        root = ET.fromstring(response.text)

        ack = None
        for elem in root.iter():
            if strip_namespace(elem.tag) == "Ack":
                ack = elem.text
                break

        if ack not in ["Success", "Warning"]:
            print("Trading API Ack:", ack)
            for elem in root.iter():
                if strip_namespace(elem.tag) == "LongMessage":
                    print("Error:", elem.text)
            break

        pagination_result = find_first(root, "PaginationResult")
        if pagination_result is not None:
            total_pages_text = child_text(
                pagination_result,
                "TotalNumberOfPages"
            )

            try:
                total_pages = int(total_pages_text)
            except Exception:
                total_pages = 1

        page_orders = []
        for elem in root.iter():
            if strip_namespace(elem.tag) == "Order":
                page_orders.append(elem)

        print(f"Orders retrieved on page {page_number}: {len(page_orders)}")

        all_orders.extend(page_orders)
        page_number += 1

    print(f"Total orders retrieved across all pages: {len(all_orders)}")
    return all_orders


def get_existing_purchase(order_id):
    result = (
        supabase.table("purchases")
        .select("purchase_id, order_date")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]

    return None


def purchase_has_tracking(purchase_id):
    shipment_result = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id")
        .eq("purchase_id", purchase_id)
        .not_.is_("tracking_number", "null")
        .limit(1)
        .execute()
    )

    if shipment_result.data:
        return True

    item_result = (
        supabase.table("purchase_items")
        .select("item_id")
        .eq("purchase_id", purchase_id)
        .not_.is_("tracking_number", "null")
        .limit(1)
        .execute()
    )

    return bool(item_result.data)


def get_existing_purchase_items(purchase_id):
    result = (
        supabase.table("purchase_items")
        .select(
            "item_id,title,quantity,supplier_sku,raw_import_json,created_at,"
            "asin,target_price,system,tracking_number,condition,"
            "supplier_listing_url,current_status,unit_cost,"
            "manual_title_override,manual_unit_cost_override,manual_split_child"
        )
        .eq("purchase_id", purchase_id)
        .order("created_at")
        .execute()
    )

    return result.data or []


def create_import_batch():
    result = (
        supabase.table("import_batches")
        .insert({
            "source_name": "eBay Trading API Buyer Purchase Sync",
            "notes": f"Buyer purchase import/update for last {DAYS_BACK} days",
        })
        .execute()
    )

    return result.data[0]["import_batch_id"]


def get_order_total(order):
    total = find_first(order, "Total")
    if total is not None and total.text:
        return decimal_to_float(parse_money(total.text))
    return None


def get_order_shipping_cost(order):
    shipping_selected = find_first(order, "ShippingServiceSelected")
    shipping = child_text(shipping_selected, "ShippingServiceCost")

    if shipping:
        return decimal_to_float(parse_money(shipping))

    return None


def get_order_tax_amount(order):
    tax = find_first(order, "TotalTaxAmount")
    if tax is not None and tax.text:
        return decimal_to_float(parse_money(tax.text))
    return None


def get_created_date(order):
    created = child_text(order, "CreatedTime")

    if not created:
        return None

    dt = datetime.fromisoformat(
        created.replace("Z", "+00:00")
    )

    local_dt = dt.astimezone(
        ZoneInfo(LOCAL_TIMEZONE)
    )

    return local_dt.date().isoformat()


def get_order_status(order):
    return child_text(order, "OrderStatus")


def order_has_shipped_time(order):
    return bool(find_first(order, "ShippedTime"))


def extract_tracking(order):
    for elem in order.iter():
        if strip_namespace(elem.tag) == "ShipmentTrackingDetails":
            tracking = child_text(elem, "ShipmentTrackingNumber")
            carrier = child_text(elem, "ShippingCarrierUsed")

            if tracking:
                return {
                    "tracking_number": tracking.strip(),
                    "carrier": carrier,
                }

    return {
        "tracking_number": None,
        "carrier": None,
    }


def extract_delivery_dates(order):
    package_info = find_first(order, "ShippingPackageInfo")

    return {
        "actual_delivery_time": child_text(package_info, "ActualDeliveryTime"),
        "estimated_delivery_min": child_text(package_info, "EstimatedDeliveryTimeMin"),
        "estimated_delivery_max": child_text(package_info, "EstimatedDeliveryTimeMax"),
    }


def extract_transactions(order):
    transactions = []

    for elem in order.iter():
        if strip_namespace(elem.tag) == "Transaction":
            transactions.append(elem)

    return transactions


def transaction_title(transaction):
    item = find_first(transaction, "Item")
    title = child_text(item, "Title")

    return title or "Unknown eBay item"


def transaction_quantity(transaction):
    qty = child_text(transaction, "QuantityPurchased")

    try:
        parsed_qty = int(qty)
        return parsed_qty if parsed_qty > 0 else 1
    except Exception:
        return 1


def transaction_line_id(transaction):
    return (
        child_text(transaction, "OrderLineItemID")
        or child_text(transaction, "InventoryReservationID")
        or child_text(transaction, "TransactionID")
    )


def transaction_item_id(transaction):
    item = find_first(transaction, "Item")
    return child_text(item, "ItemID")


def transaction_listing_url(transaction):
    item_id = transaction_item_id(transaction)
    return f"https://www.ebay.com/itm/{item_id}" if item_id else None


def money_currency(elem):
    if elem is None:
        return None

    return elem.attrib.get("currencyID")


def transaction_has_non_usd_currency(transaction):
    for field in ("TransactionPrice", "ActualShippingCost", "ActualHandlingCost"):
        currency = money_currency(find_first(transaction, field))
        if currency and currency.upper() != "USD":
            return True

    return False


def order_payment_total(order):
    return sum(
        parse_money(elem.text)
        for elem in find_all(order, "PaymentAmount")
    )


def order_refund_total(order):
    return sum(
        parse_money(elem.text)
        for elem in find_all(order, "RefundAmount")
    )


def transaction_landed_total(transaction):
    quantity = transaction_quantity(transaction)

    price_elem = find_first(transaction, "TransactionPrice")
    item_price_each = parse_money(price_elem.text if price_elem is not None else None)

    actual_shipping = parse_money(child_text(transaction, "ActualShippingCost"))
    actual_handling = parse_money(child_text(transaction, "ActualHandlingCost"))

    landed_total = (
        (item_price_each * Decimal(str(quantity)))
        + actual_shipping
        + actual_handling
    )

    return landed_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def unit_cost_from_total(total, quantity):
    unit_cost = (
        total / Decimal(str(quantity))
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return float(unit_cost)


def transaction_unit_cost(transaction):
    return unit_cost_from_total(
        transaction_landed_total(transaction),
        transaction_quantity(transaction),
    )


def transaction_unit_costs(order, transactions):
    gross_totals = [
        transaction_landed_total(transaction)
        for transaction in transactions
    ]
    gross_order_total = sum(gross_totals)
    payment_total = order_payment_total(order)
    refund_total = order_refund_total(order)
    net_payment_total = (payment_total + refund_total).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    has_refund = refund_total != Decimal("0.00")
    has_non_usd_currency = any(
        transaction_has_non_usd_currency(transaction)
        for transaction in transactions
    )

    use_net_payment = (
        net_payment_total > Decimal("0.00")
        and (
            has_non_usd_currency
            or (has_refund and len(transactions) == 1)
        )
    )

    if not use_net_payment or gross_order_total <= Decimal("0.00"):
        return [
            transaction_unit_cost(transaction)
            for transaction in transactions
        ]

    if len(transactions) == 1:
        return [
            unit_cost_from_total(
                net_payment_total,
                transaction_quantity(transactions[0]),
            )
        ]

    allocated = []
    allocated_so_far = Decimal("0.00")

    for index, transaction in enumerate(transactions):
        if index == len(transactions) - 1:
            line_total = net_payment_total - allocated_so_far
        else:
            line_total = (
                net_payment_total
                * (gross_totals[index] / gross_order_total)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            allocated_so_far += line_total

        allocated.append(
            unit_cost_from_total(
                line_total,
                transaction_quantity(transaction),
            )
        )

    return allocated


def match_existing_item(existing_items, transaction, used_item_ids):
    line_id = transaction_line_id(transaction)
    title = transaction_title(transaction)
    quantity = transaction_quantity(transaction)

    if line_id:
        for item in existing_items:
            if item.get("item_id") in used_item_ids:
                continue

            if item.get("manual_split_child"):
                continue

            if item.get("supplier_sku") == line_id:
                return item

    for item in existing_items:
        if item.get("item_id") in used_item_ids:
            continue

        if item.get("manual_split_child"):
            continue

        raw = item.get("raw_import_json") or {}
        transaction_raw = raw.get("Transaction") if isinstance(raw, dict) else {}

        if isinstance(transaction_raw, dict):
            raw_line_id = (
                transaction_raw.get("OrderLineItemID")
                or transaction_raw.get("InventoryReservationID")
                or transaction_raw.get("TransactionID")
            )

            if line_id and raw_line_id == line_id:
                return item

    for item in existing_items:
        if item.get("item_id") in used_item_ids:
            continue

        if item.get("manual_split_child"):
            continue

        if item.get("title") == title and int(item.get("quantity") or 1) == quantity:
            return item

    for item in existing_items:
        if item.get("item_id") in used_item_ids:
            continue

        if item.get("manual_split_child"):
            continue

        return item

    return None


def upsert_inbound_shipment(purchase_id, tracking, dates):
    tracking_number = tracking.get("tracking_number")

    if not tracking_number:
        return None

    existing = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id")
        .eq("purchase_id", purchase_id)
        .eq("tracking_number", tracking_number)
        .limit(1)
        .execute()
    )

    payload = {
        "purchase_id": purchase_id,
        "tracking_number": tracking_number,
        "carrier": tracking.get("carrier"),
        "shipment_status": (
            "delivered"
            if dates.get("actual_delivery_time")
            else "unknown"
        ),
        "normalized_status": (
            "delivered"
            if dates.get("actual_delivery_time")
            else "unknown"
        ),
        "estimated_delivery_date": dates.get("estimated_delivery_max"),
        "delivered_date": dates.get("actual_delivery_time"),
        "updated_at": iso(datetime.now(timezone.utc)),
    }

    if existing.data:
        shipment_id = existing.data[0]["inbound_shipment_id"]

        supabase.table("inbound_shipments").update(payload).eq(
            "inbound_shipment_id",
            shipment_id
        ).execute()

        return shipment_id

    result = supabase.table("inbound_shipments").insert(payload).execute()

    return result.data[0]["inbound_shipment_id"]


def link_shipment_item(shipment_id, item_id, quantity):
    if not shipment_id or not item_id:
        return

    existing = (
        supabase.table("inbound_shipment_items")
        .select("inbound_shipment_item_id")
        .eq("inbound_shipment_id", shipment_id)
        .eq("item_id", item_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        return

    supabase.table("inbound_shipment_items").insert({
        "inbound_shipment_id": shipment_id,
        "item_id": item_id,
        "quantity_expected_in_package": quantity,
        "quantity_received_from_package": None,
        "received_verified": False,
        "notes": "Linked from eBay Trading API buyer purchase sync",
    }).execute()


def build_item_payload(
    purchase_id,
    transaction,
    tracking,
    dates,
    import_batch_id,
    existing_item=None,
    calculated_unit_cost=None,
    seller_shipped=False,
):
    quantity = transaction_quantity(transaction)
    ebay_title = transaction_title(transaction)
    title = (
        existing_item.get("title")
        if existing_item
        and existing_item.get("manual_title_override")
        and existing_item.get("title")
        else ebay_title
    )
    unit_cost = (
        existing_item.get("unit_cost")
        if existing_item
        and existing_item.get("manual_unit_cost_override")
        else calculated_unit_cost
        if calculated_unit_cost is not None
        else transaction_unit_cost(transaction)
    )
    existing_system = normalize_system(existing_item.get("system")) if existing_item else None
    detected_system = detect_system_from_title(ebay_title)
    existing_status = (
        (existing_item.get("current_status") or "").strip().lower()
        if existing_item
        else ""
    )

    return {
        "purchase_id": purchase_id,
        "asin": existing_item.get("asin") if existing_item else None,
        "supplier_sku": transaction_line_id(transaction),
        "title": title,
        "system": existing_system or detected_system,
        "quantity": quantity,
        "unit_cost": unit_cost,
        "target_price": existing_item.get("target_price") if existing_item else None,
        "current_status": derive_purchase_item_status(
            current_status=(
                existing_item.get("current_status") if existing_item else None
            ),
            tracking_number=tracking.get("tracking_number"),
            carrier_status=(
                "delivered" if dates.get("actual_delivery_time") else None
            ),
            delivered_date=dates.get("actual_delivery_time"),
            seller_shipped=seller_shipped,
        ),
        "condition": (
            existing_item.get("condition")
            if existing_item and existing_item.get("condition")
            else "unknown"
        ),
        "tracking_number": tracking.get("tracking_number"),
        "supplier_listing_url": (
            existing_item.get("supplier_listing_url")
            if existing_item
            else None
        ) or transaction_listing_url(transaction),
        "manual_title_override": (
            bool(existing_item.get("manual_title_override"))
            if existing_item
            else False
        ),
        "manual_unit_cost_override": (
            bool(existing_item.get("manual_unit_cost_override"))
            if existing_item
            else False
        ),
        "manual_split_child": (
            bool(existing_item.get("manual_split_child"))
            if existing_item
            else False
        ),
        "import_batch_id": import_batch_id,
        "raw_import_json": element_to_dict(transaction),
    }


def upsert_purchase_item(
    purchase_id,
    transaction,
    tracking,
    dates,
    import_batch_id,
    existing_items,
    used_item_ids,
    calculated_unit_cost=None,
    seller_shipped=False,
):
    matched_item = match_existing_item(
        existing_items=existing_items,
        transaction=transaction,
        used_item_ids=used_item_ids,
    )

    payload = build_item_payload(
        purchase_id=purchase_id,
        transaction=transaction,
        tracking=tracking,
        dates=dates,
        import_batch_id=import_batch_id,
        existing_item=matched_item,
        calculated_unit_cost=calculated_unit_cost,
        seller_shipped=seller_shipped,
    )

    if matched_item:
        item_id = matched_item["item_id"]
        used_item_ids.add(item_id)

        supabase.table("purchase_items").update(payload).eq(
            "item_id",
            item_id
        ).execute()

        return item_id

    item_result = supabase.table("purchase_items").insert(payload).execute()

    item_id = item_result.data[0]["item_id"]
    used_item_ids.add(item_id)

    return item_id


def build_unknown_item_payload(
    purchase_id,
    tracking,
    dates,
    import_batch_id,
    raw_order,
    existing_item=None,
    seller_shipped=False,
):
    title = (
        existing_item.get("title")
        if existing_item
        and (
            existing_item.get("manual_title_override")
            or existing_item.get("title")
        )
        else "Unknown eBay item"
    )
    unit_cost = (
        existing_item.get("unit_cost")
        if existing_item and existing_item.get("manual_unit_cost_override")
        else None
    )
    existing_system = normalize_system(existing_item.get("system")) if existing_item else None
    existing_status = (
        (existing_item.get("current_status") or "").strip().lower()
        if existing_item
        else ""
    )

    return {
        "purchase_id": purchase_id,
        "title": title,
        "quantity": (
            existing_item.get("quantity")
            if existing_item and existing_item.get("quantity")
            else 1
        ),
        "unit_cost": unit_cost,
        "asin": existing_item.get("asin") if existing_item else None,
        "target_price": existing_item.get("target_price") if existing_item else None,
        "system": existing_system or detect_system_from_title(title),
        "current_status": derive_purchase_item_status(
            current_status=(
                existing_item.get("current_status") if existing_item else None
            ),
            tracking_number=tracking.get("tracking_number"),
            carrier_status=(
                "delivered" if dates.get("actual_delivery_time") else None
            ),
            delivered_date=dates.get("actual_delivery_time"),
            seller_shipped=seller_shipped,
        ),
        "condition": (
            existing_item.get("condition")
            if existing_item and existing_item.get("condition")
            else "unknown"
        ),
        "tracking_number": tracking.get("tracking_number"),
        "supplier_listing_url": (
            existing_item.get("supplier_listing_url")
            if existing_item
            else None
        ),
        "manual_title_override": (
            bool(existing_item.get("manual_title_override"))
            if existing_item
            else False
        ),
        "manual_unit_cost_override": (
            bool(existing_item.get("manual_unit_cost_override"))
            if existing_item
            else False
        ),
        "manual_split_child": (
            bool(existing_item.get("manual_split_child"))
            if existing_item
            else False
        ),
        "import_batch_id": import_batch_id,
        "raw_import_json": raw_order,
    }


def upsert_purchase(order, import_batch_id):
    order_id = child_text(order, "OrderID")

    if not order_id:
        return "skipped_missing_order_id"

    existing_purchase = get_existing_purchase(order_id)

    if (
        SKIP_EXISTING_ORDERS_WITH_TRACKING
        and existing_purchase
        and purchase_has_tracking(existing_purchase["purchase_id"])
    ):
        return "skipped_existing_with_tracking"

    tracking = extract_tracking(order)
    dates = extract_delivery_dates(order)
    raw_order = element_to_dict(order)
    seller_shipped = order_has_shipped_time(order)

    purchase_payload = {
        "supplier": "eBay",
        "supplier_order_id": order_id,
        "order_date": get_created_date(order),
        "total_order_cost": get_order_total(order),
        "shipping_cost": get_order_shipping_cost(order),
        "tax_amount": get_order_tax_amount(order),
        "order_status": get_order_status(order),
        "import_batch_id": import_batch_id,
        "raw_import_json": raw_order,
    }

    if existing_purchase:
        purchase_id = existing_purchase["purchase_id"]

        supabase.table("purchases").update(purchase_payload).eq(
            "purchase_id",
            purchase_id
        ).execute()

    else:
        purchase_result = (
            supabase.table("purchases")
            .insert(purchase_payload)
            .execute()
        )

        purchase_id = purchase_result.data[0]["purchase_id"]

    shipment_id = upsert_inbound_shipment(
        purchase_id=purchase_id,
        tracking=tracking,
        dates=dates,
    )

    existing_items = get_existing_purchase_items(purchase_id)
    used_item_ids = set()

    transactions = extract_transactions(order)
    calculated_unit_costs = transaction_unit_costs(order, transactions)

    if not transactions:
        existing_item = existing_items[0] if existing_items else None

        item_payload = build_unknown_item_payload(
            purchase_id=purchase_id,
            tracking=tracking,
            dates=dates,
            import_batch_id=import_batch_id,
            raw_order=raw_order,
            existing_item=existing_item,
            seller_shipped=seller_shipped,
        )

        if existing_item:
            item_id = existing_item["item_id"]
            supabase.table("purchase_items").update(item_payload).eq(
                "item_id",
                item_id
            ).execute()
        else:
            item_result = supabase.table("purchase_items").insert(
                item_payload
            ).execute()
            item_id = item_result.data[0]["item_id"]

        link_shipment_item(
            shipment_id=shipment_id,
            item_id=item_id,
            quantity=item_payload["quantity"],
        )

        return "updated" if existing_purchase else "inserted"

    for index, transaction in enumerate(transactions):
        quantity = transaction_quantity(transaction)

        item_id = upsert_purchase_item(
            purchase_id=purchase_id,
            transaction=transaction,
            tracking=tracking,
            dates=dates,
            import_batch_id=import_batch_id,
            existing_items=existing_items,
            used_item_ids=used_item_ids,
            calculated_unit_cost=calculated_unit_costs[index],
            seller_shipped=seller_shipped,
        )

        link_shipment_item(
            shipment_id=shipment_id,
            item_id=item_id,
            quantity=quantity,
        )

    return "updated" if existing_purchase else "inserted"


def main():
    print("Starting eBay buyer purchase sync...")
    print(f"SKIP_EXISTING_ORDERS_WITH_TRACKING: {SKIP_EXISTING_ORDERS_WITH_TRACKING}")

    access_token = get_access_token()
    orders = get_buyer_orders(access_token)

    print(f"Buyer orders retrieved: {len(orders)}")

    import_batch_id = create_import_batch()

    inserted = 0
    updated = 0
    skipped_existing_with_tracking = 0
    skipped_missing_order_id = 0
    skipped_other = 0

    for index, order in enumerate(orders, start=1):
        result = upsert_purchase(order, import_batch_id)

        if result == "inserted":
            inserted += 1
        elif result == "updated":
            updated += 1
        elif result == "skipped_existing_with_tracking":
            skipped_existing_with_tracking += 1
        elif result == "skipped_missing_order_id":
            skipped_missing_order_id += 1
        else:
            skipped_other += 1

        if index % 25 == 0:
            print(f"Processed {index} of {len(orders)} orders...")

    print()
    print("eBay buyer purchase sync complete.")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")
    print(f"Skipped existing with tracking: {skipped_existing_with_tracking}")
    print(f"Skipped missing order id: {skipped_missing_order_id}")
    print(f"Skipped other: {skipped_other}")


if __name__ == "__main__":
    main()
