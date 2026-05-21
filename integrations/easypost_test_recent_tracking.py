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
    print("Finding recent tracking numbers...")

    result = (
        supabase.table("inbound_shipments")
        .select("tracking_number, created_at")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )

    if not result.data:
        print("No tracking numbers found.")
        return

    for row in result.data:
        tracking_number = row["tracking_number"]
        print()
        print(f"Testing tracking number: {tracking_number}")

        try:
            tracker = client.tracker.create(
                tracking_code=tracking_number
            )

            print(f"Carrier: {tracker.carrier}")
            print(f"Status: {tracker.status}")
            print(f"Estimated delivery: {tracker.est_delivery_date}")
            print(f"Tracking code: {tracker.tracking_code}")

            if tracker.tracking_details:
                latest = tracker.tracking_details[-1]
                print("Latest message:", latest.message)
                print("Latest status:", latest.status)
                print("Latest datetime:", latest.datetime)
            else:
                print("No tracking details returned.")

        except Exception as error:
            print("EasyPost error:", error)


if __name__ == "__main__":
    main()