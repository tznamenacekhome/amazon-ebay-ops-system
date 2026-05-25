# CURRENT_STATE.md

Last Updated: 2026-05-24

# Midnight Blue Operations Platform (MBOP)

MBOP is the internal operations platform for Midnight Blue Enterprises, LLC.

# System Status Overview

| Subsystem | Status |
|---|---|
| eBay ingestion | Mature |
| RevSeller enrichment | Functional but evolving |
| Purchases UI | Operational and componentized |
| Receiving workflow | First slice implemented |
| Shipment enrichment | Functional with remaining FedEx/webhook follow-up |
| Sync orchestration | Mature |
| Dashboard analytics | First slice implemented |
| Matching engine | Emerging subsystem |
| Export pipeline | Planned |
| Legacy spreadsheet backfill | Recently used / repeatable script available |

---

# Current Backend State

## eBay Buyer Purchase Sync

Status: STABLE

Implemented:
- Trading API GetOrders
- pagination
- tracking extraction
- eBay item/listing URL derivation from transaction ItemID
- delivery extraction
- landed cost calculations
- net-cost handling for foreign-currency purchases when eBay provides USD payment totals
- single-item partial refund cost adjustment from eBay payment/refund totals
- shipment linking
- inbound shipment linking
- import batching
- timezone normalization
- duplicate prevention
- buyer-purchase-only ingestion via Trading API OrderRole=Buyer

Current optimization:
SKIP_EXISTING_ORDERS_WITH_TRACKING = True

Known inefficiency:
Still fetches 90 days every sync.

Recent cleanup:
- removed 50 eBay seller orders that had been written to purchases by the legacy Sell Fulfillment sync
- disabled the legacy seller-order sync write path so seller orders are not inserted into purchases

---

## EasyPost Shipment Enrichment

Status: FUNCTIONAL / WEBHOOK-READY

Implemented:
- EasyPost SDK dependency added to requirements.txt
- shipment sync reuses stored easypost_tracker_id values
- carrier is passed to EasyPost when known
- invalid tracking placeholders are skipped
- EasyPost calls are capped at 5 requests per second
- 429 responses retry with exponential backoff
- current EasyPost SDK tracker fields are read defensively
- delivered date falls back to delivered tracking events when needed
- EasyPost webhook route exists at /api/easypost/webhook
- webhook route validates EasyPost HMAC headers before updating Supabase
- purchases API falls back to eBay EstimatedDeliveryTimeMax when no carrier ETA exists
- missing stored eBay ETA values were backfilled into inbound_shipments for 2026-05-01+ purchases

Recent backfill:
- purchases from 2026-05-01 to current were synced
- 101 candidate shipment rows inspected
- 97 shipment rows successfully processed
- 87 trackers created
- 10 trackers reused
- 2 invalid untracked placeholder rows skipped
- 2 FedEx rows remain unresolved due to EasyPost credential errors
- 88 missing shipment ETA values were restored from stored eBay estimates

Remaining setup:
- deploy the app to a public HTTPS server
- configure EASYPOST_WEBHOOK_SECRET
- register the EasyPost webhook URL in EasyPost
- resolve or intentionally bypass FedEx tracking credential errors

---

## RevSeller Integration

Status: PARTIAL

Implemented:
- Google Sheets API integration
- ASIN enrichment
- matched Amazon/RevSeller title storage in purchase_items.amazon_title
- target price enrichment
- diagnostics
- ambiguity handling
- system-aware matching
- shared backend system detection
- strict title+system RevSeller matching with a unique compact same-system fallback
- manual UI ASIN/price corrections propagate to matching purchase items
- manual match memory is supported through manual_item_matches once the SQL migration is applied
- reusable marketplace title cleaner before RevSeller normalized matching
- legacy Purchases sheet backfill script can fill missing ASINs and target sell prices by eBay order number
- manual eBay title and purchase-price overrides are supported with sync-preservation flags
- manual split purchase item rows are supported for multi-game eBay listings

Current result:
~760 successful matches

Recent legacy sheet backfill:
- source: Google Sheet "ebay purchases", Purchases tab
- script: integrations/backfill_purchase_items_from_purchase_sheet.py
- matched by eBay order number, with title/system disambiguation for multi-row orders
- filled 340 missing ASINs
- filled 2,141 missing target sell prices
- remaining after backfill: 37 missing ASINs, 62 missing target sell prices
- unresolved rows were left untouched when order matches were ambiguous or absent

---

# Current Frontend State

## App Shell

Status: OPERATIONAL

Implemented:
- compact shared left-side navigation
- Dashboard, Purchases, and Receiving menu items
- active mode highlighting
- content remains dense and table-focused
- implementation lives in web/app/AppShell.tsx

---

## Dashboard UI

Status: FIRST SLICE IMPLEMENTED

Implemented:
- dashboard workspace at /dashboard
- dashboard API route at /api/dashboard/purchases
- monthly purchase units and total cost view grouped by year/month
- pivot-style table inspired by the legacy Excel purchase summary
- horizontal monthly cost chart for quick outlier/completeness scanning
- dashboard excludes Return Opened rows
- dashboard excludes Cancelled rows
- dashboard excludes purchase items marked exclude_from_purchase_reporting once the reporting-exclusion SQL migration is applied
- dashboard aggregation uses vw_purchases_dashboard.unit_cost multiplied by quantity
- frontend only renders API-provided aggregates and does not recalculate landed cost

Current purpose:
Help identify purchase data completeness and cost accuracy by comparing MBOP monthly totals to the legacy spreadsheet pivot.

