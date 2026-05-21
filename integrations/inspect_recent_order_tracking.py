import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

def main():
    result = (
    supabase.table("purchases")
    .select("supplier_order_id, order_date, raw_import_json")
    .eq("supplier", "eBay")
    .not_.is_("raw_import_json", "null")
    .not_.is_("order_date", "null")
    .order("created_at", desc=True)
    .limit(5)
    .execute()
)

    for purchase in result.data:
        raw = purchase.get("raw_import_json") or {}

        print()
        print("Order:", purchase.get("supplier_order_id"))
        print("Date:", purchase.get("order_date"))
        print("Order keys:", list(raw.keys()))

        print("Fulfillment status:", raw.get("orderFulfillmentStatus"))

        instructions = raw.get("fulfillmentStartInstructions", [])
        print("Fulfillment instructions count:", len(instructions))

        for i, instruction in enumerate(instructions):
            print(f"Instruction {i} keys:", list(instruction.keys()))

            shipping_step = instruction.get("shippingStep", {})
            print("Shipping step keys:", list(shipping_step.keys()))

            tracking_details = shipping_step.get("shipmentTrackingDetails", [])
            print("Tracking details count:", len(tracking_details))

            for detail in tracking_details:
                print("Tracking detail keys:", list(detail.keys()))
                print("Carrier:", detail.get("shippingCarrierCode"))
                print("Tracking:", detail.get("shipmentTrackingNumber"))

if __name__ == "__main__":
    main()