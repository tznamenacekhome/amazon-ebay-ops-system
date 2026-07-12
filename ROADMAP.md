# ROADMAP.md

# Midnight Blue Operations Platform

This roadmap tracks MBOP, the internal operations platform for Midnight Blue Enterprises, LLC.

---

# High Priority

## AWS Scheduler Migration

Status:
Completed / routine monitoring.

Completed:
- web deployment is live on ECS/Fargate behind Cognito/ALB auth per latest handoff
- `Dockerfile.scheduler` added for the separate Python scheduler image
- AWS scheduler foundation created: ECR repo, log group, Secrets Manager entries, execution-role secret policy, EventBridge Scheduler role, and `mbop-scheduler-task:1`
- AWS scheduler group names added to `run_all_syncs.py`
- Keepa unattended scheduler defaults tightened for rolling refresh and FBA prep pricing
- authoritative docs added under `docs/aws/`
- scheduler image built and pushed to ECR
- ECS `--list` smoke tests passed for all AWS scheduler groups
- a real ECS `purchase-ingestion` smoke run completed successfully
- Supabase scheduler telemetry SQL applied with service-role grants
- `run_all_syncs.py` writes scheduler run/job telemetry to Supabase
- System Health reads cloud scheduler telemetry
- System Health scheduler group drawers show descriptions, affected MBOP
  features, schedules, last-success age, recent run history, and parsed job
  metrics
- staggered EventBridge Scheduler jobs created and enabled
- `sourcing-catalog` resized to `1024 CPU / 2048 MB` after a default-size
  `OutOfMemoryError`
- live AWS check confirmed 18 enabled `mbop-*` EventBridge schedules targeting
  ECS `runTask`
- Supabase telemetry shows successful `ok` runs for every enabled production
  scheduler group
- local Windows scheduler jobs are retired; the latest local Task Scheduler
  check found no matching `Amazon eBay Ops*` or `MBOP*` tasks

Next work:
- let all scheduler groups run at least once on the metrics-enabled image so
  every drawer has useful counters
- continue routine monitoring in System Health and CloudWatch; tune cadence
  only if real runtime or external API behavior shows pressure
- add alerting/notification later if failed scheduler jobs need push alerts

---

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
Split monitoring workspace implemented / drill-down refinement remaining.

Completed:
- `/dashboard` is now a compact tabbed monitoring workspace with URL-addressed
  Overview, Financial, Operations, Inventory, Amazon, Growth, Sourcing, Loss
  Prevention, and System Health views.
- focused `/api/dashboard/*` routes provide backend-owned aggregates for each
  tab without triggering external syncs, token spending, or workflow writes.
- Overview shows business value KPIs, attention rows, and a scaled business
  value trend with axes, dates, point markers, and value summary.
- Financial shows profitability windows, cash position, Amazon Funds Available,
  payout reconciliation, data completeness, and a Schedule C placeholder.
- Operations shows receiving/FBA prep queues, purchase cleanup, order-problem
  counts, workflow aging, and attention rows.
- Inventory shows value by location/state/age, capital at risk, concentration,
  and reconciliation attention.
- Amazon shows sales/profitability, FBA/listing health, repricing rollups, top
  sellers, stale high-capital inventory, Seller Central account-health score,
  Feedback Manager lifetime rating, and 1-3 star feedback alerts.
- Growth, Sourcing, Loss Prevention, and System Health tabs are implemented
  from existing backend data and Supabase-backed scheduler telemetry.
- dashboard metadata hydration now pages through `purchase_items` instead of
  giant Supabase `IN` filters, preventing transient metadata lookup failures
  from reviving excluded purchase rows in cleanup counts.
- landed-cost math remains backend-owned through `vw_purchases_dashboard.unit_cost`.

Next steps:
- add drill-down links from operational dashboard counts into Purchases, Receiving, and FBA filtered views
- monitor Dashboard freshness against the oldest required cash/value input so
  stale Amazon cash, YNAB cash, or business value snapshots are visible
