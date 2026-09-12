import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from build_sourcing_seed_asins import latest_inventory_planning_by_asin, stale_in_stock_no_recent_sales
from sourcing_coverage_cycle import build_unified_priority_queue


class PlanningLookupTests(unittest.TestCase):
    def test_bounded_deduplicated_lookup_and_missing_cache(self):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(data=[{"asin": "B000000001"}])
        cache = {}
        self.assertEqual(latest_inventory_planning_by_asin(client, [" b000000001 ", "B000000001", "MISSING", None], cache=cache),
                         {"B000000001": {"asin": "B000000001"}})
        latest_inventory_planning_by_asin(client, ["B000000001", "MISSING"], cache=cache)
        client.rpc.assert_called_once_with("sourcing_latest_inventory_planning", {"requested_asins": ["B000000001", "MISSING"]})
        client.table.assert_not_called()

    def test_batch_size_and_no_global_cache(self):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(data=[])
        latest_inventory_planning_by_asin(client, [f"B{i:09}" for i in range(205)])
        self.assertEqual([len(c.args[1]["requested_asins"]) for c in client.rpc.call_args_list], [100, 100, 5])
        latest_inventory_planning_by_asin(client, ["B000000000"])
        self.assertEqual(client.rpc.call_count, 4)

    def test_empty_scope_does_no_database_work(self):
        client = MagicMock()
        self.assertEqual(latest_inventory_planning_by_asin(client, []), {})
        client.rpc.assert_not_called()

    def test_failure_does_not_cache_missing_or_fall_back_to_history(self):
        client = MagicMock()
        client.rpc.return_value.execute.side_effect = RuntimeError("unavailable")
        cache = {}
        with self.assertRaises(RuntimeError):
            latest_inventory_planning_by_asin(client, ["B000000001"], cache=cache)
        self.assertEqual(cache, {})
        client.table.assert_not_called()

    def test_invalid_responses_are_not_cached(self):
        for rows in [None, [{"asin": "OTHER"}], [{"asin": "A"}, {"asin": "A"}]]:
            client = MagicMock()
            client.rpc.return_value.execute.return_value = SimpleNamespace(data=rows)
            cache = {}
            with self.assertRaises(ValueError):
                latest_inventory_planning_by_asin(client, ["A"], cache=cache)
            self.assertEqual(cache, {})

    def test_queue_shares_cache_but_new_build_gets_fresh_cache(self):
        caches = []
        def recent(*args, planning_cache):
            self.assertEqual(planning_cache, {})
            planning_cache['A'] = {}
            caches.append(planning_cache)
            return []
        def catalog(*args, planning_cache):
            self.assertIs(planning_cache, caches[-1])
            self.assertEqual(planning_cache, {'A': {}})
            return []
        with patch('sourcing_coverage_cycle.build_recent_sales_seeds', side_effect=recent), \
             patch('sourcing_coverage_cycle.build_full_listing_seeds', side_effect=catalog), \
             patch('sourcing_coverage_cycle.build_purchased_not_sent_seeds', return_value=[]):
            for _ in range(2):
                build_unified_priority_queue(MagicMock(), settings=object())
        self.assertIsNot(caches[0], caches[1])

    def test_compact_raw_projection_preserves_age_and_sales_fallback_decisions(self):
        for inventory in [0, 1, 5]:
            for sales in [None, 0, 2]:
                for raw_sales in [None, '0', '3']:
                    for age in [None, '0', '4']:
                        raw = {'inv-age-31-to-60-days': age, 'inv-age-61-to-90-days': '2',
                               'sales-shipped-last-30-days': raw_sales, 'unused': 'large payload'}
                        old = {'sales_shipped_last_30_days': sales, 'inv_age_91_to_180_days': 1, 'raw_planning_json': raw}
                        compact = {**old, 'raw_planning_json': {k: v for k, v in raw.items() if k != 'unused'}}
                        self.assertEqual(stale_in_stock_no_recent_sales('A', inventory, old),
                                         stale_in_stock_no_recent_sales('A', inventory, compact))


if __name__ == '__main__':
    unittest.main()
