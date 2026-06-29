# ZFI Integration

Last updated: 2026-06-29

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
business value trend reporting, and Schedule C placeholders should be treated
as transitional until ZFI replaces them.

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
- `business-value-finalizer`
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
- does not disable MBOP YNAB
- does not remove or mutate MBOP `business_value_snapshots`
- sets `source_system = 'mbop'`
- sets `source_type = 'migrated_mbop_history'`
- preserves original MBOP `snapshot_date`
- preserves component values such as Amazon inventory, pre-Amazon inventory,
  Amazon cash, Amazon cash in transit, YNAB cash on hand, and total business
  value
- maps MBOP inventory components into ZFI `inventory_value`
- maps MBOP YNAB cash-on-hand into ZFI `business_cash`
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
  `business_finance_replacement_v2`
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
  Amazon-to-bank in-transit cash, deferred/reserved cash, temporary MBOP YNAB
  Business cash during the parallel period, available business cash, payout
  status summary, source timestamps, freshness, and warnings.
- `payout_reconciliation`: in-transit payout amount, completed payouts matched
  or not matched to YNAB, latest payout/deposit dates where MBOP has them,
  reconciliation status, and explicit warnings for values MBOP does not safely
  model yet.
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
  has a backend-owned source. Examples include unrecoverable return fees,
  listing-health dollar value, and YNAB Amazon deposits without matched payout.

## Operator Checklist

1. Add `ZFI_SUPABASE_URL` and `ZFI_SUPABASE_SERVICE_ROLE_KEY` to the server-side
   environment only.
2. Run a dry run and review the printed JSON.
3. Run `--apply` manually.
4. Confirm the row appears in ZFI Supabase.
5. Let ZFI build finance views from the ZFI-owned table.
