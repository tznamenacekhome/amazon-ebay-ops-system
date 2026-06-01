# CURRENT_STATE.md

Last Updated: 2026-05-31

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
| Keepa catalog intelligence | Token-aware enrichment working |
| Informed Repricer intelligence | Read-only report snapshot import working |
| Unified inventory state / reconciliation | First slice implemented |
| Amazon FBA workflow | First slice implemented |
| Aged Amazon Inventory Repricing Advisor | First slice implemented |
| Amazon Sales Orders | First slice implemented / backfill in progress |
| Non-eBay purchase COGS sources | Manual import bridge implemented |
| Legacy spreadsheet backfill | Recently used / repeatable script available |

---

# Supabase Capacity

Status: PAID PLAN / IO GUARDRAILS DOCUMENTED

Current plan limits are documented in `docs/supabase_capacity.md`, including 8 GB included disk size per project, 250 GB egress, 250 GB cached egress, 100 GB file storage, 7-day backups, and 7-day log retention.

Important operating note:
The paid plan limits do not by themselves guarantee enough sustained disk IO for MBOP. Disk IO Budget exhaustion caused Supabase API/Table Editor connection failures on 2026-05-28. Before broad syncs, large backfills, or snapshot-heavy changes, check Database Health and warn the operator if Disk IO Budget is materially consumed or database size approaches the 8 GB included disk limit.

---

# Current Backend State

## Amazon Sales Orders

Status: FIRST SLICE IMPLEMENTED / 2025-FORWARD DATA SET

Implemented:
- Amazon sales order and order-item tables remain separate from `purchases` and `purchase_items`
- Amazon order sync imports non-PII order headers and item detail from SP-API Orders
- Amazon finance sync stores normalized financial events for fee and fulfillment-cost calculation
- Veeqo label sync stores Merchant Fulfilled shipment/label cost where Veeqo has a matching order
- `amazon_sales_profitability` stores backend-calculated revenue, fees, fulfillment cost, COGS, net profit, ROI, and data status
- Sales Orders UI at `/sales-orders` displays backend/API-provided values only
- Sales Orders refresh runs the scheduled-style sales sync on demand without historical backfill
- Sales Orders splits stored `missing_fees` rows for display: unfulfilled orders show `Pending`, while shipped/fulfilled orders show `Missing Fees`
- Sales Orders API and sync/backfill scripts enforce a 2025-01-01 operating cutoff
- pre-2025 Amazon sales orders imported by recent Amazon LastUpdated activity are excluded from the UI/API and have cleanup SQL in `sql/2026-05-31_remove_pre_2025_amazon_sales_orders.sql`

Backfill:
- 2026 Amazon sales history backfill completed through May except the current-day edge chunk rejected by Amazon's CreatedBefore freshness rule
- `integrations/backfill_amazon_sales_history.py` now caps through-today backfill chunks at a safe retrieval cutoff
- 2025 Amazon sales history backfill is running from `logs/amazon_sales_backfill_2025_state.json`

COGS state:
- InventoryLab import/backfill is now treated as a completed legacy bridge
- non-eBay purchase COGS source imports have been loaded for TIM/prep-center and Merchant Fulfilled supplier sheets
- active Merchant Fulfilled inventory layers support `merchant_available` and `merchant_allocated`
- most current missing Amazon sales COGS rows already have matching costed eBay purchase data by ASIN
- next required COGS step is an eBay purchase FIFO allocator that consumes `purchase_items` into `amazon_sales_cogs_consumption` after the 2025 sales backfill finishes

Manual review export:
- latest missing COGS review export: `exports/missing_amazon_cogs_review.csv`
- current pattern before 2025 backfill completion: most missing rows are `purchase_data_available_needs_fifo`, with a small exception set for purchase quantity short or no purchase ASIN match

---

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

Status: LOCAL SCHEDULER CONFIGURED / BROAD INTEGRATION AUTOMATION ENABLED

