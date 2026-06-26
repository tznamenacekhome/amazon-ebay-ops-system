# ZFI Financial UI PRD

**Document:** ZFI Financial UI PRD  
**Version:** 2  
**Last updated:** 2026-06-26  
**Purpose:** Define the ZoltarFI / ZFI business financial UI requirements and the migration boundary between MBOP and ZFI.

---

## 1. Summary

MBOP currently contains several financial dashboard views that helped bootstrap business visibility while the resale operations platform matured. ZFI can now receive MBOP business summary payloads in the ZFI Supabase database.

The long-term direction is:

- **MBOP** remains the operational source of truth for resale operations.
- **ZFI** becomes the financial reporting, household/business planning, cash-flow, tax, and business value system.
- MBOP should share business-operational financial summaries with ZFI, but not personal finance data.
- ZFI should combine MBOP summaries with YNAB, tax returns, receipts, paystubs, Plaid, and manual inputs.

MBOP should not become a personal finance, tax, or household net worth application.

---

## 2. Core Boundary

### MBOP Mission

Run the resale business.

MBOP owns operational workflows and operational truth:

- Purchases
- Receiving
- Inventory state
- Inventory value
- Inventory reconciliation
- FBA prep and shipments
- Amazon/eBay sales operations
- Returns/refunds follow-up
- Item-level profitability
- Order-level profitability
- COGS allocation
- Shipping label costs
- Marketplace operational metrics
- Sourcing ROI
- Repricing and aged inventory action queues

### ZFI Mission

Optimize the household and business financial future.

ZFI owns financial interpretation and planning:

- Household net worth
- Business net worth in household context
- Cash-flow planning
- YNAB integration
- Business cash from YNAB business category balances
- Schedule C / tax categorization
- Quarterly tax estimate support
- Annual tax packet support
- Owner draws/contributions
- Tax return intelligence
- Paystub intelligence
- Receipt/item-level purchase intelligence
- HELOC and mortgage planning
- Retirement planning
- Ask Zoltar analysis

---

## 3. Goals

- Move financial planning surfaces out of MBOP and into ZFI.
- Preserve MBOP operational profitability and inventory diagnostics needed to run the resale business day to day.
- Use MBOP-pushed business summary payloads as one ZFI data source.
- Avoid shared auth, shared user tables, or ZFI personal finance readback into MBOP.
- Give ZFI a finance UI that can grow into YNAB, tax, cash-flow, receipt, investment, and household planning.
- Preserve existing MBOP business value history through a one-time backfill into ZFI.
- Allow parallel comparison of MBOP and ZFI values before retiring MBOP YNAB sync.

---

## 4. Non-Goals

- Do not remove working MBOP dashboards immediately.
- Do not add ZFI UI inside MBOP.
- Do not expose ZFI household or personal finance data to MBOP.
- Do not add marketplace write actions.
- Do not make MBOP responsible for Schedule C/tax category classification.
- Do not require MBOP to maintain long-term business value history after the one-time backfill.
- Do not require MBOP to maintain YNAB integration permanently.

---

## 5. Current Source MBOP UI To Move, Keep, Or De-emphasize

### 5.1 Move To ZFI

These should become ZFI-owned views:

- Business value trend after one-time historical backfill.
- Financial dashboard cash position summary.
- Amazon payout/cash status.
- Amazon available to withdraw.
- Amazon-to-bank in-transit cash.
- Amazon deferred/reserved cash where available.
- Financial data completeness as close/readiness context.
- Growth dashboard revenue/profit/business-value trends.
- Schedule C placeholder/future tax reporting surface.
- YNAB Business cash and transaction-based finance planning.

### 5.2 Keep In MBOP

These remain MBOP operational views:

