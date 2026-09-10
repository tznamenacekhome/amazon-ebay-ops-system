# Amazon returns analysis review package

Start with the [full report](../../AMAZON_RETURN_ECONOMICS.md), then inspect:

- [summary.json](summary.json): headline metrics and coverage.
- [return_detail.csv](return_detail.csv): 191 physical-return records, costs, scenarios, and reconciliation flags.
- [fee_events.csv](fee_events.csv): signed fee evidence, including unresolved records.
- [sales_denominator.csv](sales_denominator.csv): 2,970 eligible sales lines representing 3,052 units.
- [segments.csv](segments.csv): ASIN, platform, month, reason, disposition, and price/cost bands.
- [refunds_without_physical_return.csv](refunds_without_physical_return.csv): 28 refund records across 26 sale lines without physical-return matches.

Disposition follow-up (same frozen cohort and source evidence):

- [disposition_summary.json](disposition_summary.json): decision metrics, $0.4341 missing-basis sensitivity, and refined unmatched-refund classifications.
- [game_disposition_buckets.csv](game_disposition_buckets.csv): five exclusive buckets, costs, basis, and coverage.
- [game_disposition_detail.csv](game_disposition_detail.csv): the 99 game returns, raw values, case evidence, and unconfirmed removal candidates.
- [game_return_reasons.csv](game_return_reasons.csv): reason-level condition and cost breakdowns.
- [game_return_asins.csv](game_return_asins.csv): ASIN concentrations with sold denominators and small-sample flags.
- [refund_only_analysis.csv](refund_only_analysis.csv): one row per unmatched sale line, separating full product refunds, shipping-only concessions, and a zero-amount record.

Method: [analysis CLI](../../../integrations/analyze_amazon_return_economics.py). Verification: [tests](../../../tests/test_amazon_return_economics.py).

These are frozen outputs from the September 9, 2026 analysis. Raw API responses and credentials are not included. The outputs contain business order and transaction identifiers for audit, but no customer comments.

The exclusive disposition buckets contain 67 sellable, 31 unsellable, and one reimbursed unit. The reimbursed unit is also physically sellable, giving 68 sellable units when reporting condition. Zero rows in the Unknown classification bucket does not mean every recovery is known: all 31 unsellable units still lack a final measured recovery outcome. Removal candidates are not proven physical-unit matches. Refund-only reimbursements must not be subtracted from the separately measured physical-return cohort.

For review, check population consistency, deferred/released transaction deduplication, fee hierarchy, revenue reversal treatment, reimbursement matching, and missing-basis/recovery handling. The report's known-cost and zero-recovery scenarios are incomplete; neither is a defensible complete business-wide maximum. Blank monetary values represent unavailable evidence, not zero. Revenue/refund line totals repeat when one sale line has multiple returns and must not be summed blindly. Use `cohort_in_period` to select the 180 returns belonging to the paid US sales cohort.