Implemented:
- `run_all_syncs.py` runs eBay buyer purchase sync, EasyPost shipment sync, eBay supplier returns sync, RevSeller enrichment, Amazon FBA inventory, Amazon listing status, Amazon inventory planning, Amazon Finance, Informed Repricer reports, YNAB Business cash balance, guarded Keepa enrichment, and the daily business value snapshot
- `run_all_syncs.bat` targets the repo at `C:\Dev\amazon-ebay-ops-system`
- scheduler output is appended to `logs/scheduler.log`
- local AM/PM Windows scheduled tasks were recreated after the repo moved out of OneDrive
- individual script failures are collected and reported without preventing later independent syncs from running
- scheduled Keepa enrichment is capped to 10 stale active-Amazon ASINs, uses stock/offers without history, and skips calls unless at least 100 Keepa tokens are available

Recent validation:
- direct all-sync execution completed successfully with exit code 0 after adding Amazon FBA inventory throttling safeguards
- eBay buyer purchase sync retrieved 652 orders and updated 31
- EasyPost sync processed/reused 103 shipment trackers with 2 FedEx credential errors remaining
- eBay supplier returns sync updated 7 returns
- RevSeller sync completed and wrote diagnostics
- Amazon FBA inventory sync fetched 6,292 summaries, upserted 6,292 SKUs, and inserted 6,292 snapshots
- Amazon listing-status sync inserted 296 active listing snapshots
- Amazon inventory planning sync inserted 295 planning rows
- Amazon Finance sync inserted a balance snapshot
- Informed report sync inserted 968 listing snapshots
- YNAB Business balance sync inserted a $3,231.24 snapshot
- scheduled Keepa run selected 1 stale active-Amazon ASIN, inserted 1 snapshot, and spent 5 tokens
- business value snapshot upserted the 2026-05-27 daily value

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
- leading condition-noise title variant fallback for same-system RevSeller matching, such as `New Hitman 3` -> `Hitman 3`
- trailing condition-noise title variant fallback, such as `... Xbox One new` -> the catalog title without `new`
- catalog connector fallback for RevSeller titles ending in `for`, such as `ARK Ultimate Survivor Edition for PlayStation 4`
- token-set same-system fallback for reordered catalog titles, such as `Rock Band the Beatles` -> `The Beatles: Rock Band`
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
- FBA inventory pagination delay plus retry/backoff for Amazon 429/5xx responses
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
- active listing-status sync selected 296 current Amazon SKUs, inserted 296 listing snapshots, updated 296 Amazon SKU rows, and had 0 fetch failures
- latest active listing snapshot set contains 49 rows with Amazon listing issues
- inventory planning dry run/write validation has parsed the Amazon planning report successfully
- latest all-sync inventory planning write inserted 295 planning snapshot rows
- Amazon FBA inventory snapshots now normalize reserved customer order, FC transfer, FC processing, future supply, researching, and unfulfillable damage/defect breakdowns from raw SP-API inventory details
- a follow-up full FBA inventory sync initially hit Amazon SP-API 429 QuotaExceeded; after adding retry/backoff and page pacing, the sync fetched 6,292 summaries, upserted 6,292 SKUs, and inserted 6,292 fresh inventory snapshots

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
- `--missing-only` excludes ASINs that already have a Keepa product snapshot
- `--stale-days` limits scheduled refreshes to ASINs without snapshots or with snapshots older than the configured age, ordered missing/oldest first
- `--min-tokens` skips product calls safely when available Keepa tokens are below the configured floor
- ASIN source defaults to canonical inventory: current Amazon FBA inventory plus MBOP purchase inventory before Listed
- raw Keepa product payload is preserved on `keepa_product_snapshots`
- normalized summary fields include current/average price signals, sales rank, sales-rank drops, offer count, review count, and rating
- normalized history points are optional via `--write-history`; raw history remains stored even when normalized points are not inserted

