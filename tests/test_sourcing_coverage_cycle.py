import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from sourcing_coverage_cycle import (  # noqa: E402
    PRIORITY_CATALOG_REMAINING,
    PRIORITY_PURCHASED_NOT_SENT,
    PRIORITY_RECENTLY_SOLD,
    is_purchased_not_yet_sent_to_amazon,
    queue_row_from_seed,
    queue_sort_key,
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


if __name__ == "__main__":
    unittest.main()
