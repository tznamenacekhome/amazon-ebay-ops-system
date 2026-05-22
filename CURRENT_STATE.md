# CURRENT_STATE.md

Last Updated: 2026-05-22

# System Status Overview

| Subsystem | Status |
|---|---|
| eBay ingestion | Mature |
| RevSeller enrichment | Functional but evolving |
| Purchases UI | Operational and componentized |
| Receiving workflow | Designed only |
| Shipment enrichment | Partial |
| Sync orchestration | Mature |
| Dashboard analytics | Early/planned |
| Matching engine | Emerging subsystem |
| Export pipeline | Planned |

---

# Current Backend State

## eBay Buyer Purchase Sync

Status: STABLE

Implemented:
- Trading API GetOrders
- pagination
- tracking extraction
- delivery extraction
- landed cost calculations
- shipment linking
- inbound shipment linking
- import batching
- timezone normalization
- duplicate prevention

Current optimization:
SKIP_EXISTING_ORDERS_WITH_TRACKING = True

Known inefficiency:
Still fetches 90 days every sync.

---

## RevSeller Integration

Status: PARTIAL

Implemented:
- Google Sheets API integration
- ASIN enrichment
- target price enrichment
- diagnostics
- ambiguity handling
- system-aware matching
- shared backend system detection
- strict title+system RevSeller matching

Current result:
~760 successful matches

---

# Current Frontend State

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

Current architecture:
web/app/page.tsx is now the composition layer.

Primary remaining UI opportunity:
iterate on ASIN review and operational throughput without merging receiving workflow concerns.

Recent backend update:
- eBay buyer purchase sync now populates purchase_items.system from recognized eBay title platform terms
- existing empty systems were backfilled where recognized
- RevSeller enrichment no longer applies unique-title matches without a recognized system
