import datetime as dt
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
import push_zfi_business_summary as publisher
from zfi_management_profitability import cost_categories, refund_facts, summarize_management_window, utc_bounds


def sale(**changes):
    return dict({"amazon_order_id": "order", "sold_at": "2026-09-10T12:00:00Z",
                 "sale_price": 50, "cogs": 10, "quantity": 1, "data_status": "complete",
                 "amazon_fees_excluding_fulfillment": 5, "fulfillment_cost": 4,
                 "fulfillment_cost_source": "amazon_fba_fee", "fulfillment_channel": "AFN",
                 "order_status": "Shipped", "is_replacement_order": False,
                 "net_profit": 31}, **changes)


def refund(**changes):
    return dict({"financial_event_id": "refund", "event_type": "RefundEventList",
                 "posted_date": "2026-09-05T12:00:00Z", "charge_type": "Principal",
                 "amount": -20, "currency": "USD"}, **changes)


def label(**changes):
    return dict({"veeqo_shipment_id": "shipment", "amazon_order_id": "order",
                 "label_cost_currency": "USD", "label_cost_amount": 3, "label_cost_source_field": "label_cost"}, **changes)


class ManagementContractTests(unittest.TestCase):
    def setUp(self):
        self.start = dt.date(2026, 9, 1)
        self.end = dt.date(2026, 9, 17)

    def summary(self, rows, refunds=None, labels=None):
        return summarize_management_window(rows, self.start, self.end, {}, refunds or [], labels or [])

    def test_live_publisher_reaches_push_with_unknown_label_cost(self):
        payload = {
            "source": "mbop", "schema_version": "2026-09-17", "generated_at": "2026-09-18T00:00:00Z",
            "source_summary": {}, "period": {"start_date": "2026-09-01", "end_date": "2026-09-18"},
            "sales": {"gross_sales": 50},
            "costs": {"marketplace_fees": 5, "shipping_label_costs": None, "fulfillment_costs": None, "cogs": 10},
            "profitability": {"estimated_net_profit": 31},
            "inventory": {"current_inventory_value": 10}, "alerts": [],
        }
        args = SimpleNamespace(start_date="2026-09-01", end_date="2026-09-18", generated_by="test",
                               apply=True, target_table="mbop_business_summaries", retry_attempts=1, retry_delay_seconds=0)
        with patch.object(publisher, "parse_args", return_value=args), \
             patch.object(publisher, "load_dotenv"), \
             patch.object(publisher, "get_mbop_supabase_client"), \
             patch.object(publisher, "get_zfi_supabase_client"), \
             patch.object(publisher, "build_payload", return_value=payload), \
             patch.object(publisher, "push_with_retry") as push, \
             patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(publisher.main(), 0)
            push.assert_called_once()
            self.assertIsNone(push.call_args.kwargs["row"]["payload"]["costs"]["shipping_label_costs"])
            self.assertIn("Shipping label costs: Unavailable", output.getvalue())
            self.assertIn("Fulfillment costs: Unavailable", output.getvalue())

    def test_calendar_month_not_rolling_30_days(self):
        result = publisher.build_profitability_windows([
            sale(sold_at="2026-08-25T12:00:00Z"), sale()], self.end, {}, refund_events=[], labels=[])
        self.assertEqual(result["30d"]["gross_sales"], 100)
        self.assertEqual(result["current_month"]["gross_sales"], 50)
        self.assertEqual(result["current_month"]["source_start_date"], "2026-09-01")
        self.assertEqual(result["ytd"]["management_pnl"]["source_start_date"], "2026-01-01")
        self.assertEqual(result["90d"]["source_start_date"], "2026-06-20")

    def test_local_midnight_and_exclusive_end(self):
        result = self.summary([sale(sold_at="2026-09-01T06:59:59Z"),
                               sale(sold_at="2026-09-18T06:59:59.999999Z"),
                               sale(sold_at="2026-09-18T07:00:00Z")])
        self.assertEqual(result["gross_sales"], 50)

    def test_dst_bounds(self):
        start, end = utc_bounds(dt.date(2026, 3, 1), dt.date(2026, 3, 31))
        self.assertEqual(start, "2026-03-01T08:00:00+00:00")
        self.assertEqual(end, "2026-04-01T07:00:00+00:00")

    def test_ytd_uses_local_january_first(self):
        result = publisher.build_profitability_windows([
            sale(sold_at="2026-01-01T07:59:59Z"), sale(sold_at="2026-01-01T08:00:00Z")],
            self.end, {}, refund_events=[], labels=[])
        self.assertEqual(result["ytd"]["management_pnl"]["gross_sales"], 50)

    def test_refund_processed_period_keeps_original_sale(self):
        rows = [sale(sold_at="2026-08-10T12:00:00Z", data_status="refunded")]
        september = self.summary(rows, [refund()])
        august = summarize_management_window(rows, dt.date(2026, 8, 1), dt.date(2026, 8, 31), {}, [refund()], [])
        self.assertEqual(august["gross_sales"], 50)
        self.assertEqual(august["cogs"], 10)
        self.assertEqual(august["refunds_returns_observed"], 0)
        self.assertEqual(september["refunds_returns_observed"], 20)
        self.assertEqual(september["gross_sales"], 0)
        self.assertIsNone(september["refunds_returns"])
        self.assertIsNone(september["net_profit"])

    def test_refunds_exclude_tax_fees_and_buyer_refunds_preserve_signs(self):
        events = [refund(), refund(), refund(financial_event_id="tax", charge_type="Tax", amount=-2),
                  refund(financial_event_id="fee", fee_type="Commission", charge_type=None, amount=3),
                  refund(financial_event_id="promo", charge_type=None, promotion_type="Promotion", amount=2),
                  refund(financial_event_id="buyer", event_type="ebay_buyer_refund", amount=-99)]
        self.assertEqual(self.summary([], events)["refunds_returns_observed"], 18)

    def test_invalid_refund_is_null_not_partial(self):
        for changes in ({"currency": "CAD"}, {"posted_date": None}, {"amount": "NaN"},
                        {"charge_type": "Unknown"}, {"financial_event_id": None}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.summary([], [refund(**changes)])["refunds_returns_observed"])

    def test_empty_refund_source_never_asserts_complete_zero(self):
        result = self.summary([])
        self.assertIsNone(result["refunds_returns"])
        self.assertEqual(result["refund_coverage"], "unverified")

    def test_fba_is_not_shipping(self):
        result = self.summary([sale()])
        self.assertEqual(result["fulfillment_costs"], 4)
        self.assertEqual(result["shipping_label_costs"], 0)
        self.assertEqual(result["marketplace_fees"], 5)

    def test_legitimate_zero_marketplace_fee_is_complete(self):
        result = self.summary([sale(amazon_fees_excluding_fulfillment=0)])
        self.assertEqual(result["marketplace_fees"], 0)

    def test_missing_mfn_label_does_not_null_complete_fba_fulfillment(self):
        result = self.summary([sale(amazon_order_id="fba"), sale(
            amazon_order_id="mfn", fulfillment_channel="MFN",
            fulfillment_cost=None, fulfillment_cost_source="missing")])
        self.assertEqual(result["fulfillment_costs"], 4)
        self.assertIsNone(result["shipping_label_costs"])

    def test_missing_fba_cost_does_not_null_legitimate_zero_labels(self):
        result = self.summary([sale(fulfillment_cost=None, fulfillment_cost_source="missing")])
        self.assertIsNone(result["fulfillment_costs"])
        self.assertEqual(result["shipping_label_costs"], 0)

    def test_pending_cancelled_and_replacement_rows_do_not_block_shipped_sales(self):
        result = self.summary([
            sale(), sale(order_status="Pending", sale_price=None),
            sale(order_status="Canceled", data_status="cancelled", sale_price=None),
            sale(is_replacement_order=True, sale_price=None),
        ])
        self.assertEqual(result["gross_sales"], 50)
        self.assertEqual(result["units_sold"], 1)

    def test_refund_status_does_not_block_independent_fields(self):
        result = self.summary([sale(data_status="refunded")])
        self.assertEqual(result["gross_sales"], 50)
        self.assertEqual(result["cogs"], 10)
        self.assertEqual(result["marketplace_fees"], 5)
        self.assertEqual(result["fulfillment_costs"], 4)
        self.assertIsNone(result["refunds_returns"])
        self.assertIsNone(result["net_profit"])

    def test_multi_item_mfn_label_counted_once(self):
        row = sale(fulfillment_channel="MFN", fulfillment_cost_source="veeqo_label", fulfillment_cost=3)
        result = self.summary([row, row], labels=[label(), label()])
        self.assertEqual(result["shipping_label_costs"], 3)
        self.assertEqual(result["fulfillment_costs"], 0)

    def test_multiple_shipments_and_mixed_channels_no_double_count(self):
        result = self.summary([sale(amazon_order_id="fba"), sale(fulfillment_channel="MFN")],
                              labels=[label(), label(veeqo_shipment_id="second", label_cost_amount=2)])
        self.assertEqual(result["shipping_label_costs"], 5)
        self.assertEqual(result["fulfillment_costs"], 4)
        self.assertEqual(result["marketplace_fees"], 10)
        self.assertEqual(sum(result[k] for k in ("shipping_label_costs", "fulfillment_costs", "marketplace_fees")), 19)

    def test_generic_amazon_adjustment_not_a_safe_label(self):
        result = self.summary([sale(fulfillment_channel="MFN", fulfillment_cost_source="amazon_shipping_label")])
        self.assertIsNone(result["shipping_label_costs"])

    def test_unknown_label_currency_is_not_assumed_usd(self):
        result = self.summary([sale(fulfillment_channel="MFN")], labels=[label(label_cost_currency=None)])
        self.assertIsNone(result["shipping_label_costs"])

    def test_generic_veeqo_cost_is_not_verified_label(self):
        result = self.summary([sale(fulfillment_channel="MFN")], labels=[label(label_cost_source_field="cost")])
        self.assertIsNone(result["shipping_label_costs"])

    def test_refund_read_is_posting_period_bounded_not_sale_bounded(self):
        client = MagicMock()
        query = client.table.return_value
        query.select.return_value = query
        for name in ("eq", "gte", "lt", "order", "range", "is_", "limit"):
            getattr(query, name).return_value = query
        query.execute.return_value.data = []
        self.assertEqual(publisher.fetch_refund_events(client, self.start, self.end), [])
        query.gte.assert_called_once_with("posted_date", "2026-09-01T07:00:00+00:00")
        query.lt.assert_called_once_with("posted_date", "2026-09-18T07:00:00+00:00")
        query.limit.assert_called_once_with(1)
        query.is_.assert_called_once_with("posted_date", "null")

    def test_label_reads_only_selected_orders_in_bounded_batches(self):
        client = MagicMock()
        query = client.table.return_value
        query.select.return_value = query
        for name in ("in_", "order", "range"):
            getattr(query, name).return_value = query
        query.execute.return_value.data = []
        publisher.fetch_shipping_labels(client, [str(i) for i in range(201)])
        self.assertEqual([len(call.args[1]) for call in query.in_.call_args_list], [200, 1])
        client.reset_mock()
        publisher.fetch_shipping_labels(client, [])
        client.table.assert_not_called()

    def test_inbound_freight_does_not_enter_acquisition_cogs(self):
        result = self.summary([sale(inbound_shipping=100, prep=25)])
        self.assertEqual(result["cogs"], 10)
        self.assertEqual(result["gross_profit"], 40)

    def test_missing_cost_not_zero_or_complete_subset(self):
        result = self.summary([sale(), sale(cogs=None)])
        self.assertIsNone(result["cogs"])
        self.assertEqual(result["gross_sales"], 100)
        self.assertEqual(result["marketplace_fees"], 10)
        self.assertEqual(result["fulfillment_costs"], 8)

    def test_missing_fees_only_blocks_marketplace_fee_total(self):
        result = self.summary([sale(data_status="missing_fees")])
        self.assertEqual(result["gross_sales"], 50)
        self.assertEqual(result["cogs"], 10)
        self.assertIsNone(result["marketplace_fees"])
        self.assertEqual(result["fulfillment_costs"], 4)

    def test_cancelled_excluded_refunded_sale_retained(self):
        result = self.summary([sale(data_status="cancelled"), sale(data_status="refunded")])
        self.assertEqual(result["gross_sales"], 50)
        self.assertEqual(result["units_sold"], 1)
        self.assertEqual(result["marketplace_fees"], 5)

    def test_publisher_contract_preserves_sections(self):
        with patch.multiple(publisher, fetch_sales_orders=lambda *a: {"order": "2026-09-10"},
                            fetch_sales_orders_since=lambda *a: [{"amazon_order_id": "order", "purchase_date": "2026-09-10T12:00:00Z", "fulfillment_channel": "AFN", "order_status": "Shipped", "is_replacement_order": False}],
                            fetch_sales_profitability=lambda *a: [sale()], fetch_purchase_rows=lambda *a: [],
                            fetch_all=lambda *a, **k: [], fetch_latest_row=lambda *a: None,
                            fetch_refund_events=lambda *a: [], fetch_shipping_labels=lambda *a: []):
            payload = publisher.build_payload(None, start_date="2026-09-01", end_date="2026-09-17", generated_by="test")
        self.assertEqual(payload["payload_version"], "business_finance_replacement_v3")
        self.assertEqual(set(payload["profitability_windows"]), {"30d", "90d", "ytd", "current_month"})
        self.assertEqual(payload["costs"]["shipping_label_costs"], 0)
        self.assertEqual(payload["costs"]["fulfillment_costs"], 4)
        self.assertIsNone(payload["sales"]["refunds_returns"])
        for key in ("sales", "costs", "inventory", "profitability", "cash_operational", "cash_position",
                    "payout_reconciliation", "inventory_capital", "loss_prevention", "top_sellers",
                    "growth_summary", "sourcing_summary", "financial_readiness", "alerts", "source_summary"):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