Latest validation:
- syntax checks passed for Keepa client and sync scripts
- dry run selected 5 ASINs, returned 5 products, parsed 1,868 potential history points, had 0 failures, and spent 10 Keepa tokens
- small write inserted 5 Keepa product snapshots and 0 history rows
- plan-only mode selected 409 canonical ASINs with 285 Keepa tokens available, so a broad sync was intentionally not run yet
- follow-up missing-only writes inserted 303 additional Keepa snapshots with 0 failures and no normalized history rows
- scheduled stale-refresh mode now keeps active-Amazon Keepa snapshots fresh without broad token-spending runs
- scheduled active-Amazon Keepa run currently uses `--limit 10 --batch-size 10 --stale-days 7 --min-tokens 100 --offers 20 --stock --no-history --write`
- latest scheduled Keepa write selected 1 stale active-Amazon ASIN, inserted 1 snapshot, and spent 5 tokens

Boundary:
Keepa is catalog intelligence only. It must not write to purchases, purchase_items, receiving, FBA shipment workflow tables, or Amazon seller workflow tables.

---

## Informed Repricer Intelligence

Status: READ-ONLY REPORT SNAPSHOT IMPORT WORKING

Purpose:
Use Informed Repricer report data to make the Aged Amazon Inventory Repricing Advisor more specific about manual repricer floor/rule review.

Implemented:
- `sql/2026-05-26_add_informed_repricing_snapshots.sql`
- `integrations/informed_repricing_client.py`
- `integrations/informed_sync_reports.py`
- `informed_report_runs`
- `informed_listing_snapshots`
- `informed_rule_snapshots`
- `vw_latest_informed_listing_snapshot`
- `vw_latest_informed_rule_snapshot`

Current behavior:
- `INFORMED_REPRICER_API_KEY` is read from `.env`
- the integration uses the read-only Informed Reports API only
- plan-only mode lists recent report requests and prints known MBOP report-type guidance
- report request/status/download flow is supported
- signed report download URLs are redacted before storing run metadata
- CSV/TSV/TXT and ZIP-contained report files are parsed defensively
- raw report rows are preserved on snapshot rows
- no Listings Management API feed/upload endpoint is called

Latest validation:
- official docs confirmed Reports API request/status/download behavior, that Reports API supersedes Export API, and that Listings Management API is the write/upload path
- plan-only discovery returned 0 recent report requests and made no report request
- `All_Fields_NextGen` dry run parsed 969 rows with 0 parse errors
- latest write mode inserted 968 Informed listing snapshots
- the Informed report provided SKU/MSKU values but no ASIN-shaped values, so advisor joins use seller SKU where ASIN is unavailable
- repricing advisor API now returns Informed rule, current price, min/max price, Buy Box price/status, repricing-enabled flag, price-gap calculations, and an Informed note where snapshots are available
- Informed rule IDs are mapped to operator-friendly names through `informed_rule_name_overrides` because the listing report exports strategy IDs but not display names

Boundary:
Informed is advisory repricer intelligence only. It must not modify Informed rules, min/max prices, managed status, Amazon prices, purchases, purchase_items, Amazon snapshots, Keepa snapshots, receiving rows, or FBA workflow rows.

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
- backend-owned advisor buckets that separate pricing work, inventory/listing exceptions, and missing data
- backend-owned target price recommendations for aged pricing rows
- dense operational table with tier, ASIN/SKU, title, quantity, age, cost, capital, current/list price, Keepa Buy Box, Keepa 90-day average, sales-rank signal, listing issue, recommendation, and reason
- competition drawer on each row showing stored Keepa offer-level competitor detail when available
- filters for tier, advisor bucket, age bucket, missing data, issue-only, and Keepa coverage

Backend inputs:
- latest Amazon FBA inventory snapshots
- `amazon_skus`
- latest Amazon listing snapshots/issues
- latest Amazon FBA Inventory Planning snapshots
- InventoryLab active inventory backfill
- `inventory_positions`
- latest Keepa product snapshots
- latest stored Keepa raw offer payload, when snapshots were captured with offer-level data
- latest Informed Repricer listing snapshots
- manual Informed rule-name overrides