Recent reconciliation:
- 2024 and 2025 dashboard totals match the legacy Excel pivot exactly
- 2026 variances are primarily returns/cancellations and split-row quantity/cost differences between MBOP and the legacy spreadsheet
- zero-cost NBA 2K22 historical rows from order 16-14113-30387 were excluded from reporting after confirming corrected received quantities elsewhere
- personal purchase and business supply reporting exclusions were identified for migration-backed cleanup
- eBay purchases after 2026-05-15 that were absent from both legacy spreadsheet Purchases and Returns tabs were excluded from reporting: 13 item rows across 12 orders
- no strict after-2026-05-15 MBOP-only rows were found on the legacy Returns tab during that reconciliation
- legacy Returns-tab matches were normalized for 2026: 26 rows to Return Opened and 13 rows to Cancelled
- one-time cleanup corrected duplicate rows, split-row quantities, partial-return quantities, one returned/refunded spreadsheet-missing order, one single-item partial refund, and three CAD purchase costs
- active dashboard total now matches the legacy pivot unit count: 4,806 units
- active dashboard cost is $84,840.36 versus the legacy pivot $84,836.31, leaving a $4.05 MBOP-over-spreadsheet variance attributed to known spreadsheet mistakes

---

## Purchases UI

Status: OPERATIONAL / COMPONENTIZED

Implemented:
- purchases workspace in Next.js / React
- API-route-only data access
- purchase table extraction
- detail drawer extraction
- editable price cell extraction
- filter bar extraction
- metric extraction
- usePurchases hook for loading, save status, errors, and API mutations
- usePurchaseFilters hook for filter state and filtered rows
- purchaseStats helper for dashboard metrics
- local documentation in web/app/purchases/README.md
- dense table layout pass
- matched Amazon title display with eBay title subtitle
- simplified ASIN column links
- status filter uses derived operational status
- ETA column uses carrier estimated delivery when available, otherwise eBay estimated delivery, and delivered date when delivered
- date formatting treats shipment dates as date-only to avoid UTC/local timezone shifts
- detail drawer status matches the table's derived operational status
- detail drawer carrier status shows carrier/shipment fields only
- detail drawer shows "--" for Amazon Title when ASIN is missing
- detail drawer saves eBay title, purchase price, ASIN, and sell price together
- detail drawer can create a manual split item row for multi-game eBay listings
- search input includes an inline clear button
- table headers sort the currently filtered row set by displayed values
- status filter includes Received for warehouse-verified delivered items

Current architecture:
web/app/page.tsx is now the composition layer.

Primary remaining UI opportunity:
iterate on ASIN review and operational throughput without merging receiving workflow concerns.

Recent backend update:
- eBay buyer purchase sync now populates purchase_items.system from recognized eBay title platform terms
- eBay buyer purchase sync preserves workflow-owned statuses: Cancelled, Received, Return Opened, and Return Pending
- existing empty systems were backfilled where recognized
- RevSeller enrichment no longer applies unique-title matches without a recognized system
- system names were normalized to operator-facing display values
- purchase_items.amazon_title was added and backfilled from RevSeller where ASIN/title data was available
- Amazon search links and RevSeller matching now share marketplace-title cleaning semantics
- marketplace-title cleaning was refined from the 100-row missing-ASIN training sheet

Manual override schema:
- sql/2026-05-23_add_purchase_item_manual_overrides.sql adds purchase item flags for manual title overrides, manual unit-cost overrides, and manual split child rows
- eBay buyer purchase sync preserves manual title/unit-cost overrides and skips manual split child rows during fallback matching

---

## Receiving UI

Status: FIRST SLICE IMPLEMENTED

Implemented:
- separate receiving workspace at /receiving
- local documentation in web/app/receiving/README.md
- receiving API route at /api/receiving
- scan-first search field with autofocus
- queue includes Delivered and Shipped (No Tracking) operational statuses
- single search result auto-opens the receiving detail view
- multiple search results remain filtered for manual row selection
- receiving queue table columns are sortable
- detail view shows all rows for the same tracking number, or same purchase when tracking is unavailable
- detail view links eBay title to the eBay listing when a supplier listing URL or eBay item ID is available
- detail view links Amazon title to Amazon using ASIN
- Amazon title display appends an operator-facing system suffix when the stored title omits the system
- per-item quantity received input
- per-item return checkbox
- per-item marketplace pick list, defaulting to Amazon
- per-item ASIN and sell price inputs
- Received button is disabled until Amazon-bound received items have ASIN and sell price
- save marks items Received or Return Pending
- partial received quantity splits remaining quantity into a new no-tracking purchase item
- marketplace is saved only on received items
- received_date is saved on received purchase items using the local receiving date

API behavior:
- /api/receiving hydrates purchase item metadata from purchase_items in chunks to avoid large PostgREST `in (...)` request failures
- receiving rows include amazon_title, supplier_sku, supplier_listing_url, ebay_listing_url, marketplace, and received_date where available
- /api/receiving enforces ASIN and sell price before marking Amazon marketplace items Received
- eBay marketplace items can be received without Amazon title, ASIN, or sell price
- Cancelled is a purchase-item workflow status and is reserved for cancellation/refund follow-up, not receiving verification

Schema:
- sql/2026-05-23_add_receiving_fields.sql adds nullable purchase_items.marketplace with Amazon/eBay allowed values and nullable purchase_items.received_date for received-date reporting

Pending:
- decide image source for eBay listing images
