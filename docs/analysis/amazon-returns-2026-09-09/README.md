# Amazon returns analysis review package

Start with the [full report](../../AMAZON_RETURN_ECONOMICS.md), then inspect:

- [summary.json](summary.json): headline metrics and coverage.
- [return_detail.csv](return_detail.csv): 191 physical-return records, costs, scenarios, and reconciliation flags.
- [fee_events.csv](fee_events.csv): signed fee evidence, including unresolved records.
- [sales_denominator.csv](sales_denominator.csv): 2,970 eligible sales lines representing 3,052 units.
- [segments.csv](segments.csv): ASIN, platform, month, reason, disposition, and price/cost bands.
- [refunds_without_physical_return.csv](refunds_without_physical_return.csv): 28 refund records across 26 sale lines without physical-return matches.

Method: [analysis CLI](../../../integrations/analyze_amazon_return_economics.py). Verification: [tests](../../../tests/test_amazon_return_economics.py).

These are frozen outputs from the September 9, 2026 analysis. Raw API responses and credentials are not included. The outputs contain business order and transaction identifiers for audit, but no customer comments.

For review, check population consistency, deferred/released transaction deduplication, fee hierarchy, revenue reversal treatment, reimbursement matching, and missing-basis/recovery handling. The report's known-cost and zero-recovery scenarios are incomplete; neither is a defensible complete business-wide maximum. Blank monetary values represent unavailable evidence, not zero. Revenue/refund line totals repeat when one sale line has multiple returns and must not be summed blindly. Use `cohort_in_period` to select the 180 returns belonging to the paid US sales cohort.
