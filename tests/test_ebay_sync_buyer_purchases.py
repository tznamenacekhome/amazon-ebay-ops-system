import os
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("EBAY_CLIENT_ID", "test-client-id")
os.environ.setdefault("EBAY_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("EBAY_REFRESH_TOKEN", "test-refresh-token")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from integrations import ebay_sync_buyer_purchases as sync  # noqa: E402


class EbayBuyerPurchaseCostTests(unittest.TestCase):
    def test_transaction_unit_costs_handles_missing_payment_and_refund_totals(self):
        order = ET.fromstring("<Order />")
        transaction = ET.fromstring(
            """
            <Transaction>
              <QuantityPurchased>1</QuantityPurchased>
              <TransactionPrice currencyID="USD">19.99</TransactionPrice>
              <ActualShippingCost currencyID="USD">4.50</ActualShippingCost>
              <ActualHandlingCost currencyID="USD">0.00</ActualHandlingCost>
            </Transaction>
            """,
        )

        self.assertEqual(sync.transaction_unit_costs(order, [transaction]), [24.49])

    def test_order_payment_and_refund_totals_default_to_decimal_zero(self):
        order = ET.fromstring("<Order />")

        self.assertEqual(sync.order_payment_total(order), sync.Decimal("0.00"))
        self.assertEqual(sync.order_refund_total(order), sync.Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
