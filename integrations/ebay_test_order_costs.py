import os
import sys
import csv
import base64
import requests
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from dotenv import load_dotenv


TEST_ORDER_IDS = [
    "27-14616-40271",
    "09-14517-77527",
    "18-14437-88058",
]

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
TOKEN_ENDPOINT = "https://api.ebay.com/identity/v1/oauth2/token"
COMPATIBILITY_LEVEL = "1423"
SITE_ID = "0"
OUTPUT_CSV = "ebay_test_order_costs_output.csv"

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}


def money(value):
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def find_text(node, path):
    found = node.find(path, NS)
    return found.text if found is not None else None


def get_required_env(name):
    value = os.getenv(name)
    if not value:
        print(f"Missing environment variable: {name}")
        sys.exit(1)
    return value.strip()


def get_access_token(client_id, client_secret, refresh_token):
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        TOKEN_ENDPOINT,
        headers={
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        timeout=60,
    )

    if not response.ok:
        print("Failed to get eBay access token.")
        print(response.status_code)
        print(response.text)
        sys.exit(1)

    return response.json()["access_token"]


def get_orders(access_token):
    order_id_xml = "".join(f"<OrderID>{order_id}</OrderID>" for order_id in TEST_ORDER_IDS)

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{access_token}</eBayAuthToken>
  </RequesterCredentials>
  <OrderIDArray>
    {order_id_xml}
  </OrderIDArray>
  <OrderRole>Buyer</OrderRole>
  <OrderStatus>All</OrderStatus>
  <DetailLevel>ReturnAll</DetailLevel>
</GetOrdersRequest>
"""

    response = requests.post(
        TRADING_ENDPOINT,
        data=body.encode("utf-8"),
        headers={
            "X-EBAY-API-CALL-NAME": "GetOrders",
            "X-EBAY-API-SITEID": SITE_ID,
            "X-EBAY-API-COMPATIBILITY-LEVEL": COMPATIBILITY_LEVEL,
            "Content-Type": "text/xml",
        },
        timeout=60,
    )

    if not response.ok:
        print("Failed to call eBay GetOrders.")
        print(response.status_code)
        print(response.text)
        sys.exit(1)

    return response.text


def main():
    load_dotenv()

    client_id = get_required_env("EBAY_CLIENT_ID")
    client_secret = get_required_env("EBAY_CLIENT_SECRET")
    refresh_token = get_required_env("EBAY_REFRESH_TOKEN")

    access_token = get_access_token(client_id, client_secret, refresh_token)
    xml_text = get_orders(access_token)

    root = ET.fromstring(xml_text)
    print(f"eBay Ack: {find_text(root, 'e:Ack')}")

    rows = []

    for order in root.findall(".//e:Order", NS):
        order_id = find_text(order, "e:OrderID")
        order_total = money(find_text(order, "e:Total"))
        order_subtotal = money(find_text(order, "e:Subtotal"))
        order_shipping_selected = money(find_text(order, "e:ShippingServiceSelected/e:ShippingServiceCost"))

        print("\n" + "=" * 100)
        print(f"ORDER: {order_id}")
        print(f"ORDER SUBTOTAL: ${order_subtotal}")
        print(f"ORDER SHIPPING SELECTED: ${order_shipping_selected}")
        print(f"ORDER TOTAL: ${order_total}")
        print("=" * 100)

        calculated_order_total = Decimal("0.00")

        for txn in order.findall(".//e:Transaction", NS):
            title = find_text(txn, "e:Item/e:Title") or "(No title found)"
            quantity = int(find_text(txn, "e:QuantityPurchased") or "1")

            item_price_each = money(find_text(txn, "e:TransactionPrice"))
            item_subtotal = item_price_each * quantity

            actual_shipping = money(find_text(txn, "e:ActualShippingCost"))
            actual_handling = money(find_text(txn, "e:ActualHandlingCost"))

            landed_line_total = item_subtotal + actual_shipping + actual_handling
            unit_cost = (landed_line_total / quantity).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            calculated_order_total += landed_line_total

            print(f"ITEM: {title}")
            print(f"QTY: {quantity}")
            print(f"ITEM PRICE EACH: ${item_price_each}")
            print(f"ITEM SUBTOTAL: ${item_subtotal}")
            print(f"ACTUAL SHIPPING: ${actual_shipping}")
            print(f"ACTUAL HANDLING: ${actual_handling}")
            print(f"NEW UNIT COST: ${unit_cost}")
            print(f"NEW LINE TOTAL: ${landed_line_total}")
            print("-" * 100)

            rows.append({
                "order_id": order_id,
                "title": title,
                "quantity": quantity,
                "item_price_each": str(item_price_each),
                "item_subtotal": str(item_subtotal),
                "actual_shipping": str(actual_shipping),
                "actual_handling": str(actual_handling),
                "new_unit_cost": str(unit_cost),
                "new_line_total": str(landed_line_total),
                "order_subtotal": str(order_subtotal),
                "order_shipping_selected": str(order_shipping_selected),
                "order_total": str(order_total),
            })

        difference = (order_total - calculated_order_total).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        print(f"CALCULATED ORDER TOTAL FROM ITEMS: ${calculated_order_total}")
        print(f"DIFFERENCE VS EBAY ORDER TOTAL: ${difference}")

    returned_ids = {row["order_id"] for row in rows}
    missing_ids = [order_id for order_id in TEST_ORDER_IDS if order_id not in returned_ids]

    if missing_ids:
        print("\nOrders requested but not returned:")
        for order_id in missing_ids:
            print(f"- {order_id}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "order_id",
            "title",
            "quantity",
            "item_price_each",
            "item_subtotal",
            "actual_shipping",
            "actual_handling",
            "new_unit_cost",
            "new_line_total",
            "order_subtotal",
            "order_shipping_selected",
            "order_total",
        ]

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\nDone.")
    print(f"CSV output created: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()