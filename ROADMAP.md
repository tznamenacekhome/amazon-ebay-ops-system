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

---

## Purchases ASIN Review Workflow

Goals:
- make Needs Review work faster
- show title and system/platform prominently
- support manual ASIN review with minimal clicks
- provide Amazon search / ASIN links
- prepare for backend-provided matching diagnostics
- reuse marketplace-title cleaning before any automated Amazon catalog search

Constraints:
- frontend must not guess matching confidence
- frontend must not auto-match across video game systems
- receiving workflow must remain separate

---

## Receiving And Listing Workflows

Future statuses:
- Received: item has been warehouse-verified after delivery
- Listed: item has been sent to Amazon FBA or listed on eBay

Next steps:
- define receiving workflow tables/fields
- define listing/FBA workflow tables/fields
- decide when these workflow statuses override shipment-derived statuses
- keep receiving/listing workflows separate from purchases review UI

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
- existing missing systems backfilled where recognized
- canonical system display names normalized
- matched Amazon/RevSeller titles stored separately from eBay titles
- reusable marketplace-title cleaner added for frontend search and backend matching
