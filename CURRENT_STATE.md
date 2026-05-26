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
| Amazon SP-API foundation | Read-only inventory/listing sync working |
| Keepa catalog intelligence | Foundation implemented / small write verified |
| Unified inventory state / reconciliation | First slice implemented |
| Amazon FBA workflow | First slice implemented |
| Aged Amazon Inventory Repricing Advisor | First slice implemented |
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

## Sync Orchestration

Status: LOCAL SCHEDULER CONFIGURED

Implemented:
- `run_all_syncs.py` runs eBay buyer purchase sync, EasyPost shipment sync, eBay supplier returns sync, and RevSeller enrichment
- `run_all_syncs.bat` targets the repo at `C:\Dev\amazon-ebay-ops-system`
- scheduler output is appended to `logs/scheduler.log`
- local AM/PM Windows scheduled tasks were recreated after the repo moved out of OneDrive

Recent validation:
- direct batch execution completed successfully with exit code 0
- eBay buyer purchase sync retrieved 646 orders and updated 27
- EasyPost sync processed/reused 97 shipment trackers with 2 FedEx credential errors remaining
- eBay supplier returns sync updated 7 returns
- RevSeller sync completed and wrote diagnostics

Remaining validation:
- confirm both Windows scheduled tasks append successful runs to `logs/scheduler.log`
- manually trigger scheduled tasks with the root task path, for example `schtasks /Run /TN "\Amazon eBay Ops Sync PM"`

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

Latest scheduler validation:
- `run_all_syncs.py` now includes EasyPost shipment sync after eBay buyer purchase sync
- latest direct scheduler run inspected 101 candidate shipment rows, reused 97 trackers, skipped 2 invalid placeholder rows, and still hit the 2 FedEx credential errors
- direct batch execution completed with exit code 0 and wrote to `logs/scheduler.log`

Remaining setup:
- deploy the app to a public HTTPS server
- configure EASYPOST_WEBHOOK_SECRET
- register the EasyPost webhook URL in EasyPost
- resolve or intentionally bypass FedEx tracking credential errors
- confirm both local Windows AM/PM scheduled tasks append successful runs after the repo move to `C:\Dev`

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

## Amazon SP-API Foundation

Status: READ-ONLY INVENTORY, LISTING, AND PLANNING SYNC WORKING

Implemented:
- `integrations/amazon_spapi_client.py`
- `integrations/amazon_test_connection.py`
- `integrations/amazon_sync_fba_inventory.py`
- `integrations/amazon_sync_listing_status.py`
- `integrations/amazon_sync_inventory_planning.py`
- Login with Amazon refresh-token exchange
- LWA-only SP-API request support for the post-Oct-2023 auth model
- optional legacy AWS SigV4 signing only when `AMAZON_SP_API_USE_SIGV4=true`
- read-only allow-list for FBA inventory, Listings Items, and Product Pricing paths
- paginated FBA inventory summary sync
- read-only Listings Items status/issue sync for active Amazon inventory
- read-only Reports API sync for `GET_FBA_INVENTORY_PLANNING_DATA`
- Amazon SKU upsert into `amazon_skus`
- point-in-time inventory snapshot inserts into `amazon_fba_inventory_snapshots`
- point-in-time listing snapshot inserts into `amazon_listing_snapshots`
- point-in-time inventory planning snapshot inserts into `amazon_inventory_planning_snapshots`
- latest listing snapshot view in `vw_latest_amazon_listing_snapshot`
- latest inventory planning snapshot view in `vw_latest_amazon_inventory_planning_snapshot`
- safe logging that avoids printing secrets or restricted data
- fail-safe behavior for rejected auth or rejected resource calls
- no restricted-data-token flow
- no Amazon Orders, buyer, address, or PII endpoints

