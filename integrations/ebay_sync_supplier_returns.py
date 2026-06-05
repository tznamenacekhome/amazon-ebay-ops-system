import os
import base64
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client


load_dotenv()

client_id = os.environ["EBAY_CLIENT_ID"].strip()
client_secret = os.environ["EBAY_CLIENT_SECRET"].strip()
refresh_token = os.environ["EBAY_REFRESH_TOKEN"].strip()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)


def iso(dt):
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def unwrap_value(value):
    if isinstance(value, dict):
        return value.get("value")
    return value


def money_value(obj):
    if not obj:
        return None
    obj = unwrap_value(obj)
    if isinstance(obj, dict):
        obj = obj.get("value")
    try:
        return float(obj)
    except Exception:
        return None


def money_currency(obj):
    if not obj:
        return None
    if isinstance(obj, dict):
        return obj.get("currency") or obj.get("currencyId")
    return None


def get_nested(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def get_access_token():
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join([
                "https://api.ebay.com/oauth/api_scope",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
                "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
                "https://api.ebay.com/oauth/api_scope/sell.account.readonly",
                "https://api.ebay.com/oauth/api_scope/sell.account",
                "https://api.ebay.com/oauth/api_scope/sell.finances",
                "https://api.ebay.com/oauth/api_scope/sell.payment.dispute",
            ])
        },
    )

    response.raise_for_status()
    return response.json()["access_token"]


def find_existing_return(return_id, order_id):
    if return_id:
        result = (
            supabase.table("supplier_returns")
            .select("supplier_return_id")
            .eq("ebay_return_id", return_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["supplier_return_id"]

    if order_id:
        result = (
            supabase.table("supplier_returns")
            .select("supplier_return_id")
            .eq("supplier_order_id", order_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["supplier_return_id"]

    return None


def find_purchase_item(order_id):
    if not order_id:
        return None

    purchase = (
        supabase.table("purchases")
        .select("purchase_id")
        .eq("supplier_order_id", order_id)
        .limit(1)
        .execute()
    )

    if not purchase.data:
        return None

    purchase_id = purchase.data[0]["purchase_id"]

    item = (
        supabase.table("purchase_items")
        .select("item_id")
        .eq("purchase_id", purchase_id)
        .limit(1)
        .execute()
    )

    if item.data:
        return item.data[0]["item_id"]

    return None


def get_returns(access_token):
    headers = {
        "Authorization": f"IAF {access_token}",
        "Content-Type": "application/json",
    }

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=365)

    response = requests.get(
        "https://api.ebay.com/post-order/v2/return/search",
        headers=headers,
        params={
            "limit": "50",
            "creation_date_range_from": iso(start_date),
            "creation_date_range_to": iso(end_date),
        },
    )

    response.raise_for_status()
    return response.json().get("members", [])


def map_return(ret):
    return_id = ret.get("returnId")
    order_id = ret.get("orderId")

    creation_info = ret.get("creationInfo", {})
    item_info = creation_info.get("item", {})

    buyer_refund = ret.get("buyerTotalRefund", {})
    estimated_refund = buyer_refund.get("estimatedRefundAmount")
    actual_refund = buyer_refund.get("actualRefundAmount")

    seller_due = ret.get("sellerResponseDue", {})
    buyer_due = ret.get("buyerResponseDue", {})

    escalation_info = ret.get("escalationInfo", {})
    buyer_escalation = escalation_info.get("buyerEscalationEligibilityInfo", {})
    seller_escalation = escalation_info.get("sellerEscalationEligibilityInfo", {})

    escalation_start = unwrap_value(
        buyer_escalation.get("startTime")
        or seller_escalation.get("startTime")
    )

    escalation_end = unwrap_value(
        buyer_escalation.get("endTime")
        or seller_escalation.get("endTime")
    )

    timeout_value = unwrap_value(get_nested(ret, "timeoutDate", "value"))

    return {
        "item_id": find_purchase_item(order_id),
        "supplier": "eBay",
        "supplier_order_id": order_id,
        "ebay_return_id": return_id,
        "ebay_case_id": return_id,
        "ebay_case_url": f"https://www.ebay.com/rtn/Return/ReturnsDetail?returnId={return_id}" if return_id else None,
        "ebay_order_url": f"https://www.ebay.com/mesh/ord/details?orderid={order_id}" if order_id else None,
        "ebay_item_id": item_info.get("itemId"),
        "marketplace_return_status": ret.get("status"),
        "case_status": ret.get("state"),
        "return_reason": creation_info.get("reason"),
        "resolution_type": ret.get("currentType"),
        "opened_date": unwrap_value(creation_info.get("creationDate")),
        "seller_response_deadline": unwrap_value(seller_due.get("respondByDate")),
        "return_ship_by_deadline": unwrap_value(buyer_due.get("respondByDate")),
        "escalation_available_date": escalation_start,
        "escalation_deadline_date": escalation_end,
        "last_activity_date": None,
        "refund_expected": money_value(estimated_refund),
        "refund_received": money_value(actual_refund),
        "refund_expected_currency": money_currency(estimated_refund),
        "refund_received_currency": money_currency(actual_refund),
        "buyer_username": ret.get("buyerLoginName"),
        "seller_username": ret.get("sellerLoginName"),
        "item_title": item_info.get("title"),
        "quantity_returned": item_info.get("quantity"),
        "follow_up_required": True,
        "next_action": None,
        "next_action_due_date": timeout_value,
        "raw_return_json": ret,
        "updated_at": iso(datetime.now(timezone.utc)),
    }


def upsert_return(ret):
    return_id = ret.get("returnId")
    order_id = ret.get("orderId")
    payload = map_return(ret)

    existing_id = find_existing_return(return_id, order_id)

    if existing_id:
        supabase.table("supplier_returns").update(payload).eq(
            "supplier_return_id", existing_id
        ).execute()
        print(f"Updated return: {return_id}")
        return "updated"

    supabase.table("supplier_returns").insert(payload).execute()
    print(f"Inserted return: {return_id}")
    return "inserted"


def main():
    print("Starting eBay supplier returns sync...")

    access_token = get_access_token()
    returns = get_returns(access_token)

    print(f"Returns retrieved: {len(returns)}")

    inserted = 0
    updated = 0

    for ret in returns:
        result = upsert_return(ret)

        if result == "inserted":
            inserted += 1
        elif result == "updated":
            updated += 1

    print("Supplier returns sync complete.")
    print(f"Inserted: {inserted}")
    print(f"Updated: {updated}")


if __name__ == "__main__":
    main()
