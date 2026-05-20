import os
from dotenv import load_dotenv
from supabase import create_client


def get_count(supabase, table):
    result = supabase.table(table).select("*", count="exact").limit(1).execute()
    return result.count


def main():
    print("Starting data quality analysis...")

    load_dotenv()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )

    total_items = get_count(supabase, "purchase_items")
    total_purchases = get_count(supabase, "purchases")
    total_returns = get_count(supabase, "supplier_returns")

    print()
    print("Table counts")
    print("------------")
    print(f"purchases: {total_purchases}")
    print(f"purchase_items: {total_items}")
    print(f"supplier_returns: {total_returns}")

    print()
    print("Purchase item status counts")
    print("---------------------------")

    statuses = (
        supabase.table("purchase_items")
        .select("current_status")
        .execute()
    )

    status_counts = {}
    for row in statuses.data:
        status = row.get("current_status") or "blank"
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in sorted(status_counts.items()):
        print(f"{status}: {count}")

    print()
    print("Return linkage")
    print("--------------")

    linked_returns = (
        supabase.table("supplier_returns")
        .select("supplier_return_id")
        .not_.is_("item_id", "null")
        .execute()
    )

    unlinked_returns = (
        supabase.table("supplier_returns")
        .select("supplier_return_id")
        .is_("item_id", "null")
        .execute()
    )

    print(f"linked supplier returns: {len(linked_returns.data)}")
    print(f"unlinked supplier returns: {len(unlinked_returns.data)}")

    print()
    print("Tracking coverage")
    print("-----------------")

    tracked_items = (
        supabase.table("purchase_items")
        .select("item_id")
        .not_.is_("tracking_number", "null")
        .execute()
    )

    untracked_items = (
        supabase.table("purchase_items")
        .select("item_id")
        .is_("tracking_number", "null")
        .execute()
    )

    print(f"items with tracking: {len(tracked_items.data)}")
    print(f"items without tracking: {len(untracked_items.data)}")

    print()
    print("Sample unlinked returns")
    print("-----------------------")

    sample_returns = (
        supabase.table("supplier_returns")
        .select("supplier_order_id, refund_expected, opened_date, shipped_date, notes")
        .is_("item_id", "null")
        .limit(10)
        .execute()
    )

    for row in sample_returns.data:
        print(row)

    print()
    print("Analysis complete.")


if __name__ == "__main__":
    main()