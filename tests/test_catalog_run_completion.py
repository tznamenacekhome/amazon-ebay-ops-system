import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from run_daily_catalog_sourcing import daily_run_failed
from score_sourcing_opportunities import scoring_run_update, fetch_candidates


class CatalogCompletionTests(unittest.TestCase):
    def test_candidates_are_fetched_lazily_without_skipping_page_boundary(self):
        db = MagicMock()
        query = db.table.return_value
        for method in ("select", "eq", "order", "range"):
            getattr(query, method).return_value = query
        query.execute.side_effect = [SimpleNamespace(data=[{"candidate_id": i} for i in range(100)]),
                                     SimpleNamespace(data=[{"candidate_id": 100}])]
        rows = fetch_candidates(db, "run")
        query.execute.assert_not_called()
        self.assertEqual(next(rows), {"candidate_id": 0})
        self.assertEqual(query.execute.call_count, 1)
        self.assertEqual([r["candidate_id"] for r in rows], list(range(1, 101)))
        self.assertEqual([call.args for call in query.range.call_args_list], [(0, 99), (100, 199)])
        query.order.assert_called_with("candidate_id")

    def test_failed_search_is_not_successful_completion(self):
        for reason in ("ebay_rate_limited", "ebay_transient_error", "ebay_child_failed"):
            self.assertTrue(daily_run_failed(reason))
        for reason in ("quota_reserve_reached", "manual_chunk_limit", "cycle_completed"):
            self.assertFalse(daily_run_failed(reason))

    def test_chunk_and_historical_rescore_preserve_owner_status_and_time(self):
        self.assertEqual(scoring_run_update(123, True), {"opportunity_count": 123})
        update = scoring_run_update(123, False)
        self.assertEqual(update["status"], "completed")
        self.assertIn("completed_at", update)
