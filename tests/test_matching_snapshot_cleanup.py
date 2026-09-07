from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
import build_matching_intelligence_examples as builder


class MatchingCleanupTests(unittest.TestCase):
    def test_sourcing_only_rebuild_keeps_reused_action_evidence(self):
        db = MagicMock()
        self.assertEqual(builder.clear_backfill_snapshots(db, source="sourcing"), 0)
        db.table.assert_not_called()

    def test_batches_are_scoped_and_deleted_without_returning_payloads(self):
        db = MagicMock()
        query = db.table.return_value
        for method in ("select", "eq", "is_", "order", "limit", "delete", "in_"):
            getattr(query, method).return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[{"listing_snapshot_id": "a"}, {"listing_snapshot_id": "b"}]),
            SimpleNamespace(data=[]),
            SimpleNamespace(data=[{"listing_snapshot_id": "c"}]),
            SimpleNamespace(data=[]),
            SimpleNamespace(data=[]),
        ]
        self.assertEqual(builder.clear_backfill_snapshots(db, batch_size=2), 3)
        self.assertEqual(query.delete.call_count, 2)
        for call in query.delete.call_args_list:
            self.assertEqual(call.kwargs, {"returning": "minimal"})
        self.assertEqual([call.args for call in query.in_.call_args_list if call.args[0] == "listing_snapshot_id"],
                         [("listing_snapshot_id", ["a", "b"]), ("listing_snapshot_id", ["c"])])
        for call in query.eq.call_args_list:
            self.assertEqual(call.args, ("snapshot_source", "matching_intelligence_backfill"))
        self.assertEqual(query.is_.call_count, 5)
        for call in query.is_.call_args_list:
            self.assertEqual(call.args, ("action_id", "null"))

    def test_exhausted_cleanup_retries_prevent_replacement_inserts(self):
        db = MagicMock()
        query = db.table.return_value
        for method in ("select", "eq", "is_", "order", "limit", "delete", "in_"):
            getattr(query, method).return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[{"listing_snapshot_id": "a"}]),
            *[RuntimeError("statement timeout") for _ in range(4)],
        ]
        with patch.object(builder.time, "sleep"), self.assertRaisesRegex(RuntimeError, "statement timeout"):
            builder.write_rows(db, [], [{"snapshot_event": "backfill"}], "all")
        query.insert.assert_not_called()
        self.assertEqual(query.execute.call_count, 5)


if __name__ == "__main__":
    unittest.main()
