# MBOP Financial Functionality Retirement

Date: 2026-07-14

## Summary

ZFI has replaced MBOP's legacy financial-planning surfaces. MBOP now retains
operational profitability, sales/orders, COGS, fees, inventory operational
value, Amazon payout/cash source data, and outbound ZFI summary pushes.

Removed from active MBOP code:

- YNAB cash balance sync.
- YNAB Business transaction sync.
- MBOP business-value snapshot production.
- Dashboard Financial tab and API route.
- Dashboard Growth tab and API route.
- Overview business-value cards and trend.
- High-level Amazon dashboard revenue/profit/Sales Performance sections.

Preserved:

- `integrations/push_zfi_business_summary.py`.
- Amazon sales order, finance-event, profitability, fee, COGS, and fulfillment
  source tables.
- Amazon Finance balance snapshots as Amazon-owned operational payout/cash
  signals.
- Inventory operational value by workflow state.
- Sourcing operational estimated profit/ROI signals.
- One-time historical business-value backfill tooling:
  `integrations/backfill_zfi_business_value_history.py`.

## Growth Tab Decision

After removing business value, revenue/profit trends, long-range interpretation,
and growth signals, the Growth tab had no coherent operational-only view left.
It was removed rather than left as an empty shell.

## Amazon Finance Change

`integrations/amazon_sync_finance_balances.py` no longer reads
`ynab_business_transactions`. `in_transit_to_bank` is now Amazon Processing fund
transfers only. Recent completed Amazon transfers are preserved as Amazon-only
reference context in the raw breakdown, but MBOP no longer decides whether they
matched bank/YNAB deposits.

## Database Objects Found

Legacy objects that are now exclusive to retired MBOP financial functionality:

- `ynab_category_balance_snapshots`
- `vw_latest_ynab_category_balance_snapshot`
- `ynab_business_transactions`
- `business_value_snapshots`

The migration in `sql/2026-07-14_retire_mbop_financial_legacy.sql` is prepared
but was not applied. It drops only these legacy reporting objects. Apply it only
after confirming no audit/retention need remains for the local MBOP copies.

## Validation Scope

No deployment was performed. No production data was changed.
