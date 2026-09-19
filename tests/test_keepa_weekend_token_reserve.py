from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATIONS = ROOT / "integrations"
if str(INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(INTEGRATIONS))

from keepa_sync_products import active_weekend_token_reserve  # noqa: E402


class KeepaWeekendTokenReserveTests(unittest.TestCase):
    def test_reserve_is_active_saturday_and_sunday_in_pacific_time(self) -> None:
        saturday = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)
        sunday = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)

        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=saturday), 150)
        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=sunday), 150)

    def test_full_pool_is_available_on_weekdays(self) -> None:
        friday = datetime(2026, 9, 19, 6, 59, tzinfo=timezone.utc)
        monday = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)

        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=friday), 0)
        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=monday), 0)

    def test_pacific_midnight_controls_the_boundary(self) -> None:
        before_saturday = datetime(2026, 9, 19, 6, 59, 59, tzinfo=timezone.utc)
        saturday_midnight = datetime(2026, 9, 19, 7, 0, tzinfo=timezone.utc)

        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=before_saturday), 0)
        self.assertEqual(active_weekend_token_reserve(150, "America/Los_Angeles", now=saturday_midnight), 150)


if __name__ == "__main__":
    unittest.main()