- Sales Orders item/order profitability.
- Missing COGS, missing fees, and missing fulfillment cost operational queues.
- Purchase profitability and sourcing ROI.
- Inventory value by operational state.
- Aged inventory/repricing action queues.
- FBA prep value and shipment readiness.
- Return/refund impact on specific purchase items or order-problem cases.
- Inventory value for:
  - Items at Amazon FBA
  - Items on order and not yet received
  - Items delivered but not yet received
  - Items in shipment to Amazon
  - Merchant-fulfilled inventory
  - Other MBOP operational states
- Item-level COGS and profitability.

### 5.3 Copy, Then De-emphasize In MBOP

Some views can exist in both places briefly while ZFI matures:

- 30/90/YTD gross sales, fees, COGS, net profit, and ROI.
- Current inventory value and aged inventory value.
- Amazon cash and in-transit cash.
- Total business value history only until one-time backfill is verified.
- YNAB-based values only until ZFI business finance reporting is verified.

Once ZFI has equivalent or better views, MBOP should mark broader financial widgets as legacy or link users to ZFI.

---

## 6. Data Source Strategy

### 6.1 ZFI Import Layer

ZFI should treat MBOP as one financial source among several.

MBOP data should land in ZFI import/staging tables first, then be normalized into reporting tables.

Recommended pattern:

```text
MBOP operational data
  -> MBOP publisher/export job
  -> ZFI Supabase import tables
  -> ZFI normalized financial tables
  -> ZFI dashboards
  -> Ask Zoltar
```

ZFI should not treat raw imported JSON as the long-term reporting model.

### 6.2 Initial Source Table

Current source table:

```text
public.mbop_business_summaries
```

This may remain for the first implementation, but the architecture should evolve toward generalized financial source import tables, such as:

```text
financial_import_runs
financial_source_payloads
mbop_business_summary_snapshots
mbop_inventory_value_snapshots
mbop_profitability_snapshots
mbop_amazon_cash_snapshots
```

### 6.3 Key Imported Fields

Required metadata:

- `source`
- `schema_version`
- `period_start`
- `period_end`
- `generated_at`
- `payload`
- `source_summary`
- import run ID
- data freshness status
- confidence notes

Important payload sections:

- `sales`
- `costs`
- `inventory`
- `profitability`
- `cash_operational`
- `alerts`
- `source_timestamps`
- `reconciliation_confidence_notes`

ZFI should treat MBOP payloads as imported operational summaries, not as the only financial source of truth.

---

## 7. Business Value History Requirement

### 7.1 One-Time Historical Backfill

MBOP currently has historical business value snapshots that should not be lost.

Requirement:

- MBOP must provide a one-time backfill of every historical Business Value snapshot already stored in MBOP.
- ZFI must import and preserve those historical rows.
- ZFI should identify the rows as migrated from MBOP.
- Each imported snapshot should retain original date/time, source notes, component values, and confidence notes where available.
- After verification, ZFI becomes the owner of Business Value history going forward.

### 7.2 Future Ownership

After the one-time backfill is verified:

- MBOP should no longer maintain full Business Value history.
- MBOP should not be required to maintain the YNAB integration or business cash values for historical valuation.
- ZFI should maintain Business Value history using:
  - MBOP inventory value snapshots
  - MBOP Amazon cash/payout snapshots
  - YNAB business cash/category balance
  - ZFI financial calculations

### 7.3 Business Value Formula

Business Value in ZFI should be calculated as:

```text
Inventory Value
  from MBOP operational inventory valuation

+ Business Cash
  from YNAB business category balance in ZFI

+ Amazon Available Balance
  from MBOP Amazon operational cash snapshot

+ Amazon Funds In Transit
  from MBOP Amazon payout/cash snapshot

= Business Value
```

ZFI may later expand this formula to include additional business assets or liabilities.

---

## 8. Product Requirements

## 8.1 Business Summary Dashboard

ZFI should provide a business summary dashboard powered by the latest MBOP summary payload and ZFI business cash data.

Required metrics:

