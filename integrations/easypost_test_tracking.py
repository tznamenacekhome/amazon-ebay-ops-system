import os
from dotenv import load_dotenv
import easypost
from supabase import create_client

load_dotenv()

client = easypost.EasyPostClient(os.environ["EASYPOST_API_KEY"])

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def main():
    print("Finding sample tracking number...")

    result = (
        supabase.table("inbound_shipments")
        .select("tracking_number")
        .limit(1)
        .execute()
    )

    if not result.data:
        print("No tracking numbers found.")
        return

    tracking_number = result.data[0]["tracking_number"]

    print(f"Testing tracking number: {tracking_number}")

    tracker = client.tracker.create(
        tracking_code=tracking_number
    )

    print()
    print("Tracker created successfully")
    print("--------------------------------")
    print(f"Carrier: {tracker.carrier}")
    print(f"Status: {tracker.status}")
    print(f"Estimated delivery: {tracker.est_delivery_date}")
    print(f"Tracking code: {tracker.tracking_code}")

    if tracker.tracking_details:
        latest = tracker.tracking_details[-1]

        print()
        print("Latest tracking detail")
        print("--------------------------------")
        print(f"Message: {latest.message}")
        print(f"Status: {latest.status}")
        print(f"Datetime: {latest.datetime}")
        print(f"Location: {latest.tracking_location}")


if __name__ == "__main__":
    main()