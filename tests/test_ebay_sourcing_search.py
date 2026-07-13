from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations"))

from ebay_sourcing_search import (  # noqa: E402
    EBAY_US_VIDEO_GAMES_CATEGORY_ID,
    candidate_decision,
    detail_plan_for_candidate,
    enrich_item_with_detail,
    search_ebay,
    search_queries_for_seed,
    should_reject_summary,
)
from sourcing_match_rules import evaluate_static_match_rules  # noqa: E402


def seed(title: str, system: str | None = None) -> dict:
    raw_context = {"estimated_fee_cost": 5}
    if system:
        raw_context["inferred_system"] = system
    return {
        "sourcing_run_id": "run-1",
        "coverage_cycle_id": "cycle-1",
        "seed_id": "seed-1",
        "asin": "B000TEST",
        "amazon_title": title,
        "target_sale_price": 40,
        "raw_context_json": raw_context,
    }


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        item_location_countries=["US", "CA"],
        delivery_country="US",
        buyer_country="US",
        buyer_zip="93022",
        min_profit_dollars=5,
        min_roi_percent=40,
        best_offer_min_ask_percent=60,
        excluded_keywords=["download", "steam", "disc only"],
    )


def mapped_candidate(
    title: str,
    *,
    price: float = 15,
    shipping_cost: float | None = 5,
    buying_options: list[str] | None = None,
    platform: str | None = "Nintendo Switch",
    category_id: str = EBAY_US_VIDEO_GAMES_CATEGORY_ID,
) -> dict:
    raw = {
        "itemId": "v1|123|0",
        "title": title,
        "localizedAspects": [{"name": "Platform", "value": platform}] if platform else [],
        "categories": [{"categoryId": category_id, "categoryName": "Video Games"}],
    }
    if shipping_cost is not None:
        raw["shippingOptions"] = [{"shippingCost": {"value": str(shipping_cost)}}]
    return {
        "sourcing_run_id": "run-1",
        "seed_id": "seed-1",
        "asin": "B000TEST",
        "ebay_item_id": "v1|123|0",
        "ebay_title": title,
        "item_location_country": "US",
        "condition": "Brand New",
        "price": price,
        "shipping_cost": shipping_cost,
        "landed_cost": None if shipping_cost is None else price + shipping_cost,
        "buying_options": buying_options or ["FIXED_PRICE"],
        "best_offer_enabled": "BEST_OFFER" in (buying_options or []),
        "raw_ebay_json": raw,
    }


