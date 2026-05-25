# CURRENT_STATE.md

Last Updated: 2026-05-25

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
| Amazon FBA workflow | First slice implemented |
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

Recent ASIN validation:
- script: integrations/validate_asins_against_purchase_sheet.py
- compares MBOP active purchase item ASIN quantities to the reference spreadsheet Purchases tab by eBay order number
- cleanup script: integrations/apply_sheet_asin_validation_fixes.py
- latest cleanup applied 31 spreadsheet-authoritative ASIN corrections
- latest validation scanned 2,879 spreadsheet rows and compared 2,825 orders
- 2,825 orders matched exactly by ASIN and quantity
- latest clean report: data/asin_validation_20260524_201926.csv

---

# Current Frontend State

## App Shell

Status: OPERATIONAL

Implemented:
- compact shared left-side navigation
- Dashboard, Purchases, Receiving, and Amazon FBA menu items
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
- operational unit count by purchase item status
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
- local documentation in web/app/purchases/README.md
- dense table layout pass
- matched Amazon title display with eBay title subtitle
- simplified ASIN column links
- status filter uses stored backend-owned purchase_items.current_status
- ETA column uses carrier estimated delivery when available, otherwise eBay estimated delivery, and delivered date when delivered
- date formatting treats shipment dates as date-only to avoid UTC/local timezone shifts
- detail drawer status matches the table's stored operational status
- detail drawer carrier status shows carrier/shipment fields only
- detail drawer shows "--" for Amazon Title when ASIN is missing
- detail drawer saves eBay title, Amazon title, purchase price, system, ASIN, and sell price together
- detail drawer can edit system from the canonical system pick list
- detail drawer can create a manual split item row for multi-game eBay listings
- search input includes an inline clear button
- table headers use server-side sorting through /api/purchases
- status filter includes Received and Listed workflow statuses
- Needs Review now includes missing ASIN, invalid ASIN placeholder, missing sell price, missing system, or missing Amazon title for rows with an ASIN
- purchases API uses server-side filtering, sorting, and paging from vw_purchases_dashboard
- purchases API filters directly on backend-normalized purchase_items.current_status
- purchases list payload is lean; detail-only metadata is hydrated only for returned page rows
- purchases and receiving APIs hide purchase items marked exclude_from_purchase_reporting
- purchases API excludes reporting-excluded rows before database pagination so pages are full usable pages
- purchases client also filters reportable-excluded rows before storing fetched or cached rows
- default purchases status filter is All Except Listed, with All Status available for full history
- purchases UI browser caching is temporarily disabled for server-side performance testing
- purchases cache key was bumped after reporting-exclusion fixes so stale non-resale rows are not reused
- purchases cache key was bumped again after backend status normalization so stale derived-status filter results are not reused
- purchases Refresh now clears all purchases query-cache entries before reloading

Current architecture:
web/app/page.tsx is now the composition layer.
/api/purchases owns list filtering, sorting, pagination, and summary counts.

Primary remaining UI opportunity:
iterate on ASIN review and operational throughput without merging receiving workflow concerns.

Recent backend update:
- eBay buyer purchase sync now populates purchase_items.system from recognized eBay title platform terms
- eBay buyer purchase sync preserves workflow-owned statuses: Cancelled, Listed, Received, Return Opened, and Return Pending
- eBay buyer purchase sync writes canonical non-locked statuses such as No Tracking, Shipped (No Tracking), Awaiting Carrier Scan, and Delivered
- EasyPost sync/webhook updates linked purchase_items.current_status from carrier state while preserving workflow-locked statuses
- one-time backend status backfill normalized 83 purchase item statuses from older ordered/in-transit/delivered placeholders
- existing empty systems were backfilled where recognized
- RevSeller enrichment no longer applies unique-title matches without a recognized system
- system names were normalized to operator-facing display values
- purchase_items.amazon_title was added and backfilled from RevSeller where ASIN/title data was available
- Amazon search links and RevSeller matching now share marketplace-title cleaning semantics
- marketplace-title cleaning was refined from the 100-row missing-ASIN training sheet

Recent one-time status backfill:
- source: reference Google Sheet "status" tab
- script: integrations/backfill_status_from_reference_sheet.py
- explicit sheet statuses were applied to purchase_items.current_status
- Listed rows were backfilled to `listed`
- Received rows were backfilled to `received`
- blank sheet statuses were skipped and left as their existing MBOP operational statuses
- one mixed-status quantity row was split so one unit could be Listed and one Received

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
- receiving API applies the ready-to-receive status filter before returning rows
- scan-first search field with autofocus
- queue includes Delivered and Shipped (No Tracking) operational statuses
- single search result auto-opens the receiving detail view
- multiple search results remain filtered for manual row selection
- receiving queue table columns are sortable
- receiving queue displays the count of items ready to receive, and matching count while searching
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

---

## Amazon FBA UI

Status: FIRST SLICE IMPLEMENTED

Implemented:
- separate Amazon FBA workspace at /fba
- FBA API route at /api/fba-shipments
- received Amazon-bound purchase items are grouped into one row per ASIN
- grouped rows show ASIN, Amazon title, system, weighted cost per unit, sell price, quantity, oldest purchase date, and supplier
- rows are sorted by system and Amazon title
- shipment stats show ASIN count, total units, total cost, and selected cost
- CSV export uses the currently selected quantities for InventoryLab import
- detail expansion shows supplier order ID, Amazon title, ASIN, received quantity, quantity to send, and unit cost for underlying purchase items
- quantity-to-send supports excluding a specific unit from an FBA shipment
- saving with a shipment ID links included items to fba_shipments/fba_shipment_items and moves included quantities to Listed
- partial included quantities split the remaining quantity into a Received split child row
- same-ASIN Amazon title fallback fills FBA display titles when a Received row has ASIN but blank amazon_title
- rows with no stored Amazon title display an explicit Missing Amazon title indicator instead of silently using the eBay title

Schema:
- sql/2026-05-24_add_fba_shipments.sql adds fba_shipments and fba_shipment_items
- historical Listed items should be linked to legacy_listed_no_shipment_id when no real shipment ID will be backfilled
