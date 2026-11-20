import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from amazon_sku_identity import fulfillment_method, sku_identity
from amazon_sync_merchant_listings import normalize_fulfillment_channel, build_sku_row
from amazon_sync_fba_shipments import seller_skus_for_amazon_items
from amazon_sales_profitability import lookup_cogs, fetch_inventorylab_backfill
from amazon_sync_fba_inventory import upsert_amazon_skus


class SkuIdentityTests(unittest.TestCase):
    def test_default_report_is_merchant_and_drops_fba_network_sku(self):
        self.assertEqual(normalize_fulfillment_channel("DEFAULT"), "DEFAULT")
        row = build_sku_row(row={"fulfillment-channel": "DEFAULT"}, existing={"fnsku": "FBA-NETWORK"},
                            seller_sku="MF-SKU", asin="ASIN", marketplace_id="US", report_type="ALL", captured_at="NOW")
        self.assertEqual(row["fulfillment_channel"], "DEFAULT")
        self.assertIsNone(row["fnsku"])

    def test_method_is_part_of_sku_identity(self):
        self.assertEqual(fulfillment_method("Amazon"), "FBA")
        self.assertEqual(fulfillment_method("DEFAULT"), "MF")
        self.assertNotEqual(sku_identity("US", "Amazon", "SKU"), sku_identity("US", "DEFAULT", "SKU"))
        self.assertIsNone(sku_identity("US", "unknown", "SKU"))

    def test_ambiguous_fba_asin_does_not_invent_sku_mapping(self):
        item = [{"ASIN": "B0033T1UWW"}]
        self.assertEqual(seller_skus_for_amazon_items(item, {"ONE": {"asin": "B0033T1UWW"}}), ["ONE"])
        self.assertEqual(seller_skus_for_amazon_items(item, {"ONE": {"asin": "B0033T1UWW"}, "TWO": {"asin": "B0033T1UWW"}}), [])

    def test_mf_cogs_never_uses_fba_opening_balance(self):
        db = Mock()
        self.assertEqual(lookup_cogs(db, {"seller_sku": "MF-SKU"}, 1, fulfillment_channel="MFN"), (None, "missing", None))
        db.table.assert_not_called()
        self.assertIsNone(fetch_inventorylab_backfill(db, None, "B0033T1UWW"))
        db.table.return_value.execute.assert_not_called()

    def test_fba_inventory_preserves_observed_merchant_listing_method(self):
        db = Mock()
        query = db.table.return_value
        query.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [
            {"seller_sku": "CONVERTED", "marketplace_id": "US", "fulfillment_channel": "DEFAULT", "last_listing_sync_at": "NOW"}]
        rows = [{"seller_sku": "CONVERTED", "marketplace_id": "US", "fulfillment_channel": "Amazon", "fnsku": "OLD-FNSKU"}]
        self.assertEqual(upsert_amazon_skus(db, rows), 1)
        self.assertEqual(rows[0]["fulfillment_channel"], "DEFAULT")
        self.assertIsNone(rows[0]["fnsku"])


if __name__ == "__main__":
    unittest.main()
