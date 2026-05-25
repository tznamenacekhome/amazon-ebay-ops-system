# ROADMAP.md

# Midnight Blue Operations Platform

This roadmap tracks MBOP, the internal operations platform for Midnight Blue Enterprises, LLC.

---

# High Priority

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

---

## Dashboard Analytics

Status:
First purchase completeness slice implemented.

Completed:
- added Dashboard menu item to the MBOP left navigation
- added /dashboard workspace
- added /api/dashboard/purchases aggregation route
- added monthly units and total cost chart
- added year/month pivot-style table with grand total
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

Near-term goals:
- compare MBOP monthly totals against the legacy Excel pivot
- identify missing historical purchase imports by month
- surface data completeness gaps before deeper workflow redesign

Next steps:
- build a repeatable dashboard reconciliation report using the shared reference spreadsheet and Supabase
- classify discrepancies into MBOP-only, spreadsheet-only, Returns-tab/status mismatch, and same-order quantity/cost mismatch
- keep known partial-refund, CAD, duplicate-row, and split-row orders as reconciliation regression examples
- add drill-down from a dashboard month into the matching filtered purchases list
- add reconciliation indicators once expected monthly spreadsheet totals are stored or imported
- add a UI control for marking purchase items excluded from reporting with a reason
- add filters for status, marketplace, received date, and system after the first chart proves useful
- keep 2026-05-16+ MBOP-only purchases reportable unless explicitly confirmed as non-resale, return/cancelled, or otherwise excluded

---

## Purchases ASIN Review Workflow

Goals:
- make Needs Review work faster
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
- apply sql/2026-05-23_add_receiving_fields.sql in Supabase
- test receiving flow against real delivered and shipped-without-tracking rows
- decide source for eBay listing image URLs
- apply/backfill sql/2026-05-24_add_fba_shipments.sql in Supabase
- test FBA export against InventoryLab import requirements
- review whether FBA needs a historical shipments screen or shipment lookup by shipment ID
- keep receiving/listing workflows separate from purchases review UI

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
- 5 requests/second cap added
- 429 retry/backoff added
- invalid tracking placeholders skipped
- carrier passed when known
- May-current shipment backfill completed for 97 of 101 candidate shipment rows
- missing eBay ETA values restored for 88 shipment rows from 2026-05-01 onward

Remaining:
- resolve FedEx credential errors for tracking 381367337613 and 381418656302
- decide whether FedEx should be configured in EasyPost or handled through a direct carrier fallback
- validate the local Windows AM/PM scheduler now that it points to `C:\Dev\amazon-ebay-ops-system\run_all_syncs.bat`
- keep scheduled polling as the local freshness fallback until public EasyPost webhooks are live

---

## Local Sync Scheduler

Status:
Local scheduler configured; ongoing task-run validation remains.

Completed:
- `run_all_syncs.py` now runs eBay buyer purchase sync, EasyPost shipment sync, eBay supplier returns sync, and RevSeller enrichment
- `run_all_syncs.bat` creates the logs directory when missing and appends to `logs/scheduler.log`
- local Windows scheduled tasks were recreated after the repo moved from OneDrive to `C:\Dev`
- direct batch execution completed successfully with exit code 0

Next steps:
- confirm both scheduled tasks append successful runs to `logs/scheduler.log`
- when manually triggering tasks, use the root task path, for example `schtasks /Run /TN "\Amazon eBay Ops Sync PM"`
- monitor scheduler logs for EasyPost FedEx credential errors and eBay token/auth issues

---

## Amazon / Keepa Catalog Integration

Goal:
Use Amazon and Keepa data to improve ASIN validation, missing-title resolution, and future automated candidate lookup.

Planned scope:
- evaluate Amazon SP-API catalog/search access and Keepa API coverage
- use marketplace-title cleaning before catalog searches
- return ASIN candidates for operator review before any automatic assignment
- validate candidate title and system/platform before writing ASINs
- use Keepa/Amazon metadata to resolve stubborn missing Amazon titles and ambiguous catalog matches
- preserve the rule that video game matching must never cross systems

First next step:
inventory available credentials, quotas, costs, and API fields, then design the smallest safe lookup workflow for one unresolved ASIN/title case

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

Required scope:
- Return Pending items from receiving
- Return Opened items from eBay return/case state
- Cancelled items from eBay/seller cancellation or reconciliation

Key requirement:
Cancelled items must remain visible to this workflow until refund receipt is confirmed.

Future cost requirements:
- store refund amount, refund date, source, and affected purchase item or quantity
- support partial refunds where the item is kept and inventory cost should be reduced
- avoid automatically spreading a multi-item partial refund across unrelated items unless the operator assigns it
- preserve manual unit-cost overrides made during reconciliation or refund review

Next steps:
- define refund fields, such as refund_expected, refund_received, refund_received_date, refund_amount, and refund_notes
- decide whether refund state belongs directly on purchase_items or in a separate return/refund workflow table
- add filters/views for refund missing and refund received
- integrate future eBay return/case/refund APIs where available

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
- apply sql/2026-05-22_add_manual_item_matches.sql in Supabase
- apply sql/2026-05-23_add_purchase_item_manual_overrides.sql in Supabase
- apply sql/2026-05-23_add_receiving_fields.sql in Supabase
- review unresolved legacy sheet matches: 28 ambiguous order matches and 30 missing order matches
