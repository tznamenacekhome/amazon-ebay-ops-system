import os

from dotenv import load_dotenv
from supabase import create_client

try:
    from system_detection import detect_system_from_title, normalize_system
except ImportError:
    from integrations.system_detection import detect_system_from_title, normalize_system


PAGE_SIZE = 1000


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def fetch_items_missing_system(supabase, offset):
    return (
        supabase.table("purchase_items")
        .select("item_id,title,system")
        .is_("system", "null")
        .range(offset, offset + PAGE_SIZE - 1)
        .execute()
        .data
        or []
    )


def main():
    load_dotenv()
    supabase = get_supabase_client()

    scanned = 0
    updated = 0
    skipped = 0
    offset = 0

    while True:
        items = fetch_items_missing_system(supabase, offset)

        if not items:
            break

        for item in items:
            scanned += 1
            system = normalize_system(item.get("system")) or detect_system_from_title(
                item.get("title")
            )

            if not system:
                skipped += 1
                continue

            supabase.table("purchase_items").update({"system": system}).eq(
                "item_id",
                item["item_id"],
            ).execute()
            updated += 1

        if len(items) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    print("Purchase item system backfill complete.")
    print(f"Scanned missing-system items: {scanned}")
    print(f"Updated: {updated}")
    print(f"Skipped no recognized system: {skipped}")


if __name__ == "__main__":
    main()
