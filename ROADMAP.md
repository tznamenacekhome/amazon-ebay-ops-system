# ROADMAP.md

# Midnight Blue Operations Platform

This roadmap tracks MBOP, the internal operations platform for Midnight Blue Enterprises, LLC.

---

# High Priority

## Amazon Sales COGS Allocation

Status:
Implemented / cleanup remaining exceptions.

Context:
- Sales Orders now has Amazon order, finance, Veeqo label, profitability, and UI
  foundations in place.
- Non-eBay COGS source rows and inventory layers have been imported for the TIM
  prep-center sheet and Merchant Fulfilled supplier sheet.
- InventoryLab imports are now considered completed legacy bridge data rather
  than the go-forward purchase-cost source.
- Missing COGS review shows most missing Amazon sales COGS rows already have
  matching costed eBay purchase data by ASIN.

Next work:
- continue filling missing purchase-source data for the remaining Amazon
  `missing_cogs` rows
- rerun the eBay and non-eBay FIFO allocators after purchase-source fixes
- rerun `exports/missing_amazon_cogs_review.csv` and the Inventory Source
  Balance Audit after each meaningful correction batch
- manually review remaining no-match, source-after-sale, or quantity-short
  exceptions
- preserve separate consumption rows per source purchase item and avoid
  over-consuming source quantity across sales and current inventory

---

## Frontend Componentization

Status:
Completed initial architecture pass.

Completed:
- split page.tsx
- reduce truncation risk
- improve maintainability
- improve AI-generated diff quality
- moved purchases list filtering, sorting, pagination, and counts to /api/purchases
- added query-aware purchases browser cache support, currently disabled for performance testing
- split lean list rows from page-scoped detail metadata hydration

Created:
- PurchasesTable.tsx
- PurchaseDetailDrawer.tsx
- EditablePriceCell.tsx
- PurchaseFilters.tsx
- PurchaseMetrics.tsx
- usePurchases.ts
- web/app/purchases/README.md

Next frontend focus:
- iterate on ASIN review workflow
- improve dense operational scanning
- preserve purchases/receiving separation
- keep page.tsx as composition layer
- consider TanStack Table later only if the table needs richer keyboard/column behaviors after server-driven data is stable

Recent UI cleanup:
- removed redundant ASIN review text from unmatched rows
- removed external-link icons from text links
- tightened purchases table spacing
- consolidated ETA/delivered date display into one color-coded column
- fixed shipment date display to avoid UTC/local timezone day shifts
- added sortable purchases table headers
- added combined eBay title, Amazon title, purchase price, system, ASIN, and sell price save in the detail drawer
- added system correction pick list in the purchase detail drawer
- added manual split item creation from the detail drawer
- added search-box clear button
- replaced full-table client filtering/sorting with server-side query handling
- defaulted purchases to all statuses except Listed while still allowing All Status history
- added shared per-screen `Last updated` indicators near refresh controls,
  backed by `/api/screen-data-freshness`
- added a Receiving refresh button to match the other MBOP screens

---

## Dashboard Analytics

Status:
Operational reconciliation first pass implemented.

Completed:
- added Dashboard menu item to the MBOP left navigation
- added /dashboard workspace
- added /api/dashboard/purchases aggregation route
- added monthly units and total cost chart
- added year/month pivot-style table with grand total
- added purchase completeness summary
- added receiving backlog summary
- added shipment prep backlog summary
- added workflow aging buckets
- added missing/exception attention table
- excluded Return Opened rows from dashboard totals
- added migration-backed reporting exclusions for personal purchases and business supplies
- recognized 2026-05-16+ purchases as MBOP-canonical because the legacy spreadsheet was no longer maintained for new purchases
- restored 13 post-2026-05-15 resale rows that had been excluded only because they were absent from the legacy spreadsheet
- normalized 2026 MBOP-active rows found on the reference Returns tab to Return Opened or Cancelled
- excluded Cancelled rows from dashboard purchase totals
- reconciled active unit count to the legacy pivot at 4,806 units
- reduced active cost variance to $4.05 MBOP-over-spreadsheet after one-time cleanup and net-cost corrections
- kept landed-cost math backend-owned through vw_purchases_dashboard.unit_cost
- confirmed 2024 and 2025 dashboard totals match the legacy Excel pivot exactly
- added Inventory Visibility as the first dashboard section
- added Inventory Value By Location table for At Amazon FBA, On the way to Amazon FBA, Received, Ordered and not received yet, and Total
- added Business Inventory And Cash Value summary with Amazon inventory, pre-Amazon purchased inventory, Amazon cash, Amazon-to-bank in-transit cash, YNAB Business cash, and total business value
- added daily business value snapshots and a history graph from the total row
- moved open inventory reconciliation findings to the dedicated Reconciliation page
- moved purchase order problems to a dedicated Purchases tab while keeping Missing Data in the editable purchases view

