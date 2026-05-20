import os
import base64
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client


SYNC_NAME = "ebay_order_sync"

load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def get_access_token():
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
        },
    )

    response.raise_for_status()
    return response.json()["access_token"]


def get_last_successful_sync():
    result = (
        supabase.table("sync_logs")
        .select("last_successful_sync_at")
        .eq("sync_name", SYNC_NAME)
        .eq("sync_status", "success")
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]["last_successful_sync_at"]

    # First run: look back 7 days
    return iso(now_utc() - timedelta(days=7))


def start_sync_log(last_sync):
    result = (
        supabase.table("sync_logs")
        .insert({
            "sync_name": SYNC_NAME,
            "sync_status": "running",
            "last_successful_sync_at": last_sync,
            "notes": "Incremental eBay order sync started",
        })
        .execute()
    )

    return result.data[0]["sync_log_id"]


def complete_sync_log(sync_log_id, records_processed, records_inserted, records_updated):
    supabase.table("sync_logs").update({
        "sync_status": "success",
        "completed_at": iso(now_utc()),
        "last_successful_sync_at": iso(now_utc()),
        "records_processed": records_processed,
        "records_inserted": records_inserted,
        "records_updated": records_updated,
        "notes": "Incremental eBay order sync completed",
    }).eq("sync_log_id", sync_log_id).execute()


def fail_sync_log(sync_log_id, error_message):
    supabase.table("sync_logs").update({
        "sync_status": "failed",
        "completed_at": iso(now_utc()),
        "error_message": error_message,
    }).eq("sync_log_id", sync_log_id).execute()


def create_import_batch():
    result = supabase.table("import_batches").insert({
        "source_name": "eBay API Incremental Sync",
        "notes": "Automated incremental eBay order synchronization",
    }).execute()

    return result.data[0]["import_batch_id"]


def get_orders(access_token, modified_since):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    params = {
        "limit": "50",
        "filter": f"lastmodifieddate:[{modified_since}..]",
    }

    response = requests.get(
        "https://api.ebay.com/sell/fulfillment/v1/order",
        headers=headers,
        params=params,
    )

    response.raise_for_status()
    return response.json().get("orders", [])


def find_purchase(order_id):
    result = (
        supabase.table("purchases")
        .select("purchase_id")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )

    if result.data:
        return result.data[0]["purchase_id"]

    return None


def extract_tracking(order):
    instructions = order.get("fulfillmentStartInstructions", [])

    if not instructions:
        return None

    shipping_step = instructions[0].get("shippingStep", {})
    tracking_details = shipping_step.get("shipmentTrackingDetails", [])

    if not tracking_details:
        return None

    return tracking_details[0].get("shipmentTrackingNumber")


def upsert_order(order, import_batch_id):
    order_id = order.get("orderId")
    existing_purchase_id = find_purchase(order_id)

    pricing = order.get("pricingSummary", {})
    total_cost = None

    if pricing.get("total"):
        total_cost = float(pricing["total"].get("value", 0))

    if existing_purchase_id:
        supabase.table("purchases").update({
            "order_status": order.get("orderFulfillmentStatus"),
            "total_order_cost": total_cost,
            "raw_import_json": order,
        }).eq("purchase_id", existing_purchase_id).execute()

        tracking_number = extract_tracking(order)

        if tracking_number:
            supabase.table("purchase_items").update({
                "tracking_number": tracking_number,
                "current_status": "in_transit",
            }).eq("purchase_id", existing_purchase_id).execute()

        print(f"Updated existing order: {order_id}")
        return "updated"

    purchase_result = supabase.table("purchases").insert({
        "supplier": "eBay",
        "supplier_order_id": order_id,
        "order_date": order.get("creationDate"),
        "total_order_cost": total_cost,
        "order_status": order.get("orderFulfillmentStatus"),
        "import_batch_id": import_batch_id,
        "raw_import_json": order,
    }).execute()

    purchase_id = purchase_result.data[0]["purchase_id"]
    tracking_number = extract_tracking(order)

    for item in order.get("lineItems", []):
        quantity = item.get("quantity", 1)

        unit_cost = None
        if item.get("lineItemCost"):
            unit_cost = float(item["lineItemCost"].get("value", 0))

        supabase.table("purchase_items").insert({
            "purchase_id": purchase_id,
            "asin": None,
            "title": item.get("title") or "Unknown eBay item",
            "system": None,
            "quantity": quantity,
            "unit_cost": unit_cost,
            "target_price": None,
            "current_status": "in_transit" if tracking_number else "ordered",
            "condition": "unknown",
            "tracking_number": tracking_number,
            "supplier_listing_url": item.get("itemWebUrl"),
            "import_batch_id": import_batch_id,
            "raw_import_json": item,
        }).execute()

    print(f"Inserted new order: {order_id}")
    return "inserted"


def main():
    print("Starting incremental eBay order sync...")

    last_sync = get_last_successful_sync()
    print(f"Last successful sync: {last_sync}")

    sync_log_id = start_sync_log(last_sync)

    processed = 0
    inserted = 0
    updated = 0

    try:
        access_token = get_access_token()
        import_batch_id = create_import_batch()
        orders = get_orders(access_token, last_sync)

        print(f"Orders retrieved: {len(orders)}")

        for order in orders:
            result = upsert_order(order, import_batch_id)
            processed += 1

            if result == "inserted":
                inserted += 1
            elif result == "updated":
                updated += 1

        complete_sync_log(sync_log_id, processed, inserted, updated)

        print("Incremental eBay sync complete.")
        print(f"Processed: {processed}")
        print(f"Inserted: {inserted}")
        print(f"Updated: {updated}")

    except Exception as error:
        fail_sync_log(sync_log_id, str(error))
        print("Sync failed.")
        print(error)
        raise


if __name__ == "__main__":
    main()