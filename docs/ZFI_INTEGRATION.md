# ZFI Integration

## Production activation (2026-09-18)

V3 is deployed and its fresh ZFI row verified. Scheduler revisions 97/98/99 use `0c94d3fb0b41`; web159 is unchanged. Generated at `2026-09-18T14:18:10.960144Z`. The null-safe console fix does not alter payload semantics. Current-month and top-level management costs remain null where production source data is incomplete; observed refunds remain diagnostic. See [deployment evidence and exact values](ZFI_V3_DEPLOYMENT_2026-09-18.md). The local-only status in the implementation section below is historical.

## Calendar-month management contract (2026-09-17)

Implemented locally as `schema_version = 2026-09-17` and
`payload_version = business_finance_replacement_v3`. No database migration is
required: the target remains the existing JSON payload column. Deployment and
live publication have not been performed for this revision.

ZFI should use `profitability_windows.current_month` for current-month facts and
`profitability_windows.ytd.management_pnl` for comparable YTD facts. The top-level
`management_pnl` describes the requested `--start-date` / `--end-date` period.
The existing `30d`, `90d`, `ytd` keys and all old top-level sections remain.
Legacy revenue/profit/ROI retain their complete-row trend semantics; they are
not a refund-adjusted management P&L. The old duplicated label/fulfillment fields
are corrected, and refund fields now carry safe nulls instead of sale-date estimates.
Do not substitute legacy net profit when management net profit is null.

### Exact definitions

- `current_month`: first day of the month containing `--end-date` through that
  date, inclusive, in `MBOP_BUSINESS_TIMEZONE` (default `America/Los_Angeles`).
  The CLI defaults to the business-local current date, including in UTC ECS.
  Timestamp comparisons use local dates and DST-aware half-open UTC bounds.
  Explicit historical end dates produce that historical calendar month.
- YTD management facts: January 1 through the same inclusive end date in the
  same timezone. `30d` and `90d` remain rolling trend windows, not months.
- `gross_sales` / `revenue`: stored sale prices of non-cancelled profitability
  rows by original order purchase date, including later-refunded rows. Missing
  prices produce null. `units_sold` uses that same population, not just complete
  rows. No eBay seller revenue is added.
- `cogs`: stored vendor-paid acquisition cost of the units sold, including
  later-refunded sales. Never add inbound-to-Amazon freight, prep, subsequent
  labels or selling fees; missing acquisition COGS produces null, not a subtotal.
- `marketplace_fees`: `amazon_sales_profitability.amazon_fees_excluding_fulfillment`.
  Excludes FBA fulfillment fees. These remain operational sale-cohort aggregates,
  **not a posted-period fee ledger**: the upstream calculator uses absolute fee
  amounts and does not reconcile refund fee credits by processing period.
  Missing-fee/refunded rows cause management fees to be null. Other values carry
  this explicit limitation. An actual fee-type breakdown is deferred because
  it would not safely reconcile to this aggregate without a fee-ledger repair.
- `fulfillment_costs`: stored `fulfillment_cost` with source `amazon_fba_fee` on
  Amazon-fulfilled orders. Unknown channels or ambiguous/missing FBA sources
  produce null. Manual values are not assigned to a category without provenance.
- `shipping_label_costs`: USD Veeqo shipment costs for merchant-fulfilled sales,
  with explicit `outbound_label_charges` or `label_cost` provenance, counted once
  per `veeqo_shipment_id`, even across multiple sale items. Costs follow the
  original order purchase period. FBA-only populations have zero label costs.
  Missing labels/currency or generic Veeqo `charge`/`cost` sources produce null.
  Generic negative Amazon adjustments and manual fulfillment overrides are not
  sufficiently identified as carrier labels and are not exported as labels.
  Inbound freight and FBA fees never enter this category.
- `gross_profit`: gross sales minus acquisition COGS, before refunds and all
  selling/fulfillment/label costs. This differs deliberately from the preserved
  legacy trend gross-profit formula; `gross_profit_basis` states the formula.
