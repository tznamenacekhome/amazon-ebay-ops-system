# Merchant-fulfilled customer returns

`/mf-returns` is the MF Open Returns log and return receiving mode. It is separate
from supplier returns, FBA Return Recovery, purchase receiving and Amazon refund
execution. The server-only `/api/mf-returns` uses existing Cognito/ALB and mutation
CSRF checks. Python uses existing Amazon LWA, EasyPost, ECS, Supabase capacity
guard and scheduler telemetry; no new service, bucket or event infrastructure.

## Sources and limits

Official sources reviewed November 8, 2026:

- [Seller-fulfilled Returns Reports](https://developer-docs.amazon/sp-api/docs/report-type-values-returns):
  `GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE`, at most 60 days per request,
  order-item IDs, RMA, quantities, tracking, reported delivery, quoted label cost,
  reported refunded amount and SAFE-T information when provided. It excludes FBA
  returns and returnless refunds. Inventory and Order Tracking / applicable
  restricted role access must be present in the seller authorization.
- [Reports processing](https://developer-docs.amazon/sp-api/docs/verify-that-report-processing-is-complete):
  request, poll and download; DONE, CANCELLED and FATAL are distinct.
  CANCELLED can mean no data or another cancellation reason. MBOP preserves it
  as unconfirmed coverage, never silently treats it as a successful empty log.
- [Finances Transactions](https://developer-docs.amazon/sp-api/reference/listtransactions):
  omit marketplaceId for US MFN, retain filters with nextToken, support empty
  pages, windows less than 180 days, allow financial posting delay (including
  the documented possible 48-hour gap). Returned marketplace and independently
  verified merchant fulfillment/account determine admission.
- [Official finance model](https://github.com/amzn/selling-partner-api-models/blob/main/models/finances-api-model/finances_2024-06-19.json).
- [Seller-fulfilled reimbursement policy](https://sellercentral.amazon.com/help/hub/reference/external/202175000)
  and [Amazon's US filing-window announcement](https://sellercentral.amazon.com/seller-forums/discussions/t/d95b0e44-60fc-4c16-b690-3626c9a3c43c):
  eligibility depends on the specific program, refund, carrier history and
  exception. The announced US SAFE-T change is not a universal deadline for all
  claims. MBOP defaults to **Needs review**. Only operator-reviewed deadlines
  with a recorded source are stored; no claims or refunds are submitted.

The `mf-returns` group refreshes report windows overlapping the latest 58–59
days, includes today, and revisits older outstanding request-date windows (six
windows / 500 outstanding records maximum, otherwise a visible review error).
Reports have persistent IDs, window dates, processing status and generation
times; pending reports resume on the next refresh. Every report window stays
under 60 days; longer requested ranges split with a one-day overlap. Finances
paginate up to 50 pages with a two-second delay and overlap the same recent
period. This is bounded discovery, not a full historical backfill. Older refund
postings retain their records; an old return request is revisited while open.

The job runs in existing `amazon-sales-recent` schedules and on manual refresh.
A serialized 90-minute worker lease tolerates process failure, with 80-minute
job timeout. Normalized returns reject older generated-report observations.
Source report rows have stable order/RMA/item keys and compact replay evidence.
Repeated package rows do not multiply expected item quantity. Conflicting
per-package quantities are flagged and require review; they are not summed.
No request/debit, receipt or inspection date is inferred from another event.
Date-only report values retain their original text in source_dates / delivery
raw; normalized local midnight is an indexing boundary, not a known scan time.

EasyPost monitors at most 50 outstanding packages / 10 new trackers per run,
reusing tracker IDs with <=4 calls/sec. First actual transit/dispatch scan and
delivery remain carrier-sourced; pre-transit label creation is not a first scan.
Amazon-reported delivery remains separately preserved. Errors show per package
and in synchronization history. Large queues require follow-up refreshes; this
does not provision new carrier webhooks. Required variables are existing Amazon
credentials/seller/marketplace, Supabase server credentials and EASYPOST_API_KEY.

## Independent financial and physical state

A return request adds no stock and proves no seller debit. Report refund totals
are observations, not posted ledger events. Transactions API IDs are the sole
canonical financial source in this workflow; legacy finance rows and report
totals are never added to them. Released/deferred-release lifecycle counterpart
IDs are reconciled, so the same economic transaction is shown once. Deferred
records remain visible but are not treated as posted refunds. No financial
operation can restock inventory.

Financial `ORDER_ID` references are not sufficient proof of a customer order:
Amazon also returned `FBA19W1MLF5L` on a shipment-related adjustment. The worker
requires the documented customer 3-7-7 ID format before any Orders lookup or MF
financial admission. Non-customer references are counted in run statistics and
excluded from this MF workflow; genuine customer-order read errors still fail
visibly. Return reports still require independently verified MF orders.

Net refund amounts are explicitly **order-level signed net**, including fees,
and must not be summed across repeated return-item rows. Item IDs and adjustment
IDs remain distinct. An unmatched adjustment is flagged for item review rather
than spread across products. Refunds without a matched return have explicit
refund-only exception rows; merchant-confirmed returnless classification clears
the unreceived follow-up flag while retaining all financial records. Amazon
report omissions cannot prove a refund is returnless.

Quoted label costs remain separate from actual posted components. When a label
charge, reimbursement or item-refund component is identifiable in financial
evidence, the operator can classify it against the actual transaction with its
signed amount and source/component reference. This annotation is marked
merchant-entered and never creates another cash entry. Unidentified charges
remain unknown, not zero. Amazon-provided SAFE-T IDs/state/amounts stay separate
from manually tracked cases and actual posted reimbursement evidence.

## Receiving, inspection and stock lineage

The existing receiving barcode normalizer supplies carrier-format candidates;
raw scan is preserved. Every match requires an explicit package choice. RMA and
order lookup can associate an expected return with an unmatched package. Multiple
matches are presented together; no automatic first-match selection. Unmatched
packages are retained as exceptions, with actual receipt date and notes.
One package can link several return items; one item can span several packages.

Receiving records only the package. Inspection requires a product identifier
scan, explicit quantity, condition, disposition, inspection date and notes;
optional missing-parts detail and HTTPS photo/document evidence links are retained.
Evidence is linked rather than copied into database byte columns. This phase
does not create a new photo-upload storage service; linked originals must remain
accessible. Merchant-entered authorization/carrier/refund dates are separate,
annotated records and do not overwrite provider timestamps.

Only **saleable** inspections create MF stock. Held, damaged, wrong and missing
findings never create available stock. Inspection holds appear independently in
MF Inventory's physical on-hand / held totals; resolving a hold appends a new
inspection and retains the superseded finding. The same held quantity cannot be
released twice. Holds are included in opening-balance overlap protection.

Account locks serialize receipts, inspections, orders and openings. Stable
request UUIDs return the same committed result on retry and reject changed
payloads. Quantity caps apply to expected returns and total shipped customer
order-item quantity across all RMAs. The client blocks concurrent saves and
resets inspection inputs after success; scanning alone never adds units.

Saleable restock follows actual shipment allocations in FIFO order, preserving
unit acquisition costs, parent lot, original listing and purchase/receipt lineage.
Returned lots use a new physical stock-start timestamp, so old shipment events
cannot consume them again. Repeated resale/return cycles retain parent lineage.
Historical shipped units without original allocations require explicit unknown
cost acknowledgment; no purchase is fabricated. Missing/ambiguous customer item
identity blocks saleable disposition until explicit exact-order reconciliation.
Original purchase rows and completed listing batches remain unchanged.

## Claims and delivery

Manual claim records store type, external case ID, submission/next follow-up/
resolution dates, claimed/reimbursed amounts, status, notes and optional sourced
deadline. They link through the return to customer order/items, finances,
packages, inspections and evidence. Amazon claim state remains source-owned.
Open/refunded/unreceived, carrier-delivered/unreceived, partial, held,
wrong/damaged/missing and unresolved claim filters are server-side/paginated.

Migration: `20261108193013_mbop_mf_returns.sql` (MBOP public objects only).
Every new table has RLS and only service-role grants; views use invoker security
and mutation functions revoke PUBLIC/anon/authenticated execution. Apply through
the documented linked CLI after full shared-ledger reconciliation and verified
project identity, then deploy existing web and scheduler Dockerfiles through
ECR/ECS. No Amazon External Fulfillment APIs are used.

Focused validation:

```powershell
.venv/Scripts/python.exe tests/test_mf_returns.py
.venv/Scripts/python.exe tests/test_mf_inventory_orders.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_mf_returns.py
node web/app/receiving/trackingScan.test.mjs
node web/app/fba/listingBatchApi.test.mjs
node web/app/fba/inventoryLabExport.test.mjs
cd web
npx.cmd tsc --noEmit
npx.cmd eslint app/mf-returns app/api/mf-returns/route.ts app/api/mf/route.ts
npm.cmd run build
```

Database tests use disposable PostgreSQL with no exposed port, not production
fixtures. Production verification must use the AWS deployment/status/browser
workflow; local build alone is not deployment proof.
