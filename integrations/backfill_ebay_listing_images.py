"""Repair explicitly selected purchase images; default is read-only preview."""
import argparse
import re

try:
    from ebay_sync_buyer_purchases import get_access_token, supabase
    from ebay_listing_images import attach_listing_images, listing_picture_urls
except ImportError:
    from integrations.ebay_sync_buyer_purchases import get_access_token, supabase
    from integrations.ebay_listing_images import attach_listing_images, listing_picture_urls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if len(args.item_id) > 25:
        parser.error("At most 25 explicitly selected items per run")
    access = get_access_token()
    for item_id in dict.fromkeys(args.item_id):
        item = supabase.table("purchase_items").select(
            "item_id,supplier_listing_url,supplier_sku,raw_import_json"
        ).eq("item_id", item_id).single().execute().data
        match = re.search(r"/itm/(?:[^/?]+/)?(\d{9,15})(?:[/?]|$)", item.get("supplier_listing_url") or "")
        match = match or re.match(r"^(\d{9,15})(?:-|$)", item.get("supplier_sku") or "")
        if not match:
            print(f"{item_id}: no exact eBay listing ID; skipped")
            continue
        legacy_id = match.group(1)
        urls = listing_picture_urls(access, legacy_id)
        print(f"{item_id}: listing {legacy_id}, {len(urls)} original photos; {'apply' if args.apply else 'preview'}")
        if args.apply and urls:
            # Re-read immediately before updating to preserve other raw metadata.
            current = supabase.table("purchase_items").select("raw_import_json").eq("item_id", item_id).single().execute().data
            raw = attach_listing_images(current.get("raw_import_json"), legacy_id, urls)
            supabase.table("purchase_items").update({"raw_import_json": raw}).eq("item_id", item_id).execute()
            saved = supabase.table("purchase_items").select("raw_import_json").eq("item_id", item_id).single().execute().data
            if saved.get("raw_import_json", {}).get("mbop_listing_images", {}).get("PictureURL") != urls:
                raise RuntimeError(f"{item_id}: image write verification failed")
            print(f"{item_id}: saved and verified")


if __name__ == "__main__":
    main()
