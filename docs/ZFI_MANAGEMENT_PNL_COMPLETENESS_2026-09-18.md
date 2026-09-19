# ZFI Current-Month Management P&L Completeness Audit

Audit cutoff: September 18, 2026, inclusive, in `America/Los_Angeles`.
Production source snapshot: `2026-09-19T03:48:48.114003Z`.

This audit explains the null current-month management fields in the deployed
`business_finance_replacement_v3` payload. It used read-only production queries
and dry runs against the MBOP Supabase project. No source rows, historical COGS,
purchases, scheduler cadence, or ZFI rows were changed.

## Result

The deployed publisher included pending Amazon orders in the management cohort.
Those rows have no recognized revenue or fees yet and incorrectly nullified
otherwise complete independent fields. The profitability calculator could also
sum both legacy Finance API fees and stale Transactions API fallback rows for the
same sale, include refund fee credits as sale expense, and count multiple
Transactions lifecycle states.

The local fix:

- limits management sale facts to shipped, non-replacement rows while retaining
  shipped rows later classified as refunded;
- evaluates revenue, COGS, marketplace fees, FBA fulfillment, and MFN labels
  independently, so one category's gap does not erase another category;
- prefers legacy sale-fee events when present, otherwise uses Shipment
  transaction events at one lifecycle state per shipment;
- excludes refund fee credits from sale-cohort marketplace-fee expense;
- preserves authoritative refund nulls and diagnostic observed refunds.

No migration is required. Deployment, recalculation, and a fresh ZFI push remain
separate production actions.

## Production population

The September 1-18 purchase-date cohort contained 161 orders, 164 profitability
rows, and 150 units:

| Amazon status | Rows | Units | Relevant finding |
| --- | ---: | ---: | --- |
| Shipped | 125 | 130 | Economically recognized management cohort |
| Pending | 20 | 20 | All 20 lack revenue and fees; excluded by the fix |
| Canceled | 19 | 0 | Already non-economic and excluded |
| Replacement | 0 | 0 | None in this cohort; explicitly excluded by the fix |

All shipped rows have sale prices. Shipped gross sales total **$5,506.59**.
The deployed null revenue was therefore a population-selection defect, not a
missing shipped-revenue source.

### COGS

Of the 125 shipped rows, 51 rows / 53 units have acquisition COGS totaling
**$791.86**; all use the InventoryLab legacy source. The other 74 rows / 77 units
are missing acquisition COGS.

A controlled dry-run review found 65 eBay rows and 6 non-eBay rows that appear
allocatable. Three rows / 6 units remain short or unmatched: one eBay unit with
insufficient quantity, four non-eBay units with insufficient quantity, and one
MFN unit with no matching source. The FIFO allocation utilities are controlled
backfills and are not scheduler jobs. They were not applied during this audit.
Consequently `cogs` and `gross_profit` correctly remain null.

### Marketplace fees and FBA fulfillment

Every shipped AFN row has applicable fee evidence, but 41 rows contain both
legacy Finance API events and Transactions fallback events. The prior calculator
summed both sources. It could also include Refund events and more than one status
for a transaction shipment.

Stored profitability totals at the audit snapshot were **$1,424.32** marketplace
fees and **$708.51** FBA fulfillment. Applying the corrected selection logic to
the same source events yields **$1,056.08** marketplace fees and **$533.84** FBA
fulfillment. Those corrected totals require a bounded profitability recalculation
before publication. Marketplace fees continue to exclude FBA fulfillment.

### Shipping labels

The shipped cohort has one MFN order / one unit. It has no stored verified USD
Veeqo shipment-label record and no sufficiently identified Amazon carrier-label
adjustment. A targeted live Veeqo dry run did not return conclusive output, so
the database absence is not treated as proof of a free label. Current-month
`shipping_label_costs` therefore remains null. An FBA-only period still reports
a legitimate numeric zero.

### Refunds

The period has 26 stored `RefundEventList` rows across five orders and five
order-plus-posted-date occurrences. Supported observed components produce
`refunds_returns_observed = 103.25`.