- Gross sales
- Marketplace fees
- Shipping/fulfillment costs
- COGS
- Gross profit
- Estimated net profit
- ROI
- Current inventory value
- Aged inventory value
- FBA inventory value
- Merchant-fulfilled inventory value
- Purchased-not-received value
- Business cash from YNAB business category balance
- Amazon available to withdraw
- Amazon-to-bank in-transit cash
- Amazon deferred/reserved cash where available

Required states:

- Empty state when no MBOP summary has been imported.
- Stale state when `generated_at` is older than expected.
- Warning state when `alerts` or `reconciliation_confidence_notes` are present.
- Comparison state while MBOP and ZFI are running in parallel.

## 8.2 Business Value Trend

ZFI should chart business value over time.

Initial sources:

- One-time migrated MBOP historical business value snapshots.
- Ongoing MBOP inventory value snapshots.
- Ongoing MBOP Amazon cash/payout snapshots.
- Ongoing ZFI YNAB business cash/category balance.

Chart requirements:

- Time-series line chart.
- Latest value.
- 30-day change.
- Period selector.
- Drilldown into inventory, business cash, Amazon available balance, Amazon in-transit cash, and profit components.
- Clear source lineage for each component.

Important behavior:

- Do not lose MBOP historical business value data.
- Do not require MBOP to maintain long-term business value history after the migration.
- Clearly distinguish migrated MBOP history from ZFI-calculated history.

## 8.3 Profitability Trend

ZFI should provide financial trend views copied conceptually from MBOP Growth and Financial dashboards.

Required views:

- Monthly gross sales
- Monthly estimated operational profit
- Monthly COGS
- Monthly marketplace fees
- Monthly shipping/fulfillment costs
- ROI trend
- Units sold trend where available
- Return/refund trend where available

Important behavior:

- Label MBOP-derived values as operational estimates.
- Surface incomplete-source warnings from MBOP payload notes.
- Do not silently use incomplete rows as final tax/accounting profit.

## 8.4 Profit Definitions

ZFI must distinguish three profit concepts:

### Operational Profit

Owned by MBOP.

Typically includes:

- Sales
- Marketplace fees
- Shipping/fulfillment costs
- COGS
- Refunds/returns

Used for operating the business.

### Accounting Profit

Owned by ZFI.

Combines operational profit with:

- Software/tools
- Office supplies
- Mileage/travel where applicable
- Home office/storage where applicable
- Insurance/professional services
- Other business expenses from YNAB

Used for business financial reporting.

### Taxable Profit

Owned by ZFI.

Uses accounting profit plus tax-specific adjustments, prior tax return context, Schedule C mapping, depreciation, and other tax items.

Used for tax planning and annual tax preparation support.

## 8.5 Cash And Payout View

ZFI should own the broader cash and payout view.

Required sections:

- Amazon available to withdraw
- Amazon in transit to bank
- Amazon deferred/reserved cash
- Imported MBOP operational cash timestamp
- Business cash from YNAB business category balance
- Later: cash-flow forecast

MBOP should push Amazon payout status and cash details to ZFI so ZFI does not need to call Amazon SP-API.

MBOP dashboard should not display Amazon payout status as a finance UI element. MBOP may keep operational links or internal data only if needed for seller action or troubleshooting.

## 8.6 Inventory Capital View

ZFI should display inventory as capital tied up in the business.

Required sections:

- Current inventory value
- Aged inventory value
- Inventory value by state
- Inventory count by state
- FBA vs merchant-fulfilled vs purchased-not-received
- Shipment-to-Amazon value
- Delivered-not-received value if available

MBOP remains the place to act on inventory:

- Receiving
- FBA prep
- Repricing
- Reconciliation
- Returns
- COGS correction

ZFI displays inventory capital; MBOP fixes inventory.

## 8.7 Tax And Close Readiness

ZFI should replace MBOP's Schedule C placeholder with an actual finance/tax planning surface.

Initial requirements:

