import os
import base64
import requests
from urllib.parse import unquote
from dotenv import load_dotenv

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
runame = os.environ["EBAY_RUNAME"].strip()

raw_code = input("Paste ONLY the code value after code= and before &: ").strip()

# eBay returns the code URL-encoded in the browser URL.
# Decode it once before sending to token endpoint.
auth_code = unquote(raw_code)

credentials = f"{client_id}:{client_secret}"
encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Authorization": f"Basic {encoded_credentials}",
}

data = {
    "grant_type": "authorization_code",
    "code": auth_code,
    "redirect_uri": runame,
}

print("Using Client ID starts with:", client_id[:8])
print("Using RuName:", runame)
print("Raw code starts with:", raw_code[:20])
print("Decoded code starts with:", auth_code[:20])

response = requests.post(
    "https://api.ebay.com/identity/v1/oauth2/token",
    headers=headers,
    data=data,
)

print("Status code:", response.status_code)
print(response.text)