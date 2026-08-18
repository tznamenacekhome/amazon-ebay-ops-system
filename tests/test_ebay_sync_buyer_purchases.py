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

    def test_cancel_status_marks_order_cancelled_before_refund_confirmation(self):
        order = ET.fromstring(
            """
            <Order>
              <OrderStatus>Completed</OrderStatus>
              <CancelStatus>CancelPending</CancelStatus>
              <AmountPaid>12.48</AmountPaid>
              <MonetaryDetails>
                <Payments>
                  <Payment>
                    <PaymentAmount>12.48</PaymentAmount>
                  </Payment>
                </Payments>
              </MonetaryDetails>
            </Order>
            """,
        )

        self.assertTrue(sync.order_is_cancelled_or_refunded(order))

    def test_cancelled_order_with_tracking_is_not_skipped_before_status_update(self):
        order = ET.fromstring(
            """
            <Order>
              <OrderID>07-14983-88088</OrderID>
              <OrderStatus>Cancelled</OrderStatus>
              <CancelStatus>CancelClosedWithRefund</CancelStatus>
              <AmountPaid>0.0</AmountPaid>
              <CreatedTime>2026-08-02T20:07:07.000Z</CreatedTime>
              <MonetaryDetails>
                <Payments>
                  <Payment>
                    <PaymentAmount>12.48</PaymentAmount>
                  </Payment>
                </Payments>
                <Refunds>
                  <Refund>
                    <RefundAmount>-12.48</RefundAmount>
                  </Refund>
                </Refunds>
              </MonetaryDetails>
              <TransactionArray>
                <Transaction>
                  <TransactionID>10087917895407</TransactionID>
                  <OrderLineItemID>137408517550-10087917895407</OrderLineItemID>
                  <QuantityPurchased>1</QuantityPurchased>
                  <TransactionPrice>7.00</TransactionPrice>
                  <ActualShippingCost>5.48</ActualShippingCost>
                  <ActualHandlingCost>0.00</ActualHandlingCost>
                  <Item>
                    <ItemID>137408517550</ItemID>
                    <Title>Star Wars Battlefront - Microsoft Xbox One</Title>
                  </Item>
                  <ShippingDetails>
                    <ShipmentTrackingDetails>
                      <ShipmentTrackingNumber>9400108106244392775893</ShipmentTrackingNumber>
                      <ShippingCarrierUsed>USPS</ShippingCarrierUsed>
                    </ShipmentTrackingDetails>
                  </ShippingDetails>
                </Transaction>
              </TransactionArray>
            </Order>
            """,
        )

        original_get_existing = sync.get_existing_purchase_for_order
        original_upsert_shipment = sync.upsert_inbound_shipment
        original_get_items = sync.get_existing_purchase_items
        original_get_details = sync.get_browse_item_details
        original_link = sync.link_shipment_item
        original_has_all_tracking = sync.purchase_has_all_tracking
        original_supabase = sync.supabase

        class TableStub:
            def __init__(self):
                self.updated_payload = None

            def update(self, payload):
                self.updated_payload = payload
                return self

            def eq(self, *_args):
                return self

            def execute(self):
                return type("Response", (), {"data": []})()

        class SupabaseStub:
            def __init__(self):
                self.purchase_items = TableStub()
                self.purchases = TableStub()

            def table(self, name):
                return getattr(self, name)

        stub = SupabaseStub()

        try:
            sync.get_existing_purchase_for_order = lambda *_args: {"purchase_id": "purchase-1"}
            sync.upsert_inbound_shipment = lambda **_kwargs: None
            sync.get_existing_purchase_items = lambda _purchase_id: [
                {
                    "item_id": "item-1",
                    "supplier_sku": "137408517550-10087917895407",
                    "current_status": "awaiting_carrier_scan",
                    "manual_title_override": False,
                    "manual_unit_cost_override": False,
                    "manual_split_child": False,
                }
            ]
            sync.get_browse_item_details = lambda *_args: None
            sync.link_shipment_item = lambda **_kwargs: None
            sync.purchase_has_all_tracking = lambda *_args: True
            sync.supabase = stub

            result = sync.upsert_purchase(order, "batch-1", "token")
        finally:
            sync.get_existing_purchase_for_order = original_get_existing
            sync.upsert_inbound_shipment = original_upsert_shipment
            sync.get_existing_purchase_items = original_get_items
            sync.get_browse_item_details = original_get_details
            sync.link_shipment_item = original_link
            sync.purchase_has_all_tracking = original_has_all_tracking
            sync.supabase = original_supabase

        self.assertEqual(result, "updated")
        self.assertEqual(stub.purchase_items.updated_payload["current_status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
