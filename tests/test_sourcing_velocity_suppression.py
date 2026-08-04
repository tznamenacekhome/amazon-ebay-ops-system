from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations"))

from build_sourcing_seed_asins import velocity_suppression_active_after_evaluation  # noqa: E402
from matching_intelligence import label_for_dismiss_reason  # noqa: E402


class FakeTable:
    def __init__(self) -> None:
        self.updates = []

    def update(self, payload):
        self.updates.append(payload)
        return self

    def eq(self, *_args):
        return self

    def execute(self):
        return None


class FakeSupabase:
    def __init__(self) -> None:
        self.fake_table = FakeTable()

    def table(self, _name):
        return self.fake_table


class SourcingVelocitySuppressionTests(unittest.TestCase):
    def test_sales_velocity_too_low_is_business_issue_not_negative_identity(self) -> None:
        self.assertEqual(
            ("valid_match_poor_opportunity", "business_issue"),
            label_for_dismiss_reason("sales_velocity_too_low"),
        )

    def test_sub_threshold_improvement_stays_suppressed(self) -> None:
        supabase = FakeSupabase()
        active = velocity_suppression_active_after_evaluation(
            supabase,
            {"suppression_id": "s1", "required_velocity": 0.5},
            0.49,
        )
        self.assertTrue(active)
        self.assertEqual("active", supabase.fake_table.updates[0].get("status", "active"))

    def test_crossing_threshold_releases_suppression(self) -> None:
        supabase = FakeSupabase()
        active = velocity_suppression_active_after_evaluation(
            supabase,
            {"suppression_id": "s1", "required_velocity": 0.5},
            0.5,
        )
        self.assertFalse(active)
        self.assertEqual("released", supabase.fake_table.updates[0]["status"])
        self.assertIsNotNone(supabase.fake_table.updates[0]["reactivated_at"])


if __name__ == "__main__":
    unittest.main()
