import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def get_count(table):
    return (
        supabase.table(table)
        .select("*", count="exact")
        .limit(1)
        .execute()
        .count
    )


def main():
    tracked_items = (
        supabase.table("purchase_items")
        .select("item_id", count="exact")
        .not_.is_("tracking_number", "null")
        .execute()
        .count
    )

    shipments = get_count("inbound_shipments")
    shipment_links = get_count("inbound_shipment_items")

    print("Inbound shipment backfill verification")
    print("--------------------------------------")
    print(f"Tracked purchase_items: {tracked_items}")
    print(f"Inbound shipments: {shipments}")
    print(f"Inbound shipment item links: {shipment_links}")

    print()
    print("Expected:")
    print("- shipment item links should equal tracked purchase_items")
    print("- inbound shipments may be lower if multiple items share one tracking number")


if __name__ == "__main__":
    main()