- add a safe capacity/IO source for System Health instead of placeholders
- decide whether account health can be captured from an approved Amazon source;
  for now account-health score and lifetime feedback summary are manual
  snapshots and SP-API feedback imports are limited to 1-3 star alert rows

---

## Business Financial Reporting

Goal:
Move household/personal-finance reporting to ZFI while keeping MBOP operational
business metrics.

Architecture docs:
See `docs/architecture/README.md`,
`docs/architecture/SYSTEM_BOUNDARIES.md`,
`docs/architecture/DATA_FLOW.md`, and
`docs/architecture/INTEGRATION_PRINCIPLES.md`.

Foundation:
- `ynab_business_transactions` stores YNAB transactions categorized as Business.
- The initial backfill starts at 2026-01-01.
- The daily scheduler refreshes the YNAB Business transaction copy once per day.
- Amazon Finance balance snapshots now reconcile completed Amazon payouts
  against YNAB Business deposit transactions before counting them as in transit.
- `integrations/push_zfi_business_summary.py` now publishes the expanded
  `business_finance_replacement_v2` payload to ZFI, preserving the original
  summary fields while adding profitability windows, cash position, payout
  reconciliation, inventory capital, loss prevention, top sellers, growth,
  sourcing, and financial-readiness sections.

Next steps:
- keep MBOP item/order profitability, COGS diagnostics, inventory value, and
  marketplace operational cash context while ZFI builds replacement finance
  views from the expanded payload.
- compare ZFI replacement values against MBOP Financial, Growth, Loss
  Prevention, Inventory, Amazon, Sourcing, and Sales Orders summaries before
  hiding or narrowing MBOP financial dashboard surfaces.
- add a future scoped operational drilldown API so ZFI/Ask Zoltar can link from
  financial summaries back to MBOP orders, purchase items, returns, inventory
  state details, COGS corrections, FBA shipments, shipping labels, and fee
  details without duplicating full MBOP operational tables in ZFI.
- add payout reconciliation review/reporting so unmatched Amazon payouts and
  unmatched Amazon-looking YNAB deposits are easy to inspect.
- let ZFI own YNAB, tax/reporting categories, Schedule C support, owner
  draws/contributions, and household/business planning views.

### Operational Drilldown From ZFI

Future enhancement:
ZFI and Ask Zoltar may request scoped item, order, return, inventory, COGS, FBA,
shipping-label, or marketplace-fee details from MBOP when a user needs to
explain a financial result.

Boundary:
- MBOP remains the operational source of truth.
- ZFI remains the financial data warehouse/intelligence layer.
- Drilldown is on-demand and scoped to the user's question.
- ZFI should not duplicate full MBOP operational tables by default.
- MBOP does not receive ZFI personal finance data.

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

## Amazon Return Recovery And Removals

Status:
Paused after operational first slice / remaining work documented.

Completed:
- customer return and reimbursement Reports API imports are working for
  `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` and
  `GET_FBA_REIMBURSEMENTS_DATA`
- removal order and removal shipment report support is allowed in the SP-API
  client, but the reports are unreliable and remain under Amazon support
  investigation
- Amazon Returns UI exists at `/amazon-return-recovery`
- the detail drawer shows customer return evidence, reimbursement evidence,
  raw Amazon evidence, original sale context, and manual
  inspection/disposition fields
- manual inspection supports observed condition, final disposition, notes,
  event timeline entries, and reimbursement review for Missing Parts / Wrong
  Item outcomes
- return recovery items marked New + Send to Amazon can appear in `/fba`
- the durable non-purchase FBA bridge table `fba_shipment_source_items` exists
  and is used as authoritative when available, with a defensive fallback only
  if the table is unavailable
- FBA shipment detail and InventoryLab CSV export can include Amazon Return
  Recovery source items without writing to `purchases` or `purchase_items`

Paused boundary:
- keep this workflow Amazon-specific
- do not write Amazon return/removal items to eBay Purchases, Receiving,
  Order Problems, or `purchase_items`
- Amazon return reason/disposition remains evidence only; final condition and
  disposition require manual physical inspection
