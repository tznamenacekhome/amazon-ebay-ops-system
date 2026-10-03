import unittest

from integrations.wholesale_repository import opportunity_status, resolve_opportunity_state


class WholesaleOpportunityStateTests(unittest.TestCase):
    def test_hard_pass_suppresses_changed_evaluation(self):
        status, scope, resurfaced = resolve_opportunity_state(
            {"evaluation_status": "complete", "is_financially_qualified": True},
            "hard", "old", "new", 0,
        )
        self.assertEqual((status, scope, resurfaced), ("hard_passed", "hard", False))

    def test_unchanged_temporary_pass_stays_passed(self):
        result = resolve_opportunity_state(
            {"evaluation_status": "complete", "is_financially_qualified": True},
            "temporary", "same", "same", 0,
        )
        self.assertEqual(result, ("temporarily_passed", "temporary", False))

    def test_changed_temporary_pass_resurfaces_same_opportunity(self):
        result = resolve_opportunity_state(
            {"evaluation_status": "complete", "is_financially_qualified": True},
            "temporary", "old", "new", 0,
        )
        self.assertEqual(result, ("ready_for_review", None, True))

    def test_unqualified_can_become_ready_after_new_evaluation(self):
        self.assertEqual(opportunity_status({"evaluation_status": "complete", "is_financially_qualified": False}), "not_financially_qualified")
        self.assertEqual(opportunity_status({"evaluation_status": "complete", "is_financially_qualified": True}), "ready_for_review")

    def test_pending_eligibility_never_routes_ready(self):
        self.assertEqual(opportunity_status({"evaluation_status": "pending_eligibility", "is_financially_qualified": True}), "pending_eligibility")

    def test_active_draft_has_added_state(self):
        result = resolve_opportunity_state(
            {"evaluation_status": "complete", "is_financially_qualified": True}, None, "same", "same", 4,
        )
        self.assertEqual(result[0], "added_to_order")


if __name__ == "__main__":
    unittest.main()
