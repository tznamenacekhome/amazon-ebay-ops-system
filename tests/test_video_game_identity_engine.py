from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations"))

from sourcing_decision_trace import enrich_sourcing_diagnostics  # noqa: E402
from sourcing_match_rules import evaluate_static_match_rules  # noqa: E402


def seed(title: str, system: str | None = None) -> dict:
    return {
        "asin": "B000TEST",
        "amazon_title": title,
        "system": system,
        "raw_context_json": {"inferred_system": system} if system else {},
    }


def candidate(title: str, *, platform: str | None = None, game_name: str | None = None, description: str | None = None) -> dict:
    aspects = []
    if platform:
        aspects.append({"name": "Platform", "value": platform})
    if game_name:
        aspects.append({"name": "Game Name", "value": game_name})
    return {
        "ebay_title": title,
        "condition": "Brand New",
        "item_location_country": "US",
        "raw_ebay_json": {
            "localizedAspects": aspects,
            "categories": [{"categoryId": "139973", "categoryName": "Video Games"}],
            "description": description,
        },
    }


class VideoGameIdentityEngineTests(unittest.TestCase):
    def assert_identity_blocked(self, amazon: str, ebay: str, *, system: str | None = None, platform: str | None = None, game_name: str | None = None) -> dict:
        diagnostics = evaluate_static_match_rules(candidate(ebay, platform=platform, game_name=game_name), seed(amazon, system))
        self.assertEqual("Blocked", diagnostics["recommendation"])
        self.assertTrue(any("video game identity conflict" in reason for reason in diagnostics["hard_blocks"]), diagnostics["hard_blocks"])
        self.assertEqual("conflict", diagnostics["identity_comparison"]["result"])
        return diagnostics

    def assert_identity_valid(self, amazon: str, ebay: str, *, system: str | None = None, platform: str | None = None, game_name: str | None = None) -> dict:
        diagnostics = evaluate_static_match_rules(candidate(ebay, platform=platform, game_name=game_name), seed(amazon, system))
        self.assertFalse(any("video game identity conflict" in reason for reason in diagnostics["hard_blocks"]), diagnostics["hard_blocks"])
        self.assertNotEqual("conflict", diagnostics["identity_comparison"]["result"])
        return diagnostics

    def test_rock_band_3_vs_the_beatles_blocks(self) -> None:
        self.assert_identity_blocked("Rock Band 3 - PlayStation 3", "The Beatles: Rock Band PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_rock_band_3_vs_metal_track_pack_blocks(self) -> None:
        self.assert_identity_blocked("Rock Band 3 - PlayStation 3", "Rock Band Metal Track Pack PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_rock_band_3_vs_country_track_pack_blocks(self) -> None:
        self.assert_identity_blocked("Rock Band 3 - PlayStation 3", "Rock Band Country Track Pack PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_rock_band_3_vs_classic_rock_track_pack_blocks(self) -> None:
        self.assert_identity_blocked("Rock Band 3 - PlayStation 3", "Rock Band Track Pack Classic Rock PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_shrek_2_vs_shrek_the_third_blocks(self) -> None:
        diagnostics = self.assert_identity_blocked("Shrek 2 - Nintendo Wii", "Shrek the Third Nintendo Wii", system="Wii", platform="Nintendo Wii")
        self.assertEqual("2", diagnostics["identity_comparison"]["amazon"]["installmentNormalized"])
        self.assertEqual("3", diagnostics["identity_comparison"]["ebay"]["installmentNormalized"])

    def test_shrek_2_vs_smash_n_crash_blocks(self) -> None:
        self.assert_identity_blocked("Shrek 2 - Nintendo Wii", "Shrek Smash N' Crash Racing Nintendo Wii", system="Wii", platform="Nintendo Wii")

    def test_disney_infinity_base_vs_2_marvel_blocks(self) -> None:
        self.assert_identity_blocked("Disney Infinity Starter Pack PS3", "Disney Infinity 2.0 Marvel Super Heroes Starter Pack PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_disney_infinity_base_vs_3_star_wars_blocks(self) -> None:
        self.assert_identity_blocked("Disney Infinity Starter Pack PS3", "Disney Infinity 3.0 Star Wars Starter Pack PS3", system="PS 3", platform="Sony PlayStation 3")

    def test_disney_infinity_2_marvel_vs_3_star_wars_blocks(self) -> None:
        self.assert_identity_blocked("Disney Infinity 2.0 Marvel Super Heroes Starter Pack", "Disney Infinity 3.0 Star Wars Starter Pack")

    def test_dead_rising_4_vs_3_blocks(self) -> None:
        diagnostics = self.assert_identity_blocked("Dead Rising 4 - Xbox One", "Dead Rising 3 Xbox One", system="Xbox One", platform="Microsoft Xbox One")
        comparison = diagnostics["identity_comparison"]["comparisons"]
        self.assertEqual("match", comparison["franchise"]["result"])
        self.assertEqual("match", comparison["coreProduct"]["result"])
        self.assertEqual("conflict", comparison["installment"]["result"])

    def test_wipeout_3_vs_2_blocks(self) -> None:
        self.assert_identity_blocked("Wipeout 3 - Nintendo 3DS", "ABC's Wipeout 2 Nintendo 3DS", system="3DS", platform="Nintendo 3DS")

    def test_wii_play_motion_vs_tiger_woods_blocks(self) -> None:
        diagnostics = self.assert_identity_blocked("Wii Play Motion - Nintendo Wii", "Tiger Woods PGA Tour 2009 Nintendo Wii", system="Wii", platform="Nintendo Wii")
        self.assertEqual("conflict", diagnostics["identity_comparison"]["comparisons"]["franchise"]["result"])

    def test_new_carnival_games_vs_cookies_counting_carnival_blocks(self) -> None:
        self.assert_identity_blocked("New Carnival Games - Nintendo Wii", "Cookie's Counting Carnival Wii", system="Wii", platform="Nintendo Wii")

    def test_new_carnival_games_vs_shrek_carnival_craze_blocks(self) -> None:
        self.assert_identity_blocked("New Carnival Games - Nintendo Wii", "Shrek's Carnival Craze Nintendo Wii", system="Wii", platform="Nintendo Wii")

    def test_final_fantasy_xiv_complete_valid(self) -> None:
        diagnostics = self.assert_identity_valid(
            "Final Fantasy XIV Online Complete Edition - PlayStation 4",
            "Final Fantasy 14 Online Complete Edition PS4",
            system="PS 4",
            platform="Sony PlayStation 4",
        )
        comparison = diagnostics["identity_comparison"]
        self.assertEqual("match", comparison["comparisons"]["installment"]["result"])
        self.assertEqual("14", comparison["amazon"]["installmentNormalized"])
        self.assertEqual("14", comparison["ebay"]["installmentNormalized"])

    def test_rock_band_playstation_3_vs_ps3_valid(self) -> None:
        diagnostics = self.assert_identity_valid("Rock Band PlayStation 3", "Rock Band PS3", system="PS 3", platform="Sony PlayStation 3")
        self.assertEqual("match", diagnostics["identity_comparison"]["comparisons"]["coreProduct"]["result"])

    def test_ps3_is_not_installment_3(self) -> None:
        diagnostics = self.assert_identity_valid("Rock Band PlayStation 3", "Rock Band PS3", system="PS 3", platform="Sony PlayStation 3")
        self.assertIsNone(diagnostics["identity_comparison"]["amazon"]["installmentNormalized"])
        self.assertIsNone(diagnostics["identity_comparison"]["ebay"]["installmentNormalized"])

    def test_xbox_360_is_not_installment_360(self) -> None:
        diagnostics = self.assert_identity_valid("Rock Band Xbox 360", "Rock Band Xbox 360", system="Xbox 360", platform="Microsoft Xbox 360")
        self.assertIsNone(diagnostics["identity_comparison"]["amazon"]["installmentNormalized"])
        self.assertIsNone(diagnostics["identity_comparison"]["ebay"]["installmentNormalized"])

    def test_generic_game_name_does_not_override_title(self) -> None:
        diagnostics = self.assert_identity_valid("Rock Band PS3", "Rock Band PlayStation 3", system="PS 3", platform="Sony PlayStation 3", game_name="Game")
        self.assertEqual("match", diagnostics["identity_comparison"]["comparisons"]["coreProduct"]["result"])

    def test_unknown_core_identity_does_not_create_positive_identity(self) -> None:
        diagnostics = self.assert_identity_valid("Mystery Product PS3", "Mystery Product PS3", system="PS 3", platform="Sony PlayStation 3")
        self.assertEqual("unknown", diagnostics["identity_comparison"]["result"])
        self.assertEqual("unknown", diagnostics["identity_comparison"]["comparisons"]["coreProduct"]["result"])

    def test_decision_trace_uses_identity_hard_block(self) -> None:
        diagnostics = self.assert_identity_blocked("Dead Rising 4 - Xbox One", "Dead Rising 3 Xbox One", system="Xbox One", platform="Microsoft Xbox One")
        enriched = enrich_sourcing_diagnostics(
            diagnostics,
            status="rejected",
            opportunity_type="best_offer",
            profit=10,
            roi_percent=40,
        )
        self.assertFalse(enriched["presentationDecision"]["eligible"])
        reason_codes = {row.get("reasonCode") for row in enriched["decisionTrace"]}
        self.assertIn("numeric_installment_mismatch", reason_codes)


if __name__ == "__main__":
    unittest.main()