- Show MBOP source completeness warnings.
- Show missing COGS/fees/fulfillment alerts.
- Show whether latest MBOP payload is fresh.
- Reserve sections for Schedule C categories.
- Reserve sections for annual tax packet support.
- Use ZFI YNAB data and uploaded tax returns for business tax categorization.

Later requirements:

- Classify YNAB/business expenses.
- Track owner draws/contributions.
- Estimate quarterly taxes.
- Build annual tax packet exports.

## 8.8 Data Lineage

Every ZFI business metric should show where it came from.

Examples:

- Inventory value:
  - Source: MBOP
  - Generated at
  - Period
  - Confidence notes
- Business cash:
  - Source: YNAB business category balance
  - Sync timestamp
- Amazon available:
  - Source: MBOP Amazon cash snapshot
  - Generated at
- Accounting profit:
  - Source: ZFI calculation from MBOP operational profit + YNAB business expenses

Every displayed number should support an “Explain This Number” interaction.

---

## 9. MBOP Changes After ZFI UI Exists

When ZFI has working replacement views:

- Keep MBOP Sales Orders profitability.
- Keep MBOP Inventory dashboard as operational inventory visibility.
- Keep inventory value and inventory reconciliation in MBOP.
- Keep item-level and order-level profitability in MBOP.
- Push Amazon payout/cash status to ZFI rather than displaying it as a MBOP dashboard finance widget.
- Mark MBOP Financial dashboard as legacy or narrow it to operational gaps.
- Remove or hide Schedule C placeholder from MBOP.
- Replace broad business value planning language with links/references to ZFI.

Do not remove MBOP functionality until ZFI is verified and Tim confirms the ZFI view replaces the MBOP use case.

---

## 10. YNAB Migration Plan

ZFI is the future owner of YNAB.

However, MBOP YNAB sync should not be turned off immediately.

### Phase 1: Parallel Run

- MBOP YNAB sync remains active.
- ZFI YNAB sync is built.
- ZFI business finance reporting is implemented.
- Reports are compared on an ongoing basis.

### Phase 2: Verification

Compare:

- Business cash
- Business category balances
- Business transactions
- Business expenses
- Profit/cash reports
- Tax category candidates

Run parallel for several weeks or until Tim is comfortable.

### Phase 3: Freeze MBOP YNAB

- Stop scheduled MBOP YNAB jobs.
- Leave code in place temporarily.
- Mark MBOP YNAB features as legacy.
- Keep historical MBOP records for audit/compare if useful.

### Phase 4: Remove/Archive MBOP YNAB

- Archive integration code after ZFI is confirmed.
- Remove MBOP YNAB UI dependencies.
- Confirm no MBOP operational workflow depends on YNAB.

---

## 11. Future Enhancement: Operational Drilldown

ZFI should remain a financial summary and planning system.

When users need operational detail, ZFI should drill into MBOP through secure APIs rather than duplicating MBOP operational tables.

Example:

```text
Ask Zoltar:
"Why did June profit drop?"

ZFI:
"Returns increased and shipping costs were higher."

User:
"Show me the problem orders."

ZFI:
Calls MBOP operational drilldown API.

MBOP:
Returns relevant orders/items/returns.
```

Possible drilldown targets:

- Orders
- Purchase items
- Returns
- Inventory state history
- COGS corrections
- FBA shipment details
- Shipping label detail
- Fee detail
- Sourcing/purchase history

This should be added to MBOP `ROADMAP.md`.

Principle:

- ZFI stores summaries and planning data.
- MBOP remains operational source of truth.
- Drilldown is on-demand and scoped.
- Do not replicate full MBOP operational data into ZFI unless a clear reporting need emerges.

---

## 12. Security Requirements

- ZFI reads from its own Supabase tables.
- MBOP writes with scoped ZFI service credentials only.
- No MBOP frontend code receives ZFI credentials.
- No ZFI personal or household data is sent back to MBOP.
- ZFI authenticated users may read imported summaries according to ZFI RLS.
- MBOP users should not automatically become ZFI users.
- MBOP service credentials should be limited to insert/update on ZFI import tables where practical.
- Raw personal finance, tax return, paystub, and household records must never be visible to MBOP.