- do not create Seller Central cases automatically unless a future approved
  Amazon write workflow exists

Remaining work:
- track the Amazon support case for
  `GET_FBA_FULFILLMENT_REMOVAL_ORDER_DETAIL_DATA` and
  `GET_FBA_FULFILLMENT_REMOVAL_SHIPMENT_DETAIL_DATA` returning `FATAL`.
  Current evidence: customer returns and reimbursements work; removal reports
  fail for multiple one-day windows despite Seller Central showing orders; one
  historical removal report succeeded once. If Amazon resolves or explains the
  issue, update the importer strategy. If reports remain unreliable, treat
  manual removal entry as the long-term fallback.
- add manual "New Removal Order" creation for removal orders not backed by
  customer-return report data. Capture removal order ID, removal source,
  submitted date, status, ASIN/SKU/FNSKU, title, quantity, carrier/tracking,
  LPN if present, and notes. Support scanning/removal slip identifiers when
  items arrive.
- expand reimbursement review beyond the current checklist. Add Seller Central
  case ID, case status, submitted date, follow-up date, response, decision,
  reimbursement amount, and closure reason. Generate manual case-prep text
  from Amazon return evidence, LPN, order ID, reimbursement rows,
  photos/evidence checklist, and inspection notes.
- add closeout paths for Sell on eBay and Dispose/Donate dispositions. Sell on
  eBay should bridge into a future eBay resale/listing queue while preserving
  ASIN, title, source cost, observed condition, and notes. Dispose/Donate
  should record a closeout event and project inventory/value impact without
  silently losing cost or value history.
- project Amazon Return Recovery states into `inventory_positions` or the
  appropriate derived inventory model: pending inspection, reimbursement
  review, ready for FBA, routed to FBA, eBay resale candidate, and
  disposed/donated.
- add dashboard summaries later for Loss Prevention, Inventory, and Amazon
  tabs, keeping all rollups backend/API-owned.
- keep return recovery imports manual/on-demand for now. Later add a
  low-frequency scheduler group for customer returns/reimbursements only. Do
  not schedule unreliable removal reports until Amazon support resolves the
  `FATAL` issue or the importer uses safe narrow windows with backoff.
- after real-world use, verify `fba_shipment_source_items` rows are created for
  Amazon return items saved to FBA shipments, routed rows stay out of open
  Return Recovery work, and InventoryLab export plus FBA shipment detail remain
  correct for mixed purchase-item and Amazon-return source shipments. Add
  audit/freshness indicators if needed.

---

## Supplier-Agnostic Purchase Entry

Future scope:
Add supplier-agnostic purchase support for inventory buys that do not come from
the eBay buyer purchase sync, including self-receive, prep-center,
Amazon-MFN, and eBay-resale paths.

Direction:
- treat InventoryLab imports as completed legacy backfill/bridge data
- use eBay purchase sync as the source of cost for eBay-sourced inventory
- use MBOP-entered non-eBay purchases as the go-forward source of cost for
  supplier, prep-center, and direct-to-Amazon purchases
- extend `purchases` and `purchase_items` rather than creating a separate
  operational purchase workflow table
- add nullable `purchase_items.fulfillment_path` with `self_receive`,
  `prep_center`, `amazon_mfn`, and `ebay_resale`
- keep `supplier` as the acquired-from field and do not add `acquisition_type`
- support eventual MBOP -> TIM Sheet export/update rather than scheduled TIM
  Sheet -> MBOP sync

Expected screen capabilities:
- list non-eBay purchases with supplier, supplier order number, purchase date,
  item title, Amazon title, ASIN, system, quantity, unit cost, target sell
  price, marketplace, fulfillment path, prep-center fields, tracking, carrier,
  notes, and shipment context
- add/import new supplier purchase rows as purchases are made
- write manual supplier purchases to `purchases` and `purchase_items`
- create/link inbound shipments when tracking is supplied and
  `fulfillment_path = self_receive`
