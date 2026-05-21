import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def main():
    since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

    print(f"Looking for tracking numbers from purchases on or after {since}...")

    result = (
        supabase.table("purchases")
        .select("purchase_id, supplier_order_id, order_date, purchase_items(title, tracking_number)")
        .gte("order_date", since)
        .execute()
    )

    candidates = []

    for purchase in result.data:
        for item in purchase.get("purchase_items", []):
            tracking_number = item.get("tracking_number")

            if not tracking_number:
                continue

            tracking_number = tracking_number.strip()

            if tracking_number.lower() in ["no tracking", "none", "n/a", "na", "not available"]:
                continue

            candidates.append({
                "order_date": purchase.get("order_date"),
                "order_id": purchase.get("supplier_order_id"),
                "title": item.get("title"),
                "tracking_number": tracking_number,
            })

    print(f"Tracking candidates found: {len(candidates)}")

    for row in candidates[:10]:
        print()
        print(f"Order date: {row['order_date']}")
        print(f"Order ID: {row['order_id']}")
        print(f"Title: {row['title']}")
        print(f"Tracking: {row['tracking_number']}")


if __name__ == "__main__":
    main()