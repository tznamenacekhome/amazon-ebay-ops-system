# CURRENT_STATE.md

Last Updated: 2026-05-22

# System Status Overview

| Subsystem | Status |
|---|---|
| eBay ingestion | Mature |
| RevSeller enrichment | Functional but evolving |
| Purchases UI | Operational but unstable |
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

Current result:
~760 successful matches
