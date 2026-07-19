from __future__ import annotations

import datetime as dt
from decimal import Decimal

from integrations.provider_costs import (
    average_tracker_cost,
    calendar_month_periods,
    calculated_month_periods,
    dollar_variance,
    easypost_line_items,
    reconcile_easypost_wallet,
    tracker_fee_for_carrier,
    unavailable_supabase_periods,
)


def test_aws_calendar_month_boundaries_are_exclusive():
    current, previous = calendar_month_periods(dt.date(2026, 7, 19))

    assert current.start == dt.date(2026, 7, 1)
    assert current.end == dt.date(2026, 8, 1)
    assert current.status == "current"
    assert previous.start == dt.date(2026, 6, 1)
    assert previous.end == dt.date(2026, 7, 1)
    assert previous.status == "completed"


def test_calculated_provider_periods_mark_calculated_calendar_month():
    current, previous = calculated_month_periods(dt.date(2026, 1, 3))

    assert current.cycle_type == "calculated_calendar_month"
    assert current.source == "calculated"
    assert previous.end == current.start


def test_dollar_variance_is_current_minus_previous_without_percentage():
    assert dollar_variance("14.25", "10.00") == Decimal("4.2500")
    assert dollar_variance("7.00", "10.00") == Decimal("-3.0000")
    assert dollar_variance(None, "10.00") is None


def test_easypost_tracker_pricing_is_tracker_only_by_carrier():
    assert tracker_fee_for_carrier("USPS") == Decimal("0.03")
    assert tracker_fee_for_carrier("UPS") == Decimal("0.02")
    assert tracker_fee_for_carrier(None) == Decimal("0.02")


def test_easypost_wallet_funding_is_not_tracker_expense():
    reconciliation = reconcile_easypost_wallet(
        opening_balance="10.00",
        funding_and_credits="20.00",
        tracker_charges_and_debits="0.40",
        other_debits="0.00",
        closing_balance="29.60",
    )

    assert reconciliation.funding_and_credits == Decimal("20.0000")
    assert reconciliation.tracker_charges_and_debits == Decimal("0.4000")
    assert reconciliation.unreconciled_difference == Decimal("0.0000")


def test_average_tracker_cost_omitted_when_inputs_are_incomplete():
    assert average_tracker_cost(None, 5) is None
    assert average_tracker_cost("1.00", 0) is None
    assert average_tracker_cost("1.00", 4) == Decimal("0.2500")


def test_supabase_periods_do_not_invent_billing_anchor_or_totals():
    current, previous = unavailable_supabase_periods(dt.date(2026, 7, 19))

    assert current.status == "unavailable"
    assert previous.status == "unavailable"
    assert current.cycle_type == "unavailable"
    assert current.source == "api"


def test_easypost_line_items_aggregate_without_labels_or_postage():
    period = calculated_month_periods(dt.date(2026, 7, 19))[0]
    rows = easypost_line_items(
        "period-1",
        period,
        [
            {"easypost_tracker_id": "trk_1", "carrier": "USPS"},
            {"easypost_tracker_id": "trk_2", "carrier": "UPS"},
            {"easypost_tracker_id": "trk_3", "carrier": "UPS"},
        ],
    )

    assert {row["category"] for row in rows} == {"tracker_fees"}
    assert {row["service"] for row in rows} == {"Tracking API"}
    assert sum(Decimal(str(row["cost"])) for row in rows) == Decimal("0.0700")
    assert all(row["raw_metadata"]["wallet_funding_not_expense"] for row in rows)