Schema:
- `sql/2026-05-25_add_amazon_spapi_foundation.sql`
- `sql/2026-05-25_add_amazon_listing_snapshots.sql`
- `sql/2026-05-25_add_amazon_inventory_planning_snapshots.sql`
- `amazon_skus`
- `amazon_fba_inventory_snapshots`
- `amazon_listing_snapshots`
- `amazon_report_runs`
- `amazon_inventory_planning_snapshots`

Current validation:
- local syntax checks pass
- auth-only smoke test succeeded after credential correction
- inventory summary smoke test can run without AWS IAM credentials
- dry run fetched 50 summaries from the first page and normalized 50 SKU/snapshot rows
- limited write upserted 50 SKU rows and inserted 50 snapshot rows
- full sync fetched 6,292 FBA inventory summaries, upserted 6,292 SKU rows, and inserted 6,292 inventory snapshot rows
- active listing-status sync selected 297 current Amazon SKUs, inserted 297 listing snapshots, updated 297 Amazon SKU rows, and had 0 fetch failures
- latest active listing snapshot set contains 49 rows with Amazon listing issues
- inventory planning dry run and write run each parsed 297 Amazon planning rows
- latest inventory planning write inserted 297 planning snapshot rows, showing 735 available units and 273 units in Amazon's 91+ day age buckets

Boundary:
Amazon seller/FBA data must stay in Amazon-specific tables and must not write to `purchases` or `purchase_items`.

---

## Keepa Catalog Intelligence

Status: FOUNDATION IMPLEMENTED / TOKEN-AWARE

Purpose:
Use Keepa read-only product data to support price-history review, sales-rank history, sales-frequency signals, and future ASIN validation.

Implemented:
- `sql/2026-05-25_add_keepa_product_snapshots.sql`
- `keepa_product_snapshots`
- `keepa_product_history_points`
- `vw_latest_keepa_product_snapshot`
- `integrations/keepa_client.py`
- `integrations/keepa_sync_products.py`

Current behavior:
- Keepa API key is read from `KEEPA_API_KEY`
- `KEEPA_DOMAIN_ID` defaults to `1` for Amazon US
- product sync defaults to dry-run mode
- `--plan-only` counts selected ASINs and Keepa token status without calling the product endpoint
- ASIN source defaults to canonical inventory: current Amazon FBA inventory plus MBOP purchase inventory before Listed
- raw Keepa product payload is preserved on `keepa_product_snapshots`
- normalized summary fields include current/average price signals, sales rank, sales-rank drops, offer count, review count, and rating
- normalized history points are optional via `--write-history`; raw history remains stored even when normalized points are not inserted

Latest validation:
- syntax checks passed for Keepa client and sync scripts
- dry run selected 5 ASINs, returned 5 products, parsed 1,868 potential history points, had 0 failures, and spent 10 Keepa tokens
- small write inserted 5 Keepa product snapshots and 0 history rows
- plan-only mode selected 409 canonical ASINs with 285 Keepa tokens available, so a broad sync was intentionally not run yet

Boundary:
Keepa is catalog intelligence only. It must not write to purchases, purchase_items, receiving, FBA shipment workflow tables, or Amazon seller workflow tables.

---

## Aged Amazon Inventory Repricing Advisor

Status: FIRST SLICE IMPLEMENTED

Purpose:
Identify active Amazon FBA inventory that has aged long enough to need manual repricing, liquidation, removal, or more data before the operator makes an Informed.co/Seller Central decision.

Implemented:
- `/api/amazon/repricing-advisor`
- `/repricing`
- shared navigation entry named Repricing
- backend-owned recommendation tiers and thresholds
- dense operational table with tier, ASIN/SKU, title, quantity, age, cost, capital, current/list price, Keepa Buy Box, Keepa 90-day average, sales-rank signal, listing issue, recommendation, and reason
- filters for tier, age bucket, missing data, issue-only, and Keepa coverage

Backend inputs:
- latest Amazon FBA inventory snapshots
- `amazon_skus`
- latest Amazon listing snapshots/issues
- latest Amazon FBA Inventory Planning snapshots
- InventoryLab active inventory backfill
- `inventory_positions`
- latest Keepa product snapshots

