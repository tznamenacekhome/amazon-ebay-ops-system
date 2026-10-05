import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from sourcing_coverage_cycle import (  # noqa: E402
    PRIORITY_CATALOG_REMAINING,
    PRIORITY_PURCHASED_NOT_SENT,
    PRIORITY_RECENTLY_SOLD,
    is_purchased_not_yet_sent_to_amazon,
    is_video_game_seed,
    build_unified_priority_queue,
    queue_row_from_seed,
    queue_sort_key,
    seed_row_for_run,
)


class SourcingCoverageCycleTests(unittest.TestCase):
    def test_purchased_received_at_home_qualifies_for_priority_2(self):
        item = {
            "asin": "B000TEST01",
            "current_status": "received",
            "marketplace": "Amazon",
            "quantity": 1,
            "exclude_from_purchase_reporting": False,
        }

        self.assertIs(is_purchased_not_yet_sent_to_amazon(item, []), True)

    def test_purchased_already_listed_does_not_qualify_for_priority_2(self):
        item = {
            "asin": "B000TEST01",
            "current_status": "listed",
            "marketplace": "Amazon",
            "quantity": 1,
            "exclude_from_purchase_reporting": False,
        }

        self.assertIs(is_purchased_not_yet_sent_to_amazon(item, []), False)

    def test_shipped_fba_link_does_not_qualify_for_priority_2(self):
        item = {
            "asin": "B000TEST01",
            "current_status": "received",
            "marketplace": "Amazon",
            "quantity": 1,
            "exclude_from_purchase_reporting": False,
        }
        fba_links = [
            {
                "quantity": 1,
                "included": True,
                "fba_shipments": {"shipment_code": "FBA123", "workflow_status": "finalized"},
            }
        ]

        self.assertIs(is_purchased_not_yet_sent_to_amazon(item, fba_links), False)

    def test_cancelled_refunded_returned_purchase_does_not_qualify(self):
        for status in ("cancelled", "return_opened", "return_pending", "refunded", "returned"):
            item = {
                "asin": "B000TEST01",
                "current_status": status,
                "marketplace": "Amazon",
                "quantity": 1,
                "exclude_from_purchase_reporting": False,
            }
            self.assertIs(is_purchased_not_yet_sent_to_amazon(item, []), False)

    def test_same_asin_highest_priority_sorts_first(self):
        seed = {
            "asin": "B000TEST01",
            "amazon_title": "Test Game",
            "last_sold_at": "2026-07-10T00:00:00+00:00",
            "inventory_need_level": "critical",
            "raw_context_json": {},
        }
        recent = queue_row_from_seed(seed, PRIORITY_RECENTLY_SOLD)
        purchased = queue_row_from_seed(seed, PRIORITY_PURCHASED_NOT_SENT)
        catalog = queue_row_from_seed(seed, PRIORITY_CATALOG_REMAINING)

        self.assertLess(queue_sort_key(recent), queue_sort_key(purchased))
        self.assertLess(queue_sort_key(purchased), queue_sort_key(catalog))

    def test_catalog_never_sold_sorts_after_catalog_with_sale_date(self):
        sold = queue_row_from_seed(
            {
                "asin": "B000TEST01",
                "amazon_title": "Sold Game",
                "last_sold_at": "2026-07-10T00:00:00+00:00",
                "inventory_need_level": "critical",
                "raw_context_json": {},
            },
            PRIORITY_CATALOG_REMAINING,
        )
        never_sold = queue_row_from_seed(
            {
                "asin": "B000TEST02",
                "amazon_title": "Never Sold Game",
                "last_sold_at": None,
                "inventory_need_level": "critical",
                "raw_context_json": {},
            },
            PRIORITY_CATALOG_REMAINING,
        )

        self.assertLess(queue_sort_key(sold), queue_sort_key(never_sold))

    def test_video_game_seed_accepts_keepa_video_games_category(self):
        seed = {
            "asin": "B000TEST01",
            "amazon_title": "Some Game",
            "raw_context_json": {
                "keepa_product_group": "Video Games",
                "keepa_category_tree": "Video Games > Nintendo Switch > Games",
            },
        }

        self.assertIs(is_video_game_seed(seed), True)

    def test_video_game_seed_rejects_known_non_game_categories(self):
        for seed in (
            {
                "asin": "B000TEST02",
                "amazon_title": "Harmony Good Dog Ceramic Dog Bowl, 6 Cups",
                "raw_context_json": {"keepa_product_group": "Pet Products", "keepa_category_tree": "Pet Supplies"},
            },
            {
                "asin": "B000TEST03",
                "amazon_title": "Happy Birthday, Mrs. Piggle-Wiggle",
                "raw_context_json": {"keepa_product_group": "Book"},
            },
            {
                "asin": "B000TEST04",
                "amazon_title": "Family Game Night Board Game",
                "raw_context_json": {"keepa_product_group": "Toys & Games", "keepa_category_tree": "Board Games"},
            },
        ):
            self.assertIs(is_video_game_seed(seed), False)

    def test_unified_priority_queue_excludes_same_run_asins(self):
        recent_seed = {
            "asin": "B000TEST01",
            "amazon_title": "Recently Sold Game",
            "last_sold_at": "2026-07-10T00:00:00+00:00",
            "inventory_need_level": "critical",
            "raw_context_json": {},
        }
        catalog_seed = {
            "asin": "B000TEST02",
            "amazon_title": "Catalog Game",
            "last_sold_at": "2026-07-09T00:00:00+00:00",
            "inventory_need_level": "high",
            "raw_context_json": {},
        }

        with (
            patch("sourcing_coverage_cycle.fetch_settings", return_value=object()),
            patch("sourcing_coverage_cycle.build_recent_sales_seeds", return_value=[recent_seed]),
            patch("sourcing_coverage_cycle.build_purchased_not_sent_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_full_listing_seeds", return_value=[catalog_seed]),
            patch("sourcing_coverage_cycle.build_wholesale_catalog_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.fetch_fresh_restricted_asins", return_value=set()),
        ):
            queue = build_unified_priority_queue(object(), exclude_asins={"B000TEST01"})

        self.assertEqual([row["asin"] for row in queue.rows], ["B000TEST02"])
        self.assertEqual(queue.counts[PRIORITY_RECENTLY_SOLD], 0)
        self.assertEqual(queue.counts[PRIORITY_CATALOG_REMAINING], 1)

    def test_duplicate_recent_sale_and_wholesale_seed_searches_once_and_merges_provenance(self):
        recent = {
            "asin": "B000TEST01", "amazon_title": "Proven Game", "source_mode": "recent_sales",
            "last_sold_at": "2026-10-01T00:00:00+00:00", "inventory_need_level": "critical",
            "target_sale_price": 40, "raw_context_json": {},
        }
        wholesale = {
            "asin": "B000TEST01", "amazon_title": "Supplier Game", "source_mode": "wholesale_catalog",
            "last_sold_at": None, "inventory_need_level": "low", "target_sale_price": 35,
            "raw_context_json": {"source_modes": ["wholesale_catalog"], "wholesale_catalog": {"supplier_selections": [{"supplier_id": "royal"}]}},
        }
        with (
            patch("sourcing_coverage_cycle.build_recent_sales_seeds", return_value=[recent]),
            patch("sourcing_coverage_cycle.build_purchased_not_sent_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_full_listing_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_wholesale_catalog_seeds", return_value=[wholesale]),
            patch("sourcing_coverage_cycle.fetch_fresh_restricted_asins", return_value=set()),
        ):
            queue = build_unified_priority_queue(object(), settings=object())
        self.assertEqual(len(queue.rows), 1)
        seed = queue.rows[0]["seed_snapshot_json"]
        self.assertEqual(seed["target_sale_price"], 40)
        self.assertEqual(seed["raw_context_json"]["source_modes"], ["recent_sales", "wholesale_catalog"])
        self.assertIn("wholesale_catalog", seed["raw_context_json"])

    def test_multiple_wholesale_products_for_one_asin_seed_once(self):
        def wholesale(supplier_id):
            return {
                "asin": "B000TEST01", "amazon_title": "Game", "source_mode": "wholesale_catalog",
                "last_sold_at": None, "inventory_need_level": "low", "target_sale_price": 35,
                "raw_context_json": {"source_modes": ["wholesale_catalog"], "wholesale_catalog": {"supplier_selections": [{"supplier_id": supplier_id}]}},
            }
        with (
            patch("sourcing_coverage_cycle.build_recent_sales_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_purchased_not_sent_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_full_listing_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_wholesale_catalog_seeds", return_value=[wholesale("one"), wholesale("two")]),
            patch("sourcing_coverage_cycle.fetch_fresh_restricted_asins", return_value=set()),
        ):
            queue = build_unified_priority_queue(object(), settings=object())
        self.assertEqual(len(queue.rows), 1)

    def test_global_fresh_restriction_excludes_other_seed_sources(self):
        recent = {"asin": "B000TEST01", "amazon_title": "Game", "last_sold_at": "2026-10-01T00:00:00+00:00", "inventory_need_level": "critical", "raw_context_json": {}}
        with (
            patch("sourcing_coverage_cycle.build_recent_sales_seeds", return_value=[recent]),
            patch("sourcing_coverage_cycle.build_purchased_not_sent_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_full_listing_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.build_wholesale_catalog_seeds", return_value=[]),
            patch("sourcing_coverage_cycle.fetch_fresh_restricted_asins", return_value={"B000TEST01"}),
        ):
            queue = build_unified_priority_queue(object(), settings=object())
        self.assertEqual(queue.rows, [])

    def test_wholesale_seed_keeps_catalog_priority_and_explicit_source(self):
        seed = {"asin": "B000TEST01", "source_mode": "wholesale_catalog", "raw_context_json": {}}
        item = {**queue_row_from_seed(seed, PRIORITY_CATALOG_REMAINING), "cycle_item_id": "item", "queue_position": 9}
        result = seed_row_for_run(item, "run", "cycle")
        self.assertEqual(result["source_mode"], "wholesale_catalog")
        self.assertEqual(result["priority_bucket"], PRIORITY_CATALOG_REMAINING)


if __name__ == "__main__":
    unittest.main()
