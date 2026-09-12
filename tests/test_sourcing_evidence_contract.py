import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from video_game_identity import build_identity_comparison
from sourcing_decision_trace import enrich_sourcing_diagnostics
from analyze_recent_sourcing_dismissals import is_system_action, classify_dependency


class EvidenceContractTests(unittest.TestCase):
    def test_unsupported_defaults_are_expectations_and_policy_stays_legacy(self):
        result = build_identity_comparison(amazon_title="Dirt - PlayStation 3", ebay_title="DiRT 3 PS3")
        for side in ("amazon", "ebay"):
            for field in ("edition", "packageType", "completeness", "digitalPhysical", "installment"):
                observed = result[side]["fields"][field]
                self.assertIsNone(observed["value"])
                self.assertEqual("unknown", observed["state"])
                self.assertTrue(observed["expectation"])
        self.assertEqual("Complete", result["amazon"]["completeness"])
        self.assertEqual("unknown", result["evidenceDecision"]["productIdentityVerdict"])

    def test_generic_core_product_does_not_establish_identity(self):
        result = build_identity_comparison(amazon_title="Rock Band", ebay_title="Rock Band")
        self.assertEqual("Main Game", result["amazon"]["coreProduct"])
        self.assertEqual("unknown", result["evidenceDecision"]["productIdentityVerdict"])

    def test_real_installment_conflict_has_sources_and_same_legacy_block(self):
        result = build_identity_comparison(amazon_title="Rock Band 2 PS3", ebay_title="Rock Band 3 PS3")
        self.assertTrue(result["hard_block"])
        comparison = result["evidenceDecision"]["comparisons"]["installment"]
        self.assertEqual("conflict", comparison["result"])
        self.assertTrue(result["amazon"]["fields"]["installment"]["sources"])
        self.assertEqual("non-match", result["evidenceDecision"]["productIdentityVerdict"])

    def test_origin_is_not_region(self):
        result = build_identity_comparison(amazon_title="Dirt", ebay_title="Dirt", evidence={"country_of_origin_values": ["Japan"]})
        self.assertIsNone(result["ebay"]["fields"]["region"]["value"])

    def test_unknown_counterpart_does_not_become_completed_comparison(self):
        result = build_identity_comparison(amazon_title="Unrecognized game", ebay_title="Shrek 2",
                                           evidence={"game_name_values": ["Shrek 3"]})
        self.assertEqual("conflicting_sources", result["ebay"]["fields"]["installment"]["state"])
        self.assertEqual("unknown", result["evidenceDecision"]["comparisons"]["installment"]["result"])

    def test_lifecycle_is_separate_from_identity(self):
        result = enrich_sourcing_diagnostics({}, status="rejected", opportunity_type="no_profitable_source_found", profit=1, roi_percent=2)
        decision = result["canonicalDecision"]
        self.assertEqual("unknown", decision["productIdentityVerdict"])
        self.assertEqual("rejected", decision["lifecycleStatus"])
        self.assertTrue(decision["evaluationId"])

    def test_provenance_filter_and_source_presence(self):
        for action in ({"dismiss_reason": "duplicate_open_asin_opportunity"}, {"raw_action_context": {"cleanup_source": None}}, {"raw_action_context": {"job": "availability_cleanup"}}):
            self.assertTrue(is_system_action(action))
        self.assertFalse(is_system_action({"dismiss_reason": "wrong_product"}))
        fields = {"aspects": ["arbitrary"], "category_ids": [], "category_names": [], "description": "present"}
        self.assertEqual("unclear", classify_dependency({"dismiss_reason": "wrong_product"}, {}, fields))


if __name__ == '__main__':
    unittest.main()
