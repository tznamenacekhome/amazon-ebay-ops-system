import unittest

from integrations.sourcing_decision_trace import enrich_sourcing_diagnostics


class SourcingDecisionTraceTest(unittest.TestCase):
    def test_numeric_block_becomes_primary_reason(self):
        diagnostics = {
            "recommendation": "Blocked",
            "numeric_identity": {
                "result": "blocked",
                "reason": "numeric identity mismatch for game installment",
            },
            "flags": ["Blocked: numeric identity mismatch for game installment"],
        }
        enriched = enrich_sourcing_diagnostics(
            diagnostics,
            status="rejected",
            opportunity_type="no_profitable_source_found",
            profit=12.5,
            roi_percent=40.0,
        )

        self.assertEqual(
            enriched["presentationDecision"]["primaryReason"]["code"],
            "numeric_installment_mismatch",
        )
        self.assertTrue(enriched["decisionTrace"])

    def test_profitability_reason_when_no_hard_block(self):
        enriched = enrich_sourcing_diagnostics(
            {"recommendation": "Probable Match"},
            status="rejected",
            opportunity_type="no_profitable_source_found",
            profit=-1.0,
            roi_percent=-2.0,
        )

        self.assertEqual(enriched["presentationDecision"]["primaryReason"]["code"], "profitability")

    def test_current_open_row_has_no_exclusion_reason(self):
        enriched = enrich_sourcing_diagnostics(
            {"recommendation": "Strong Match", "historical_positive_count": 1},
            status="open",
            opportunity_type="buy_now",
            profit=20.0,
            roi_percent=80.0,
        )

        self.assertIsNone(enriched["presentationDecision"]["primaryReason"])
        self.assertTrue(enriched["presentationDecision"]["eligible"])

    def test_platform_beats_profitability_by_priority(self):
        enriched = enrich_sourcing_diagnostics(
            {
                "recommendation": "Blocked",
                "platform_rule": {"result": "blocked", "reason": "platform mismatch"},
            },
            status="rejected",
            opportunity_type="no_profitable_source_found",
            profit=-1.0,
            roi_percent=-2.0,
        )

        self.assertEqual(enriched["presentationDecision"]["primaryReason"]["code"], "wrong_platform")


if __name__ == "__main__":
    unittest.main()
