import os
import base64
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()

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


def strip_namespace(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def find_text(parent, name):
    if parent is None:
        return None

    for elem in parent.iter():
        if strip_namespace(elem.tag) == name:
            return elem.text

    return None


def main():
    access_token = get_access_token()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

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
    <EntriesPerPage>10</EntriesPerPage>
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

    print("Status:", response.status_code)

    root = ET.fromstring(response.text)

    ack = find_text(root, "Ack")
    print("Ack:", ack)

    error = find_text(root, "LongMessage")
    if error:
        print("Error:", error)

    orders = []
    for elem in root.iter():
        if strip_namespace(elem.tag) == "Order":
            orders.append(elem)

    print("Orders found:", len(orders))

    for order in orders[:5]:
        print()
        print("OrderID:", find_text(order, "OrderID"))
        print("Created:", find_text(order, "CreatedTime"))
        print("Status:", find_text(order, "OrderStatus"))

        shipping_details = None
        for child in order.iter():
            if strip_namespace(child.tag) == "ShippingDetails":
                shipping_details = child
                break

        print("ShipmentTrackingNumber:", find_text(shipping_details, "ShipmentTrackingNumber"))
        print("ShippingCarrierUsed:", find_text(shipping_details, "ShippingCarrierUsed"))


if __name__ == "__main__":
    main()