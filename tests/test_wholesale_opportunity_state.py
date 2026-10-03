import unittest

from integrations.wholesale_repository import opportunity_status, resolve_opportunity_state

READY = {"evaluation_status": "complete", "is_financially_qualified": True}


class WholesaleOpportunityStateTests(unittest.TestCase):
    def resolve(self, evaluation, scope="temporary", reason="other", snapshot=None, draft=0):
        return resolve_opportunity_state(
            evaluation, scope, "old", "new", draft,
            active_reason=reason, decision_context={"condition_snapshot": snapshot or {}},
        )

    def test_hard_pass_persists_across_daily_evaluation(self):
        self.assertEqual(self.resolve(READY, "hard", "listing_asin_issue"), ("hard_passed", "hard", False))

    def test_new_list_alone_does_not_resurface_other(self):
        self.assertEqual(self.resolve(READY, reason="other"), ("temporarily_passed", "temporary", False))

    def test_unchanged_inventory_does_not_resurface(self):
        current = {**READY, "purchase_capacity": 0}
        self.assertEqual(self.resolve(current, reason="too_much_inventory", snapshot={"purchase_capacity": 0}),
                         ("temporarily_passed", "temporary", False))

    def test_inventory_reduction_with_positive_capacity_can_resurface(self):
        current = {**READY, "purchase_capacity": 3}
        self.assertEqual(self.resolve(current, reason="too_much_inventory", snapshot={"purchase_capacity": 0}),
                         ("ready_for_review", None, True))

    def test_capacity_change_still_obeys_normal_qualification(self):
        current = {"evaluation_status": "complete", "is_financially_qualified": False, "purchase_capacity": 3}
        self.assertEqual(self.resolve(current, reason="too_much_inventory", snapshot={"purchase_capacity": 0}),
                         ("temporarily_passed", "temporary", False))

    def test_price_risk_requires_material_five_percent_change(self):
        unchanged = {**READY, "current_buy_box_price": 100}
        self.assertEqual(self.resolve(unchanged, reason="price_risk", snapshot={"current_buy_box": 98}),
                         ("temporarily_passed", "temporary", False))
        changed = {**READY, "current_buy_box_price": 105}
        self.assertEqual(self.resolve(changed, reason="price_risk", snapshot={"current_buy_box": 98}),
                         ("ready_for_review", None, True))

    def test_competition_requires_observed_count_change(self):
        unchanged = {**READY, "offer_count_current": 4, "fba_seller_count": None}
        self.assertEqual(self.resolve(unchanged, reason="competition", snapshot={"offer_count": 4}),
                         ("temporarily_passed", "temporary", False))
        changed = {**READY, "offer_count_current": 3, "fba_seller_count": None}
        self.assertEqual(self.resolve(changed, reason="competition", snapshot={"offer_count": 4}),
                         ("ready_for_review", None, True))

    def test_pending_eligibility_never_routes_ready(self):
        self.assertEqual(opportunity_status({"evaluation_status": "pending_eligibility", "is_financially_qualified": True}), "pending_eligibility")

    def test_roi_improvement_moves_system_exclusion_to_ready(self):
        self.assertEqual(opportunity_status({"evaluation_status": "complete", "is_financially_qualified": False}), "not_financially_qualified")
        self.assertEqual(opportunity_status(READY), "ready_for_review")

    def test_active_draft_has_order_list_state(self):
        self.assertEqual(self.resolve(READY, scope=None, draft=4)[0], "added_to_order")


if __name__ == "__main__":
    unittest.main()