Next steps:
- build a repeatable dashboard reconciliation report using the shared reference spreadsheet and Supabase
- classify discrepancies into MBOP-only, spreadsheet-only, Returns-tab/status mismatch, and same-order quantity/cost mismatch
- keep known partial-refund, CAD, duplicate-row, and split-row orders as reconciliation regression examples
- add drill-down from a dashboard month into the matching filtered purchases list
- add drill-down links from operational dashboard counts into Purchases, Receiving, and FBA filtered views
- add reconciliation indicators once expected monthly spreadsheet totals are stored or imported
- add a UI control for marking purchase items excluded from reporting with a reason
- add filters for status, marketplace, received date, and system after the first chart proves useful
- keep 2026-05-16+ MBOP-only purchases reportable unless explicitly confirmed as non-resale, return/cancelled, or otherwise excluded
- refine Amazon Finance cash mapping if Seller Central exposes an additional UI-only reserve/available-balance adjustment source
- monitor Dashboard freshness against the oldest required cash/value input so
  stale Amazon cash, YNAB cash, or business value snapshots are visible

---

## Purchases ASIN Review Workflow

Goals:
- make Missing Data review faster
- show title and system/platform prominently
- support manual ASIN review with minimal clicks
- provide Amazon search / ASIN links
- prepare for backend-provided matching diagnostics
- reuse marketplace-title cleaning before any automated Amazon catalog search
- propagate manual ASIN and sell price corrections to matching title/system rows

Recent progress:
- detail drawer now saves eBay title, Amazon title, purchase price, system, ASIN, and sell price together
- detail drawer now supports system correction from the canonical system pick list
- manual correction propagation updates duplicate title/system purchases
- legacy Purchases sheet backfill filled 340 ASINs and 2,141 target sell prices
- reference spreadsheet ASIN validator added for order-by-order MBOP/spreadsheet comparison
- spreadsheet-authoritative ASIN cleanup applied 31 corrections and now validates cleanly
- manual eBay title and purchase price overrides are protected from eBay sync overwrite
- manual split item rows are supported for multi-game eBay listings

Constraints:
- frontend must not guess matching confidence
- frontend must not auto-match across video game systems
- receiving workflow must remain separate

Remaining:
- decide whether to merge or otherwise clean up legacy duplicate purchases for multi-row historical orders such as 04-14542-23405

---

## Receiving And Listing Workflows

Status:
Receiving first slice implemented. Amazon FBA first slice implemented.

Workflow statuses:
- Received: item has been warehouse-verified after delivery; displayed in purchases once the future receiving workflow sets `purchase_items.current_status = received`
- Return Pending: item was physically received but should be returned; separate from Return Opened
- Cancelled: item was cancelled by eBay/seller or reconciliation; separate from returns but requires refund confirmation
- Listed: item has been sent to Amazon FBA or listed on eBay

Completed:
- separate receiving page at /receiving
- receiving API route at /api/receiving
- shared left-side navigation between Purchases and Receiving
- scan-first receiving queue with autofocus
- auto-open detail view when search has exactly one match
- sortable receiving queue columns
- linked eBay titles in receiving detail using derived listing URLs
- linked Amazon titles in receiving detail using ASIN
- chunked receiving metadata hydration for Amazon title/listing URL reliability
- per-item quantity received, return checkbox, and marketplace selection
- per-item ASIN and sell price editing in receiving detail
- Received action gated by ASIN and sell price for Amazon-bound items
- partial quantity split into received and missing no-tracking rows
- sync guardrail so eBay purchase sync does not downgrade Received or Return Pending
- received date stored on purchase_items for future reporting/querying
- one-time reference sheet status backfill applied explicit Listed and Received values
- blank reference sheet statuses were left as their existing MBOP carrier/workflow statuses
- eBay purchase sync preserves Cancelled, Listed, Received, Return Opened, and Return Pending workflow statuses
- shared backend status normalization now writes canonical purchase_items.current_status for carrier/workflow states
- one-time status backfill normalized older ordered/in-transit/delivered placeholders into No Tracking, Shipped (No Tracking), Awaiting Carrier Scan, In Transit, and Pickup Available where appropriate
- separate Amazon FBA page at /fba
- FBA shipment API at /api/fba-shipments
- Received Amazon-bound items grouped one row per ASIN for InventoryLab export
- FBA CSV export added
- FBA shipment ID save links included purchase items and changes included quantities to Listed
- unit-level exclusions supported through quantity-to-send detail rows and split purchase item behavior
- FBA title hydration falls back to another purchase item with the same ASIN when the current Received row has a blank Amazon title