class EbaySourcingSearchTests(unittest.TestCase):
    def test_one_combined_platform_search_query_per_asin(self) -> None:
        self.assertEqual(
            search_queries_for_seed(seed("Mario Kart 8 Deluxe - Nintendo Switch [Nintendo Switch]")),
            ["mario kart 8 deluxe Switch"],
        )

    def test_unsourced_platforms_are_not_searched(self) -> None:
        self.assertEqual(search_queries_for_seed(seed("Brain Age [Nintendo DS]", "DS")), [])
        self.assertEqual(search_queries_for_seed(seed("Halo Combat Evolved [Original Xbox]", "Xbox")), [])
        self.assertEqual(search_queries_for_seed(seed("Mario Sunshine [GameCube]", "Gamecube")), [])

    def test_approved_platform_suffixes(self) -> None:
        self.assertEqual(search_queries_for_seed(seed("Nintendo Land [Wii U]", "Wii U")), ["nintendo land (Wii U,wiiu)"])
        self.assertEqual(
            search_queries_for_seed(seed("Forza Motorsport 4 [Xbox 360]", "Xbox 360")),
            ["forza motorsport 4 (Xbox 360,X360,XB360,Xbox360)"],
        )
        self.assertEqual(
            search_queries_for_seed(seed("Persona 4 Golden [PlayStation Vita]", "PS Vita")),
            ["persona 4 golden (PlayStation Vita,PSVita)"],
        )

    def test_search_uses_video_games_category_and_200_result_limit(self) -> None:
        calls = []

        def fake_get(_url, **kwargs):
            calls.append(kwargs)
            return FakeResponse(200, {"itemSummaries": []})

        with patch("ebay_sourcing_search.requests.get", side_effect=fake_get):
            results, metrics = search_ebay("token", "mario kart Switch", settings(), 200)

        self.assertEqual(results, [])
        self.assertEqual(metrics["search_call_count"], 1)
        self.assertEqual(calls[0]["params"]["limit"], 200)
        self.assertEqual(calls[0]["params"]["category_ids"], EBAY_US_VIDEO_GAMES_CATEGORY_ID)
        self.assertNotIn("offset", calls[0]["params"])

    def test_summary_blocks_wrong_platform_digital_accessory_and_incomplete_before_detail(self) -> None:
        for candidate in [
            mapped_candidate("Mario Kart 8 Deluxe PS5", platform="Sony PlayStation 5"),
            mapped_candidate("Mario Kart 8 Deluxe Switch Download Code"),
            mapped_candidate("Mario Kart 8 Deluxe Switch Controller", category_id="171833"),
            mapped_candidate("Mario Kart 8 Deluxe Switch Disc Only"),
        ]:
            decision = candidate_decision(candidate, seed("Mario Kart 8 Deluxe", "Switch"), settings(), {}, {})
            self.assertTrue(should_reject_summary(decision))

    def test_regular_listing_above_landed_cap_rejects_before_detail(self) -> None:
        decision = candidate_decision(
            mapped_candidate("Mario Kart 8 Deluxe Switch", price=30, shipping_cost=None),
            seed("Mario Kart 8 Deluxe", "Switch"),
            settings(),
            {},
            {},
        )
        self.assertTrue(decision["economic_reject"])

    def test_best_offer_above_regular_cap_can_remain_detail_eligible(self) -> None:
        decision = candidate_decision(
            mapped_candidate("Mario Kart 8 Deluxe Switch", price=28, shipping_cost=None, buying_options=["FIXED_PRICE", "BEST_OFFER"]),
            seed("Mario Kart 8 Deluxe", "Switch"),
            settings(),
            {},
            {},
        )
        self.assertFalse(decision["economic_reject"])
        self.assertIn("shipping_missing", detail_plan_for_candidate(mapped_candidate("Mario Kart 8 Deluxe Switch", shipping_cost=None), decision)["reasons"])

    def test_best_offer_requiring_too_low_offer_rejects_before_detail(self) -> None:
        decision = candidate_decision(
            mapped_candidate("Mario Kart 8 Deluxe Switch", price=50, shipping_cost=None, buying_options=["FIXED_PRICE", "BEST_OFFER"]),
            seed("Mario Kart 8 Deluxe", "Switch"),
            settings(),
            {},
            {},
        )
        self.assertTrue(decision["economic_reject"])

    def test_auction_current_price_above_cap_rejects_before_detail(self) -> None:
        candidate = mapped_candidate("Mario Kart 8 Deluxe Switch", price=35, shipping_cost=None, buying_options=["AUCTION"])
        candidate["current_bid"] = 35
        decision = candidate_decision(candidate, seed("Mario Kart 8 Deluxe", "Switch"), settings(), {}, {})
        self.assertTrue(decision["economic_reject"])

    def test_known_shipping_prevents_shipping_detail(self) -> None:
        candidate = mapped_candidate("Mario Kart 8 Deluxe Switch", shipping_cost=5)
        decision = candidate_decision(candidate, seed("Mario Kart 8 Deluxe", "Switch"), settings(), {}, {})
        self.assertNotIn("shipping_missing", detail_plan_for_candidate(candidate, decision)["reasons"])

    def test_missing_shipping_on_plausible_candidate_triggers_reason(self) -> None:
        candidate = mapped_candidate("Mario Kart 8 Deluxe Switch", shipping_cost=None)
        decision = candidate_decision(candidate, seed("Mario Kart 8 Deluxe", "Switch"), settings(), {}, {})
        plan = detail_plan_for_candidate(candidate, decision)
        self.assertTrue(plan["required"])
        self.assertIn("shipping_missing", plan["reasons"])

    def test_multiple_detail_reasons_can_be_stored(self) -> None:
        candidate = mapped_candidate("Mario Kart 8 Deluxe", shipping_cost=None, platform=None)
        decision = candidate_decision(candidate, seed("Mario Kart 8 Deluxe", "Switch"), settings(), {}, {})
        plan = detail_plan_for_candidate(candidate, decision)
        self.assertIn("shipping_missing", plan["reasons"])
        self.assertIn("platform_confirmation_needed", plan["reasons"])

    def test_successful_detail_records_populated_fields_and_cache_prevents_duplicate_call(self) -> None:
        item = {"itemId": "v1|123|0", "title": "Mario Kart 8 Deluxe Switch"}
        plan = {"required": True, "reasons": ["shipping_missing"], "fields_missing_before": ["shipping_cost"]}
        calls = []

        def fake_get(_url, **kwargs):
            calls.append(kwargs)
            return FakeResponse(200, {"itemId": "v1|123|0", "shippingOptions": [{"shippingCost": {"value": "4.99"}}]})

        cache = {}
        with patch("ebay_sourcing_search.requests.get", side_effect=fake_get):
            _merged, record, metrics = enrich_item_with_detail("token", item, seed("Mario Kart 8 Deluxe", "Switch"), "query", settings(), plan, cache)
            _merged2, record2, metrics2 = enrich_item_with_detail("token", item, seed("Mario Kart 8 Deluxe", "Switch"), "query", settings(), plan, cache)

        self.assertEqual(len(calls), 1)
        self.assertEqual(metrics["detail_call_count"], 1)
        self.assertEqual(metrics2["duplicate_detail_calls_prevented_count"], 1)
        self.assertTrue(record["success"])
        self.assertIn("shipping_cost", record["fields_populated"])
        self.assertEqual(record2["outcome"], "cache_hit")

    def test_xbox_one_and_series_cross_generation_is_not_blocked(self) -> None:
        diagnostics = evaluate_static_match_rules(
            mapped_candidate("Halo Infinite Xbox One", platform="Microsoft Xbox One"),
            seed("Halo Infinite", "Xbox Series X"),
        )
        self.assertNotEqual("Blocked", diagnostics["recommendation"])


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


if __name__ == "__main__":
    unittest.main()
