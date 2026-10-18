import unittest
from decimal import Decimal
from unittest.mock import Mock, patch
from integrations import sync_revseller_sheet as matching


def candidate():
    return {"score": .9, "row": {"asin": "TESTASIN", "raw_title": "Minecraft - PS4", "normalized_title": "minecraft", "system": "PS 4"}}


class MatchingModelMigrationTests(unittest.TestCase):
    def test_candidate_ranking_cannot_cross_platforms(self):
        self.assertEqual(matching.rank_ai_candidates({"title":"Minecraft PS4","system":"PS 4"}, {"Switch":[candidate()["row"]]}), [])

    def test_luna_keeps_json_contract_and_override_compatibility(self):
        item = {"title": "Minecraft PS4", "system": "PS 4"}
        old = matching.AiMatchClient(api_key="offline",model="gpt-4.1-mini",confidence_threshold=Decimal(".86")).build_payload(item,[candidate()])
        new = matching.AiMatchClient(api_key="offline",model=matching.DEFAULT_AI_MODEL,confidence_threshold=Decimal(".86")).build_payload(item,[candidate()])
        self.assertEqual(matching.DEFAULT_AI_MODEL, "gpt-6-luna")
        self.assertEqual(new.pop("reasoning"), {"effort": "none"})
        old.pop("model"); new.pop("model")
        self.assertEqual(new, old)

    def test_no_match_low_confidence_errors_and_success_keep_existing_behavior(self):
        for decision,status in [({"decision":"no_match"},"skipped_ai_no_match"),({"decision":"match","candidate_index":0,"confidence":.4},"skipped_ai_low_confidence"),({"decision":"match","candidate_index":0,"confidence":.95},"matched_ai_with_system")]:
            client = Mock(confidence_threshold=Decimal(".86")); client.choose_match.return_value=decision
            with patch.object(matching,"rank_ai_candidates",return_value=[candidate()]):
                row,actual,_=matching.ai_match_purchase_item({"title":"Minecraft PS4"},{},client)
            self.assertEqual(actual,status)
            self.assertEqual(row is not None,status=="matched_ai_with_system")
        client.choose_match.side_effect=RuntimeError("offline provider error")
        with patch.object(matching,"rank_ai_candidates",return_value=[candidate()]):
            self.assertEqual(matching.ai_match_purchase_item({}, {}, client)[1], "skipped_ai_error")


if __name__ == "__main__": unittest.main()