---

## 13. Success Metrics

- MBOP can push a current business summary into ZFI Supabase.
- MBOP can perform a one-time backfill of historical business value snapshots into ZFI.
- ZFI displays the latest MBOP summary without querying MBOP directly.
- ZFI displays migrated and ongoing business value history.
- ZFI uses YNAB business category balance for business cash.
- ZFI can compare ZFI YNAB-derived values against MBOP legacy YNAB values during the parallel period.
- ZFI can show business value, profitability, cash, payout, and inventory capital from imported summaries.
- MBOP keeps daily operational workflows without becoming a personal finance or tax app.
- MBOP YNAB sync is not disabled until ZFI business finance values are verified.

---

## 14. Answered Open Questions

### What refresh cadence should ZFI expect for MBOP summaries?

Event-based where possible.

Preferred cadence:

- Push after MBOP completes relevant financial refreshes, such as Amazon sales sync, inventory valuation, COGS recalculation, or Amazon cash refresh.
- Manual push must remain available.
- ZFI should mark data stale if no summary has been received within the expected window.

### Should ZFI store monthly snapshots derived from MBOP payloads, or rely on one imported row per requested period?

Store both.

- Preserve every imported payload/import run.
- Derive monthly snapshots for reporting.
- Never discard raw imports.
- Storage is cheap; history and lineage are valuable.

### How should ZFI distinguish operational estimated profit from tax/accounting profit after YNAB and tax categories are added?

Use separate named metrics:

- Operational profit: MBOP-derived.
- Accounting profit: ZFI-derived from operational profit plus YNAB business expenses.
- Taxable profit: ZFI-derived after tax rules, Schedule C mapping, and tax return context.

### Should MBOP eventually push item-level detail exports for audit drilldown, or should ZFI stay summary-only?

ZFI should stay summary-first.

Do not push item-level detail by default.

Future item-level drilldown should be on-demand through secure MBOP APIs when Ask Zoltar or a report needs operational detail.

### When should MBOP hide or deprecate the existing Financial dashboard tab?

Do not hide immediately.

Sequence:

1. Build ZFI business finance views.
2. Compare values with MBOP reports.
3. Keep MBOP financial dashboard during parallel run.
4. Narrow or mark MBOP Financial dashboard as legacy after ZFI is trusted.
5. Remove only after Tim confirms ZFI replaces the use case.

---

## 15. Next Steps

### For MBOP

1. Add/update documentation reflecting the MBOP/ZFI boundary.
2. Add Future Enhancement: Operational Drilldown to `ROADMAP.md`.
3. Add one-time historical business value backfill export/push to ZFI.
4. Continue pushing current MBOP operational summaries to ZFI.
5. Include Amazon payout/cash data in ZFI payload.
6. Keep YNAB sync active temporarily for comparison.
7. Do not remove MBOP financial dashboards yet.
8. Do not show payout status as a MBOP finance dashboard widget after ZFI view is ready.

### For ZFI

1. Build import tables and normalized reporting tables.
2. Import MBOP business summary payloads.
3. Import one-time MBOP business value history.
4. Build Business Summary Dashboard.
5. Build Business Value Trend with migrated history.
6. Build Cash/Payout view using MBOP Amazon cash and ZFI YNAB business cash.
7. Build Profitability Trend and Profit Definitions.
8. Build comparison reports between ZFI and MBOP legacy values during parallel run.
9. Build Explain This Number / data lineage interactions.
10. Prepare for future Ask Zoltar questions.

---

## 16. Guiding Principle

ZFI is the financial data warehouse and planning layer.

MBOP is the operational business system.

MBOP should publish operational financial facts. ZFI should preserve, normalize, interpret, compare, and plan from them.