- `net_profit`: null while complete refund totals and posted fee-credit treatment
  cannot be certified. ZFI owns overhead and the final management P&L.

### Seller refunds and the current source limitation

`refunds_returns` is a positive contra-revenue expense convention, recognized by
Amazon refund processing (`posted_date`), never by sale date or physical return
date. Source: `amazon_sales_financial_events`, `event_type = RefundEventList`.
Supported observed components are signed Principal, ShippingCharge, GiftWrap,
and promotion reversals, negated to express contra-revenue. Taxes and fee credits
are excluded. eBay buyer acquisition refunds and `loss_prevention` recovery
figures are different domains and never feed this calculation.

**The current source cannot certify a complete refund total.** Finance sync is
order-scoped rather than a complete posted-period ledger; its legacy deterministic
financial-event ID omits posting date, which can collapse equal repeated refunds.
Accordingly `refunds_returns` is currently null with `refund_coverage = unverified`
for current month, YTD, other windows and top-level sales. This is not zero.
`refunds_returns_observed` provides the supported stored-event subtotal for
investigation only. It deduplicates stored event IDs, handles partial refunds and
preserves credit signs; unsupported currency, amount, type, identity or undated
refund events make even that subtotal null. An empty successfully read set has
observed zero, but still does not certify zero actual refunds.

A future refund-ledger repair must establish complete posted-period ingestion
and stable event identities before making `refunds_returns` numeric. This change
does not modify the importer, rewrite historical revenue, or guess missing refunds.

### Added metadata and compatibility

Management objects include `source_start_date`, `source_end_date`,
`source_start_at`, `source_end_at_exclusive`, `timezone`, `currency`,
`source_timestamps`, `completeness_warnings`, `refund_source`, `refund_coverage`,
and `marketplace_fee_basis`, `fulfillment_cost_basis`, `shipping_label_cost_basis`,
`cogs_basis`, `gross_profit_basis`. Dates describe the requested period; timestamps
are source-row freshness, not proof of complete ingestion.

Added fields: `profitability_windows.current_month`, top-level `management_pnl`,
`profitability_windows.{30d,90d,ytd}.management_pnl`, window refund fields,
`sales.refunds_returns_observed`, `costs.fulfillment_costs`, and source timestamps
`refund_events_created_at` / `veeqo_labels_updated_at`. Changed fields:
`sales.refunds_returns`, `costs.shipping_label_costs`, and legacy window
`fulfillment_costs` / `shipping_label_costs`. Existing section names, upsert key,
30/90-day boundaries and scheduler group/cadence behavior are preserved.
Consumers must preserve nulls and warnings rather than coerce them to zero.

New reads are projected refund rows bounded by posting period, one undated-refund
sentinel, and Veeqo labels in batches of 200 selected MFN order IDs. No raw snapshot
expansion, schema change, live backfill or new scheduler job is introduced. The
publisher's pre-existing historical reads remain; review Supabase capacity before
any full live publisher verification (see `docs/supabase_capacity.md`).

Local validation: `python -m unittest discover -s tests -p test_zfi_business_summary.py`.
All 20 contract tests passed, plus 19 refund-economics, 8 finance-archive and
5 scheduler-diagnostics tests (52 total); `git diff --check` passed.
Tests cover calendar/local/DST/YTD boundaries, refund processing periods and source
limits, independent fee/fulfillment/label costs, multi-item/shipment deduplication,
COGS separation, null behavior and the full publisher payload shape.

## ZFI Buying extension (2026-09-07)

The operator has authorized a narrow read-only purchase-facts pull and a fixed purchase-ingestion trigger/status API, in addition to the existing outbound summaries. ZFI continues to own all Buying Power and YNAB reconciliation logic. The view, fields, server credentials, historical coverage, concurrency and activation are documented in [ZFI Buying integration](ZFI_BUYING_INTEGRATION.md). Production activation passed on 2026-09-07; see [activation evidence](ZFI_BUYING_ACTIVATION_2026-09-07.md).


Last updated: 2026-07-14

## 2026-07-14 MBOP Retirement Update