Next steps:
- make the System value more prominent in receiving detail, visually comparable to the eBay title
- when a scanned/searched tracking number matches multiple receiving rows or orders, auto-open the combined detail view with all matching rows, matching the behavior of clicking one of the filtered receiving results
- decide source for eBay listing image URLs
- during the Send to Amazon workflow, allow a damaged/problem copy to be moved from Amazon-bound Received inventory to eBay marketplace inventory, including splitting one unit out of a multi-quantity row when needed
- during the Send to Amazon workflow, allow an item to be moved out of FBA prep and back to the previous Delivered phase so it returns to Receiving instead of staying eligible for Amazon shipment
- review whether FBA needs a historical shipments screen or shipment lookup by shipment ID
- keep receiving/listing workflows separate from purchases review UI

---

## Non-eBay Purchase Entry

Future scope:
Add a dedicated non-eBay purchases screen for supplier purchases that do not
come from the eBay buyer purchase sync.

Direction:
- treat InventoryLab imports as completed legacy backfill/bridge data
- use eBay purchase sync as the source of cost for eBay-sourced inventory
- use MBOP-entered non-eBay purchases as the go-forward source of cost for
  supplier, prep-center, and direct-to-Amazon purchases
- support eventual MBOP -> TIM Sheet export/update rather than scheduled TIM
  Sheet -> MBOP sync

Expected screen capabilities:
- list non-eBay purchases with supplier, order date, order number, ASIN, MSKU,
  description, quantity, received/prep-center quantity, damaged quantity, unit
  cost, list price, fulfillment channel, tracking, notes, and shipment context
- add new non-eBay purchase rows as purchases are made
- edit/correct cost, quantity, fulfillment channel, and source metadata
- preserve FIFO COGS source rows for Amazon sales profitability and current
  Amazon inventory cost layers
- identify rows assigned to FBA shipments, including in-transit shipments
- keep this workflow separate from eBay `purchases`/`purchase_items` unless a
  later design intentionally promotes non-eBay purchases into the same receiving
  model

---

## eBay Seller Order Workflow

Future scope:
Add seller-order functionality separately from purchases when needed.

Constraints:
- seller orders must not write to purchases or purchase_items
- seller-order UI must remain separate from the purchases review screen
- seller fulfillment, customer shipment, sales revenue, and marketplace fee data need their own backend model

Completed guardrail:
- legacy Sell Fulfillment sync write path disabled
- historical seller orders removed from purchases

---

## Public Server Deployment

Goal:
Put the Next.js application on a public HTTPS server so external services can call API routes.

Needed for:
- EasyPost webhooks
- future external automation callbacks
- production-like testing outside localhost

Next steps:
- choose hosting target
- add app security before public exposure, including an authenticated login solution and protected routes for operational pages/API routes
- configure environment variables securely
- deploy the web app
- confirm /api/purchases and /api/easypost/webhook are reachable over HTTPS

---

## EasyPost Webhook Implementation

Status:
Route implemented locally; external EasyPost setup still pending.

Completed:
- added /api/easypost/webhook route
- validates EasyPost HMAC headers
- handles tracker.updated events
- updates inbound_shipments by easypost_tracker_id or tracking_number

Next steps:
- configure EASYPOST_WEBHOOK_SECRET
- register the public webhook URL in EasyPost after deployment
- send/observe a real tracker.updated event
- verify Supabase updates from webhook events
- decide whether to reduce scheduled polling after webhook validation

---

## Shipment Tracking Improvements

Completed:
- EasyPost dependency added
- EasyPost sync made date-scoped from 2026-05-01 by default
- EasyPost sync checks all non-delivered shipment rows before filling the remaining run with recent delivered rows
- 5 requests/second cap added
- 429 retry/backoff added
- invalid tracking placeholders skipped
- carrier passed when known
- May-current shipment backfill completed for 97 of 101 candidate shipment rows
- missing eBay ETA values restored for 88 shipment rows from 2026-05-01 onward

Remaining:
- resolve FedEx credential errors for tracking 381367337613 and 381418656302
- decide whether FedEx should be configured in EasyPost or handled through a direct carrier fallback
- monitor the local Windows AM/PM scheduler now that it points to `C:\Dev\amazon-ebay-ops-system\run_all_syncs.bat`
- keep scheduled polling as the local freshness fallback until public EasyPost webhooks are live