Current recommendation rules:
- Amazon FBA Inventory Planning age buckets are the preferred active-Amazon age source
- InventoryLab/MBOP date context is fallback only when Amazon planning data is missing
- Healthy: fallback age under 60 days with required data and no major issue
- Watch: currently filtered out of the action list unless a row has an actionable issue
- Reprice: Amazon 91-180 day bucket, or fallback 90-179 days old
- Liquidate: Amazon 181+ day bucket, or fallback 180+ days old
- Remove / eBay: unsellable quantity or non-buyable/suppressed listing status
- Needs Data: missing ASIN, cost basis, age/date context, pricing context, Keepa snapshot, or Informed snapshot
- advisor bucket `Pricing`: aged sellable inventory without listing/condition exceptions
- advisor bucket `Inventory / Listing Issue`: unsellable or suppressed/non-buyable inventory where price changes alone may not help
- buyable/discoverable listings with Amazon catalog metadata issues are ignored because there is no operator action unless the listing becomes suppressed or inventory becomes unsellable.
- advisor bucket `Missing Data`: rows missing required repricing context
- Reprice target price uses 3% below Buy Box/reference, with a cost + 10% floor
- Liquidate target price uses 8% below Buy Box/reference, with a cost + 10% floor
- target markdowns are adjusted by Informed current-velocity where available: stronger recent sales get gentler markdowns, no recent sales get firmer markdowns
- sales velocity is classified from Informed `current-velocity` as the temporary 30-day sales source; Amazon planning shipped-unit fields remain stored but are not trusted for the operator's actual sales velocity
- rows with any Informed sales in the last 30 days are excluded from the aged inventory action list even when Amazon planning age is over 90 days
- Informed notes flag stale inventory where current price is above Buy Box, min price appears above Buy Box, repricing is disabled, or a rule assignment is missing
- Informed column displays the friendly rule name when an override exists and keeps the numeric rule ID as secondary traceability
- rows under 90 days old are excluded from the action list unless they have an actionable issue
- normal inbound/FC-transfer movement is displayed as inventory detail, but is not treated as an operator-action issue by itself
- competition drawer summarizes FBA/MFN offer counts, observed stock, lowest FBA/MFN price, Buy Box seller, and per-offer seller/fulfillment/price/stock signals from the stored Keepa payload
- competition drawer uses Keepa `liveOffersOrder` when present so it shows currently live offers, filters offers to the same condition as the operator's listing when condition is known, keeps the Buy Box row first, and sorts the remaining offers by landed price from low to high
- Keepa offerCSV rows are parsed as latest time/price/shipping triples so MFN landed price includes both item price and shipping
- competition drawer identifies the operator's Amazon seller ID, labels that row as You, highlights it, and can add an MBOP-derived own-offer row if Keepa does not return the operator's live offer
- Keepa sync supports a selective `--stock` flag that requests offer stock detail; when Keepa returns live `stockCSV`, the drawer uses the latest value for competitor stock
- Informed reports provide the operator's own stock quantity but do not expose competitor stock counts in the imported report
- repricing advisor rows can be snoozed for 30 days via `amazon_repricing_advisor_snoozes`; the page defaults to Not Snoozed, can show All, and splits visible stats between active and snoozed buckets
- if stored Keepa data only has summary fields, the drawer shows that offer-level data is missing and recommends targeted Keepa offer sync for that ASIN

Latest validation:
- Next.js production build passed
- Amazon inventory planning report write inserted 295 planning snapshot rows in the latest all-sync run
- Informed `All_Fields_NextGen` report imported 968 listing snapshot rows in the latest all-sync run and joins to advisor rows by seller SKU
- Amazon planning shipped-unit fields are stored for reference, but Informed `current-velocity` is currently used as the operator-facing 30-day sales signal
- action-list counts and capital totals are live API output because snoozes, Informed velocity, and Keepa refreshes can change the visible queue
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
- `sql/2026-05-26_add_inventorylab_inventory_valuation_snapshots.sql`
- `integrations/inventorylab_inventory_valuation_import.py`
- dashboard Inventory Visibility section backed by inventory summary/reconciliation views

