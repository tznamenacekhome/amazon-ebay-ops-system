import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError
from amazon_orders_2026 import normalize_order, normalize_item, preserve_missing_fields
import amazon_sync_sales_orders as sync
from amazon_sync_sales_orders import build_order_row, build_item_row, fetch_orders, order_items_are_current


def amount(value):
    return {"amount": value, "currencyCode": "USD"}


def sample():
    return {
        "orderId": "test-order", "createdTime": "2026-10-15T01:59:43.504Z",
        "lastUpdatedTime": "2026-10-17T15:28:08.066Z",
        "salesChannel": {"marketplaceId": "US", "marketplaceName": "Amazon.com"},
        "fulfillment": {"fulfillmentStatus": "SHIPPED", "fulfilledBy": "AMAZON"},
        "proceeds": {"grandTotal": amount("74.18")},
        "buyer": {"buyerEmail": "must-not-persist@example.test"},
        "recipient": {"deliveryAddress": {"name": "must-not-persist"}},
        "orderItems": [{
            "orderItemId": "test-item", "quantityOrdered": 2,
            "product": {"asin": "TESTASIN", "title": "Example game", "sellerSku": "test-sku",
                        "condition": {"conditionType": "USED", "conditionSubtype": "VERY_GOOD"},
                        "customization": {"customerData": "must-not-persist"}},
            "fulfillment": {"quantityFulfilled": 2, "quantityUnfulfilled": 0,
                            "packing": {"giftMessage": "must-not-persist"}},
            "proceeds": {"breakdowns": [
                {"type": "ITEM", "subtotal": amount("69.98")},
                {"type": "SHIPPING", "subtotal": amount("6.99")},
                {"type": "TAX", "subtotal": amount("4.20"), "detailedBreakdowns": [{"subtype": "ITEM", "value": amount("4.20")}]},
                {"type": "DISCOUNT", "subtotal": amount("6.99"), "detailedBreakdowns": [{"subtype": "SHIPPING", "value": amount("6.99")}]},
            ]},
        }],
    }