ZFI replacement is verified. MBOP no longer runs active YNAB sync jobs or daily
business-value snapshot production, and the Dashboard Financial/Growth
planning views have been removed. `integrations/push_zfi_business_summary.py`
remains the supported outbound MBOP-to-ZFI integration for operational facts.

Historical business-value backfill tooling remains available for audit or
repeat migration needs, but ongoing business-value history belongs in ZFI.

## Purpose

MBOP runs the resale business. ZoltarFI / ZFI owns financial planning,
household/business net worth, cash flow, tax classification, and longer-range
profitability analysis.

The integration boundary is outbound-only:

MBOP operational data -> MBOP business summary payload -> ZFI Supabase

ZFI can then read the summary from its own Supabase database. MBOP does not
query ZFI and does not pull personal finance data into MBOP.

## Ownership Boundary

MBOP keeps:

- item-level and order-level resale profitability
- purchase, receiving, FBA, repricing, sourcing, and return/refund workflows
- Amazon sales order operational data
- Amazon fees and fulfillment cost used for sales-order profitability
- Veeqo label costs used for Merchant Fulfilled sales-order profitability
- COGS allocation and missing-data diagnostics
- inventory value by operational state
- Amazon-held cash and payout state as operational marketplace context

ZFI owns:

- YNAB integration going forward
- household and business net worth in one personal finance context
- business cash-flow planning
- owner draws and contributions
- recurring business expense review
- Schedule C and tax category mapping
- quarterly tax estimates
- annual tax packet support
- long-range profitability, retirement, mortgage, HELOC, and household planning

Legacy MBOP features such as YNAB cash snapshots, YNAB Business transactions,
business value trend reporting, and Schedule C placeholders are retired now
that ZFI replacement is verified.

## Security Rules

- ZFI credentials are server-side environment variables only.
- Do not expose `ZFI_SUPABASE_SERVICE_ROLE_KEY` to frontend code.
- Do not share auth, user tables, sessions, or cookies between MBOP and ZFI.
- MBOP pushes summarized business-operational data outward only.
- ZFI personal finance data must not be copied into MBOP.
- The ZFI service role key should be scoped operationally to the ZFI deployment
  environment where this manual push is run.

## MBOP Export Script

Manual script:

```powershell
.\.venv\Scripts\python.exe integrations\push_zfi_business_summary.py
```

Dry run is the default. It reads MBOP Supabase and prints the payload without
writing to ZFI.

Live push:

```powershell
.\.venv\Scripts\python.exe integrations\push_zfi_business_summary.py --apply
```

Custom period:

```powershell
.\.venv\Scripts\python.exe integrations\push_zfi_business_summary.py --start-date 2026-06-01 --end-date 2026-06-30
```

The script is now wired into AWS scheduler groups that refresh MBOP source data
used by the payload:

- `amazon-sales-recent`
- `finance-refresh`
- `fba-inventory-daily`
- `fba-shipments`

This keeps ZFI updated after MBOP refreshes Amazon/SP-API sales, finance,
inventory, and FBA-shipment source data. The job remains safe to run manually
for dry-run review, and it is nonblocking in scheduler orchestration so a ZFI
push failure does not prevent MBOP source syncs from completing.

## One-Time Business Value History Backfill

ZFI owns ongoing business value history after the one-time MBOP historical
backfill is verified. MBOP currently has historical rows in
`public.business_value_snapshots`; these rows are not written by
`integrations/push_zfi_business_summary.py`.

The one-time dry-run-first migration helper is:

```powershell
.\.venv\Scripts\python.exe integrations\backfill_zfi_business_value_history.py
```

Dry run is the default. It reads MBOP `business_value_snapshots`, maps rows to
ZFI `public.business_value_snapshots`, prints a preview, and performs no ZFI
writes.

Live backfill:

```powershell
.\.venv\Scripts\python.exe integrations\backfill_zfi_business_value_history.py --apply
```

This backfill:

