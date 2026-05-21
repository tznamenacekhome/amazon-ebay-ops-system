import os
import base64
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client


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
    if parent is None:
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


def get_access_token():
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

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
    )

    response.raise_for_status()
    return response.json()["access_token"]


def get_buyer_orders(access_token, days_back=30):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days_back)

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
    <PageNumber>1</PageNumber>
  </Pagination>
</GetOrdersRequest>"""

    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": "GetOrders",
        "X-EBAY-API-COMPATIBILITY-LEVEL": COMPATIBILITY_LEVEL,
        "X-EBAY-API-SITEID": SITE_ID,
        "X-EBAY-API-IAF-TOKEN": access_token,
    }

    response = requests.post(TRADING_ENDPOINT, headers=headers, data=xml_body)
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
        return []

    orders = []
    for elem in root.iter():
        if strip_namespace(elem.tag) == "Order":
            orders.append(elem)

    return orders


def get_order_id(order):
    return child_text(order, "OrderID")


def find_purchase(order_id):
    result = (
        supabase.table("purchases")
        .select("purchase_id")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]["purchase_id"]

    return None


def find_purchase_items(purchase_id):
    result = (
        supabase.table("purchase_items")
        .select("item_id, quantity")
        .eq("purchase_id", purchase_id)
        .execute()
    )

    return result.data or []


def extract_tracking_details(order):
    details = []

    for elem in order.iter():
        if strip_namespace(elem.tag) == "ShipmentTrackingDetails":
            carrier = child_text(elem, "ShippingCarrierUsed")
            tracking_number = child_text(elem, "ShipmentTrackingNumber")

            if tracking_number:
                details.append({
                    "carrier": carrier,
                    "tracking_number": tracking_number.strip(),
                })

    return details


def extract_delivery_dates(order):
    package_info = find_first(order, "ShippingPackageInfo")

    return {
        "actual_delivery_time": child_text(package_info, "ActualDeliveryTime"),
        "estimated_delivery_min": child_text(package_info, "EstimatedDeliveryTimeMin"),
        "estimated_delivery_max": child_text(package_info, "EstimatedDeliveryTimeMax"),
    }


def upsert_inbound_shipment(purchase_id, tracking_number, carrier, dates):
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
        "carrier": carrier,
        "shipment_status": "delivered" if dates.get("actual_delivery_time") else "unknown",
        "normalized_status": "delivered" if dates.get("actual_delivery_time") else "unknown",
        "estimated_delivery_date": dates.get("estimated_delivery_max"),
        "delivered_date": dates.get("actual_delivery_time"),
        "updated_at": iso(datetime.now(timezone.utc)),
    }

    if existing.data:
        shipment_id = existing.data[0]["inbound_shipment_id"]

        supabase.table("inbound_shipments").update(payload).eq(
            "inbound_shipment_id", shipment_id
        ).execute()

        return shipment_id, "updated"

    result = supabase.table("inbound_shipments").insert(payload).execute()

    return result.data[0]["inbound_shipment_id"], "inserted"


def link_shipment_items(shipment_id, purchase_id):
    items = find_purchase_items(purchase_id)

    inserted_links = 0

    for item in items:
        item_id = item["item_id"]
        quantity = item.get("quantity") or 1

        existing = (
            supabase.table("inbound_shipment_items")
            .select("inbound_shipment_item_id")
            .eq("inbound_shipment_id", shipment_id)
            .eq("item_id", item_id)
            .limit(1)
            .execute()
        )

        if existing.data:
            continue

        supabase.table("inbound_shipment_items").insert({
            "inbound_shipment_id": shipment_id,
            "item_id": item_id,
            "quantity_expected_in_package": quantity,
            "quantity_received_from_package": None,
            "received_verified": False,
            "notes": "Linked from eBay Trading API buyer tracking sync"
        }).execute()

        inserted_links += 1

    return inserted_links


def update_purchase_items_primary_tracking(purchase_id, tracking_number):
    supabase.table("purchase_items").update({
        "tracking_number": tracking_number,
        "current_status": "delivered"
    }).eq("purchase_id", purchase_id).execute()


def main():
    print("Starting eBay buyer tracking sync...")

    access_token = get_access_token()
    orders = get_buyer_orders(access_token, days_back=30)

    print(f"Buyer orders found: {len(orders)}")

    tracking_records_found = 0
    shipments_inserted = 0
    shipments_updated = 0
    links_inserted = 0
    unmatched_orders = 0

    for order in orders:
        order_id = get_order_id(order)

        if not order_id:
            continue

        purchase_id = find_purchase(order_id)

        if not purchase_id:
            unmatched_orders += 1
            continue

        tracking_details = extract_tracking_details(order)

        if not tracking_details:
            continue

        dates = extract_delivery_dates(order)

        for tracking in tracking_details:
            tracking_records_found += 1

            shipment_id, result = upsert_inbound_shipment(
                purchase_id=purchase_id,
                tracking_number=tracking["tracking_number"],
                carrier=tracking["carrier"],
                dates=dates
            )

            if result == "inserted":
                shipments_inserted += 1
            else:
                shipments_updated += 1

            links_inserted += link_shipment_items(shipment_id, purchase_id)

            update_purchase_items_primary_tracking(
                purchase_id,
                tracking["tracking_number"]
            )

            print(f"{result.title()} tracking for order {order_id}: {tracking['tracking_number']}")

    print()
    print("eBay buyer tracking sync complete.")
    print(f"Tracking records found: {tracking_records_found}")
    print(f"Shipments inserted: {shipments_inserted}")
    print(f"Shipments updated: {shipments_updated}")
    print(f"Shipment item links inserted: {links_inserted}")
    print(f"Orders not matched to purchases: {unmatched_orders}")


if __name__ == "__main__":
    main()