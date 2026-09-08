"""Shared read-only sourcing eligibility for previously declined item offers."""
from decimal import Decimal
from sourcing_common import chunked


def listing_id(candidate):
    parts = str(candidate.get("ebay_item_id") or "").split("|")
    if len(parts) == 3 and parts[2] != "0":
        return None
    price = candidate.get("offer_price") or (candidate.get("raw_ebay_json") or {}).get("price") or {}
    if price.get("currency", "USD") != "USD" or price.get("convertedFromCurrency", "USD") != "USD":
        return None
    item_id = str(candidate.get("ebay_legacy_item_id") or (parts[1] if len(parts) == 3 else parts[0]))
    return item_id if item_id.isascii() and item_id.isdigit() else None


def fetch_declines(db, candidates):
    ids = sorted({key for candidate in candidates if (key := listing_id(candidate))})
    result = {}
    for batch in chunked(ids, 100):
        rows = db.table("sourcing_declined_ebay_offers").select("ebay_legacy_item_id,declined_offer_amount").in_("ebay_legacy_item_id", batch).execute().data or []
        result.update({r["ebay_legacy_item_id"]: r["declined_offer_amount"] for r in rows})
    return result


def is_suppressed(candidate, opportunity_type, max_offer_price, declines):
    if opportunity_type != "best_offer":
        return False
    amount = declines.get(listing_id(candidate))
    if amount is None:
        return False
    return max_offer_price is None or Decimal(str(max_offer_price)).quantize(Decimal("0.01")) <= Decimal(str(amount))
