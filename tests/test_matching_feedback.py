import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from build_matching_intelligence_examples import label_for_action, label_for_receiving_outcome
from matching_intelligence import label_for_dismiss_reason
from reprocess_current_unreviewed_sourcing import summarize


class MatchingFeedbackTests(unittest.TestCase):
    def test_seller_listing_mismatch_is_negative_identity(self) -> None:
        self.assertEqual(label_for_dismiss_reason("seller_listing_mismatch"), ("non_match", "negative_identity"))

    def test_closest_excluded_action_labels(self) -> None:
        self.assertEqual(label_for_action("confirmed_valid_match", None), ("match", "positive_identity"))
        self.assertEqual(label_for_action("confirmed_exclusion", None), ("non_match", "negative_identity"))

    def test_receiving_sourcing_false_positive_is_negative_identity(self) -> None:
        self.assertEqual(
            label_for_receiving_outcome({"outcome": "sourcing_false_positive", "condition_issue": "wrong_edition_version"}),
            ("non_match", "negative_identity", "wrong_edition_version"),
        )
        self.assertEqual(
            label_for_receiving_outcome({"outcome": "sourcing_false_positive", "condition_issue": None}),
            ("non_match", "negative_identity", "sourcing_false_positive"),
        )

    def test_reprocess_summary_counts_scope_only(self) -> None:
        summary = summarize(
            [
                {
                    "status_changed": False,
                    "recommendation_changed": False,
                    "score_changed": False,
                    "newly_hard_blocked": False,
                    "new_status": "open",
                    "old_status": "open",
                    "leaves_presentation": False,
                    "enters_presentation": False,
                    "diagnostic_only_change": True,
                },
                {
                    "status_changed": True,
                    "recommendation_changed": True,
                    "score_changed": True,
                    "newly_hard_blocked": True,
                    "new_status": "rejected",
                    "old_status": "open",
                    "leaves_presentation": True,
                    "enters_presentation": False,
                    "diagnostic_only_change": False,
                },
            ]
        )
        self.assertEqual(summary["rows_in_scope"], 2)
        self.assertEqual(summary["newly_hard_blocked"], 1)
        self.assertEqual(summary["rows_leaving_presentation"], 1)
        self.assertEqual(summary["purchased_completed_dismissed_touched"], 0)


if __name__ == "__main__":
    unittest.main()
