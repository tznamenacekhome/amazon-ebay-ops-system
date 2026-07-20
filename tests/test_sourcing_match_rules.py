from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations"))

from sourcing_match_rules import evaluate_static_match_rules  # noqa: E402


def seed(title: str, system: str | None = None) -> dict:
    raw_context = {}
    if system:
        raw_context = {
            "inferred_system": system,
            "inferred_system_source": "test_fixture",
        }
    return {
        "asin": "B000TEST",
        "amazon_title": title,
        "raw_context_json": raw_context,
    }


def candidate(
    title: str,
    *,
    platform: str | list[str] | None = None,
    game_name: str | None = None,
    category_id: str = "139973",
    category_name: str = "Video Games",
    description: str | None = None,
    item_type: str | None = None,
    region_code: str | None = None,
) -> dict:
    aspects = []
    for name, value in (
        ("Platform", platform),
        ("Game Name", game_name),
        ("Type", item_type),
        ("Region Code", region_code),
    ):
        if value:
            aspects.append({"name": name, "value": value})
    return {
        "ebay_title": title,
        "condition": "Brand New",
        "item_location_country": "US",
        "raw_ebay_json": {
            "localizedAspects": aspects,
            "categories": [{"categoryId": category_id, "categoryName": category_name}],
            "description": description,
        },
    }