- is one-time migration tooling, not ongoing sync
- is not scheduled
- does not re-enable MBOP YNAB
- does not remove or mutate MBOP `business_value_snapshots`
- sets `source_system = 'mbop'`
- sets `source_type = 'migrated_mbop_history'`
- preserves original MBOP `snapshot_date`
- preserves component values such as Amazon inventory, pre-Amazon inventory,
  Amazon cash, Amazon cash in transit, legacy YNAB cash on hand, and total
  business value
- maps MBOP inventory components into ZFI `inventory_value`
- maps legacy MBOP YNAB cash-on-hand into ZFI `business_cash`
- maps MBOP Amazon cash in transit into ZFI `amazon_funds_in_transit`
- preserves MBOP component values and `raw_rollup_json` inside ZFI
  `source_payload` and `raw_component_context`
- uses a deterministic UUID primary key derived from the MBOP snapshot id/date
  to avoid duplicate migrated rows

ZFI migration `017` must grant service-role access before the script can read
counts or write rows through PostgREST:

```sql
grant select, insert, update on public.business_value_snapshots to service_role;
```

If that grant is missing, dry run still previews MBOP mappings, but the ZFI row
count prints as unavailable. Live `--apply` will fail safely.

## Environment Variables

MBOP source database:

```text
SUPABASE_URL=<mbop supabase url>
SUPABASE_SERVICE_ROLE_KEY=<mbop service role key>
```

ZFI target database:

```text
ZFI_SUPABASE_URL=<zfi supabase url>
ZFI_SUPABASE_SERVICE_ROLE_KEY=<zfi service role key>
ZFI_BUSINESS_SUMMARY_TABLE=mbop_business_summaries
ZFI_BUSINESS_VALUE_HISTORY_TABLE=business_value_snapshots
ZFI_PUSH_RETRY_ATTEMPTS=3
ZFI_PUSH_RETRY_DELAY_SECONDS=2
ZFI_PUSH_GENERATED_BY=manual
```

`ZFI_BUSINESS_SUMMARY_TABLE`, `ZFI_BUSINESS_VALUE_HISTORY_TABLE`,
`ZFI_PUSH_RETRY_ATTEMPTS`,
`ZFI_PUSH_RETRY_DELAY_SECONDS`, and `ZFI_PUSH_GENERATED_BY` are optional.

## ZFI Supabase Table

ZFI-side setup is complete. ZFI migration
`supabase/migrations/016_mbop_business_summaries.sql` created
`public.mbop_business_summaries` with this shape:

```sql
create table if not exists public.mbop_business_summaries (
  mbop_business_summary_id uuid primary key default gen_random_uuid(),

  source text not null default 'mbop',
  schema_version text not null,
  period_start date not null,
  period_end date not null,
  generated_at timestamptz not null,

  payload jsonb not null,
  source_summary jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (source, period_start, period_end)
);

create index if not exists mbop_business_summaries_period_idx
  on public.mbop_business_summaries (period_start desc, period_end desc);

create index if not exists mbop_business_summaries_generated_idx
  on public.mbop_business_summaries (generated_at desc);

create index if not exists mbop_business_summaries_payload_gin_idx
  on public.mbop_business_summaries using gin (payload);
```

RLS is enabled in ZFI. Authenticated ZFI users have read-only access. MBOP
ingestion uses backend/service-role credentials only. No MBOP auth, MBOP users,
shared auth, or personal-finance readback was added.

The ZFI service-role database role also needs table privileges for PostgREST
upserts:

```sql
grant select, insert, update on public.mbop_business_summaries to service_role;
```

Without that grant, MBOP live push fails with PostgreSQL code `42501`
(`permission denied for table mbop_business_summaries`).

## Payload Fields

Top-level metadata:

- `source`: always `mbop`
- `schema_version`: payload version
- `payload_version`: current expanded payload is
  `business_finance_replacement_v3`
- `summary_id`: stable UUID for the source/period
- `generated_at`: UTC generation timestamp
- `generated_by`: manual/operator label
- `period.start_date` and `period.end_date`

Sales:

