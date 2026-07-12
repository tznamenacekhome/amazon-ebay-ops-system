from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from run_sourcing_workflow import choose_batch_opportunities, summarize_funnel_from_rows  # noqa: E402


class SourcingProgressiveBatchTests(unittest.TestCase):
    def test_choose_batch_opportunities_skips_nonqualifying_and_prior_batch_rows(self):
        rows = [
            {"opportunity_id": "shown", "status": "open", "opportunity_type": "buy_now", "ebay_item_id": "1", "score": 99},
            {"opportunity_id": "rejected", "status": "rejected", "opportunity_type": "buy_now", "ebay_item_id": "2"},
            {"opportunity_id": "watch", "status": "open", "opportunity_type": "watch", "ebay_item_id": "3"},
            {"opportunity_id": "first", "status": "open", "opportunity_type": "buy_now", "ebay_item_id": "v1|100|0"},
            {"opportunity_id": "duplicate", "status": "open", "opportunity_type": "best_offer", "ebay_item_id": "100"},
            {"opportunity_id": "second", "status": "open", "opportunity_type": "auction", "ebay_item_id": "200"},
        ]

        selected = choose_batch_opportunities(rows, {"shown"}, 10)

        self.assertEqual([row["opportunity_id"] for row in selected], ["first", "second"])

    def test_choose_batch_opportunities_stops_at_target(self):
        rows = [
            {"opportunity_id": f"opp-{index}", "status": "open", "opportunity_type": "buy_now", "ebay_item_id": str(index)}
            for index in range(5)
        ]

        selected = choose_batch_opportunities(rows, set(), 3)

        self.assertEqual([row["opportunity_id"] for row in selected], ["opp-0", "opp-1", "opp-2"])

    def test_summarize_funnel_counts_blocks_and_profitability_rejects(self):
        rows = [
            {"status": "open", "opportunity_type": "buy_now"},
            {"status": "rejected", "opportunity_type": "no_profitable_source_found", "ai_flags": ["Blocked: wrong platform"]},
            {"status": "rejected", "opportunity_type": "no_profitable_source_found", "ai_flags": []},
            {"status": "open", "opportunity_type": "watch"},
        ]

        funnel = summarize_funnel_from_rows(rows, batch_item_count=1)

        self.assertEqual(funnel["scored_opportunities"], 4)
        self.assertEqual(funnel["valid_open_opportunities"], 2)
        self.assertEqual(funnel["batch_opportunities"], 1)
        self.assertEqual(funnel["hard_blocked_opportunities"], 1)
        self.assertEqual(funnel["profitability_rejects"], 1)
        self.assertEqual(funnel["review_or_watch"], 1)


if __name__ == "__main__":
    unittest.main()
