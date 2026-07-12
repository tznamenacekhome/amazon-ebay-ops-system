from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from run_sourcing_workflow import choose_batch_opportunities, fetch_ebay_search_summary, summarize_funnel_from_rows  # noqa: E402
from ebay_api_limits import browse_call_budget, parse_browse_quota  # noqa: E402
from score_sourcing_opportunities import required_offer_percent, suggested_max_bid, suggested_offer  # noqa: E402


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

    def test_choose_batch_opportunities_target_zero_keeps_all_unique_rows(self):
        rows = [
            {"opportunity_id": "first", "status": "open", "opportunity_type": "buy_now", "ebay_item_id": "v1|100|0"},
            {"opportunity_id": "duplicate", "status": "open", "opportunity_type": "best_offer", "ebay_item_id": "100"},
            {"opportunity_id": "second", "status": "open", "opportunity_type": "auction", "ebay_item_id": "200"},
        ]

        selected = choose_batch_opportunities(rows, set(), 0)

        self.assertEqual([row["opportunity_id"] for row in selected], ["first", "second"])

    def test_parse_browse_quota_from_analytics_payload(self):
        quota = parse_browse_quota(
            {
                "rateLimits": [
                    {"apiName": "Other", "resources": []},
                    {
                        "apiName": "Browse",
                        "resources": [
                            {
                                "name": "buy.browse",
                                "rates": [
                                    {
                                        "count": 5020,
                                        "limit": 5000,
                                        "remaining": 0,
                                        "reset": "2026-07-12T07:00:00.000Z",
                                        "timeWindow": 86400,
                                    }
                                ],
                            }
                        ],
                    },
                ]
            }
        )

        self.assertIsNotNone(quota)
        self.assertEqual(quota.remaining, 0)
        self.assertEqual(quota.limit, 5000)
        self.assertEqual(browse_call_budget(quota, reserve=100), 0)

    def test_suggested_offer_discounts_below_ask_when_cap_exceeds_listing_price(self):
        settings = SimpleNamespace(best_offer_min_ask_percent=60)
        candidate = {"best_offer_enabled": True, "price": 20, "shipping_cost": 5}

        offer = suggested_offer(candidate, 40, settings)

        self.assertEqual(offer, 19)
        self.assertEqual(required_offer_percent(candidate, offer), 95)

    def test_suggested_offer_skips_when_profitable_offer_would_be_too_low(self):
        settings = SimpleNamespace(best_offer_min_ask_percent=60)
        candidate = {"best_offer_enabled": True, "price": 20, "shipping_cost": 5}

        self.assertIsNone(suggested_offer(candidate, 16, settings))

    def test_suggested_max_bid_subtracts_shipping_from_landed_cap(self):
        candidate = {"shipping_cost": 7.5}

        self.assertEqual(suggested_max_bid(candidate, 30, False), 22.5)
        self.assertIsNone(suggested_max_bid(candidate, 30, True))

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

    def test_fetch_ebay_search_summary_handles_nested_summary(self):
        supabase = FakeSupabase({"raw_summary_json": {"ebay_search": {"rate_limited": True, "searched_seed_count": 0}}})

        summary = fetch_ebay_search_summary(supabase, "run-1")

        self.assertEqual(summary, {"rate_limited": True, "searched_seed_count": 0})


class FakeSupabase:
    def __init__(self, row):
        self.row = row

    def table(self, _name):
        return self

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def maybe_single(self):
        return self

    def execute(self):
        return FakeResponse(self.row)


class FakeResponse:
    def __init__(self, data):
        self.data = data


if __name__ == "__main__":
    unittest.main()
