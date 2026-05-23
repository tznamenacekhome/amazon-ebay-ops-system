# DECISIONS.md

# Core Architecture Decisions

## eBay Trading API Is Authoritative

Decision:
Use Trading API GetOrders for buyer purchases.

Reason:
Sell Fulfillment API unreliable/incomplete.

Constraint:
eBay Sell Fulfillment API returns seller orders. Those records must not be written to purchases or purchase_items.

---

## Supabase Is Operational Source of Truth

Decision:
All operational workflows center around Supabase.

Pattern:
Python Integrations
-> Supabase
-> API Routes
-> Frontend

---

## Purchases Frontend Uses Component + Hook Boundaries

Decision:
Keep the purchases page as a composition layer and move reusable UI and derived logic into web/app/purchases.

Current structure:
- page.tsx composes the workspace
- usePurchases owns loading, API mutations, save state, and error state
- usePurchaseFilters owns filter state and filtered rows
- purchaseStats computes dashboard metrics
- PurchasesTable, PurchaseDetailDrawer, EditablePriceCell, PurchaseFilters, and PurchaseMetrics own focused UI sections

Reason:
The previous page.tsx monolith increased maintenance risk, truncation risk, and regression risk during AI-assisted edits.

Rule:
Do not place landed cost calculations, matching logic, or receiving workflow behavior in the purchases frontend.

---

## System Detection Is Backend-Owned

Decision:
Recognized video game system/platform values are populated by backend import/enrichment code, not inferred in the React frontend.

Reason:
System/platform is part of matching correctness. Frontend inference can hide missing backend data and risks incorrect ASIN review decisions.

Implementation:
- shared system detection lives in integrations/system_detection.py
- eBay buyer purchase sync populates purchase_items.system from eBay titles when a recognized system is present
- RevSeller enrichment requires title+system alignment before assigning ASIN and target price

---

## Matched Amazon Title Is Stored Separately

Decision:
Store the matched Amazon/RevSeller title in purchase_items.amazon_title while preserving the eBay supplier title in purchase_items.title.

Reason:
Operators need to review the matched Amazon identity without losing the original supplier listing title used for traceability and ambiguity checks.

Display:
The purchases table uses amazon_title as the primary item title for matched ASIN rows when available, and shows the eBay title underneath prefixed with "ebay: ".

---

## Marketplace Title Cleaning Is Shared

Decision:
Use a named reusable title cleaner before Amazon search and before matching marketplace titles to RevSeller data.

Names:
- Python backend: clean_marketplace_title_for_search
- TypeScript frontend: cleanMarketplaceTitleForSearch

Reason:
eBay titles often include condition, shipping, punctuation, release years, and platform placement patterns that should be normalized consistently before search or fuzzy matching.

Current use:
- purchases UI Search Amazon links
- RevSeller enrichment normalized title preprocessing

Future use:
Amazon catalog search automation should use this cleaner before searching for candidate ASINs.

---

## Carrier Tracking Status Comes From EasyPost

Decision:
Use eBay for purchase shipment ingestion and EasyPost for carrier tracking enrichment.

Reason:
eBay buyer purchase APIs provide tracking numbers, carrier names, seller shipped signals, estimated delivery fields, and sometimes actual delivery dates, but they do not reliably provide normal carrier scan states such as in transit, out for delivery, pickup available, or exception.

Implementation:
- eBay import creates/updates inbound shipment rows
- EasyPost sync creates or reuses trackers and writes carrier status, normalized status, carrier ETA, events, and tracking URL
- EasyPost sync stays at or below 5 requests per second and retries 429 responses with backoff
- invalid placeholder tracking strings are ignored
- EasyPost updates preserve existing ETA when EasyPost does not return a carrier ETA

Display:
The purchases ETA column uses carrier estimated delivery for undelivered items when available, falls back to eBay estimated delivery when no carrier ETA exists, and uses delivered date for delivered items. Shipment dates are displayed as date-only values to avoid UTC/local timezone display shifts.

---

## EasyPost Webhooks Are The Long-Term Tracking Update Path

Decision:
Move ongoing tracking updates toward EasyPost webhooks instead of frequent polling.

Reason:
Webhooks are more efficient for the operator, EasyPost, and tracking-update cost/traffic patterns.

Implementation status:
- webhook receiver exists at /api/easypost/webhook
- receiver validates EasyPost HMAC headers
- receiver handles tracker.updated events and updates inbound_shipments

Remaining dependency:
The app must be deployed to a public HTTPS server and EasyPost must be configured with the public webhook URL and shared secret.
