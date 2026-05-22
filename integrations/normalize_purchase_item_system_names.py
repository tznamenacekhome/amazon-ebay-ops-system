import os

from dotenv import load_dotenv
from supabase import create_client

try:
    from system_detection import normalize_system
except ImportError:
    from integrations.system_detection import normalize_system


PAGE_SIZE = 1000


def get_supabase_client():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variable."
        )

    return create_client(supabase_url, supabase_key)


def fetch_items_with_system(supabase, offset):
    return (
        supabase.table("purchase_items")
        .select("item_id,system")
        .not_.is_("system", "null")
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
        items = fetch_items_with_system(supabase, offset)

        if not items:
            break

        for item in items:
            scanned += 1
            current_system = item.get("system")
            normalized_system = normalize_system(current_system)

            if not normalized_system:
                skipped += 1
                continue

            if normalized_system == current_system:
                continue

            supabase.table("purchase_items").update({"system": normalized_system}).eq(
                "item_id",
                item["item_id"],
            ).execute()
            updated += 1

        if len(items) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    print("Purchase item system name normalization complete.")
    print(f"Scanned items with system: {scanned}")
    print(f"Updated: {updated}")
    print(f"Skipped unrecognized existing system: {skipped}")


if __name__ == "__main__":
    main()