- keep `fulfillment_path = prep_center` rows out of normal Receiving
- add a Prep Center workspace with received/sent-to-Amazon actions, Amazon
  shipment ID capture, and prep-center received/shipped dates
- edit/correct cost, quantity, fulfillment path, and source metadata
- preserve FIFO COGS source rows for Amazon sales profitability and current
  Amazon inventory cost layers
- identify rows assigned to FBA shipments, including in-transit shipments
- dashboard/reporting should include manual supplier purchases without double
  counting inventory already represented in Amazon FBA

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
- future independent Supabase/Postgres backups after cloud migration

Current state:
- AWS ECS/Fargate hosting is live for the web app.
- Cognito/ALB authentication is working per the latest handoff.
- The custom app domain is `https://mbop.midnightblueenterprises.com`.
- Logout is available from the shared app shell and routes through Cognito.
- EasyPost webhook delivery is registered through the production AWS domain.

Next steps:
- observe real EasyPost webhook delivery and verify Supabase shipment updates
- add an independent scheduled Postgres backup, such as `pg_dump` to cloud
  object storage or another off-site destination, so MBOP is not relying only
  on Supabase's short-retention managed backups

---

## EasyPost Webhook Implementation

Status:
Deployed and smoke-tested / real EasyPost event observation pending.

Completed:
- added /api/easypost/webhook route
- validates EasyPost HMAC headers and/or the configured EasyPost outbound token
- handles tracker.updated events
- updates inbound_shipments by easypost_tracker_id or tracking_number
- registered EasyPost production webhook
- added ALB unauthenticated path rule for `/api/easypost/webhook`
- deployed webhook secret through AWS Secrets Manager and current web task
  revisions
- public GET smoke returns `405` instead of Cognito redirect
- authenticated non-tracker smoke POST returns accepted/ignored response

Next steps:
- send/observe a real tracker.updated event
- verify Supabase updates from webhook events
- decide whether to reduce scheduled polling after webhook validation

---

## Shipment Tracking Improvements

Completed:
- EasyPost dependency added
- EasyPost sync now prioritizes undelivered inbound shipments and no longer uses
  the 2026-05-01 backfill date by default
- EasyPost sync checks all non-delivered shipment rows before filling the remaining run with recent delivered rows
- 5 requests/second cap added
- 429 retry/backoff added
- invalid tracking placeholders skipped
- carrier passed when known
- May-current shipment backfill completed for 97 of 101 candidate shipment rows
- missing eBay ETA values restored for 88 shipment rows from 2026-05-01 onward
- Order Problems no longer treats an expired eBay ETA as a problem by itself
  when carrier tracking has current activity; missing tracking or more than 4
  days without carrier activity still qualifies
- carrier events/statuses such as return-to-sender now seed or relabel derived
  Order Problems as `carrier_exception_candidate`
- FedEx credential errors for tracking `381367337613` and `381418656302` were
  addressed and removed from the active issue list

Remaining:
- observe real EasyPost webhook deliveries before reducing scheduled polling
- continue tracking carrier exceptions through Order Problems and shipment detail

---

## Local Sync Scheduler

Status:
Superseded by AWS EventBridge Scheduler; local Windows tasks retired.

Completed:
- `run_all_syncs.py` now runs eBay buyer purchase sync, sourcing purchase matching, EasyPost shipment sync, read-only eBay Order Problems return/inquiry sync, RevSeller enrichment, Amazon FBA inventory, Amazon FBA shipment sync, Amazon listing status, Amazon inventory planning, Amazon Finance balances, Informed Repricer reports, YNAB Business cash balance/transactions, sourcing listing availability cleanup, guarded Keepa enrichment, and business value snapshots
- legacy scheduler groups split freshness work into `core`, `daily`, and
  `catalog`; production AWS now uses the explicit cloud groups documented in
  `docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`
- legacy eBay supplier returns sync has been removed from active orchestration
  and System Health; the Order Problems return sync owns return/inquiry/case
  freshness
- `run_all_syncs.bat` remains a manual/local development helper that creates
  the logs directory when missing and appends to `logs/scheduler.log`
