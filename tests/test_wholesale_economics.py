from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))

from wholesale_evaluate_opportunities import keepa_current_price_context  # noqa: E402
from integrations.wholesale_economics import (
    EconomicsInput, FeeEvidence, evaluate_economics, informational_risk_signals,
    supplier_price_history,
)

D = Decimal


def fees(total="8.00", referral="4.00", fba="4.00"):
    return FeeEvidence(D(total), D(referral), D(fba))


def values(**overrides):
    base = dict(supplier_cost=D("15"), current_buy_box=D("31.99"), keepa_avg90=D("34.25"),
                current_fees=fees(), avg90_fees=fees("8.30", "4.30", "4.00"),
                is_accessory=False, sales_rank_drops90=36,
                fba_fulfillable_units=3, inbound_units=2, draft_commitment_units=0)
    base.update(overrides)
    return EconomicsInput(**base)


class WholesaleEconomicsTests(unittest.TestCase):
    def test_keepa_now_falls_back_from_used_buy_box_to_low_fba_new(self):
        context = keepa_current_price_context({
            "buy_box_price_current_cents": 3187,
            "new_fba_price_current_cents": 3187,
            "new_price_current_cents": 3019,
            "raw_keepa_json": {"stats": {"buyBoxIsUsed": True, "buyBoxIsFBA": True}},
        })
        self.assertEqual(context, {
            "price": D("31.87"), "source": "fba", "label": "Low FBA New",
            "fulfillment": "fba", "is_buy_box": False,
        })

    def test_keepa_now_uses_low_mf_new_before_generic_new(self):
        current = [-1] * 19
        current[1] = 4200
        current[2] = 3500
        current[7] = 4100
        context = keepa_current_price_context({
            "new_price_current_cents": 4200,
            "raw_keepa_json": {"stats": {"buyBoxIsUsed": True, "current": current}},
        })
        self.assertEqual((context["price"], context["source"], context["label"]),
                         (D("41"), "mf", "Low MF New"))

    def test_keepa_now_reports_used_only_when_no_new_offer_exists(self):
        current = [-1] * 19
        current[2] = 2500
        context = keepa_current_price_context({
            "raw_keepa_json": {"stats": {"buyBoxIsUsed": True, "current": current}},
        })
        self.assertEqual(context["source"], "used_only")
        self.assertIsNone(context["price"])

    def test_true_roi_uses_supplier_cost_denominator_and_allowances(self):
        result = evaluate_economics(values())
        expected_profit = D("31.99") - D("15") - D("8") - D("0.3839") - D("0.21") - D("0.0153")
        self.assertEqual(result["current"]["profit"], expected_profit)
        self.assertEqual(result["current"]["roi"], (expected_profit / D("15")).quantize(D("0.00000001")))
        self.assertEqual(result["inbound_allowance"], D("0.3839"))
        self.assertEqual(result["return_allowance"], D("0.21"))
        self.assertEqual(result["storage_allowance"], D("0.0153"))

    def test_current_only_qualifies(self):
        result = evaluate_economics(values(current_buy_box=D("40"), keepa_avg90=D("25")))
        self.assertEqual(result["qualification_basis"], "current_only")
        self.assertTrue(result["is_financially_qualified"])

    def test_avg90_only_qualifies(self):
        result = evaluate_economics(values(current_buy_box=D("25"), keepa_avg90=D("40")))
        self.assertEqual(result["qualification_basis"], "avg90_only")

    def test_both_qualify(self):
        self.assertEqual(evaluate_economics(values(current_buy_box=D("40"), keepa_avg90=D("40")))["qualification_basis"], "both")

    def test_neither_qualifies(self):
        result = evaluate_economics(values(current_buy_box=D("25"), keepa_avg90=D("25")))
        self.assertEqual(result["qualification_basis"], "neither")
        self.assertFalse(result["is_financially_qualified"])

    def test_missing_current_can_qualify_via_avg90(self):
        result = evaluate_economics(values(current_buy_box=None, current_fees=None, keepa_avg90=D("40")))
        self.assertEqual(result["qualification_basis"], "avg90_only")
        self.assertIn("current_buy_box_unavailable", result["incomplete_reasons"])

    def test_missing_avg90_can_qualify_via_current(self):
        result = evaluate_economics(values(current_buy_box=D("40"), keepa_avg90=None, avg90_fees=None))
        self.assertEqual(result["qualification_basis"], "current_only")
        self.assertIn("keepa_avg90_unavailable", result["incomplete_reasons"])

    def test_missing_fee_blocks_that_price_basis(self):
        result = evaluate_economics(values(current_fees=None, keepa_avg90=D("25")))
        self.assertEqual(result["qualification_basis"], "incomplete")

    def test_25_percent_floor_recalculates_price_dependent_referral_fee(self):
        result = evaluate_economics(values(current_buy_box=D("40"), current_fees=fees("10", "6", "4")))
        expected = (D("15") * D("1.25") + D("4") + D("0.6092")) / (D("1") - D("0.15"))
        self.assertEqual(result["current"]["floor"], expected.quantize(D("0.0001")))

    def test_price_headroom_is_informational_ratio(self):
        result = evaluate_economics(values(current_buy_box=D("40")))
        expected = (D("40") - result["current"]["floor"]) / D("40")
        self.assertEqual(result["current_price_headroom"], expected.quantize(D("0.00000001")))

    def test_capacity_deducts_fba_inbound_and_draft(self):
        result = evaluate_economics(values(sales_rank_drops90=36, fba_fulfillable_units=3,
                                            inbound_units=2, draft_commitment_units=4))
        self.assertEqual(result["expected_monthly_sales"], D("12.0000"))
        self.assertEqual(result["purchase_capacity"], D("3.0000"))

    def test_capacity_never_below_zero(self):
        self.assertEqual(evaluate_economics(values(sales_rank_drops90=3, fba_fulfillable_units=10))["purchase_capacity"], D("0.0000"))

    def test_unknown_velocity_keeps_capacity_unknown(self):
        result = evaluate_economics(values(sales_rank_drops90=None))
        self.assertIsNone(result["expected_monthly_sales"])
        self.assertIsNone(result["purchase_capacity"])

    def test_accessory_allowances_are_not_silently_games(self):
        result = evaluate_economics(values(is_accessory=True))
        self.assertEqual(result["allowance_status"], "accessory_review_required")
        self.assertEqual(result["qualification_basis"], "incomplete")

    def test_risk_signals_do_not_change_economics(self):
        before = evaluate_economics(values())
        informational_risk_signals(current_price=D("20"), avg30_price=D("40"), avg90_price=D("50"),
                                   supplier_change_30d=D("-0.50"), offer_count_current=99)
        after = evaluate_economics(values())
        self.assertEqual(before, after)

    def test_supplier_history_requires_actual_30_and_90_day_coverage(self):
        rows = [
            {"effective_date": "2026-01-01", "revision": 1, "supplier_price": "20"},
            {"effective_date": "2026-03-10", "revision": 1, "supplier_price": "18"},
            {"effective_date": "2026-04-15", "revision": 1, "supplier_price": "15"},
        ]
        result = supplier_price_history(rows)
        self.assertEqual(result["previous"], D("18"))
        self.assertEqual(result["price_30d"], D("18"))
        self.assertEqual(result["price_90d"], D("20"))
        self.assertEqual(result["historical_low"], D("15"))

    def test_supplier_history_does_not_fabricate_missing_window(self):
        result = supplier_price_history([{"effective_date": "2026-04-01", "revision": 1, "supplier_price": "15"},
                                         {"effective_date": "2026-04-15", "revision": 1, "supplier_price": "14"}])
        self.assertIsNone(result["price_30d"])
        self.assertIsNone(result["change_30d"])


if __name__ == "__main__":
    unittest.main()
