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

---

## Purchases ASIN Review Workflow

Goals:
- make Needs Review work faster
- show title and system/platform prominently
- support manual ASIN review with minimal clicks
- provide Amazon search / ASIN links
- prepare for backend-provided matching diagnostics

Constraints:
- frontend must not guess matching confidence
- frontend must not auto-match across video game systems
- receiving workflow must remain separate

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
