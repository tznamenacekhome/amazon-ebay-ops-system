# ZFI Financial UI PRD

Last updated: 2026-06-26

## Summary

MBOP currently contains several financial dashboard views that helped bootstrap
business visibility while the resale operations platform matured. Now that ZFI
can receive MBOP business summary payloads in `public.mbop_business_summaries`,
the broader financial planning UI should move or be copied into ZFI.

MBOP should remain focused on operational decisions: what to buy, receive,
list, reprice, return, reconcile, and fix. ZFI should own financial planning:
business value over time, cash flow, tax/category reporting, owner finances,
and household/business context.

## Goals

- Move financial planning surfaces out of MBOP and into ZFI.
- Preserve MBOP operational profitability and inventory diagnostics needed to
  run the resale business day to day.
- Use MBOP's pushed business summary payload as the first ZFI data source.
- Avoid shared auth, shared user tables, or ZFI personal finance readback into
  MBOP.
- Give ZFI a finance UI that can grow into YNAB, tax, cash-flow, and household
  planning without expanding MBOP's scope.

## Non-Goals

- Do not remove working MBOP dashboards immediately.
- Do not add ZFI UI inside MBOP.
- Do not expose ZFI household or personal finance data to MBOP.
- Do not add marketplace write actions.
- Do not make MBOP responsible for tax category classification.

## Source MBOP UI To Move Or Copy

### Move To ZFI

These should become ZFI-owned views:

- Business value trend from MBOP Dashboard Overview.
- Financial dashboard cash position summary.
- Amazon-to-bank payout reconciliation.
- Financial data completeness as close/readiness context.
- Growth dashboard revenue/profit/business-value trends.
- Schedule C placeholder/future tax reporting surface.
- YNAB Business cash and transaction-based finance planning.

### Keep In MBOP

These remain MBOP operational views:

- Sales Orders item/order profitability.
- Missing COGS, missing fees, and missing fulfillment cost operational queues.
- Purchase profitability and sourcing ROI.
- Inventory value by operational state.
- Aged inventory/repricing action queues.
- FBA prep value and shipment readiness.
- Return/refund impact on specific purchase items or order-problem cases.
- Amazon Funds Available link/state where it helps the operator act in Seller
  Central.

### Copy, Then De-emphasize In MBOP

Some views can exist in both places briefly while ZFI matures:

- 30/90/YTD gross sales, fees, COGS, net profit, and ROI.
- Current inventory value and aged inventory value.
- Amazon cash and in-transit cash.
- Total business value history.

Once ZFI has equivalent or better views, MBOP should mark these broader
financial widgets as legacy or link users to ZFI.

## Users

- Business operator: wants a daily operational snapshot in MBOP and financial
  planning in ZFI.
- ZFI household finance user: wants business value, cash flow, taxes, and
  household planning in one system.
- Future MBOP operator/user: may need resale workflow access but must not gain
  access to personal finance or ZFI data.

## Data Source

Initial source table in ZFI:

`public.mbop_business_summaries`

Key fields:

- `source`
- `schema_version`
- `period_start`
- `period_end`
- `generated_at`
- `payload`
- `source_summary`

Important payload sections:

- `sales`
- `costs`
- `inventory`
- `profitability`
- `cash_operational`
- `alerts`
- `source_timestamps`
- `reconciliation_confidence_notes`

ZFI should treat this table as an imported operational summary, not as the only
financial source of truth. ZFI can combine it later with YNAB, bank, tax, and
household data.

## Product Requirements

### 1. Business Summary Dashboard

ZFI should provide a business summary dashboard powered by the latest MBOP
summary payload.

Required metrics:

- Gross sales.
- Marketplace fees.
- Shipping/fulfillment costs.
- COGS.
- Gross profit.
- Estimated net profit.
- ROI.
- Current inventory value.
- Aged inventory value.
- FBA inventory value.
- Merchant-fulfilled inventory value.
- Purchased-not-received value.
- Amazon cash.
- Amazon available to withdraw.
- Amazon-to-bank in-transit cash.

Required states:

- Empty state when no MBOP summary has been imported.
- Stale state when `generated_at` is older than the expected refresh cadence.
- Warning state when `alerts` or `reconciliation_confidence_notes` are present.

