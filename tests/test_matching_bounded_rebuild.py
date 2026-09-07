import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
import build_matching_intelligence_examples as builder


class BoundedRebuildTests(unittest.TestCase):
    def test_reused_evidence_and_missing_evidence_cross_batch_boundaries(self):
        actions = [{"action_id": str(i), "opportunity_id": "opp-" + str(i), "action_type": "dismissed",
                    "dismiss_reason": "wrong_system"} for i in range(205)]
        read_sizes = []

        def existing(db, ids):
            return {key: {"listing_snapshot_id": "saved-" + key, "action_id": key,
                          "ebay_title": "Original reviewed title"} for key in ids if int(key) % 2 == 0}

        def opportunities(db, ids):
            read_sizes.append(len(ids))
            return [{"opportunity_id": key, "sourcing_ebay_candidates": {
                "ebay_title": "Backfilled title", "raw_ebay_json": {"description": "Historical evidence"}}} for key in ids]

        with builder.SnapshotSpool() as spool, patch.object(builder, "paginate_table", return_value=actions), \
                patch.object(builder, "fetch_listing_snapshots_by_action_ids", side_effect=existing), \
                patch.object(builder, "fetch_opportunities_by_ids", side_effect=opportunities):
            examples, result = builder.build_sourcing_examples(None, None, snapshot_sink=spool)
            self.assertIs(result, spool)
            self.assertEqual(len(examples), 205)
            self.assertEqual(len(spool), 102)
            self.assertEqual(len(read_sizes), 3)
            self.assertLessEqual(max(read_sizes), 100)
            self.assertEqual(examples[0]["listing_snapshot_id"], "saved-0")
            self.assertEqual(examples[200]["listing_snapshot_id"], "saved-200")
            self.assertEqual(examples[1]["ebay_description"], "Historical evidence")
            snapshots = list(spool)
            self.assertEqual(snapshots, list(spool))
            self.assertEqual(snapshots[0]["raw_ebay_json"], {"description": "Historical evidence"})
        self.assertTrue(spool.file.closed)
