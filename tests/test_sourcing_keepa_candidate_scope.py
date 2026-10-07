from types import SimpleNamespace
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
import build_sourcing_seed_asins as seeds


class KeepaCandidateScopeTests(unittest.TestCase):
    def test_wholesale_candidate_only_keepa_snapshot_is_not_a_full_listing_seed(self):
        def paginated(_supabase, table, _columns, **_kwargs):
            if table == "amazon_skus":
                return []
            if table == "vw_latest_keepa_product_snapshot":
                return [
                    {
                        "asin": "B07BZ2BMMK",
                        "title": "Human Fall Flat - Nintendo Switch",
                        "captured_at": "2099-01-01T00:00:00+00:00",
                        "new_price_current_cents": 7968,
                        "buy_box_price_avg90_cents": 7967,
                        "buy_box_price_current_cents": 7968,
                    },
                    {
                        "asin": "B000CAT001",
                        "title": "Independent Catalog Game - Nintendo Switch",
                        "captured_at": "2099-01-01T00:00:00+00:00",
                        "new_price_current_cents": 3999,
                        "buy_box_price_avg90_cents": 3999,
                        "buy_box_price_current_cents": 3999,
                    },
                ]
            if table == "wholesale_amazon_candidates":
                return [{"asin": "B07BZ2BMMK"}]
            raise AssertionError(table)

        with (
            patch.object(seeds, "paginate_table", side_effect=paginated),
            patch.object(seeds, "latest_listing_context_by_sku", return_value={}),
            patch.object(seeds, "latest_listing_context_by_asin", return_value={}),
            patch.object(seeds, "latest_inventory_by_asin", return_value={}),
            patch.object(seeds, "latest_catalog_context_by_asin", return_value={}),
            patch.object(seeds, "fetch_blocked_asins", return_value=set()),
            patch.object(seeds, "latest_inventory_planning_by_asin", return_value={}),
            patch.object(seeds, "finalize_seeds", side_effect=lambda rows, *_args, **_kwargs: list(rows)),
        ):
            result = seeds.build_full_listing_seeds(
                object(),
                SimpleNamespace(min_amazon_price=0),
                100,
            )

        self.assertEqual([row["asin"] for row in result], ["B000CAT001"])

    def test_wholesale_candidate_does_not_hide_an_owned_amazon_listing(self):
        def paginated(_supabase, table, _columns, **_kwargs):
            if table == "amazon_skus":
                return [
                    {
                        "asin": "B07BZ2BMMK",
                        "seller_sku": "OWNED-SKU",
                        "product_name": "Human Fall Flat - Nintendo Switch",
                        "fulfillment_channel": "AMAZON_NA",
                        "listing_price": 39.99,
                    }
                ]
            if table == "vw_latest_keepa_product_snapshot":
                return []
            if table == "wholesale_amazon_candidates":
                return [{"asin": "B07BZ2BMMK"}]
            raise AssertionError(table)

        with (
            patch.object(seeds, "paginate_table", side_effect=paginated),
            patch.object(seeds, "latest_listing_context_by_sku", return_value={}),
            patch.object(seeds, "latest_listing_context_by_asin", return_value={}),
            patch.object(seeds, "latest_inventory_by_asin", return_value={}),
            patch.object(seeds, "latest_catalog_context_by_asin", return_value={}),
            patch.object(seeds, "fetch_blocked_asins", return_value=set()),
            patch.object(seeds, "latest_inventory_planning_by_asin", return_value={}),
            patch.object(seeds, "finalize_seeds", side_effect=lambda rows, *_args, **_kwargs: list(rows)),
        ):
            result = seeds.build_full_listing_seeds(
                object(),
                SimpleNamespace(min_amazon_price=0),
                100,
            )

        self.assertEqual([row["asin"] for row in result], ["B07BZ2BMMK"])


if __name__ == "__main__":
    unittest.main()
