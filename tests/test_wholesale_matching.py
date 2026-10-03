import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from wholesale_matching import (  # noqa: E402
    canonical_platform, evaluate_compatibility, identity_signature,
    identifier_search, merge_candidates, query_fingerprint, select_preferred,
    title_platform_query,
)


def product(title="Metroid Prime 4 Beyond", system="SW2"):
    return {"raw_title": title, "raw_system": system}


def catalog(title="Metroid Prime 4 Beyond", platform="Switch 2", **values):
    return {"product_type": "VIDEO_GAME", "normalized_platform": platform,
            "relevant_attributes_json": {"title": title}, **values}


class WholesaleMatchingTests(unittest.TestCase):
    def test_identifier_search_accepts_upc_and_ean_only(self):
        self.assertEqual(identifier_search("045496906023"), ("045496906023", "UPC"))
        self.assertEqual(identifier_search("0045496906023"), ("0045496906023", "EAN"))
        self.assertIsNone(identifier_search("12345"))

    def test_platform_codes_are_canonical(self):
        self.assertEqual(canonical_platform("ACCSW2"), "Switch 2")
        self.assertEqual(canonical_platform("P4"), "PS 4")
        self.assertEqual(title_platform_query("  Game Name  ", "PS5"), "Game Name PS 5")

    def test_query_cache_key_ignores_formatting_but_includes_marketplace(self):
        left = query_fingerprint("identifier", " 0123 ", "ATVPDKIKX0DER")
        right = query_fingerprint("IDENTIFIER", "0123", "ATVPDKIKX0DER")
        self.assertEqual(left, right)
        self.assertNotEqual(left, query_fingerprint("identifier", "0123", "other"))

    def test_merge_deduplicates_and_preserves_both_sources(self):
        rows = merge_candidates([{"asin": "B000000001"}], [{"asin": "B000000001"}, {"asin": "B000000002"}])
        self.assertEqual([row["asin"] for row in rows], ["B000000001", "B000000002"])
        self.assertEqual(rows[0]["match_sources"], ["identifier", "title_platform"])

    def test_platform_mismatch_is_incompatible(self):
        result = evaluate_compatibility(product(system="SW2"), catalog(platform="PS 5"))
        self.assertEqual(result.status, "incompatible")
        self.assertIn("platform_mismatch", result.reason_codes)

    def test_accessory_game_mismatch_is_incompatible(self):
        result = evaluate_compatibility(product("Wireless Controller", "ACCSW"), catalog("Adventure Quest", "Switch"))
        self.assertEqual(result.status, "incompatible")
        self.assertIn("accessory_type_mismatch", result.reason_codes)

    def test_digital_physical_mismatch_is_incompatible(self):
        result = evaluate_compatibility(product(), catalog("Metroid Prime 4 Beyond Digital Code"))
        self.assertEqual(result.status, "incompatible")
        self.assertIn("digital_physical_mismatch", result.reason_codes)

    def test_code_in_box_is_distinct_from_download_only(self):
        result = evaluate_compatibility(product("Game Code in Box"), catalog("Game Digital Download Code"))
        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.details["supplier_format"], "code_in_box")

    def test_edition_mismatch_is_incompatible(self):
        result = evaluate_compatibility(product("Game Deluxe Edition"), catalog("Game Standard Edition"))
        self.assertEqual(result.status, "incompatible")
        self.assertIn("edition_mismatch", result.reason_codes)

    def test_bundle_mismatch_is_incompatible(self):
        result = evaluate_compatibility(product("Game Bundle"), catalog("Game"))
        self.assertEqual(result.status, "incompatible")
        self.assertIn("bundle_mismatch", result.reason_codes)

    def test_region_without_candidate_evidence_is_uncertain(self):
        result = evaluate_compatibility(product("Metroid Prime 4 Beyond EU Version"), catalog())
        self.assertEqual(result.status, "uncertain")
        self.assertIn("region_evidence_incomplete", result.reason_codes)

    def test_missing_platform_evidence_is_uncertain(self):
        result = evaluate_compatibility(product(), catalog(platform=None))
        self.assertEqual(result.status, "uncertain")
        self.assertIn("candidate_platform_missing", result.reason_codes)

    def test_compatible_exact_identity(self):
        self.assertEqual(evaluate_compatibility(product(), catalog()).status, "compatible")

    def test_prior_sales_win_before_velocity(self):
        result = select_preferred([
            {"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "eligible", "prior_account_sale": False, "keepa_sales_rank_drops90": 500},
            {"asin": "B000000002", "compatibility_status": "compatible", "eligibility_status": "eligible", "prior_account_sale": True, "keepa_sales_rank_drops90": 1},
        ])
        self.assertEqual(result.selected_asin, "B000000002")

    def test_restricted_top_candidate_falls_through(self):
        result = select_preferred([
            {"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "restricted", "prior_account_sale": True, "keepa_sales_rank_drops90": 500},
            {"asin": "B000000002", "compatibility_status": "compatible", "eligibility_status": "eligible", "prior_account_sale": False, "keepa_sales_rank_drops90": 1},
        ])
        self.assertEqual(result.selected_asin, "B000000002")

    def test_known_velocity_ranks_ahead_of_unknown(self):
        result = select_preferred([
            {"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "eligible", "keepa_sales_rank_drops90": None},
            {"asin": "B000000002", "compatibility_status": "compatible", "eligibility_status": "eligible", "keepa_sales_rank_drops90": 0},
        ])
        self.assertEqual(result.selected_asin, "B000000002")

    def test_manual_selection_persists_only_while_valid(self):
        rows = [
            {"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "restricted", "keepa_sales_rank_drops90": 100},
            {"asin": "B000000002", "compatibility_status": "compatible", "eligibility_status": "eligible", "keepa_sales_rank_drops90": 1},
        ]
        result = select_preferred(rows, "B000000001")
        self.assertEqual((result.selection_source, result.selected_asin), ("automatic", "B000000002"))
        self.assertTrue(result.rationale["manual_override_invalidated"])

    def test_unknown_eligibility_blocks_selection(self):
        result = select_preferred([{"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "unknown"}])
        self.assertEqual(result.status, "eligibility_pending")

    def test_all_restricted_has_distinct_state(self):
        result = select_preferred([{"asin": "B000000001", "compatibility_status": "compatible", "eligibility_status": "restricted"}])
        self.assertEqual(result.status, "restricted_no_eligible")

    def test_identity_signature_tracks_material_identity(self):
        baseline = identity_signature(product())
        self.assertNotEqual(baseline, identity_signature(product(system="PS5")))
        self.assertNotEqual(baseline, identity_signature(product("Metroid Prime 4 Beyond Deluxe")))

    def test_supplier_price_does_not_change_identity_or_search_key(self):
        first = {**product(), "supplier_price": "10.00"}
        second = {**product(), "supplier_price": "25.00"}
        self.assertEqual(identity_signature(first), identity_signature(second))
        self.assertEqual(query_fingerprint("title_platform", title_platform_query(first["raw_title"], first["raw_system"]), "US"),
                         query_fingerprint("title_platform", title_platform_query(second["raw_title"], second["raw_system"]), "US"))


if __name__ == "__main__":
    unittest.main()