- direct batch execution completed successfully with exit code 0
- integration failures are collected and reported while later independent syncs continue running
- Amazon FBA inventory sync now uses page pacing plus SP-API 429/5xx retry/backoff
- Amazon FBA shipment sync now refreshes MBOP shipment status, shipment item
  receiving quantities, FBA availability, fulfillment center, milestones, and
  outbound-to-Amazon remaining value
- scheduled Keepa enrichment only refreshes stale active-Amazon ASINs and skips calls when the token pool is below the configured floor
- scheduled sourcing listing availability cleanup checks open, Watch, and ROI-snoozed opportunities and automatically dismisses ended/sold-out/missing eBay listings with `no_longer_available`; Purchased / Offer Made rows remain for purchase matching/enrichment
- eBay buyer purchases now sync a recent window plus targeted no-tracking
  refresh instead of a broad 90-day daily buyer-order pull
- Amazon sales orders skip item-detail calls when LastUpdateDate has not changed
  and order items are already present
- Amazon listing status supports stale-day filtering so normal runs can skip
  recently refreshed SKUs
- YNAB Business transactions run incrementally with an overlap instead of
  refetching transactions already stored in MBOP
- inventory reconciliation can skip when source datasets have not changed, with
  a fail-open fallback when source freshness columns are unavailable
- AWS EventBridge Scheduler now owns production cadence through
  `mbop-scheduler-task:1`
- Catalog, Daily, AM, PM, and Inventory Source Balance Audit local scheduled
  tasks no longer appear in the latest local Task Scheduler check

Next steps:
- split the dashboard refresh/value jobs into lighter operational and heavier
  reporting paths, then optimize the reporting path separately
- add `purchase_items.updated_at` or an equivalent source-change ledger so
  inventory reconciliation skip-if-unchanged can avoid fail-open runs
- monitor AWS scheduler logs for EasyPost webhook/polling behavior, eBay
  token/auth issues, SP-API throttling, and Keepa token skips

---

## Dashboard Split

Phase 1 implemented:
- `/dashboard` now uses compact URL-addressable tabs:
  Overview, Financial, Operations, Inventory, Amazon, Growth, and System Health
- only Overview and Operations fetch live data in this phase
- `/api/dashboard/overview` returns business value snapshot metrics, attention
  summary rows, and a compact business value trend
- `/api/dashboard/operations` returns receiving, FBA prep, purchase cleanup,
  order-problem, workflow-aging, and top-attention summaries
- the left navigation keeps Dashboard as the single monitoring entry point; the
  separate System Health nav item was removed from the compact left nav
- dashboard React components render API-provided values and do not calculate
  landed cost, inventory value, workflow status, repricing tiers, or profit

Remaining:
- Phase 2: Financial and Inventory tabs with dedicated backend summaries
- Phase 3: Amazon, Growth, and System Health tabs with scheduler/API health
  rollups
- replace remaining legacy `/api/dashboard/purchases` use once historical
  purchase/month reporting has a focused destination

Remaining phases MVP implemented:
- Inventory, Amazon, Growth, Sourcing, Loss Prevention, and System Health tabs
  now have focused read-only API routes under `/api/dashboard/*`
- dashboard tab list now includes Sourcing and Loss Prevention while preserving
  one top-level Dashboard left-nav entry
- routes load independently and do not run external syncs, marketplace writes,
  Keepa token-spending calls, or workflow mutations
- Sourcing is an explainable manual research queue derived from existing
  sales/profit/inventory data, not an automated buy engine
- Loss Prevention summarizes risk from order-problem cases and reconciliation
  signals without replacing the Order Problems workflow

Still open:
- add exact filter support to destination workflow pages for dashboard
  drill-downs that currently degrade to base routes
- add safe Supabase capacity and disk IO signal sourcing for System Health

Financial implemented:
- `/api/dashboard/financial` summarizes existing Amazon sales profitability,
  YNAB Business cash, Amazon cash balances, payout reconciliation, financial
  data completeness, and the future Schedule C reporting placeholder
