import unittest

from integrations.amazon_sales_profitability import split_fee_totals


def fee(*, source="amazon_spapi_finances", event_type="ShipmentEventList",
        fee_type="Commission", amount=-5, status=None, transaction_type="Shipment",
        shipment_id="shipment"):
    raw = {}
    if source == "amazon_spapi_transactions":
        raw = {
            "transaction_status": status,
            "transaction": {
                "transactionType": transaction_type,
                "relatedIdentifiers": [{
                    "relatedIdentifierName": "SHIPMENT_ID",
                    "relatedIdentifierValue": shipment_id,
                }],
            },
        }
    return {
        "source": source,
        "event_type": event_type,
        "fee_type": fee_type,
        "amount": amount,
        "raw_financial_event_json": raw,
    }


class SaleFeeSelectionTests(unittest.TestCase):
    def test_legacy_fee_source_wins_over_stale_transaction_fallback(self):
        totals = split_fee_totals([
            fee(amount=-5),
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=-5, status="DEFERRED"),
        ])
        self.assertEqual(totals["amazon_fees_excluding_fulfillment"], 5)

    def test_refund_fee_credit_is_not_a_sale_cohort_expense(self):
        totals = split_fee_totals([
            fee(amount=-5),
            fee(event_type="RefundEventList", amount=2),
        ])
        self.assertEqual(totals["amazon_fees_excluding_fulfillment"], 5)

    def test_transaction_fallback_uses_one_lifecycle_status(self):
        totals = split_fee_totals([
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=-5, status="DEFERRED"),
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=-5, status="RELEASED"),
        ])
        self.assertEqual(totals["amazon_fees_excluding_fulfillment"], 5)

    def test_transaction_fallback_preserves_separate_shipments(self):
        totals = split_fee_totals([
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=-5, status="RELEASED", shipment_id="one"),
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=-6, status="DEFERRED", shipment_id="two"),
        ])
        self.assertEqual(totals["amazon_fees_excluding_fulfillment"], 11)

    def test_refund_transaction_is_not_a_sale_fee_fallback(self):
        totals = split_fee_totals([
            fee(source="amazon_spapi_transactions", event_type="TransactionEventList",
                amount=2, status="RELEASED", transaction_type="Refund"),
        ])
        self.assertFalse(totals["fees_present"])

    def test_zero_fee_is_complete_when_an_applicable_fee_event_exists(self):
        totals = split_fee_totals([fee(fee_type="FBAFulfillmentFee", amount=-4)])
        self.assertTrue(totals["fees_present"])
        self.assertEqual(totals["amazon_fees_excluding_fulfillment"], 0)
        self.assertEqual(totals["fba_fulfillment_fee"], 4)


if __name__ == "__main__":
    unittest.main()
