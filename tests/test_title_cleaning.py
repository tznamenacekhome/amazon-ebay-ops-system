import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from title_cleaning import clean_marketplace_title_for_search, decompose_title_for_search


class TitleCleaningRegressionTests(unittest.TestCase):
    def test_existing_ebay_query_behavior_is_unchanged(self):
        self.assertEqual(
            clean_marketplace_title_for_search("Nintendo Switch Mario Kart 8 Deluxe - Brand New Sealed"),
            "Mario Kart 8 Deluxe Nintendo Switch",
        )
        self.assertEqual(clean_marketplace_title_for_search("Wii Play"), "Wii Play")

    def test_supplier_profile_preserves_identity_sensitive_terms(self):
        core, platforms = decompose_title_for_search(
            "P4 Game Deluxe Code in Box EU Version",
            leading_system_aliases=["P4"], remove_marketplace_noise=False,
        )
        self.assertEqual(core, "Game Deluxe Code in Box EU Version")
        self.assertEqual(platforms, ["P4"])


if __name__ == "__main__":
    unittest.main()