- `/dashboard?view=financial` renders those API-provided values without
  frontend landed-cost or profit recalculation

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

## Seller Intelligence Subsystem

Future scope:
Build seller-level learning that helps MBOP decide which eBay sellers are worth
watching, buying from, or avoiding.

Planned capabilities:
- seller trust scoring based on purchase outcomes, delivery reliability,
  cancellation/refund history, return rates, and listing quality signals
- seller ROI history based on realized MBOP purchase cost, Amazon sale value,
  fees, returns, and final profit outcomes
- offer acceptance history by seller, including offer amount, asking price,
  discount percentage, accepted/declined/expired result, and time to response
- seller inventory expansion search that can discover other listings from a
  promising seller after one listing qualifies
- seller opportunity conversion rate from surfaced opportunity to purchased,
  received, listed, sold, returned, or dismissed
- richer seller reliability metrics separated from product/condition return
  strikes, including item-not-received, refund-delay, and seller-cancelled
  history
- trusted-seller rules and diagnostics after warning/penalty behavior is proven

Constraints:
- seller intelligence must remain advisory unless a future workflow explicitly
  approves automated action
- seller scoring must not overwrite purchase, receiving, return, or sourcing
  workflow state
- seller matching should use stable seller identifiers from eBay when available
  and preserve raw evidence for auditability
- avoid sellers should warn and penalize first; hide-by-default is intentionally
  deferred until diagnostics are proven

---

## Matching Intelligence Remaining Work

Future scope:
Finish wiring the Matching Intelligence evidence set into live sourcing
diagnostics before any AI-driven matching or eBay-to-Amazon sourcing.

Implemented foundation:
- matching examples are rebuilt from sourcing actions, manual match memory,
  purchase history, sourcing purchase matches, receiving outcomes, and order
  problem cases
- historical/manual purchase evidence is treated as verified positive match
  evidence
- listing snapshots are preserved for opportunities, actions, and best-effort
  historical/manual purchases
- live Amazon-to-eBay sourcing consumes exact positive/negative examples,
  seller warnings, hard platform rules, item-specific Platform, category
  evidence, Game Name, numeric sequel/year checks, edition/version checks,
  digital/service terms, accessory/merchandise terms, incomplete-product terms,
  and region signals
- daily Amazon-to-eBay sourcing discovery now uses a unified
  `daily_catalog_sourcing` coverage cycle that spends the usable eBay Browse
  quota across recently sold ASINs, purchased-not-sent Amazon-bound items, and
  remaining eligible catalog ASINs without re-searching an ASIN during the same
  cycle
- Matching Intelligence refresh runs through sync orchestration after purchase,
  dismissal, return, and catalog updates, then rescoring refreshes recent
  sourcing runs
- deterministic matcher regression tests cover known recent false-positive
  patterns, and the latest quality sprint/rescore is documented in
  `docs/sourcing_matching_quality_sprint_2026-07-11.md`

Remaining capabilities:
- full per-opportunity diagnostics UI showing hard-rule pass/fail, title
  overlap, system/platform checks, positive and negative historical examples,
  seller warnings, score adjustments, and final recommendation
- dedicated uncertain-match review workflow for current opportunities that need
  operator review instead of normal opportunity handling
- sample-driven fuzzy matching that uses the labeled examples after the sample
  set is large enough; target at least 5,000 strong examples before AI-assisted
  opportunity review
- AI review against live opportunities using title, photos, item specifics,
  description, condition, seller evidence, and historical examples
- normalized image/listing clue scoring that can use structured clues such as
  PEGI, Greatest Hits, disc only, missing shrink wrap, reseal, and damaged case
  instead of only storing them as evidence
- formal configurable matching weights by evidence source, outcome, confidence,
  and recency
- richer example/detail browser for snapshots and examples, including raw
  evidence drill-down where available
- automated reason discovery from repeated notes and reviewed near misses, with
  operator approval before adding new structured reasons

Not planned:
- strong or required note prompts for specific dismissal reasons. Notes remain
  optional and are stored whenever entered.

