"""Read buyer Best Offers; retain only explicit USD declines for sourcing.

Default is read-only. --apply writes compact evidence, never purchase data or
eBay offers. An incomplete/failed fetch must not be reported as a successful sync.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import requests

from refresh_sourcing_listing_availability_trading_fallback import get_access_token
from sourcing_common import get_supabase_client, load_environment, chunked

NS = {"e": "urn:ebay:apis:eBLBaseComponents"}


def request_body(token: str, page: int) -> bytes:
    # Match the working production Trading credential envelope; header-only
    # authentication returned eBay XML error 5 during the account preflight.
    return f'''<?xml version="1.0" encoding="utf-8"?>
<GetMyeBayBuyingRequest xmlns="urn:ebay:apis:eBLBaseComponents">
<RequesterCredentials><eBayAuthToken>{escape(token)}</eBayAuthToken></RequesterCredentials>
<BestOfferList><Include>true</Include><Pagination><EntriesPerPage>100</EntriesPerPage><PageNumber>{page}</PageNumber></Pagination></BestOfferList>
</GetMyeBayBuyingRequest>'''.encode()


def parse_page(xml: str) -> tuple[list[dict], int]:
    root = ET.fromstring(xml)
    if root.findtext("e:Ack", namespaces=NS) != "Success":
        # Fail on Warning too: partial/unsupported responses are not empty success.
        codes = [e.findtext("e:ErrorCode", namespaces=NS) for e in root.findall("e:Errors", NS)]
        raise RuntimeError(f"GetMyeBayBuying did not succeed; error codes: {codes}")
    container = root.find("e:BestOfferList", NS)
    if container is None:
        return [], 0
    pages_text = container.findtext("e:PaginationResult/e:TotalNumberOfPages", namespaces=NS)
    items = container.findall("e:ItemArray/e:Item", NS)
    if pages_text is None and items:
        raise RuntimeError("BestOfferList omitted pagination metadata")
    pages = int(pages_text or "0")
    rows = []
    for item in items:
        amount = item.find("e:BestOfferDetails/e:BestOffer", NS)
        row = {
            "ebay_legacy_item_id": item.findtext("e:ItemID", default="", namespaces=NS),
            "status": item.findtext("e:BestOfferDetails/e:BestOfferStatus", default="", namespaces=NS),
            "currency": amount.get("currencyID") if amount is not None else None,
            "amount": amount.text if amount is not None else None,
            "variation": item.find("e:Variations", NS) is not None or item.find("e:Variation", NS) is not None,
        }
        rows.append(row)
    return rows, pages


def fetch_offers(token: str, max_pages: int = 20, post=requests.post) -> list[dict]:
    rows = []
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(0.2)
        response = post("https://api.ebay.com/ws/api.dll", headers={
            "Content-Type": "text/xml",
            "X-EBAY-API-CALL-NAME": "GetMyeBayBuying",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1423",
            "X-EBAY-API-SITEID": "0",
            "X-EBAY-API-IAF-TOKEN": token,
        }, data=request_body(token, page), timeout=60)
        response.raise_for_status()
        page_rows, pages = parse_page(response.text)
        rows.extend(page_rows)
        if page >= pages:
            return rows
        if not page_rows:
            raise RuntimeError("BestOfferList returned an empty page before its reported end")
    raise RuntimeError(f"BestOfferList exceeds bounded {max_pages}-page sync; no evidence written")


def declined_evidence(rows: list[dict]) -> list[dict]:
    highest: dict[str, Decimal] = {}
    for row in rows:
        if row.get("status") != "Declined" or row.get("currency") != "USD" or row.get("variation"):
            continue
        item_id = row.get("ebay_legacy_item_id") or ""
        if not item_id.isascii() or not item_id.isdigit():
            continue
        try:
            amount = Decimal(str(row.get("amount")))
            if not amount.is_finite() or amount <= 0 or amount >= Decimal("10000000000"):
                continue
            if amount != amount.quantize(Decimal("0.01")):
                continue
        except InvalidOperation:
            continue
        highest[item_id] = max(highest.get(item_id, Decimal(0)), amount)
    return [{"ebay_legacy_item_id": item_id, "declined_offer_amount": str(amount)} for item_id, amount in highest.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_environment()
    rows = fetch_offers(get_access_token())
    evidence = declined_evidence(rows)
    if args.apply:
        db = get_supabase_client()
        for batch in chunked(evidence, 100):
            db.rpc("record_sourcing_declined_offers", {"offers": batch}).execute()
    print(json.dumps({"offers_returned": len(rows), "statuses": dict(Counter(r["status"] for r in rows)),
                      "declined_usd_listings": len(evidence), "applied": args.apply}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