- `gross_sales`
- `marketplace_sales_by_channel.amazon`
- `marketplace_sales_by_channel.ebay`
- `marketplace_sales_by_channel.other`
- `refunds_returns`
- `units_sold`
- `complete_sales_rows`
- `total_sales_rows`

Costs:

- `marketplace_fees`
- `shipping_label_costs`
- `inbound_shipping_prep_costs`
- `cogs`
- `inventory_purchases`
- `software_tool_expenses`

Inventory:

- `current_inventory_value`
- `aged_inventory_value`
- `inventory_count_by_state`
- `inventory_value_by_state`
- `fba_inventory_value`
- `merchant_fulfilled_inventory_value`
- `purchased_not_received_value`

Profitability:

- `gross_profit`
- `estimated_net_profit`
- `roi`

Operational cash:

- `amazon_cash`
- `amazon_available_to_withdraw`
- `amazon_to_bank_in_transit`
- `amazon_deferred_or_reserved_cash`

Review support:

- `alerts`
- `source_timestamps`
- `source_summary`
- `reconciliation_confidence_notes`

Expanded dashboard-replacement sections:

- `profitability_windows`: 30-day, 90-day, and YTD gross sales, revenue,
  Amazon/marketplace fees, fulfillment/shipping-label costs, COGS, gross
  profit, net profit, ROI, average profit per unit, units sold, period source
  dates, timestamps, and completeness warnings.
- `cash_position`: Amazon cash total, available-to-withdraw cash,
  Amazon-to-bank in-transit cash, deferred/reserved cash, payout status summary,
  source timestamps, freshness, and warnings. ZFI-owned YNAB cash is not read
  back into MBOP.
- `payout_reconciliation`: in-transit payout amount from Amazon Processing
  transfers, latest payout dates where MBOP has them, source status, and
  explicit warnings for values MBOP does not safely model yet.
- `inventory_capital`: total, Amazon, and pre-Amazon inventory value; value by
  operational location; value by age bucket; capital-at-risk buckets; source
  timestamps; and warnings for missing or unavailable valuation concepts.
- `loss_prevention`: open sales/value-at-risk, refund pending, expected and
  received refunds, partial refunds, refund-event totals, Amazon
  reimbursement totals, currency handling, and conservative nulls/warnings for
  unrecoverable fees that still need financial mapping.
- `top_sellers`: 90-day top sellers by revenue, profit, and ROI, with ASIN,
  title, units sold, revenue, net profit, ROI, average profit per unit, and
  source period.
- `growth_summary`: recent monthly revenue, profit, inventory spend, ending
  inventory/business value, units sold, ROI, and average profit per unit where
  source data is available.
- `sourcing_summary`: replenishment/research queue count, estimated value,
  total profit opportunity, average estimated profit, average ROI, max-buy
  total, and timestamps.
- `financial_readiness`: missing COGS units/value, missing fees, pending fees,
  missing fulfillment-cost count, stale source count, source freshness summary,
  blocking issues, and warning issues.

## Current Limitations

- eBay seller revenue is currently `0` because MBOP does not yet own eBay
  seller-order ingestion.
- Software/tool expenses are `null` because ZFI should own expense
  classification.
- Owner draws, contributions, taxes, YNAB budgeting, and household context are
  intentionally absent from MBOP payloads.
- Net profit is based on complete Amazon profitability rows. Missing COGS,
  missing fees, refunded, and cancelled rows are surfaced in alerts/confidence
  notes rather than silently blended into complete-profit totals.
- Some replacement fields intentionally remain `null` with warnings until MBOP
  has a backend-owned source. Examples include unrecoverable return fees and
  listing-health dollar value. YNAB-owned deposit matching now belongs in ZFI.

## Operator Checklist

1. Add `ZFI_SUPABASE_URL` and `ZFI_SUPABASE_SERVICE_ROLE_KEY` to the server-side
   environment only.
2. Run a dry run and review the printed JSON.
3. Run `--apply` manually.
4. Confirm the row appears in ZFI Supabase.
5. Let ZFI build finance views from the ZFI-owned table.