class Orders2026Tests(unittest.TestCase):
    def test_shipping_discount_is_not_counted_twice(self):
        normalized = normalize_order(sample())
        row = build_item_row("test-order", normalized["_order_items"][0])
        self.assertEqual(row["item_price_amount"], 69.98)
        self.assertEqual(row["shipping_price_amount"], 6.99)
        self.assertEqual(row["item_promotion_discount_amount"], 0)
        self.assertEqual(row["ship_promotion_discount_amount"], 6.99)
        self.assertEqual(row["shipping_tax_amount"], 0)
        self.assertEqual(row["item_tax_amount"], 4.2)
        self.assertEqual(row["quantity_shipped"], 2)
        self.assertEqual(row["condition_subtype_id"], "VeryGood")

    def test_projection_does_not_persist_unsolicited_pii_or_embedded_items(self):
        normalized = normalize_order(sample())
        row = build_order_row(normalized, "batch")
        self.assertNotIn("must-not-persist", str(row))
        self.assertNotIn("must-not-persist", str(normalized))
        self.assertNotIn("_order_items", row["raw_order_json"])

    def test_pending_omissions_preserve_known_values_but_zero_updates(self):
        normalized = normalize_order(sample())
        normalized["OrderTotal"] = None
        row = preserve_missing_fields(build_order_row(normalized, "batch"), {
            "order_total_amount": 74.18, "payment_method": "Other", "is_prime": True,
        })
        self.assertEqual(row["order_total_amount"], 74.18)
        self.assertEqual(row["payment_method"], "Other")
        self.assertTrue(row["is_prime"])
        self.assertEqual(preserve_missing_fields({"quantity_shipped": 0}, {"quantity_shipped": 2})["quantity_shipped"], 0)

    def test_legacy_status_channel_programs_cancellation_and_dates(self):
        value = sample()
        value["fulfillment"] = {"fulfillmentStatus": "CANCELLED", "fulfilledBy": "MERCHANT"}
        value["programs"] = ["PRIME", "AMAZON_BUSINESS"]
        value["orderItems"][0]["cancellation"] = {"cancellationRequest": {"requester": "BUYER"}}
        row = build_order_row(normalize_order(value), "batch")
        self.assertEqual(row["order_status"], "Canceled")
        self.assertEqual(row["fulfillment_channel"], "MFN")
        self.assertTrue(row["is_prime"])
        self.assertTrue(row["buyer_requested_cancel"])
        self.assertEqual(row["number_of_items_shipped"], 2)
        self.assertTrue(order_items_are_current(normalize_order(value), {"last_update_date": "2026-10-17T15:28:08+00:00", "item_count": 1}))

    def test_missing_items_fail_closed_and_mixed_currency_rejected(self):
        value = sample(); del value["orderItems"]
        with self.assertRaises(ValueError): normalize_order(value)
        item = sample()["orderItems"][0]
        item["proceeds"]["breakdowns"].append({"type": "ITEM", "subtotal": {"amount": "1", "currencyCode": "CAD"}})
        with self.assertRaises(ValueError): normalize_item(item)

    def test_search_pagination_retains_filters_and_never_requests_pii(self):
        client = AmazonSPAPIClient(config=SimpleNamespace(marketplace_id="US"))
        client.request = Mock(side_effect=[{"orders": [sample()], "pagination": {"nextToken": "page2"}}, {"orders": [sample()]}])
        self.assertEqual(len(list(client.iter_sales_orders(last_updated_after="2026-10-15T00:00:00Z", page_delay_seconds=0))), 2)
        calls = client.request.call_args_list
        self.assertEqual(calls[0].args, ("GET", "/orders/2026-01-01/orders"))
        self.assertEqual(calls[1].kwargs["params"]["lastUpdatedAfter"], calls[0].kwargs["params"]["lastUpdatedAfter"])
        self.assertEqual(calls[1].kwargs["params"]["paginationToken"], "page2")
        self.assertEqual(calls[1].kwargs["params"]["includedData"], "FULFILLMENT,PROCEEDS,CANCELLATION")
        with self.assertRaises(AmazonSPAPIError): client.search_sales_orders()
        with self.assertRaises(AmazonSPAPIError): client.search_sales_orders(last_updated_after="x", created_after="y")
        with self.assertRaises(AmazonSPAPIError): client.validate_read_only_request("POST", "/orders/2026-01-01/orders")

    def test_repeated_tokens_and_invalid_payload_fail_closed(self):
        client = AmazonSPAPIClient(config=SimpleNamespace(marketplace_id="US"))
        client.request = Mock(return_value={"orders": [], "pagination": {"nextToken": "repeat"}})
        with self.assertRaises(AmazonSPAPIError): list(client.iter_sales_orders(last_updated_after="x", page_delay_seconds=0))
        client.request = Mock(return_value={"unexpected": []})
        with self.assertRaises(AmazonSPAPIError): list(client.iter_sales_orders(last_updated_after="x"))

    def test_active_sync_uses_embedded_items_and_optional_target_is_unchanged(self):
        args = SimpleNamespace(order_id=None,last_updated_after="x",created_after=None,created_before=None,max_pages=1,order_page_delay_seconds=0,limit=None)
        client = Mock(); client.iter_sales_orders.return_value = [sample()]
        orders = fetch_orders(client, args)
        self.assertEqual(orders[0]["_order_items"][0]["OrderItemId"], "test-item")
        client.iter_orders.assert_not_called()
        client.iter_order_items.assert_not_called()
        args.order_id = "target"
        client.get_order.return_value = {"payload": {"AmazonOrderId": "target"}}
        self.assertEqual(fetch_orders(client, args), [{"AmazonOrderId": "target"}])

    def test_apply_uses_embedded_items_and_preserves_stored_fields(self):
        args = SimpleNamespace(order_id=None,last_updated_after="x",created_after=None,created_before=None,max_pages=1,order_page_delay_seconds=0,limit=None,skip_unchanged_order_items=False,order_item_delay_seconds=0,apply=True)
        client = Mock(); client.iter_sales_orders.return_value = [sample()]
        existing = {"test-order": {"row": {"payment_method":"Other","is_prime":True},"items":{"test-item":{"gift_wrap_price_amount":0}},"item_count":1,"last_update_date":"older"}}
        with patch.object(sync,"parse_args",return_value=args), patch.object(sync.AmazonSPAPIClient,"from_env",return_value=client), patch.object(sync,"get_supabase_client",return_value=Mock()), patch.object(sync,"fetch_existing_order_context",return_value=existing), patch.object(sync,"print_summary"), patch.object(sync,"upsert_rows") as writes:
            self.assertEqual(sync.main(), 0)
        client.iter_order_items.assert_not_called()
        order_write = writes.call_args_list[0].args
        item_write = writes.call_args_list[1].args
        self.assertEqual(order_write[1], "amazon_sales_orders")
        self.assertEqual(order_write[2][0]["payment_method"], "Other")
        self.assertTrue(order_write[2][0]["is_prime"])
        self.assertEqual(item_write[1], "amazon_sales_order_items")
        self.assertEqual(item_write[2][0]["gift_wrap_price_amount"], 0)
        self.assertEqual(item_write[2][0]["item_promotion_discount_amount"], 0)


if __name__ == "__main__": unittest.main()
