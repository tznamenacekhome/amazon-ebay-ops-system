import unittest
import sys
from pathlib import Path
from types import SimpleNamespace


INTEGRATIONS = Path(__file__).resolve().parents[1] / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

from fba_pricing_keepa_until_complete import keepa_batch_command  # noqa: E402


def args(*, offers=None):
    return SimpleNamespace(batch_size=20, offers=offers)


class FbaPricingKeepaTests(unittest.TestCase):
    def test_default_batch_uses_lightweight_stats_without_offers(self):
        command = keepa_batch_command(["B000000001", "B000000002"], args())

        self.assertIn("--no-history", command)
        self.assertIn("--no-rating", command)
        self.assertNotIn("--offers", command)
        self.assertNotIn("--only-live-offers", command)
        self.assertEqual(command.count("--asin"), 2)

    def test_offer_enrichment_remains_explicit_for_diagnostics(self):
        command = keepa_batch_command(["B000000001"], args(offers=3))

        self.assertEqual(command[command.index("--offers") + 1], "3")
        self.assertIn("--only-live-offers", command)


if __name__ == "__main__":
    unittest.main()
