import datetime as dt
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

import run_daily_sourcing_discovery as discovery
import run_all_syncs


class DailySourcingScheduleTests(unittest.TestCase):
    def test_discovery_runs_on_both_weekend_days(self):
        for day in (10, 11):
            with self.subTest(day=day):
                with patch("sys.argv", ["discovery"]), \
                     patch("time.time", return_value=dt.datetime(2026, 10, day, 19, tzinfo=dt.UTC).timestamp()), \
                     patch.object(discovery.subprocess, "run") as run, \
                     patch.object(discovery, "fetch_browse_quota", return_value={}), \
                     patch.object(discovery, "browse_call_budget", return_value=0):
                    self.assertEqual(discovery.main(), 0)
                    run.assert_called_once()
                    self.assertIn("integrations/run_daily_catalog_sourcing.py", run.call_args.args[0])

    def test_production_group_does_not_skip_weekends(self):
        job = next(job for job in run_all_syncs.JOBS if job.name == "Daily catalog sourcing")
        self.assertIn("sourcing-catalog", job.groups)
        self.assertNotIn("--skip-weekends", job.command())


if __name__ == "__main__":
    unittest.main()