This remains diagnostic. The finance importer is order-scoped instead of a
certified posted-period ledger, and the legacy deterministic event identifier
omits `posted_date`, so repeated equal refunds can collide. Transactions refund
rows also contain lifecycle states rather than a unique posted ledger. Therefore
`refunds_returns = null` and `net_profit = null` remain required, with explicit
warnings. No refund semantics were changed.

## Field dependency matrix

| Field | Included shipped facts | Conditions that make it null |
| --- | --- | --- |
| `gross_sales` / `revenue` | Stored sale prices for shipped, non-replacement rows | Any included row lacks sale price |
| `cogs` | Acquisition cost only | Any included row lacks acquisition COGS |
| `marketplace_fees` | Sale-cohort Amazon fees excluding fulfillment | Any included shipped row lacks applicable fee evidence |
| `fulfillment_costs` | AFN `amazon_fba_fee` values | An included AFN row lacks an unambiguous FBA fee source, or channel is unknown |
| `shipping_label_costs` | Verified USD Veeqo costs for included MFN orders | An included MFN order lacks a verified label, or channel is unknown |
| `refunds_returns` | Certified posted-period contra-revenue | Refund ledger coverage is not certified |
| `gross_profit` | Gross sales minus acquisition COGS | Revenue or COGS is null |
| `net_profit` | Full management equation | Refunds or any required cost field is null |

Pending, canceled, and replacement rows do not block shipped facts. A refunded
shipped row remains in sale revenue, acquisition COGS, sale fees, and fulfillment;
refund authority is handled only by the refund fields.

## Before and expected after recalculation

The deployed row at `2026-09-18T14:18:10.960144Z` reported 145 units and null
management revenue and costs. Production source data changed after that row, so
the values below are an audit of the later exact snapshot rather than a
like-for-like replay.

| Field | Local fixed publisher on stored profitability | After bounded profitability recalculation |
| --- | ---: | ---: |
| Units sold | 130 | 130 |
| Gross sales / revenue | $5,506.59 | $5,506.59 |
| COGS | null | null until controlled allocation and shortage review |
| Marketplace fees | $1,424.32 stored but not publishable as corrected | $1,056.08 |
| FBA fulfillment | $708.51 stored but not publishable as corrected | $533.84 |
| Shipping labels | null | null until verified label evidence exists |
| Refunds | null | null |
| Refunds observed | $103.25 diagnostic | $103.25 diagnostic |
| Gross profit | null | null |
| Net profit | null | null |

The payload still uses original Amazon order `purchase_date` as its cohort date.
That is not a true shipment-posting ledger: current-period legacy shipment events
cover only part of the purchase cohort, while Transactions rows have deferred and
released lifecycle duplicates and include sales purchased before September. A
date-basis change is deferred until MBOP has a certified shipment fact and a
complete posted-period rule.

## Production continuation

After deploying the scheduler image containing this change, perform a bounded
September refresh and profitability recalculation, then push a fresh summary:

```powershell
.\.venv\Scripts\python.exe integrations\amazon_sync_sales_finances.py --purchase-date-start 2026-09-01T00:00:00Z --purchase-date-end 2026-09-19T00:00:00Z --order-finance-delay-seconds 1.5 --apply
.\.venv\Scripts\python.exe integrations\amazon_sales_profitability.py --purchase-date-start 2026-09-01T00:00:00Z --purchase-date-end 2026-09-19T00:00:00Z --apply
.\.venv\Scripts\python.exe integrations\push_zfi_business_summary.py --start-date 2026-09-01 --end-date 2026-09-18 --generated-by zfi-pnl-completeness --apply
```

First repeat the Supabase capacity preflight and capture bounded source counts.
Afterward verify the new ZFI row and compare bounded source counts/hashes. Do not
run FIFO allocators as part of this continuation. Do not change scheduler cadence.

Local diagnostic CSVs were produced under ignored `exports/` for the 20 pending
revenue rows, 74 shipped missing-COGS rows, 41 dual fee-source rows, and one
missing-label row. They intentionally are not committed because they contain
order-level operational data.
