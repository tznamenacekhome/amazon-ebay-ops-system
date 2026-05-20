import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

def main():
    tracked = (
        supabase.table("purchase_items")
        .select("item_id", count="exact")
        .not_.is_("tracking_number", "null")
        .execute()
    )

    untracked = (
        supabase.table("purchase_items")
        .select("item_id", count="exact")
        .is_("tracking_number", "null")
        .execute()
    )

    print("Tracking summary")
    print("----------------")
    print(f"Tracked items: {tracked.count}")
    print(f"Untracked items: {untracked.count}")

    print()
    print("Sample tracked items")
    print("--------------------")

    samples = (
        supabase.table("purchase_items")
        .select("title, tracking_number, current_status")
        .not_.is_("tracking_number", "null")
        .limit(10)
        .execute()
    )

    for row in samples.data:
        print(row)

if __name__ == "__main__":
    main()