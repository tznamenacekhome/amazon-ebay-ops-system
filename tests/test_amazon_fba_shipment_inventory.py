import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from amazon_sync_fba_shipments import fetch_latest_inventory


class InventoryLookupTests(unittest.TestCase):
    def test_latest_lookup_is_bounded_and_marketplace_scoped(self):
        database = MagicMock()
        query = database.table.return_value
        query.select.return_value = query
        query.eq.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[{
                "seller_sku": "sku-a", "fulfillable_quantity": 3,
                "reserved_quantity": 2, "unfulfillable_quantity": None,
                "total_quantity": 5,
            }]),
            SimpleNamespace(data=[]),
        ]
        result = fetch_latest_inventory(database, ["sku-a", "missing", "sku-a"], "US")
        self.assertEqual(result, {"sku-a": {
            "available": 3, "reserved": 2, "unfulfillable": 0, "total": 5,
        }})
        self.assertEqual(query.execute.call_count, 2)
        self.assertTrue(all(c.args == ("amazon_fba_inventory_snapshots",)
                            for c in database.table.call_args_list))
        self.assertEqual([c.args for c in query.eq.call_args_list], [
            ("seller_sku", "sku-a"), ("marketplace_id", "US"),
            ("seller_sku", "missing"), ("marketplace_id", "US"),
        ])
        query.order.assert_called_with("captured_at", desc=True)
        self.assertTrue(all(c.args == (1,) for c in query.limit.call_args_list))

    def test_empty_skus_do_not_query(self):
        database = MagicMock()
        self.assertEqual(fetch_latest_inventory(database, [], "US"), {})
        database.table.assert_not_called()


if __name__ == "__main__":
    unittest.main()
