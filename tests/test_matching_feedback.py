import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from build_matching_intelligence_examples import label_for_action, label_for_receiving_outcome
from analyze_matching_feedback import summarize_feedback_rows
from matching_feedback import matching_feedback_from_context, normalize_matching_feedback
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

    def test_legacy_full_title_maps_to_evidence_not_rule_failure(self) -> None:
        feedback = normalize_matching_feedback(
            {
                "allAssumptionsCorrect": False,
                "incorrectRows": ["full_title", "game_name"],
            }
        )
        self.assertEqual(feedback["failedRuleFamilies"], [])
        self.assertIn("amazon_title", feedback["evidenceSources"])
        self.assertIn("ebay_title", feedback["evidenceSources"])
        self.assertIn("ebay_game_name", feedback["evidenceSources"])

    def test_legacy_rule_rows_map_to_rule_families(self) -> None:
        feedback = normalize_matching_feedback(
            {
                "incorrectRows": [
                    "core_game_identity",
                    "platform_system",
                    "installment_number",
                    "edition_version",
                ]
            }
        )
        self.assertEqual(
            feedback["failedRuleFamilies"],
            ["core_game_identity", "platform", "numeric_installment", "edition_version"],
        )

    def test_all_assumptions_correct_clears_failures_and_evidence(self) -> None:
        feedback = normalize_matching_feedback(
            {
                "allAssumptionsCorrect": True,
                "failedRuleFamilies": ["platform"],
                "evidenceSources": ["amazon_title"],
                "incorrectRows": ["platform_system"],
            }
        )
        self.assertEqual(feedback["failedRuleFamilies"], [])
        self.assertEqual(feedback["evidenceSources"], [])
        self.assertEqual(feedback["legacyIncorrectRows"], [])

    def test_rock_band_track_pack_feedback_shape(self) -> None:
        feedback = normalize_matching_feedback(
            {
                "failedRuleFamilies": ["core_game_identity"],
                "evidenceSources": ["amazon_title", "ebay_title", "ebay_game_name"],
            }
        )
        self.assertEqual(feedback["failedRuleFamilies"], ["core_game_identity"])
        self.assertEqual(feedback["evidenceSources"], ["amazon_title", "ebay_title", "ebay_game_name"])
        self.assertNotIn("numeric_installment", feedback["failedRuleFamilies"])
        self.assertNotIn("platform", feedback["failedRuleFamilies"])
        self.assertNotIn("edition_version", feedback["failedRuleFamilies"])

    def test_matching_feedback_from_legacy_action_context(self) -> None:
        feedback = matching_feedback_from_context(
            {
                "diagnosticsFeedback": {
                    "allAssumptionsCorrect": False,
                    "incorrectRows": ["edition_version"],
                }
            }
        )
        self.assertEqual(feedback["failedRuleFamilies"], ["edition_version"])

    def test_feedback_aggregation_counts_rule_families_and_evidence(self) -> None:
        summary = summarize_feedback_rows(
            [
                {
                    "action_id": "a1",
                    "action_type": "dismissed",
                    "dismiss_reason": "wrong_product",
                    "created_at": "2026-08-02T10:00:00Z",
                    "raw_action_context": {
                        "matchingFeedback": {
                            "failedRuleFamilies": ["core_game_identity"],
                            "evidenceSources": ["amazon_title", "ebay_title"],
                        }
                    },
                },
                {
                    "action_id": "a2",
                    "action_type": "dismissed",
                    "dismiss_reason": "wrong_platform",
                    "created_at": "2026-08-02T11:00:00Z",
                    "raw_action_context": {
                        "diagnosticsFeedback": {
                            "incorrectRows": ["platform_system", "full_title"],
                        }
                    },
                },
            ]
        )
        self.assertEqual(summary["rule_family_counts"]["core_game_identity"], 1)
        self.assertEqual(summary["rule_family_counts"]["platform"], 1)
        self.assertEqual(summary["evidence_source_counts"]["amazon_title"], 2)
        self.assertEqual(summary["dismiss_reason_counts"]["wrong_product"], 1)


if __name__ == "__main__":
    unittest.main()
