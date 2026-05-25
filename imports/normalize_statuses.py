import os
from dotenv import load_dotenv
from supabase import create_client


LOCKED_STATUSES = [
    "cancelled",
    "listed",
    "received",
    "return_opened",
    "return_pending",
]


def main():
    print("Starting status normalization...")

    load_dotenv()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )

    # 1. Mark items with supplier returns as return_opened
    returns = (
        supabase.table("supplier_returns")
        .select("item_id")
        .not_.is_("item_id", "null")
        .execute()
    )

    returned_item_ids = [row["item_id"] for row in returns.data]

    print(f"Returned items found: {len(returned_item_ids)}")

    for item_id in returned_item_ids:
        supabase.table("purchase_items").update({
            "current_status": "return_opened"
        }).eq("item_id", item_id).execute()

    # 2. Mark non-returned, non-workflow-locked items with tracking as in_transit
    tracked_items = (
        supabase.table("purchase_items")
        .select("item_id")
        .not_.is_("tracking_number", "null")
        .not_.in_("current_status", LOCKED_STATUSES)
        .execute()
    )

    print(f"Tracked non-locked items found: {len(tracked_items.data)}")

    for row in tracked_items.data:
        supabase.table("purchase_items").update({
            "current_status": "in_transit"
        }).eq("item_id", row["item_id"]).execute()

    # 3. Mark non-returned, non-workflow-locked items without tracking as ordered
    untracked_items = (
        supabase.table("purchase_items")
        .select("item_id")
        .is_("tracking_number", "null")
        .not_.in_("current_status", LOCKED_STATUSES)
        .execute()
    )

    print(f"Untracked non-locked items found: {len(untracked_items.data)}")

    for row in untracked_items.data:
        supabase.table("purchase_items").update({
            "current_status": "ordered"
        }).eq("item_id", row["item_id"]).execute()

    print("Status normalization complete.")


if __name__ == "__main__":
    main()
