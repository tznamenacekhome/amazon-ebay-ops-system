from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WholesalePhase3BContractTests(unittest.TestCase):
    def test_evaluation_workspace_keeps_required_decision_evidence_together(self):
        source = (ROOT / "web/app/wholesale/page.tsx").read_text(encoding="utf-8")
        for required in (
            "Supplier evidence", "Selected Amazon listing", "Match evidence",
            "Prior account sale", "Current Buy Box economics",
            "90-day average economics", "Cost assumptions",
            "Inventory and capacity", "Risk signals", "Pass and open next",
        ):
            self.assertIn(required, source)

    def test_candidate_selection_requests_bounded_scheduler_evaluation(self):
        route = (ROOT / "web/app/api/wholesale/products/[productId]/matching/route.ts").read_text(encoding="utf-8")
        self.assertIn("runSchedulerCommandTask", route)
        self.assertIn("integrations/wholesale_evaluate_opportunities.py", route)
        self.assertIn('"--limit", "1"', route)
        self.assertIn("candidateDto", route)
        self.assertIn("buy_box_price_avg90_cents", route)

    def test_candidate_ui_waits_for_selected_asin_evaluation(self):
        source = (ROOT / "web/app/wholesale/page.tsx").read_text(encoding="utf-8")
        self.assertIn("evaluation_requested === false", source)
        self.assertIn("status.evaluation?.asin === asin", source)
        self.assertIn("Select and recalculate", source)


if __name__ == "__main__":
    unittest.main()
