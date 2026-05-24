# ROADMAP.md

# High Priority

## Frontend Componentization

Status:
Completed initial architecture pass.

Completed:
- split page.tsx
- reduce truncation risk
- improve maintainability
- improve AI-generated diff quality

Created:
- PurchasesTable.tsx
- PurchaseDetailDrawer.tsx
- EditablePriceCell.tsx
- PurchaseFilters.tsx
- PurchaseMetrics.tsx
- usePurchases.ts
- usePurchaseFilters.ts
- purchaseStats.ts
- web/app/purchases/README.md

Next frontend focus:
- iterate on ASIN review workflow
- improve dense operational scanning
- preserve purchases/receiving separation
- keep page.tsx as composition layer

Recent UI cleanup:
- removed redundant ASIN review text from unmatched rows
- removed external-link icons from text links
- tightened purchases table spacing
- consolidated ETA/delivered date display into one color-coded column
- fixed shipment date display to avoid UTC/local timezone day shifts
- added sortable purchases table headers
- added combined eBay title, purchase price, ASIN, and sell price save in the detail drawer
- added manual split item creation from the detail drawer
- added search-box clear button

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
- detail drawer now saves eBay title, purchase price, ASIN, and sell price together
- manual correction propagation updates duplicate title/system purchases
- legacy Purchases sheet backfill filled 340 ASINs and 2,141 target sell prices
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

Workflow statuses:
- Received: item has been warehouse-verified after delivery; displayed in purchases once the future receiving workflow sets `purchase_items.current_status = received`

Future statuses:
- Listed: item has been sent to Amazon FBA or listed on eBay

Next steps:
- define receiving workflow tables/fields
- define the API/action that sets `purchase_items.current_status = received`
- define listing/FBA workflow tables/fields
- decide when Listed overrides shipment-derived and receiving-derived statuses
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
- add a recurring scheduler only if webhooks are not enough for operational freshness

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
- review unresolved legacy sheet matches: 28 ambiguous order matches and 30 missing order matches
