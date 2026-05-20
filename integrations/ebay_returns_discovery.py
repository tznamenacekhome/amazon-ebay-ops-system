import os
import base64
import json
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()


def get_access_token():
    credentials = f"{client_id}:{client_secret}"

    encoded_credentials = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join([
            "https://api.ebay.com/oauth/api_scope",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
            "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
            "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
            "https://api.ebay.com/oauth/api_scope/sell.account",
            "https://api.ebay.com/oauth/api_scope/sell.finances",
            "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
        ])
    }

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers=headers,
        data=data,
    )

    print("Token status:", response.status_code)

    response.raise_for_status()

    return response.json()["access_token"]


def main():
    access_token = get_access_token()

    headers = {
        "Authorization": f"IAF {access_token}",
        "Content-Type": "application/json",
    }

    url = "https://api.ebay.com/post-order/v2/return/search"

    params = {
        "limit": "10"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    print("Returns search status:", response.status_code)

    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)


if __name__ == "__main__":
    main()