---

## Local Sync Scheduler

Status:
Local scheduler configured; broad integration automation enabled with ongoing task-run validation.

Completed:
- `run_all_syncs.py` now runs eBay buyer purchase sync, EasyPost shipment sync, RevSeller enrichment, Amazon FBA inventory, Amazon listing status, Amazon inventory planning, Amazon Finance balances, Informed Repricer reports, YNAB Business cash balance, guarded Keepa enrichment, and business value snapshots
- legacy eBay supplier returns sync is disabled while the new Order Problems
  return sync is validated
- `run_all_syncs.bat` creates the logs directory when missing and appends to `logs/scheduler.log`
- local Windows scheduled tasks were recreated after the repo moved from OneDrive to `C:\Dev`
- direct batch execution completed successfully with exit code 0
- integration failures are collected and reported while later independent syncs continue running
- Amazon FBA inventory sync now uses page pacing plus SP-API 429/5xx retry/backoff
- scheduled Keepa enrichment only refreshes stale active-Amazon ASINs and skips calls when the token pool is below the configured floor

Next steps:
- confirm both scheduled tasks continue appending successful runs to `logs/scheduler.log`
- when manually triggering tasks, use the root task path, for example `schtasks /Run /TN "\Amazon eBay Ops Sync PM"`
- monitor scheduler logs for EasyPost FedEx credential errors, eBay token/auth issues, SP-API throttling, and Keepa token skips

---

## Amazon / Keepa Catalog Integration

Goal:
Use Amazon and Keepa data to improve ASIN validation, missing-title resolution, and future automated candidate lookup.

Foundation completed:
- added read-only Amazon SP-API client with LWA-only auth for the post-Oct-2023 SP-API model
- retained optional legacy SigV4 signing only behind `AMAZON_SP_API_USE_SIGV4=true`
- added auth/inventory smoke-test script
- added Amazon-specific tables for seller SKUs and FBA inventory snapshots
- added paginated FBA inventory sync into `amazon_skus` and `amazon_fba_inventory_snapshots`
- full sync validated 6,292 Amazon FBA inventory summaries
- kept Amazon seller data separate from purchases and purchase_items
- auth-only validation succeeds after credential correction
- added read-only Keepa schema for product snapshots, optional history points, and latest-snapshot view
- added token-aware Keepa client and product sync script
- Keepa dry run/write path verified with 5 ASINs
- Keepa plan-only mode selected 409 canonical ASINs with 285 available tokens, so broad sync should be staged by token availability
- scheduled Keepa enrichment now refreshes only stale active-Amazon ASINs, caps each run, and skips token-spending calls when token balance is below the configured floor

Planned scope:
- use marketplace-title cleaning before catalog searches
- return ASIN candidates for operator review before any automatic assignment
- validate candidate title and system/platform before writing ASINs
- use Keepa/Amazon metadata to resolve stubborn missing Amazon titles and ambiguous catalog matches
- preserve the rule that video game matching must never cross systems

First next step:
surface Keepa price/rank/sales-rank-drop and competition signals where useful without allowing Keepa to overwrite workflow-owned purchase data

Operational caution:
Run `integrations/keepa_sync_products.py --plan-only` before broad Keepa syncs, then sync in staged batches based on available token balance.

---

## Amazon Orders And Sales Integration

Future scope:
Import Amazon sales/order activity for inventory movement, valuation, sell-through, and cash-flow reporting.

Goals:
- mark Amazon FBA inventory as sold when Amazon reports sales
- reduce current inventory value using MBOP go-forward cost basis and legacy opening-balance valuation where applicable
- support sell-through analytics by ASIN, system, purchase cohort, and listing age
- support richer Amazon settlement/disbursement detail beyond the current Finance balance snapshot
- improve repricing decisions with actual MBOP sales velocity and realized sale prices
- replace the Aged Amazon Inventory page's temporary Informed `current-velocity` signal with Amazon order/sales data once the Amazon sales integration is implemented

Constraints:
- keep Amazon seller orders/sales separate from eBay purchases and `purchase_items`
- do not request or store restricted customer PII unless a future workflow explicitly requires and approves it
- use read-only Amazon reports/API access first
- preserve Amazon-specific raw report rows for auditability
- frontend must render backend-provided sales and valuation aggregates only