Current recommendation rules:
- Amazon FBA Inventory Planning age buckets are the preferred active-Amazon age source
- InventoryLab/MBOP date context is fallback only when Amazon planning data is missing
- Healthy: fallback age under 60 days with required data and no major issue
- Watch: Amazon 0-90 day bucket, or fallback 60-89 days old
- Reprice: Amazon 91-180 day bucket, or fallback 90-179 days old
- Liquidate: Amazon 181+ day bucket, or fallback 180+ days old
- Remove / eBay: unsellable quantity, Amazon listing issue, or non-buyable listing status
- Needs Data: missing ASIN, cost basis, age/date context, pricing context, or Keepa snapshot

Latest validation:
- Next.js production build passed
- Amazon inventory planning report dry run parsed 297 rows and 735 available units
- Amazon inventory planning report write inserted 297 planning snapshot rows
- API route returned 297 active Amazon SKU rows and 761 units with planning age buckets where available
- estimated capital tied up: $13,597.34
- aged capital over 90 days: $5,265.19
- aged capital over 180 days: $1,881.41
- tier counts: 57 Remove / eBay, 1 Liquidate, 3 Reprice, 236 Needs Data
- `/repricing` rendered successfully with HTTP 200

Boundary:
This is not an automated repricer. It does not write prices to Amazon, does not call Amazon write endpoints, does not modify Informed.co, and does not write to purchases, purchase_items, receiving, or FBA shipment workflow tables.

---

## Unified Inventory State And Reconciliation

Status: FIRST SLICE IMPLEMENTED

Purpose:
Provide a normalized, derived inventory-position layer that can answer:
- what MBOP believes is owned
- where the inventory physically is
- what marketplace it is intended for
- what Amazon FBA currently reports
- what needs operator review before inventory confidence is high

