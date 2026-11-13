import unittest
from unittest.mock import Mock, patch
from integrations.sales_shipping_costs import extract_shipments, label_evidence, order_label_cost, allocate_cost
from integrations.veeqo_sync_sales_labels import (preserve_cost_evidence, needs_reconciliation,
    select_work, load_pages, VeeqoClient, shipping_required, main, persist_shipments)
from integrations.amazon_sales_profitability import amazon_shipping_label_cost, fulfillment_cost_for_order, refresh_shipping_profitability


def shipment(id=1, value=6, unit="USD"):
    return {"id": id, "outbound_label_charges": {"value": value, "unit": unit},
            "tracking_number": {"id": 999, "shipment_id": id, "tracking_number": "not-exported"}}


def order(oid="one", date="2026-10-01T00:00:00+00:00", **kw):
    return {"amazon_order_id": oid, "purchase_date": date, "order_status": "Shipped", **kw}


class ShippingTests(unittest.TestCase):
    def test_scheduler_counters_use_actual_shipping_attempts(self):
        import json
        from run_all_syncs import parse_job_metrics
        values = {"attempted_orders":3,"eligible_orders":100,"reconciled_costs":2,"unresolved_shipped_orders":1,
                  "external_api_calls":4,"retry_count":1,"rate_limit_count":1}
        result = parse_job_metrics("METADATA_JSON: " + json.dumps({"shipping_reconciliation":values}) + "\nEligible Orders: 100\nAttempted Orders: 3\nExternal Api Calls: 4")
        self.assertEqual(result["rows_read"],3)
        self.assertEqual(result["external_api_calls"],4)
        self.assertEqual(result["retry_count"],1)
    def test_tracking_objects_not_shipments_and_duplicate_container(self):
        s = shipment()
        self.assertEqual(extract_shipments({"allocations": [{"shipment": s}], "shipments": [s]}), [s])

    def test_multiple_shipments_require_every_amount(self):
        self.assertEqual(order_label_cost({"shipments": [shipment(), shipment(2, 4)]}), (10, "reconciled"))
        self.assertIsNone(order_label_cost({"shipments": [shipment(), shipment(2, None)]})[0])

    def test_zero_needs_explicit_source_and_currency(self):
        self.assertEqual(label_evidence(shipment(value=0)), (0, "reconciled"))
        self.assertIsNone(label_evidence({"id": 1, "cost": 0})[0])
        self.assertIsNone(label_evidence(shipment(unit=None))[0])
        self.assertEqual(label_evidence(shipment(unit=None), "USD")[0], 6)

    def test_non_finite_negative_currency_void_adjustment(self):
        for s in [shipment(value="NaN"), shipment(value=-1), shipment(unit="CAD"),
                  {**shipment(), "voided_at": "today"}, {**shipment(), "refunds": [{"amount": 6}]}]:
            self.assertIsNone(label_evidence(s)[0])

    def test_preserve_valid_amount_but_honor_void(self):
        old = {"shipments": [shipment()]}
        new = {"shipments": [{**shipment(value=None), "voided_at": "today"}]}
        merged = preserve_cost_evidence(old, new)
        self.assertEqual(merged["shipments"][0]["outbound_label_charges"]["value"], 6)
        self.assertIsNone(order_label_cost(merged)[0])
        self.assertEqual(order_label_cost(preserve_cost_evidence(old, {"shipments": [shipment(value=None)]}))[0], 6)

    def test_existing_preshipment_order_is_retried(self):
        o = order()
        known = {"one": {"raw_veeqo_order_json": {"status": "awaiting_fulfillment", "allocations": []}}}
        profits = {"one": [{"fulfillment_cost": None}]}
        self.assertTrue(needs_reconciliation(o, known, profits))
        known["one"]["raw_veeqo_order_json"]["shipments"] = [shipment()]
        self.assertTrue(needs_reconciliation(o, known, profits))  # failed profitability write still retries
        profits["one"] = [{"fulfillment_cost": 6, "fulfillment_cost_source": "veeqo_label"}]
        self.assertFalse(needs_reconciliation(o, known, profits))

    def test_old_backlog_reserved_and_fair_after_failure(self):
        rows = [order(str(i)) for i in range(5)] + [order("recent", "2026-11-06")]
        first, cursor = select_work(rows, "2026-10-24", None, 3, 2, {})
        second, _ = select_work(rows, "2026-10-24", None, 3, 2, cursor)
        self.assertEqual(len(first), 3)
        self.assertIn("recent", [r["amazon_order_id"] for r in first])
        self.assertNotEqual([r["amazon_order_id"] for r in first[1:]], [r["amazon_order_id"] for r in second[1:]])

    def test_database_pagination(self):
        client = Mock(); query = client.table.return_value.select.return_value.order.return_value
        query.range.return_value.execute.side_effect = [Mock(data=[order(str(i)) for i in range(100)]), Mock(data=[order("last")])]
        self.assertEqual(len(load_pages(client, "orders", "amazon_order_id")), 101)
        self.assertEqual(query.range.call_args_list[1].args, (100, 199))

    def test_search_paginates_and_requires_exact_identity(self):
        client = VeeqoClient("secret")
        client.list_orders = Mock(side_effect=[[{"id": i, "number": "wrong"} for i in range(25)], [{"id": 26, "number": "wanted"}]])
        client.get_order = Mock(return_value={"id": 26, "number": "wanted"})
        self.assertEqual(client.find_order_by_amazon_order_id("wanted")["id"], 26)
        self.assertEqual(client.list_orders.call_count, 2)

    def test_search_page_limit_is_failure_not_false_missing(self):
        client = VeeqoClient("secret")
        client.list_orders = Mock(return_value=[{"id":i,"number":"wrong"} for i in range(25)])
        with self.assertRaisesRegex(RuntimeError, "pagination limit"):
            client.find_order_by_amazon_order_id("wanted")
        self.assertEqual(client.list_orders.call_count, 6)

    def test_incomplete_shipment_write_keeps_last_cost_columns(self):
        client = Mock()
        old = {"veeqo_shipment_id":"1", "label_cost_amount":6, "label_cost_currency":"USD", "label_cost_source_field":"outbound_label_charges"}
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [old]
        rows = [{"veeqo_shipment_id":"1", "label_cost_amount":None,"raw_veeqo_shipment_json":{"voided_at":"today"}}]
        persist_shipments(client,"one",rows)
        self.assertEqual(rows[0]["label_cost_amount"],6)
        self.assertEqual(rows[0]["raw_veeqo_shipment_json"],{"voided_at":"today"})

    @patch("integrations.veeqo_sync_sales_labels.time.sleep")
    def test_retry_limit_and_no_response_body_leak(self, sleep):
        session = Mock(); session.request.return_value = Mock(ok=False, status_code=429, headers={}, text="customer secret")
        client = VeeqoClient("secret", session)
        with self.assertRaisesRegex(RuntimeError, "HTTP 429") as caught:
            client.get_order(1)
        self.assertNotIn("customer", str(caught.exception))
        self.assertEqual(client.api_calls, 4)
        self.assertEqual(client.retries, 3)

    def test_multi_item_allocation_exact_cents(self):
        items = [{"amazon_order_item_id": "b", "quantity_ordered": 2}, {"amazon_order_item_id": "a", "quantity_ordered": 1}]
        self.assertEqual(allocate_cost(10, items), {"a": 3.34, "b": 6.66})
        self.assertEqual(sum(allocate_cost(10, items).values()), 10)
        self.assertIsNone(allocate_cost(None, items)["a"])

    def test_amazon_adjustments_require_postage_evidence_and_net_refunds(self):
        def event(kind, amount, fid):
            return {"event_type": "AdjustmentEventList", "currency": "USD", "amount": amount, "financial_event_id": fid,
                "raw_financial_event_json": {"event": {"AdjustmentType": kind}, "path": ["AdjustmentEventList", "AdjustmentAmount"]}}
        unrelated = event("REVERSAL_REIMBURSEMENT", -40, "x")
        self.assertIsNone(amazon_shipping_label_cost([unrelated]))
        charge, refund = event("PostageBilling_Postage", -6, "c"), event("PostageRefund_Postage", 1, "r")
        self.assertEqual(amazon_shipping_label_cost([unrelated, charge, charge, refund]), 5)

    def test_veeqo_and_amazon_never_added_together(self):
        self.assertEqual(fulfillment_cost_for_order({"fulfillment_channel": "MFN"}, 0, 6, 6, None), (6, "veeqo_label"))

    def test_pending_and_cancelled_not_attempted(self):
        self.assertFalse(shipping_required(order(order_status="Canceled")))
        self.assertFalse(shipping_required(order(order_status="Unshipped")))
        self.assertTrue(shipping_required(order(order_status="Shipped - Delivered to Buyer")))

    def test_missing_credentials_visible_without_api(self):
        import argparse
        import os
        client = Mock()
        client.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        args = argparse.Namespace(apply=False, amazon_order_id=None, asin=None, missing_only=True,
            purchase_date_start=None, purchase_date_end=None, limit=50, backlog_limit=20)
        with patch("integrations.veeqo_sync_sales_labels.parse_args", return_value=args), \
             patch("integrations.veeqo_sync_sales_labels.get_supabase_client", return_value=client), \
             patch("integrations.veeqo_sync_sales_labels.load_mf_orders", return_value=[]), \
             patch("integrations.veeqo_sync_sales_labels.load_pages", return_value=[]), \
             patch("integrations.veeqo_sync_sales_labels.load_dotenv"), \
             patch.dict(os.environ, {}, clear=True), \
             patch("integrations.veeqo_sync_sales_labels.emit_summary") as summary:
            self.assertEqual(main(), 1)
            self.assertEqual(summary.call_args.args[0]["queue_status"], "missing_credentials")

    def test_shipping_repair_preserves_cogs_and_does_not_touch_consumption(self):
        client = Mock()
        row = {"amazon_order_id": "one", "amazon_order_item_id": "a", "sale_price": 30,
               "amazon_fees_excluding_fulfillment": 4, "cogs": 7, "data_status": "missing_fulfillment_cost"}
        client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [row]
        with patch("integrations.amazon_sales_profitability.fetch_order_items", return_value=[{"amazon_order_item_id":"a", "quantity_ordered":1}]), \
             patch("integrations.amazon_sales_profitability.fetch_financial_events", return_value=[]), \
             patch("integrations.amazon_sales_profitability.fetch_veeqo_label_cost", return_value=6), \
             patch("integrations.amazon_sales_profitability.fetch_fulfillment_cost_override", return_value=None):
            refresh_shipping_profitability(client, order(fulfillment_channel="MFN"))
        update = client.table.return_value.update.call_args.args[0]
        self.assertEqual(update["fulfillment_cost"], 6)
        self.assertEqual(update["net_profit"], 13)
        self.assertNotIn("cogs", update)
        self.assertEqual({c.args[0] for c in client.table.call_args_list}, {"amazon_sales_profitability"})

    def test_preshipment_refresh_success_and_api_failure_are_observable(self):
        import argparse
        import os
        from contextlib import ExitStack
        args = argparse.Namespace(apply=True, amazon_order_id="one", asin=None, missing_only=True,
            purchase_date_start=None, purchase_date_end=None, limit=50, backlog_limit=20)
        for fail in (False, True):
            db = Mock()
            db.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
            db.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []
            api = Mock(api_calls=1, retries=0, rate_limits=0)
            api.get_order.return_value = {"id":1,"number":"one","shipments":[shipment()]}
            if fail:
                api.get_order.side_effect = RuntimeError("source unavailable")
            with ExitStack() as stack:
                def mock(name, **kw):
                    return stack.enter_context(patch("integrations.veeqo_sync_sales_labels." + name, **kw))
                mock("parse_args",return_value=args)
                mock("get_supabase_client",return_value=db)
                mock("load_mf_orders",return_value=[order()])
                mock("load_pages",side_effect=lambda client, table, *args: [{"amazon_order_id":"one","veeqo_order_id":"1","raw_veeqo_order_json":{"status":"awaiting_fulfillment"}}] if table == "veeqo_sales_orders" else [])
                mock("load_dotenv")
                stack.enter_context(patch.dict(os.environ,{"VEEQO_KEY":"secret"}))
                stack.enter_context(patch("integrations.sourcing_database_guard.wait_for_database"))
                mock("VeeqoClient",return_value=api)
                mock("upsert_rows"); mock("persist_shipments"); mock("notify_backlog")
                repair = mock("refresh_shipping_profitability")
                summary = mock("emit_summary")
                self.assertEqual(main(), 1 if fail else 0)
                stats = summary.call_args.args[0]
                self.assertEqual(stats["attempted_orders"],1)
                self.assertEqual(stats["api_failures"],int(fail))
                self.assertEqual(stats["reconciled_costs"],int(not fail))
                self.assertEqual(repair.call_count,int(not fail))

    def test_verified_amazon_or_manual_cost_is_not_a_false_backlog(self):
        profits = {"one":[{"amazon_order_item_id":"a","quantity":1,"fulfillment_cost":5.8,"fulfillment_cost_source":"amazon_shipping_label"}]}
        self.assertFalse(needs_reconciliation(order(), {}, profits, {"one":(5.8,"amazon_shipping_label",{})}))
        self.assertTrue(needs_reconciliation(order(), {}, profits, {"one":(None,"missing",{})}))
        self.assertIsNone(fulfillment_cost_for_order(order(),0,None,None,{"fulfillment_cost":5,"currency":"CAD"})[0])


if __name__ == "__main__":
    unittest.main()