Current behavior:
- workflow tables remain authoritative
- the reconciliation script rebuilds derived current inventory positions from purchases, purchase_items, FBA shipment rows, and latest Amazon FBA snapshots
- state is modeled across separate dimensions: inventory state, physical location, marketplace intent, listing channel, operational status, and condition/disposition
- Amazon FBA snapshot inventory is projected into Amazon-specific inventory positions
- Amazon listing-status snapshots are consumed as reconciliation findings only, not as additional inventory units
- InventoryLab historical active-inventory backfill can provide legacy cost/date context for current Amazon FBA inventory
- InventoryLab inventory valuation snapshots provide the legacy opening-balance valuation for current Amazon FBA inventory
- canonical current inventory is defined as current Amazon FBA inventory plus MBOP purchase inventory that has not yet reached the Listed workflow state, plus current non-historical FBA shipment links on the way to Amazon
- Amazon-bound purchase inventory with `current_status = listed` and no current FBA shipment link is treated as historical/sold-through in the derived purchase projection; current FBA shipment links are projected as `outbound_to_amazon`
- dashboard Amazon FBA value prefers the latest InventoryLab valuation snapshot when available, while MBOP remains authoritative for received, ordered, and outbound inventory
- business value snapshots use MBOP outbound shipment cost for saved FBA shipments and avoid double-counting overlapping Amazon inbound rows for the same ASINs
- reconciliation currently compares MBOP Amazon-intended inventory to latest Amazon FBA inventory at ASIN level and surfaces Amazon listing issue/suppression signals
- old open reconciliation findings are deferred when a new reconciliation run writes current findings