Candidate sources:
- Amazon settlement/disbursement reports for cash and fee reconciliation
- Amazon sales/order reports with PII excluded where possible
- Amazon inventory ledger/event data for sold, removed, returned, and transferred units

Next steps:
- identify the lowest-PII Amazon report set that can support sold-unit decrementing and settlement cash reporting
- add Amazon-specific snapshot tables before any workflow logic
- define how sold units consume legacy InventoryLab opening-balance inventory versus MBOP-created FBA inventory
- update inventory reconciliation so current canonical inventory equals Amazon FBA on hand plus pre-listed MBOP inventory, minus confirmed Amazon sales/removals where needed

---

## Late Delivery And Seller Case Workflow

Use case:
Identify purchases that have passed their expected delivery date so the operator can open an eBay case, request shipment from the seller, or pursue a refund.

Foundation completed:
- ETA uses carrier estimate when available
- ETA falls back to eBay estimated delivery for shipments with no carrier ETA, including shipped-without-tracking items

Next steps:
- add a Late / Overdue derived status or filter
- define lateness using the displayed ETA and non-delivered operational status
- surface shipped-without-tracking overdue items prominently
- support direct navigation to the relevant eBay order/case workflow
- record case-opened and refund/resolution outcomes in backend-owned workflow data

---

## Return And Refund Workflow

Goal:
Track return/cancellation outcomes through refund confirmation.

Status:
First slice implemented in Purchases -> Order Problems.

Implemented:
- `order_problem_cases` and `order_problem_events` provide the separate workflow
  tables for return/refund/cancellation follow-up.
- Return Pending items from receiving seed Return Needed cases.
- Return Opened and Cancelled items remain visible until operator resolution.
- Order Problems stage chips cover candidates, return needed, return opened,
  needs response, waiting on seller, ready to ship back, return shipped, refund
  pending, missing item pending, escalation available, and resolved/closed.
- The detail drawer supports MBOP-local workflow actions and notes.
- `integrations/ebay_sync_order_problem_returns.py` reads eBay Post-Order return
  data and stores local case/event updates without writing back to eBay.

Remaining:
- validate the read-only eBay return sync against live return data before
  scheduling it.
- add full case/event timeline endpoints and richer drawer history.
- add read-only support for eBay INR/item-not-received inquiries and cases if
  those endpoints are available for buyer-side data.
- define a controlled partial-refund cost adjustment workflow for cases where
  the item is kept and inventory cost should be reduced.
- preserve manual unit-cost overrides made during reconciliation or refund
  review.
- consider future eBay write actions only after explicit operator workflow,
  permission, and safety design.

---

## Marketplace Title Cleaning Improvements

Problem:
Amazon search and future matching still fail when eBay titles contain extra seller keywords, condition words, edition noise, packaging terms, or promotional fragments.

Goals:
- improve Search Amazon result quality
- improve RevSeller/future fuzzy matching preprocessing
- build toward automated Amazon catalog search and ASIN candidate lookup

Next steps:
- collect failing eBay title examples and expected cleaned search terms
- create a reusable excluded-keyword/phrase list for marketplace title cleaning
- add regression tests for `clean_marketplace_title_for_search` and `cleanMarketplaceTitleForSearch`
- log/display the generated Amazon search term for diagnostics during ASIN review
- separate always-excluded terms from terms that may be meaningful in some titles
- consider preserving edition words only when they affect the product identity
- add diagnostics comparing original eBay title, cleaned search term, detected system, and selected ASIN

Constraints:
- do not remove words that are part of the actual game title
- do not infer ASINs from frontend-only logic
- keep system/platform handling explicit and backend-owned
- automated catalog search must return candidates for review before any auto-assignment

Recent progress:
- created a 100-row missing-ASIN Google Sheet training set
- applied first-pass rules for condition/shipping/media clutter, publisher/studio noise, unicode punctuation, and the `Wii Play` title special case

---

## RevSeller Matching Improvements

Goals:
- fuzzy matching
- confidence scoring
- ambiguity handling
- review queue
- diagnostics expansion

Completed foundation:
- centralized backend system detection
- strict title+system matching for ASIN enrichment
- unique compact same-system fallback for spacing/compound-word variants
- manual UI match corrections can become reusable match memory
- legacy Purchases sheet backfill script added for historical ASIN/price data
- existing missing systems backfilled where recognized
- canonical system display names normalized
- matched Amazon/RevSeller titles stored separately from eBay titles
- reusable marketplace-title cleaner added for frontend search and backend matching

Remaining:
- review unresolved legacy sheet matches: 28 ambiguous order matches and 30 missing order matches
