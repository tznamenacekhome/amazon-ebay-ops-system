"""Seller listing identity includes marketplace, fulfillment method, and MSKU."""

FBA_CHANNELS = {"AMAZON", "AMAZON_NA", "AFN", "FBA"}
MF_CHANNELS = {"DEFAULT", "MFN", "MF", "FBM", "MERCHANT", "MERCHANT_NA"}


def fulfillment_method(channel):
    value = str(channel or "").strip().upper()
    if value in FBA_CHANNELS:
        return "FBA"
    if value in MF_CHANNELS:
        return "MF"
    return None


def sku_identity(marketplace, channel, seller_sku):
    method = fulfillment_method(channel)
    sku = str(seller_sku or "").strip()
    return (marketplace, method, sku) if marketplace and method and sku else None