Latest validation:
- InventoryLab active inventory import read 951 rows, skipped 653 inactive rows, matched 298 active rows by MSKU, found 0 ambiguous rows, and upserted 298 legacy backfill records
- InventoryLab valuation import read 297 rows, found 0 missing MSKUs, 0 missing total values, 0 duplicate MSKUs, and upserted a $13,453.87 / 761-unit legacy Amazon FBA opening-balance valuation
- inventory reconciliation loaded 298 InventoryLab cost/date overlay rows
- latest write run projected 2,943 MBOP positions, 451 Amazon positions, and 392 open findings after adding current FBA shipment outbound projection
- current Amazon shipment `FBA19F8YW7CV` projects 216 linked shipment rows, 277 units, and $5,634.77 as `outbound_to_amazon`
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
- Dashboard, Purchases, Receiving, Amazon FBA, Repricing, and Reconciliation menu items
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
- pivot-style table inspired by the legacy Excel purchase summary
- horizontal monthly cost chart for quick outlier/completeness scanning
- purchase completeness summary for active rows
- receiving backlog summary for Delivered and Shipped (No Tracking) rows
- shipment prep backlog summary for Received Amazon-bound FBA candidates
- workflow aging buckets for receiving and FBA prep
- order problem counts for past-ETA, stale/no-tracking, and exception/return-pending rows
- Inventory Visibility section backed by the normalized inventory-position and reconciliation layer
- dashboard now places Inventory Visibility first and removes the old top Total Units / Total Cost / Months row
- inventory metrics focus on Canonical Units, Amazon FBA Sellable, and MBOP Cost Basis
- Inventory Value By Location table with units and total cost for At Amazon FBA, On the way to Amazon FBA, Received, Ordered and not received yet, and Total
- business inventory/cash value summary showing Amazon/current inbound inventory value, pre-Amazon purchased inventory value, Amazon cash, Amazon-to-bank in-transit cash, YNAB cash-on-hand from the Business category snapshot, and total business value
- open reconciliation findings moved off the main dashboard to `/inventory-reconciliation`
- `/inventory-reconciliation` explains finding source and operator follow-up patterns for MBOP/Amazon quantity, stranded, suppressed, unsellable, and mapping issues
- dashboard excludes Return Opened rows
- dashboard excludes Cancelled rows
- dashboard excludes purchase items marked exclude_from_purchase_reporting once the reporting-exclusion SQL migration is applied
- dashboard aggregation uses vw_purchases_dashboard.unit_cost multiplied by quantity
- frontend only renders API-provided aggregates and does not recalculate landed cost
- `integrations/ynab_sync_cash_balance.py` stores the read-only YNAB Business category balance in `ynab_category_balance_snapshots`
- latest YNAB Business category snapshot currently reports $3,231.24 as cash on hand
- `integrations/amazon_sync_finance_balances.py` stores read-only Amazon Finance cash snapshots in `amazon_finance_balance_snapshots`
- latest Amazon Finance snapshot reports $2,979.69 Amazon cash, $2,232.84 Amazon-to-bank in-transit cash, $2,631.96 deferred/reserved cash, and $347.73 API open/available balance
- `integrations/business_value_snapshot.py` stores one backend-computed business value snapshot per day in `business_value_snapshots`
- latest business value snapshot for 2026-05-30 reports $28,627.77 total business value, including $5,980.36 of Amazon outbound/on-way value
- clicking the Total row in the Business Inventory And Cash Value dashboard panel opens a modal with a business value history graph
- Purchases workspace now has separate tabs for the normal editable purchases table and an Order Problems table
- Purchases `Missing Data` filter keeps ASIN/sell-price/system/Amazon-title cleanup in the normal editable view
- Purchases Order Problems tab shows past-ETA, stale/no-tracking, carrier exception, and return-pending rows with issue/age-focused columns

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
- detail drawer can mark an item Return Pending for return/refund follow-up
- detail drawer can create a manual split item row for multi-game eBay listings
- search input includes an inline clear button
- table headers use server-side sorting through /api/purchases
- status filter includes Received and Listed workflow statuses
- Missing Data includes missing ASIN, invalid ASIN placeholder, missing sell price, missing system, or missing Amazon title for rows with an ASIN
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
- RevSeller enrichment now safely handles leading `New` as condition text only as a same-system fallback, which corrected order `20-14670-25041` to ASIN `B08MG5FYS6`
- RevSeller enrichment now handles unique same-system token-set matches, which corrected order `20-14670-25040` to ASIN `B001TOQ8LG`
- RevSeller enrichment now handles trailing condition `new`, publisher noise, common `survior` typo correction, and safe trailing `for` catalog variants, which corrected orders `20-14670-25046` and `20-14670-25045`

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
- search supports order number, tracking number, scanned carrier barcode payloads, and title text
- queue includes Delivered and Shipped (No Tracking) operational statuses
- single search result auto-opens the receiving detail view
- multiple search results remain filtered for manual row selection
- receiving queue table columns are sortable
- receiving queue displays the count of items ready to receive, and matching count while searching
- detail view shows all rows for the same tracking number, or same purchase when tracking is unavailable
- detail view links eBay title to the eBay listing when a supplier listing URL or eBay item ID is available
- detail view links Amazon title to Amazon using ASIN
- Amazon title display appends an operator-facing system suffix when the stored title omits the system
- detail view shows system/platform near the title and supports Enter to receive plus Escape to close without receiving
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
- CSV export labels the target sell price column as List Price
- shipment input is labeled Amazon Shipment ID and uses an Amazon shipment ID example placeholder
- detail expansion shows supplier order ID, Amazon title, ASIN, received quantity, quantity to send, and unit cost for underlying purchase items
- quantity-to-send supports excluding a specific unit from an FBA shipment
- saving with a shipment ID links included items to fba_shipments/fba_shipment_items and moves included quantities to Listed
- saved current shipment links are projected as outbound-to-Amazon inventory value
- partial included quantities split the remaining quantity into a Received split child row
- same-ASIN Amazon title fallback fills FBA display titles when a Received row has ASIN but blank amazon_title
- rows with no stored Amazon title display an explicit Missing Amazon title indicator instead of silently using the eBay title

Schema:
- sql/2026-05-24_add_fba_shipments.sql adds fba_shipments and fba_shipment_items
- historical Listed items should be linked to legacy_listed_no_shipment_id when no real shipment ID will be backfilled
