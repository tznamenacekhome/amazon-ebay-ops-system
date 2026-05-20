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

    response.raise_for_status()

    return response.json()["access_token"]


def main():
    access_token = get_access_token()

    headers = {
        "Authorization": f"IAF {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.get(
        "https://api.ebay.com/post-order/v2/return/search",
        headers=headers,
        params={"limit": "5"}
    )

    print("Status:", response.status_code)

    response.raise_for_status()

    data = response.json()

    print()
    print("Top level keys")
    print("----------------")

    for key in data.keys():
        print(key)

    returns = data.get("members", [])

    print()
    print(f"Returns found: {len(returns)}")

    if not returns:
        return

    first_return = returns[0]

    print()
    print("First return keys")
    print("------------------")

    for key in first_return.keys():
        print(key)

    print()
    print("Nested object keys")
    print("-------------------")

    for key, value in first_return.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for nested_key in value.keys():
                print(f"  - {nested_key}")

if __name__ == "__main__":
    main()