import datetime as dt
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from run_daily_sourcing_discovery import is_weekend  # noqa: E402


class DailySourcingScheduleTests(unittest.TestCase):
    def test_weekends_are_skipped_in_business_timezone(self):
        saturday = dt.datetime(2026, 10, 10, 19, tzinfo=dt.UTC)
        sunday = dt.datetime(2026, 10, 11, 19, tzinfo=dt.UTC)
        self.assertTrue(is_weekend("America/Los_Angeles", now=saturday))
        self.assertTrue(is_weekend("America/Los_Angeles", now=sunday))

    def test_weekdays_continue_spending_quota(self):
        monday = dt.datetime(2026, 10, 12, 19, tzinfo=dt.UTC)
        self.assertFalse(is_weekend("America/Los_Angeles", now=monday))


if __name__ == "__main__":
    unittest.main()
