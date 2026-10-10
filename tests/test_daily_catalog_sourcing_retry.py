import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from run_daily_catalog_sourcing import insert_cycle_items  # noqa: E402


class TransientUpsert:
    def __init__(self):
        self.attempts = 0
        self.payloads = []

    def table(self, name):
        self.table_name = name
        return self

    def upsert(self, payload, *, on_conflict):
        self.payloads.append((payload, on_conflict))
        return self

    def execute(self):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("RemoteProtocolError: ConnectionTerminated")
        return SimpleNamespace(data=[])


class DailyCatalogSourcingRetryTests(unittest.TestCase):
    def test_cycle_item_upsert_retries_a_terminated_supabase_connection(self):
        supabase = TransientUpsert()

        with patch("run_daily_catalog_sourcing.time.sleep"):
            insert_cycle_items(supabase, "cycle-1", [{"asin": "B000TEST01"}])

        self.assertEqual(supabase.table_name, "sourcing_coverage_cycle_items")
        self.assertEqual(supabase.attempts, 2)
        self.assertEqual(supabase.payloads[-1][1], "coverage_cycle_id,asin")
        self.assertEqual(supabase.payloads[-1][0][0]["coverage_cycle_id"], "cycle-1")


if __name__ == "__main__":
    unittest.main()
