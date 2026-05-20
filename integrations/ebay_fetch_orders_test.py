import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()

def get_access_token():
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    }

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers=headers,
        data=data,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def main():
    print("Getting fresh eBay access token...")
    access_token = get_access_token()

    print("Fetching recent eBay orders...")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    params = {
        "limit": "10",
    }

    response = requests.get(
        "https://api.ebay.com/sell/fulfillment/v1/order",
        headers=headers,
        params=params,
    )

    print("Status code:", response.status_code)
    print(response.text)


if __name__ == "__main__":
    main()