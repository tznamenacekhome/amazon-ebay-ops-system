import os
import base64
import json
import requests
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
            "scope": " ".join([
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            ])
        },
    )

    response.raise_for_status()
    return response.json()["access_token"]


def main():
    access_token = get_access_token()

    orders = (
        supabase.table("purchases")
        .select("supplier_order_id, order_date")
        .eq("supplier", "eBay")
        .not_.is_("order_date", "null")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    for order in orders.data:
        order_id = order["supplier_order_id"]

        print()
        print(f"Order: {order_id}")
        print(f"Date: {order.get('order_date')}")

        url = f"https://api.ebay.com/sell/fulfillment/v1/order/{order_id}/shipping_fulfillment"

        response = requests.get(url, headers=headers)

        print("Status:", response.status_code)

        if response.status_code != 200:
            print(response.text)
            continue

        data = response.json()
        print("Top keys:", list(data.keys()))

        members = data.get("members", [])
        print("Fulfillments found:", len(members))

        for fulfillment in members:
            print("Fulfillment keys:", list(fulfillment.keys()))
            print("Carrier:", fulfillment.get("shippingCarrierCode"))
            print("Tracking:", fulfillment.get("trackingNumber"))
            print("Shipped date:", fulfillment.get("shippedDate"))
            print("Line items:", json.dumps(fulfillment.get("lineItems", []), indent=2))


if __name__ == "__main__":
    main()