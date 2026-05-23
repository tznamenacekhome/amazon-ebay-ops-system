# CURRENT_STATE.md

Last Updated: 2026-05-23

# System Status Overview

| Subsystem | Status |
|---|---|
| eBay ingestion | Mature |
| RevSeller enrichment | Functional but evolving |
| Purchases UI | Operational and componentized |
| Receiving workflow | Designed only |
| Shipment enrichment | Functional with remaining FedEx/webhook follow-up |
| Sync orchestration | Mature |
| Dashboard analytics | Early/planned |
| Matching engine | Emerging subsystem |
| Export pipeline | Planned |
| Legacy spreadsheet backfill | Recently used / repeatable script available |

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
- buyer-purchase-only ingestion via Trading API OrderRole=Buyer

Current optimization:
SKIP_EXISTING_ORDERS_WITH_TRACKING = True

Known inefficiency:
Still fetches 90 days every sync.

Recent cleanup:
- removed 50 eBay seller orders that had been written to purchases by the legacy Sell Fulfillment sync
- disabled the legacy seller-order sync write path so seller orders are not inserted into purchases

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

Remaining setup:
- deploy the app to a public HTTPS server
- configure EASYPOST_WEBHOOK_SECRET
- register the EasyPost webhook URL in EasyPost
- resolve or intentionally bypass FedEx tracking credential errors

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
- dense table layout pass
- matched Amazon title display with eBay title subtitle
- simplified ASIN column links
- status filter uses derived operational status
- ETA column uses carrier estimated delivery when available, otherwise eBay estimated delivery, and delivered date when delivered
- date formatting treats shipment dates as date-only to avoid UTC/local timezone shifts
- detail drawer status matches the table's derived operational status
- detail drawer carrier status shows carrier/shipment fields only
- detail drawer shows "--" for Amazon Title when ASIN is missing
- detail drawer saves ASIN and sell price together as one correction
- table headers sort the currently filtered row set by displayed values

Current architecture:
web/app/page.tsx is now the composition layer.

Primary remaining UI opportunity:
iterate on ASIN review and operational throughput without merging receiving workflow concerns.

Recent backend update:
- eBay buyer purchase sync now populates purchase_items.system from recognized eBay title platform terms
- existing empty systems were backfilled where recognized
- RevSeller enrichment no longer applies unique-title matches without a recognized system
- system names were normalized to operator-facing display values
- purchase_items.amazon_title was added and backfilled from RevSeller where ASIN/title data was available
- Amazon search links and RevSeller matching now share marketplace-title cleaning semantics
- marketplace-title cleaning was refined from the 100-row missing-ASIN training sheet