class SourcingMatchRuleTests(unittest.TestCase):
    def assert_blocked(self, diagnostics: dict, contains: str) -> None:
        self.assertEqual("Blocked", diagnostics["recommendation"])
        self.assertTrue(
            any(contains.casefold() in reason.casefold() for reason in diagnostics["hard_blocks"]),
            diagnostics["hard_blocks"],
        )

    def test_seed_inferred_platform_blocks_wrong_item_specific_platform(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Need for Speed Rivals Xbox One", platform="Microsoft Xbox One"),
            seed("Need for Speed Rivals", "PS 4"),
        )
        self.assert_blocked(diagnostics, "platform mismatch")
        self.assertEqual("test_fixture", diagnostics["platform_rule"]["seed_system_source"])
        self.assertEqual("item_specifics_platform", diagnostics["platform_rule"]["candidate_system_source"])

    def test_ps4_seed_blocks_ps3_listing(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Minecraft PlayStation 3 Edition", platform="Sony PlayStation 3"),
            seed("Minecraft", "PS 4"),
        )
        self.assert_blocked(diagnostics, "platform mismatch")

    def test_wii_seed_blocks_wii_u_listing(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Wii Party U Nintendo Wii U", platform="Nintendo Wii U"),
            seed("Wii Party", "Wii"),
        )
        self.assert_blocked(diagnostics, "platform mismatch")

    def test_3ds_seed_blocks_ds_listing(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Mario Kart DS Nintendo DS Brand New", platform="Nintendo DS"),
            seed("Mario Kart 7", "3DS"),
        )
        self.assert_blocked(diagnostics, "unsupported sourcing platform")

    def test_3ds_seed_blocks_mixed_3ds_ds_listing(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Professor Layton 3DS DS Compatible Bundle", platform=["Nintendo 3DS", "Nintendo DS"]),
            seed("Professor Layton and the Miracle Mask", "3DS"),
        )
        self.assert_blocked(diagnostics, "unsupported sourcing platform")

    def test_3ds_listing_still_passes(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Super Mario 3D Land Nintendo 3DS Brand New", platform="Nintendo 3DS"),
            seed("Super Mario 3D Land", "3DS"),
        )
        self.assertNotEqual("Blocked", diagnostics["recommendation"])

    def test_game_vs_controller_accessory_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Halo Infinite Xbox Wireless Controller",
                platform="Microsoft Xbox Series X",
                category_id="171833",
                category_name="Video Game Controllers",
                item_type="Controller",
            ),
            seed("Halo Infinite", "Xbox Series X"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_game_vs_cake_topper_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Rock Band Cake Topper And Rings Music Celebration Wii Xbox PS4",
                category_id="102430",
                category_name="Cake Toppers",
            ),
            seed("Wii Music", "Wii"),
        )
        self.assert_blocked(diagnostics, "category")

    def test_game_vs_puzzle_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Transformers Revenge of the Fallen Puzzle",
                category_id="19183",
                category_name="Puzzles",
            ),
            seed("Transformers: Revenge of the Fallen", "PC"),
        )
        self.assert_blocked(diagnostics, "category")

    def test_game_vs_plush_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Minecraft Creeper Plush Toy", category_name="Plush Toys"),
            seed("Minecraft", "Switch"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_game_vs_power_disc_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Disney Infinity Wreck-It Ralph Power Disc", category_name="Toys to Life"),
            seed("Wreck-It Ralph", "Wii"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_strategy_guide_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("The Legend of Zelda Breath of the Wild Strategy Guide"),
            seed("The Legend of Zelda Breath of the Wild", "Switch"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_digital_service_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Call of Duty Black Ops Cold War Operator Skin Message Delivery"),
            seed("Call of Duty Black Ops Cold War", "PS 5"),
        )
        self.assert_blocked(diagnostics, "digital")

    def test_numeric_year_mismatch_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Just Dance 2025 Limited Edition Nintendo Switch Ariana Grande Song Pack", platform="Nintendo Switch"),
            seed("Just Dance 2018", "Switch"),
        )
        self.assert_blocked(diagnostics, "numeric")

    def test_premium_seed_vs_base_listing_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Mortal Kombat 11 Nintendo Switch", platform="Nintendo Switch"),
            seed("Mortal Kombat 11 Premium Edition", "Switch"),
        )
        self.assert_blocked(diagnostics, "edition")

    def test_microfiber_cleaner_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Yo-Kai Watch Microfiber Cleaner Yokai Cloth", category_name="Animation Merchandise"),
            seed("YO-KAI WATCH", "3DS"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_kids_meal_backpack_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("LOT OF 2 Subway Kids Meal PINK BAG 2018 JUST DANCE Drawstring Backpack NEW"),
            seed("Just Dance 2018", "Switch"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_hot_wheels_diecast_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Hot Wheels White Ford Shelby GT 350 HW Forza Motorsport 4/5 2021",
                item_type="Diecast Vehicle",
            ),
            seed("Forza Motorsport 5", "Xbox One"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_game_protector_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Protector 0.50mm PET Acid-Free for Nintendo Switch Metroid Dread Special Edition",
                platform="Nintendo Switch",
                game_name="Metroid",
            ),
            seed("Metroid Dread: Special Edition", "Switch"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_scrapbook_punch_out_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "SUZY'S ZOO FLOWERS FRAMES & CORNERS SCRAPBOOKING PUNCH OUTS #83015",
                item_type="Laser Cut Punch Out",
            ),
            seed("Punch-Out!!", "Wii"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_annual_game_year_mismatch_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Tiger Woods PGA Tour 09: All-Play Nintendo Wii New Sealed", platform="Nintendo Wii"),
            seed("Tiger Woods PGA TOUR 12: The Masters", "Wii"),
        )
        self.assert_blocked(diagnostics, "numeric")

    def test_matching_annual_game_number_is_not_blocked_by_release_year(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Tiger Woods PGA Tour 10 (Microsoft Xbox 360, 2009) Brand New Factory Sealed", platform="Microsoft Xbox 360"),
            seed("Tiger Woods PGA Tour 10 - Xbox 360", "Xbox 360"),
        )
        self.assertNotEqual("Blocked", diagnostics["recommendation"])
        self.assertFalse(any("numeric" in reason.casefold() for reason in diagnostics["hard_blocks"]))

    def test_cable_pedal_drum_sticks_block(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Rock Band Drum Sticks Pedal Cable Set", category_name="Video Game Accessories"),
            seed("Rock Band", "Wii"),
        )
        self.assert_blocked(diagnostics, "accessory")

    def test_disc_only_listing_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Elden Ring PS5 Disc Only", platform="Sony PlayStation 5"),
            seed("Elden Ring", "PS 5"),
        )
        self.assert_blocked(diagnostics, "incomplete")

    def test_explicit_foreign_region_blocks(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Mario Kart 8 Deluxe PEGI PAL", platform="Nintendo Switch", region_code="PAL"),
            seed("Mario Kart 8 Deluxe", "Switch"),
        )
        self.assert_blocked(diagnostics, "non-North-American")

    def test_valid_same_platform_physical_game_passes(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate("Mario Kart 8 Deluxe Nintendo Switch Brand New", platform="Nintendo Switch"),
            seed("Mario Kart 8 Deluxe", "Switch"),
        )
        self.assertIn(diagnostics["recommendation"], {"Probable Match", "Strong Match"})
        self.assertFalse(diagnostics["hard_blocks"])

    def test_loose_disc_inside_complete_case_is_not_disc_only_blocked(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Super Smash Bros Ultimate Nintendo Switch Brand New",
                platform="Nintendo Switch",
                description="Loose disc in case from shipping, complete with disc and case.",
            ),
            seed("Super Smash Bros Ultimate", "Switch"),
        )
        self.assertFalse(any("disc only" in reason.casefold() for reason in diagnostics["hard_blocks"]))

    def test_game_accessory_bundle_routes_to_review(self) -> None:
        diagnostics = evaluate_static_match_rules(
            candidate(
                "Mario Kart 8 Deluxe Game Bundle with Steering Wheel Accessory",
                platform="Nintendo Switch",
                category_name="Video Game Accessories",
            ),
            seed("Mario Kart 8 Deluxe", "Switch"),
        )
        self.assertNotEqual("Blocked", diagnostics["recommendation"])
        self.assertTrue(any("bundle review" in warning.casefold() for warning in diagnostics["warnings"]))


if __name__ == "__main__":
    unittest.main()
