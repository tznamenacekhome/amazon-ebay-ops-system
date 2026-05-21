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
    <EntriesPerPage>1</EntriesPerPage>
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

    print("Ack:", find_text(root, "Ack"))
    print("OrderID:", find_text(root, "OrderID"))

    search_terms = [
        "Tracking",
        "Shipment",
        "Shipping",
        "Delivery",
        "Carrier",
        "Package",
        "Fulfillment",
    ]

    print()
    print("Matching XML fields")
    print("-------------------")

    found = 0

    for elem in root.iter():
        tag = strip_namespace(elem.tag)

        if any(term.lower() in tag.lower() for term in search_terms):
            value = elem.text.strip() if elem.text and elem.text.strip() else ""
            print(f"{tag}: {value}")
            found += 1

    print()
    print(f"Matching fields found: {found}")


if __name__ == "__main__":
    main()