Implemented:
- `sql/2026-05-25_add_inventory_state_reconciliation.sql`
- `inventory_positions`
- `inventory_movements`
- `inventory_reconciliation_events`
- `inventory_reconciliation_event_items`
- `vw_inventory_position_summary`
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_amazon_listing_snapshot`
- `vw_open_inventory_reconciliation_items`
- `integrations/inventory_reconcile.py`
- `sql/2026-05-25_add_inventorylab_legacy_active_inventory.sql`
- `integrations/inventorylab_active_inventory_backfill.py`
- dashboard Inventory Visibility section backed by inventory summary/reconciliation views

Current behavior:
- workflow tables remain authoritative
- the reconciliation script rebuilds derived current inventory positions from purchases, purchase_items, FBA shipment rows, and latest Amazon FBA snapshots
- state is modeled across separate dimensions: inventory state, physical location, marketplace intent, listing channel, operational status, and condition/disposition
- Amazon FBA snapshot inventory is projected into Amazon-specific inventory positions
- Amazon listing-status snapshots are consumed as reconciliation findings only, not as additional inventory units
- InventoryLab historical active-inventory backfill can provide legacy cost/date context for current Amazon FBA inventory
- canonical current inventory is defined as current Amazon FBA inventory plus MBOP purchase inventory that has not yet reached the Listed workflow state
- Amazon-bound purchase inventory with `current_status = listed` is treated as historical/sold-through in the derived purchase projection; current Amazon FBA inventory is represented by Amazon SP-API snapshot positions instead
- reconciliation currently compares MBOP Amazon-intended inventory to latest Amazon FBA inventory at ASIN level and surfaces Amazon listing issue/suppression signals
- old open reconciliation findings are deferred when a new reconciliation run writes current findings

Latest validation:
- InventoryLab active inventory import read 951 rows, skipped 653 inactive rows, matched 298 active rows by MSKU, found 0 ambiguous rows, and upserted 298 legacy backfill records
- inventory reconciliation loaded 298 InventoryLab cost/date overlay rows
- latest write run projected 2,923 MBOP positions, 311 Amazon positions, and 377 open findings after adding Amazon listing-status issue findings
- latest reconciliation includes 55 Amazon stranded/suppressed listing findings from the read-only Listings Items snapshots
- 310 Amazon inventory positions currently carry InventoryLab legacy cost/date context
- Next.js production build passed after dashboard API/UI updates

Boundary:
This layer is derived and additive. It does not replace purchases, receiving, FBA shipment preparation, Amazon SP-API snapshot ownership, or workflow-owned cost updates on purchase_items.

Product identity:
ASIN is MBOP's primary Amazon inventory identity. MSKU/Seller SKU remains stored for Amazon traceability and InventoryLab row matching, but MBOP is not currently building a separate SKU-to-purchase mapping workflow.

First-pass limitation:
Amazon reconciliation is intentionally noisy while MBOP separates current Amazon inventory from historical purchase/listing records. Findings are meant to drive inventory confidence work, not imply all mismatches are defects.

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

Status: OPERATIONAL FIRST PASS / INVENTORY VISIBILITY ADDED

Implemented:
- dashboard workspace at /dashboard
- dashboard API route at /api/dashboard/purchases
- monthly purchase units and total cost view grouped by year/month
- operational unit count by purchase item status
- pivot-style table inspired by the legacy Excel purchase summary
- horizontal monthly cost chart for quick outlier/completeness scanning
- purchase completeness summary for active rows
- receiving backlog summary for Delivered and Shipped (No Tracking) rows
- shipment prep backlog summary for Received Amazon-bound FBA candidates
- workflow aging buckets for receiving and FBA prep
- operational attention table for past-ETA, stale/no-tracking, exception, return-pending, and missing-data rows
- Inventory Visibility section backed by the normalized inventory-position and reconciliation layer
- inventory metrics for owned/in-flow units, Amazon-ready units, Amazon sellable/inbound/reserved/unsellable units, eBay-assigned units, reconciliation findings, and MBOP cost basis
- open reconciliation finding table showing issue type, ASIN/SKU, title, MBOP quantity, and Amazon quantity
- dashboard excludes Return Opened rows
- dashboard excludes Cancelled rows
- dashboard excludes purchase items marked exclude_from_purchase_reporting once the reporting-exclusion SQL migration is applied
- dashboard aggregation uses vw_purchases_dashboard.unit_cost multiplied by quantity
- frontend only renders API-provided aggregates and does not recalculate landed cost

Current purpose:
Help identify purchase data completeness, receiving backlog, shipment prep backlog, workflow aging, and exception/missing-data visibility from one operational screen.

Recent reconciliation:
- 2024 and 2025 dashboard totals match the legacy Excel pivot exactly
- 2026 variances are primarily returns/cancellations and split-row quantity/cost differences between MBOP and the legacy spreadsheet
- zero-cost NBA 2K22 historical rows from order 16-14113-30387 were excluded from reporting after confirming corrected received quantities elsewhere
- personal purchase and business supply reporting exclusions were identified for migration-backed cleanup
- eBay purchases after 2026-05-15 are MBOP-canonical because the legacy spreadsheet was no longer maintained for new purchases
- a prior exclusion of 13 post-2026-05-15 MBOP-only resale rows was reversed
- no strict after-2026-05-15 MBOP-only rows were found on the legacy Returns tab during that reconciliation
- legacy Returns-tab matches were normalized for 2026: 26 rows to Return Opened and 13 rows to Cancelled
- one-time cleanup corrected duplicate rows, split-row quantities, partial-return quantities, one returned/refunded spreadsheet-missing order, one single-item partial refund, and three CAD purchase costs
- active dashboard total now matches the legacy pivot unit count: 4,806 units
- active dashboard cost is $84,840.36 versus the legacy pivot $84,836.31, leaving a $4.05 MBOP-over-spreadsheet variance attributed to known spreadsheet mistakes

Current reconciliation boundary:
The legacy spreadsheet is useful for historical data before 2026-05-16. For purchases on or after 2026-05-16, MBOP is the canonical purchase source.

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
