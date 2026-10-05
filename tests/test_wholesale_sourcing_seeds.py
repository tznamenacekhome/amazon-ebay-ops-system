import datetime as dt
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from build_sourcing_seed_asins import (  # noqa: E402
    fetch_fresh_new_eligibility_by_asin,
    wholesale_selection_is_seed_eligible,
)
from sourcing_coverage_cycle import dismiss_open_opportunities_for_restricted_asins  # noqa: E402


ASIN = "B000TEST01"
PRODUCT = "product-1"


def state(**changes):
    return {
        "match_status": "matched",
        "selected_candidate_id": "candidate-1",
        "selection_source": "automatic",
        **changes,
    }


def candidate(**changes):
    return {"asin": ASIN, "compatibility_status": "compatible", **changes}


def eligible_evidence():
    return {ASIN: {"asin": ASIN, "eligibility_status": "eligible"}}


class WholesaleSourcingSeedTests(unittest.TestCase):
    def qualifies(self, state_row=None, candidate_row=None, *, non_na=None, evidence=None, blocked=None):
        return wholesale_selection_is_seed_eligible(
            state_row if state_row is not None else state(),
            candidate_row if candidate_row is not None else candidate(),
            PRODUCT,
            non_na or set(),
            eligible_evidence() if evidence is None else evidence,
            blocked or set(),
        )

    def test_selected_compatible_fresh_eligible_asin_becomes_seed(self):
        self.assertTrue(self.qualifies())

    def test_restricted_selected_asin_does_not_become_seed(self):
        self.assertFalse(self.qualifies(evidence={ASIN: {"eligibility_status": "restricted"}}))

    def test_pending_or_unknown_eligibility_does_not_become_seed(self):
        self.assertFalse(self.qualifies(evidence={ASIN: {"eligibility_status": "unknown"}}))

    def test_stale_eligibility_does_not_become_seed(self):
        self.assertFalse(self.qualifies(evidence={}))

    def test_incompatible_candidate_is_excluded(self):
        self.assertFalse(self.qualifies(candidate_row=candidate(compatibility_status="incompatible")))

    def test_no_selected_candidate_is_excluded(self):
        self.assertFalse(wholesale_selection_is_seed_eligible(state(), None, PRODUCT, set(), eligible_evidence(), set()))

    def test_identity_review_is_excluded(self):
        self.assertFalse(self.qualifies(state_row=state(match_status="identity_review")))

    def test_non_na_classification_is_excluded(self):
        self.assertFalse(self.qualifies(non_na={PRODUCT}))

    def test_manual_selected_eligible_asin_is_included(self):
        self.assertTrue(self.qualifies(state_row=state(selection_source="manual")))

    def test_existing_blocked_asin_is_excluded(self):
        self.assertFalse(self.qualifies(blocked={ASIN}))

    def test_later_restriction_then_restored_eligibility_controls_future_seed(self):
        self.assertFalse(self.qualifies(evidence={ASIN: {"eligibility_status": "restricted"}}))
        self.assertTrue(self.qualifies(evidence=eligible_evidence()))

    def test_fresh_cache_reader_drops_expired_evidence(self):
        client = MagicMock()
        query = client.table.return_value
        query.select.return_value = query
        query.eq.return_value = query
        query.in_.return_value = query
        query.execute.return_value = SimpleNamespace(data=[
            {"asin": ASIN, "eligibility_status": "eligible", "checked_at": "2026-10-01T00:00:00Z", "expires_at": "2026-10-06T00:00:00Z"},
            {"asin": "B000TEST02", "eligibility_status": "eligible", "checked_at": "2026-09-01T00:00:00Z", "expires_at": "2026-09-02T00:00:00Z"},
        ])
        rows = fetch_fresh_new_eligibility_by_asin(
            client,
            [ASIN, "B000TEST02"],
            now=dt.datetime(2026, 10, 4, tzinfo=dt.UTC),
            seller_id="seller",
            marketplace_id="market",
        )
        self.assertEqual(set(rows), {ASIN})

    def test_restriction_dismissal_preserves_opportunity_and_records_history(self):
        client = MagicMock()
        opportunities = MagicMock()
        actions = MagicMock()
        client.table.side_effect = lambda name: opportunities if name == "sourcing_opportunities" else actions
        opportunities.select.return_value = opportunities
        opportunities.in_.return_value = opportunities
        opportunities.update.return_value = opportunities
        opportunities.execute.side_effect = [
            SimpleNamespace(data=[{
                "opportunity_id": "11111111-1111-1111-1111-111111111111",
                "candidate_id": "22222222-2222-2222-2222-222222222222",
                "asin": ASIN,
                "ebay_item_id": "item-1",
                "status": "open",
            }]),
            SimpleNamespace(data=[]),
        ]
        actions.upsert.return_value = actions
        actions.execute.return_value = SimpleNamespace(data=[])

        self.assertEqual(dismiss_open_opportunities_for_restricted_asins(client, {ASIN}), 1)
        opportunities.update.assert_called_once()
        self.assertEqual(opportunities.update.call_args.args[0]["status"], "dismissed")
        actions.upsert.assert_called_once()
        payload = actions.upsert.call_args.args[0][0]
        self.assertEqual(payload["dismiss_reason"], "amazon_new_condition_restricted")
        self.assertFalse(any(call.args and call.args[0] == "delete" for call in opportunities.method_calls))


if __name__ == "__main__":
    unittest.main()