---

## Return Intelligence Subsystem

Future scope:
Use receiving, return, and listing evidence to learn which sourcing listings
are likely to cause bad outcomes.

Planned capabilities:
- return outcome learning based on return reason, refund timing, seller
  response, carrier exception, no-refund closure, and final cost recovery
- AI clue extraction from return-causing listings to identify phrases, photos,
  category mismatches, condition wording, seller behavior, or title patterns
  that should affect future sourcing decisions
- dedicated return intelligence report that separates identity/condition
  strikes from reliability/refund/cancellation issues
- consistent linking between return cases, receiving outcomes, listing
  snapshots, seller identity, purchase item, and eBay item evidence when all
  identifiers are available

Implemented foundation:
- listing snapshot preservation now includes historical/manual purchase
  backfill evidence for Matching Intelligence
- receiving outcome learning now captures correct item, wrong item, wrong
  condition, packaging issue, incomplete item, listed successfully, structured
  image clues, and receiving notes
- Matching Intelligence exposes a near-miss review queue for title-similar
  dismissed/condition examples

Constraints:
- preserved listing snapshots should support audit and learning without
  becoming the editable operational source of truth
- AI-extracted clues must be explainable and reviewable before they influence
  matching, seller scoring, or sourcing filters
- return intelligence must remain separate from the Order Problems workflow;
  Order Problems owns active refund/case execution

---

## eBay -> Amazon Sourcing Engine

Future scope:
Add a sourcing mode that starts from eBay market supply and evaluates whether
listings can profitably map to Amazon resale opportunities.

Dependencies:
- Matching Intelligence Layer completion, including title/platform matching,
  ambiguity handling, negative-match learning, diagnostics, and review queues
- Amazon -> eBay sourcing validation, proving that the current Amazon-inventory
  driven workflow produces reliable matches, ROI estimates, seller outcomes,
  and return-risk signals before reversing the search direction
- sufficient labeled evidence to support AI or fuzzy matching without creating
  cross-platform or wrong-title matches

Planned direction:
- use the completed matching layer to prevent cross-platform video game matches
- evaluate landed cost, Amazon sell price, fees, velocity, competition, and
  return-risk signals before surfacing opportunities
- preserve the operator-review-first model until match quality and outcome
  learning are strong enough to justify deeper automation

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
Operational first slice implemented in Purchases -> Order Problems.

Implemented:
- `order_problem_cases` and `order_problem_events` provide the separate workflow
  tables for return/refund/cancellation follow-up.
- Return Pending items from receiving seed Return Needed cases.
- Return Opened and Cancelled items remain visible until operator resolution.
- Order Problems stage chips cover candidates, return needed, return opened,
  needs response, waiting on seller, ready to ship back, return shipped, refund
  pending, missing item pending, escalation available, and resolved/closed.
- The dense table has consolidated issue/status columns, top-of-table current
  filter stats, order/detail links, next action, refund amounts, tracking/ETA,
  and a drawer button.
- The detail drawer supports MBOP-local workflow actions, notes, replacement
  tracking, refund confirmation, and Close No Refund for unrecoverable/no-refund
  outcomes.
- The detail drawer shows the local return type selector, captured eBay/case
  status fields, refund amounts, relevant workflow dates, identifiers, and the
  recent `order_problem_events` timeline.
- `integrations/ebay_sync_order_problem_returns.py` reads eBay Post-Order
  returns, INR inquiries/details, and cases, then stores local case/event
  updates without writing back to eBay.
- Inquiry detail enrichment captures seller make-it-right/escalation dates and
  replacement tracking that eBay does not include in inquiry search summaries.

Remaining:
- add first-class scheduled cancellation search import if more cancellation
  refund-follow-up cases appear.
- define a controlled partial-refund cost adjustment workflow for cases where
  the item is kept and inventory cost should be reduced.
- preserve manual unit-cost overrides made during reconciliation or refund
  review.
- add deeper event-history pagination only if the recent drawer timeline is too
  short for active case review.
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
