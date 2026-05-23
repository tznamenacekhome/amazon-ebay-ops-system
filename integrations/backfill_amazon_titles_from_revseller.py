import os

from dotenv import load_dotenv
from supabase import create_client

import sync_revseller_sheet


PAGE_SIZE = 1000


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def fetch_items_with_asin(supabase, offset):
    return (
        supabase.table("purchase_items")
        .select("item_id,asin,amazon_title")
        .not_.is_("asin", "null")
        .range(offset, offset + PAGE_SIZE - 1)
        .execute()
        .data
        or []
    )


def build_title_by_asin(revseller_rows):
    title_by_asin = {}

    for row in revseller_rows:
        existing = title_by_asin.get(row["asin"])
        if existing is None or row["row_date"] >= existing["row_date"]:
            title_by_asin[row["asin"]] = row

    return {
        asin: row["raw_title"]
        for asin, row in title_by_asin.items()
    }


def main():
    load_dotenv()

    sync_revseller_sheet.REVSELLER_SHEET_ID = os.getenv("REVSELLER_GOOGLE_SHEET_ID")
    sync_revseller_sheet.REVSELLER_WORKSHEET_NAME = os.getenv(
        "REVSELLER_WORKSHEET_NAME",
        "Sheet1",
    )

    supabase = get_supabase_client()
    revseller_rows = sync_revseller_sheet.load_revseller_rows()
    title_by_asin = build_title_by_asin(revseller_rows)

    scanned = 0
    updated = 0
    skipped_no_title = 0
    offset = 0

    while True:
        items = fetch_items_with_asin(supabase, offset)

        if not items:
            break

        for item in items:
            scanned += 1
            amazon_title = title_by_asin.get(item.get("asin"))

            if not amazon_title:
                skipped_no_title += 1
                continue

            if item.get("amazon_title") == amazon_title:
                continue

            supabase.table("purchase_items").update({"amazon_title": amazon_title}).eq(
                "item_id",
                item["item_id"],
            ).execute()
            updated += 1

        if len(items) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    print("Amazon title backfill complete.")
    print(f"Scanned matched items: {scanned}")
    print(f"Updated: {updated}")
    print(f"Skipped no RevSeller title for ASIN: {skipped_no_title}")


if __name__ == "__main__":
    main()
