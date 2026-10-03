from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WholesalePhase3BContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = (ROOT / "web/app/wholesale/page.tsx").read_text(encoding="utf-8")
        cls.full_api = (ROOT / "web/app/api/wholesale/full-import/route.ts").read_text(encoding="utf-8")
        cls.match_api = (ROOT / "web/app/api/wholesale/products/[productId]/matching/route.ts").read_text(encoding="utf-8")

    def test_exact_three_tab_navigation_and_order_list_name(self):
        self.assertIn('type Tab = "ready" | "order" | "full"', self.page)
        self.assertIn('[["ready", "Ready to Review"], ["order", "Order List"], ["full", "Full Import"]]', self.page)
        self.assertNotIn("Temporary Passes", self.page)
        self.assertNotIn("Added to Order", self.page)

    def test_ready_column_order_and_no_evaluate_popup(self):
        columns = ["Supplier Item", "Amazon Match", "Supplier Price", "Current Buy Box", "90-Day Average", "Supplier History", "Inventory / Capacity", "Risk Signals", "Actions"]
        positions = [self.page.index(f"<Th>{column}</Th>") for column in columns]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn(">Evaluate<", self.page)
        self.assertNotIn("EvaluationDialog", self.page)

    def test_full_import_is_supplier_and_list_date_aware(self):
        for text in ("Supplier list date", "Effective list date:", "Imported:", "Products:", "All suppliers"):
            self.assertIn(text, self.page)
        self.assertIn("fetchImportObservations(supabase, selectedImport.import_id)", self.full_api)
        self.assertIn('eq("import_id", importId)', self.full_api)
        self.assertIn("wholesale_supplier_observations", self.full_api)
        self.assertIn("IMPORT_OBSERVATION_PAGE_SIZE = 500", self.full_api)
        self.assertIn("offset + IMPORT_OBSERVATION_PAGE_SIZE - 1", self.full_api)

    def test_full_import_explicit_filters(self):
        for text in ("ROI Too Low", "Restricted", "Eligibility Pending", "Pricing / Keepa Pending",
                     "Non-North-American Version", "Listing / ASIN Issue", "Unsupported Product Economics",
                     "Passed — Too Much Inventory", "Passed — Price Risk", "Passed — Competition", "Passed — Other"):
            self.assertIn(text, self.page)
        self.assertNotIn('"Not Qualified"', self.page)

    def test_candidate_evidence_and_compatibility_are_human_readable(self):
        for text in ("Matched by UPC + Title/Platform", "Matched by Title + Platform", "Supplier identifier:",
                     "Amazon identifier:", "Search:", "Amazon result:", "Compatible — title and platform align",
                     "Not compatible — different platform", "Review needed — region unclear"):
            self.assertIn(text, self.page)
        self.assertIn("match_evidence", self.match_api)
        self.assertIn("query_context", self.match_api)

    def test_candidate_selection_is_eligible_compatible_and_recalculated(self):
        self.assertIn('candidate.compatibility_status !== "compatible"', self.page)
        self.assertIn('candidate.eligibility_status !== "eligible"', self.page)
        self.assertIn("evaluation_requested === false", self.page)
        self.assertIn("integrations/wholesale_evaluate_opportunities.py", self.match_api)

    def test_order_list_explicitly_remains_draft_only(self):
        self.assertIn("This saves a draft commitment only", self.page)
        self.assertIn("does not create a supplier purchase order", self.page)


if __name__ == "__main__":
    unittest.main()