### 2. Business Value Trend

ZFI should chart business value over time using imported MBOP summaries.

Initial calculated value:

`inventory.current_inventory_value + cash_operational.amazon_cash + cash_operational.amazon_to_bank_in_transit`

If ZFI later has bank/YNAB cash data, ZFI should calculate a broader business
net worth value in ZFI, not MBOP.

Chart requirements:

- Time-series line chart.
- Latest value.
- 30-day change.
- Period selector.
- Drilldown into inventory, cash, and profit components.

### 3. Profitability Trend

ZFI should provide financial trend views copied conceptually from MBOP Growth
and Financial dashboards.

Required views:

- Monthly gross sales.
- Monthly estimated net profit.
- Monthly COGS.
- Monthly marketplace fees.
- ROI trend.
- Units sold trend where available.

Important behavior:

- Label MBOP-derived values as operational estimates.
- Surface incomplete-source warnings from MBOP payload notes.
- Do not silently use incomplete rows as final tax/accounting profit.

### 4. Cash And Payout View

ZFI should own the broader cash-flow view.

Required sections:

- Amazon available to withdraw.
- Amazon in transit to bank.
- Amazon deferred/reserved cash.
- Imported MBOP operational cash timestamp.
- Later: bank/YNAB business cash.
- Later: cash-flow forecast.

MBOP should keep only the operational Seller Central funds/action context.

### 5. Inventory Capital View

ZFI should display inventory as capital tied up in the business.

Required sections:

- Current inventory value.
- Aged inventory value.
- Inventory value by state.
- Inventory count by state.
- FBA vs merchant-fulfilled vs purchased-not-received.

MBOP remains the place to act on inventory: receiving, FBA prep, repricing,
reconciliation, and returns.

### 6. Tax And Close Readiness

ZFI should replace MBOP's Schedule C placeholder with an actual finance/tax
planning surface.

Initial requirements:

- Show MBOP source completeness warnings.
- Show missing COGS/fees/fulfillment alerts.
- Show whether latest MBOP payload is fresh.
- Reserve sections for Schedule C categories.
- Reserve sections for annual tax packet support.

Later requirements:

- Classify YNAB/business expenses.
- Track owner draws/contributions.
- Estimate quarterly taxes.
- Build annual tax packet exports.

## MBOP Changes After ZFI UI Exists

When ZFI has working replacement views:

- Keep MBOP Sales Orders profitability.
- Keep MBOP Inventory dashboard as operational inventory visibility.
- Keep MBOP operational Amazon cash links if they support seller action.
- Mark MBOP Financial dashboard as legacy or narrow it to operational gaps.
- Remove or hide Schedule C placeholder from MBOP.
- Replace broad business value planning language with links/references to ZFI.

Do not remove MBOP functionality until ZFI is verified and the operator confirms
the ZFI view replaces the MBOP use case.

## Security Requirements

- ZFI reads from its own Supabase table.
- MBOP writes with ZFI backend/service-role credentials only.
- No MBOP frontend code receives ZFI credentials.
- No ZFI personal or household data is sent back to MBOP.
- ZFI authenticated users may read imported summaries according to ZFI RLS.
- MBOP users should not automatically become ZFI users.

## Success Metrics

- MBOP `push_zfi_business_summary.py --apply` creates or updates one ZFI row per
  period.
- ZFI displays the latest MBOP summary without requiring ZFI to query MBOP.
- ZFI can show business value, profitability, cash, and inventory capital from
  imported summaries.
- MBOP can keep daily operational workflows without becoming a personal finance
  or tax app.

## Open Questions

- What refresh cadence should ZFI expect for MBOP summaries: daily, weekly, or
  manual close-period only?
- Should ZFI store monthly snapshots derived from MBOP payloads, or rely on one
  imported row per requested period?
- How should ZFI distinguish operational estimated profit from tax/accounting
  profit after YNAB and tax categories are added?
- Should MBOP eventually push item-level detail exports for audit drilldown, or
  should ZFI stay summary-only?
- When should MBOP hide or deprecate the existing Financial dashboard tab?
