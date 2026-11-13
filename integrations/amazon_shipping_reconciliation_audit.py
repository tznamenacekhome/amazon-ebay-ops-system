"""Read-only, PII-free unit-level shipping reconciliation CSV for a shipped cohort."""
import argparse
import csv
import io
import json
from dotenv import load_dotenv
try:
    from .veeqo_sync_sales_labels import get_supabase_client, load_mf_orders, load_pages, shipping_required
    from .sales_shipping_costs import extract_shipments, order_label_cost, allocate_cost
    from .amazon_sales_profitability import amazon_shipping_label_cost
except ImportError:
    from veeqo_sync_sales_labels import get_supabase_client, load_mf_orders, load_pages, shipping_required
    from sales_shipping_costs import extract_shipments, order_label_cost, allocate_cost
    from amazon_sales_profitability import amazon_shipping_label_cost


def audit(client, asin, units=25):
    items = load_pages(client, "amazon_sales_order_items", "amazon_order_id,amazon_order_item_id,quantity_shipped,quantity_ordered",
                       lambda q: q.eq("asin", asin))
    orders = {o["amazon_order_id"]: o for o in load_mf_orders(client) if shipping_required(o)}
    items = sorted((i for i in items if i["amazon_order_id"] in orders),
                   key=lambda i: (orders[i["amazon_order_id"]]["purchase_date"], i["amazon_order_id"], i["amazon_order_item_id"]), reverse=True)
    result = []
    for item in items:
        if len(result) >= units:
            break
        oid = item["amazon_order_id"]
        sources = client.table("veeqo_sales_orders").select("raw_veeqo_order_json").eq("amazon_order_id", oid).execute().data or []
        payload = sources[0]["raw_veeqo_order_json"] if len(sources) == 1 else {}
        amount, reason = order_label_cost(payload)
        source = "veeqo_label"
        evidence = ";".join(str(s.get("id") or s.get("shipment_id")) for s in extract_shipments(payload))
        if amount is None:
            events = client.table("amazon_sales_financial_events").select("*").eq("amazon_order_id", oid).execute().data or []
            amazon = amazon_shipping_label_cost(events)
            if amazon is not None:
                amount, source, reason = amazon, "amazon_shipping_label", "reconciled"
                evidence = ";".join(e["financial_event_id"] for e in events if (e.get("raw_financial_event_json") or {}).get("event", {}).get("AdjustmentType", "").startswith(("PostageBilling_", "PostageRefund_")))
        all_items = client.table("amazon_sales_order_items").select("amazon_order_item_id,quantity_ordered,quantity_shipped").eq("amazon_order_id", oid).execute().data or []
        allocated = allocate_cost(amount, all_items).get(item["amazon_order_item_id"])
        stored = client.table("amazon_sales_profitability").select("fulfillment_cost,fulfillment_cost_source,cogs,data_status").eq("amazon_order_id", oid).eq("amazon_order_item_id", item["amazon_order_item_id"]).execute().data or [{}]
        quantity = int(item.get("quantity_shipped") or 0)
        for index in range(min(quantity, units - len(result))):
            result.append({"unit": len(result) + 1, "asin": asin, "purchase_date": orders[oid]["purchase_date"],
                "amazon_order_id": oid, "amazon_order_item_id": item["amazon_order_item_id"], "unit_within_item": index + 1,
                "shipped_item_quantity": quantity, "actual_order_shipping_usd": amount,
                "allocated_item_shipping_usd": allocated, "allocated_unit_shipping_usd": round(allocated / quantity, 4) if allocated is not None and quantity else None,
                "source": source if amount is not None else "missing", "source_ids": evidence,
                "veeqo_status": payload.get("status"), "veeqo_checked_at": (payload.get("_mbop_shipping_reconciliation") or {}).get("checked_at"),
                "reason": reason if payload else "missing_veeqo_match", "stored_item_fulfillment_cost": stored[0].get("fulfillment_cost"),
                "stored_source": stored[0].get("fulfillment_cost_source"), "cogs": stored[0].get("cogs"), "data_status": stored[0].get("data_status")})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asin", default="B092FLB415")
    parser.add_argument("--units", type=int, default=25)
    args = parser.parse_args()
    load_dotenv()
    rows = audit(get_supabase_client(), args.asin, args.units)
    print("AUDIT_JSON: " + json.dumps(rows))
    if rows:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        print("CSV_BEGIN\n" + output.getvalue() + "CSV_END")
    return 0 if len(rows) == args.units else 1


if __name__ == "__main__":
    raise SystemExit(main())
