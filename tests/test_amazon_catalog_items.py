from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations"))

from amazon_sync_catalog_items import normalize_catalog_item  # noqa: E402


class AmazonCatalogItemsTests(unittest.TestCase):
    def test_catalog_items_platform_edition_and_variation_relationships(self) -> None:
        payload = {
            "attributes": {
                "item_name": [{"value": "Final Fantasy XIV Online Complete Edition - PlayStation 4"}],
                "platform": [{"value": "Sony PlayStation 4"}],
                "edition": [{"value": "Complete Edition"}],
                "release_date": [{"value": "2017-06-20"}],
                "format": [{"value": "Physical"}],
                "item_package_quantity": [{"value": "1"}],
            },
            "productTypes": [{"productType": "VIDEO_GAME_SOFTWARE"}],
            "relationships": [
                {
                    "variationTheme": {"theme": "Platform"},
                    "relationships": [
                        {"type": "PARENT", "asin": "B000PARENT"},
                        {"type": "CHILD", "asin": ["B000CHILD1", "B000CHILD2"]},
                    ],
                }
            ],
        }
        row = normalize_catalog_item("B008E6ZXBI", payload, "ATVPDKIKX0DER")
        self.assertEqual("PS 4", row["normalized_platform"])
        self.assertEqual("Complete Edition", row["normalized_edition"])
        self.assertEqual("2017-06-20", row["normalized_release_date"])
        self.assertEqual(2017, row["normalized_release_year"])
        self.assertEqual("VIDEO_GAME_SOFTWARE", row["product_type"])
        self.assertEqual(["B000PARENT"], row["variation_parent_asins"])
        self.assertEqual(["B000CHILD1", "B000CHILD2"], row["variation_child_asins"])

    def test_catalog_items_safe_fallback(self) -> None:
        row = normalize_catalog_item("B000TEST", {"attributes": {}, "summaries": [{"itemName": "Unknown Game"}]}, "ATVPDKIKX0DER")
        self.assertIsNone(row["normalized_platform"])
        self.assertIsNone(row["normalized_edition"])
        self.assertEqual("Unknown Game", row["relevant_attributes_json"]["title"])


if __name__ == "__main__":
    unittest.main()
