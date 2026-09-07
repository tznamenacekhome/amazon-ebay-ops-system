from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from build_matching_intelligence_examples import MATCHING_SNAPSHOT_COLUMNS, OPPORTUNITY_SNAPSHOT_COLUMNS, SEED_SNAPSHOT_COLUMNS
from matching_intelligence import example_from_snapshot, build_listing_snapshot


class MatchingSnapshotProjectionTests(unittest.TestCase):
    def test_opportunity_projection_preserves_full_snapshot_including_raw_ebay(self):
        opportunity = {key: "value-" + key for key in OPPORTUNITY_SNAPSHOT_COLUMNS.split(",")}
        opportunity["matching_diagnostics"] = {"large": "unused" * 1000}
        seed = {key: "seed-" + key for key in SEED_SNAPSHOT_COLUMNS.split(",")}
        seed["raw_keepa_json"] = {"large": "unused" * 1000}
        candidate = {"ebay_title": "Game", "raw_ebay_json": {
            "description": "Case and cartridge", "localizedAspects": [{"name": "Platform", "value": "Switch"}],
            "additionalImages": [{"imageUrl": "back"}], "seller": {"username": "seller"}}}
        with patch("matching_intelligence.dt") as clock:
            clock.datetime.now.return_value.isoformat.return_value = "fixed"
            full = build_listing_snapshot(opportunity=opportunity, seed=seed, candidate=candidate, event="backfill")
            compact = build_listing_snapshot(
                opportunity={key: opportunity[key] for key in OPPORTUNITY_SNAPSHOT_COLUMNS.split(",")},
                seed={key: seed[key] for key in SEED_SNAPSHOT_COLUMNS.split(",")},
                candidate=candidate, event="backfill")
        self.assertEqual(full, compact)
        self.assertEqual(full["raw_ebay_json"], candidate["raw_ebay_json"])

    def test_compact_snapshot_preserves_identity_and_review_evidence(self):
        full = {
            "listing_snapshot_id": "snapshot-1", "action_id": "action-1",
            "opportunity_id": "opportunity-1", "candidate_id": "candidate-1",
            "asin": "TESTASIN01", "amazon_title": "Game for Switch",
            "amazon_system": "Switch", "amazon_image_url": "amazon-image",
            "ebay_item_id": "v1|123|0", "ebay_legacy_item_id": "123",
            "ebay_title": "Game cartridge", "ebay_description": "Case included",
            "ebay_primary_image_url": "primary", "ebay_image_urls": ["primary", "back"],
            "ebay_item_specifics_json": {"Platform": "Nintendo Switch"},
            "ebay_condition": "Used", "ebay_category": "Video Games",
            "seller_username": "test-seller", "captured_at": "2026-09-06T01:00:00Z",
            "raw_ebay_json": {"large_unused_payload": "x" * 10000},
            "raw_context_json": {"original_request": "unused"},
            "price": 12, "shipping_cost": 3, "quantity_available": 2,
        }
        compact = {key: full[key] for key in MATCHING_SNAPSHOT_COLUMNS.split(",")}
        for action in ({}, {"action_id": "action-1", "action_type": "dismissed",
                            "dismiss_reason": "wrong_system", "notes": "Reviewed case photo",
                            "created_at": "2026-09-06T02:00:00Z"}):
            with self.subTest(action=action), patch("matching_intelligence.dt") as clock:
                clock.datetime.now.return_value.isoformat.return_value = "fixed-rebuild-time"
                args = dict(source_table="sourcing_actions", source_id="action-1",
                            source_detail="dismissed", action=action,
                            match_label="non_match", label_type="negative_identity",
                            raw_context={"action": action})
                self.assertEqual(example_from_snapshot(snapshot=full, **args),
                                 example_from_snapshot(snapshot=compact, **args))


if __name__ == "__main__":
    unittest.main()
