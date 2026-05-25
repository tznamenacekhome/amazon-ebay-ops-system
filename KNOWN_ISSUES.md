# KNOWN_ISSUES.md

This file tracks known issues for Midnight Blue Operations Platform (MBOP).

# High Priority

## eBay Seller Orders In Purchases

Status: RESOLVED / MONITOR

Problem:
The legacy eBay Sell Fulfillment sync wrote seller/customer orders into purchases, causing sold items to appear on the purchases page.

Resolution:
- removed 50 seller orders from purchases
- removed their 50 purchase_items
- verified no seller-style eBay payloads remain in purchases
- disabled integrations/ebay_sync_orders.py from writing seller orders to purchases

Guardrail:
Future eBay seller-order functionality must use separate tables/workflows and must not write to purchases or purchase_items.

---

## page.tsx Monolith

Status: RESOLVED / MONITOR

File:
web/app/page.tsx

Resolution:
- extracted purchases table
- extracted detail drawer
- extracted editable price cell
- extracted filter bar
- extracted metrics
- moved purchase API state into usePurchases
- moved filtering into usePurchaseFilters
- moved metric calculation into purchaseStats

Remaining risk:
Future UI work could reintroduce large JSX blocks or mixed responsibilities.

Recommended guardrail:
Keep page.tsx focused on composition and UI-local workflow state.

---

## RevSeller Matching Ambiguity

Status: ACTIVE

Problem:
same game titles exist across multiple systems.

Risks:
- incorrect ASIN assignment
- incorrect sell price enrichment

Recommended next mitigation:
- build an explicit ASIN review workflow in the purchases UI
- surface system/platform prominently
- rely on backend-provided matching diagnostics and confidence
- never infer matching confidence in the frontend

Current mitigation:
- backend system detection has been centralized
- eBay import/sync populates purchase_items.system from recognized title terms
- RevSeller enrichment requires system-aware matching before ASIN assignment
- matched Amazon/RevSeller title is stored separately from the eBay supplier title for review clarity
- shared marketplace-title cleaning now runs before RevSeller normalized matching
- legacy Purchases sheet backfill filled many missing values but skipped ambiguous multi-row order matches

---

## Remaining Missing ASIN / Target Price Rows

Status: ACTIVE

Problem:
After RevSeller enrichment and legacy Purchases sheet backfill, some purchase_items still lack ASINs and/or target sell prices.

Current count after latest backfill:
- 37 rows missing ASIN
- 62 rows missing target sell price

Known causes:
- old Purchases sheet did not contain the order number
- multi-row order matches were ambiguous
- some items are not in RevSeller/Amazon catalog data yet

Recommended next mitigation:
- review the 28 ambiguous order matches from the legacy sheet backfill
- review the 30 missing order-number matches
- use manual drawer save so corrections propagate to matching rows
- apply manual_item_matches SQL migration so manual corrections become reusable match memory

---

## Reference Spreadsheet ASIN Mismatches

Status: RESOLVED / MONITOR

Problem:
A validation pass found MBOP active purchase item ASIN quantities did not exactly match the reference spreadsheet Purchases tab for 30 unique orders.

Current validation:
- script: `integrations/validate_asins_against_purchase_sheet.py`
- cleanup script: `integrations/apply_sheet_asin_validation_fixes.py`
- spreadsheet ASINs were treated as authoritative when MBOP conflicted or was blank
- 31 purchase item ASINs were corrected from the spreadsheet
- latest report: `data/asin_validation_20260524_201926.csv`
- 2,825 of 2,825 compared orders matched exactly

Recommended guardrail:
- rerun the validator after future ASIN enrichment or large manual correction passes
- keep the cleanup script as a controlled spreadsheet-authoritative repair path

---

## Dashboard / Legacy Spreadsheet Variance

Status: MOSTLY RESOLVED / MONITOR

Problem:
The new MBOP dashboard intentionally calculates purchase units and cost from Supabase, while the legacy Excel pivot was built from the historical spreadsheet.

Current reconciliation:
- 2024 and 2025 match the legacy Excel pivot exactly
- strict after-2026-05-15 MBOP-only eBay purchases absent from both Purchases and Returns tabs were excluded from dashboard reporting
- no after-2026-05-15 MBOP-only rows were found on the Returns tab
- 39 2026 MBOP-active rows found on the legacy Returns tab were normalized: 26 Return Opened and 13 Cancelled
- one-time cleanup corrected duplicate rows, split-row quantities, partial-return quantities, one returned/refunded spreadsheet-missing order, one single-item partial refund, and three CAD purchase costs
- active unit count now matches the legacy pivot exactly: 4,806 units
- active cost is $84,840.36 in MBOP versus $84,836.31 in the legacy pivot, leaving a $4.05 MBOP-over-spreadsheet variance
- the remaining small cost variance is currently treated as legacy spreadsheet error unless new evidence appears
- order 16-14113-30387 had historical zero-cost NBA 2K22 rows that were excluded from reporting after corrected received quantities were confirmed
- order 19-14476-44107 is a confirmed personal Tommy Bahama shirt purchase
- order 11-14441-71152 is a confirmed business supply padded-mailer purchase, not resale inventory

Recommended next mitigation:
- create a repeatable reconciliation report that classifies differences as MBOP-only, spreadsheet-only, returns-tab, and same-order amount/quantity mismatch
- keep partial refunds and foreign-currency examples in regression checks for future eBay sync changes

---

## Multi-Item Partial Refund Allocation

Status: ACTIVE / FUTURE WORKFLOW

Problem:
Single-item partial refunds can be safely applied to the purchase item cost, but multi-item partial refunds may apply to only one line or quantity and should not be automatically spread across unrelated items.

Current mitigation:
- eBay buyer purchase sync applies net payment/refund totals only for single-item partial refunds
- item-level manual cost corrections set `manual_unit_cost_override = true`

Recommended next mitigation:
- model refunds explicitly in the future Return and Refund workflow
- record refund amount, refund date, source, and affected purchase item or quantity
- use refund records to adjust item cost or reporting intentionally

---

## EasyPost FedEx Tracking Credentials

Status: ACTIVE

Problem:
Two FedEx tracking numbers from the 2026-05-01+ backfill failed in EasyPost with "Credentials not found for the specified carrier", even when retried without passing carrier.

Affected orders:
- 06-14656-35281, tracking 381367337613, order date 2026-05-17
- 27-14629-25992, tracking 381418656302, order date 2026-05-18

Risk:
FedEx shipments may remain at unknown or awaiting-carrier status unless EasyPost FedEx credentials are configured or a separate FedEx/direct-carrier path is added.

Recommended next mitigation:
- verify FedEx tracking support/credentials in the EasyPost account
- decide whether to configure FedEx credentials in EasyPost or add a carrier-direct fallback later

---

## EasyPost Webhook Requires Public HTTPS Hosting

Status: ACTIVE

Problem:
The webhook route exists locally, but EasyPost cannot deliver production webhooks to localhost.

Risk:
Until the app is deployed publicly and registered with EasyPost, tracking updates still require running the sync script manually or on a scheduler.

Recommended next mitigation:
- deploy the Next.js app to a public HTTPS server
- configure EASYPOST_WEBHOOK_SECRET
- register /api/easypost/webhook in EasyPost
- test webhook HMAC validation with a real EasyPost event

---

## Legacy Multi-Row Purchase Shape

Status: ACTIVE / LOW RISK

Problem:
Some historical multi-game eBay listings were imported from the legacy spreadsheet as duplicate purchases with one purchase_item each instead of one purchase with multiple purchase_items.

Example:
- order 04-14542-23405 currently exists as two purchase records with the same eBay order ID

Current mitigation:
- new manual split item support can represent multi-game listings as multiple purchase_items under one purchase going forward
- eBay sync preserves manual item overrides and skips manual split child rows during fallback matching

Recommended next mitigation:
- decide whether historical duplicate purchases should be merged into one purchase with multiple purchase_items
- avoid bulk merging until receiving/shipment side effects are reviewed

---

## Receiving eBay Listing Images

Status: DECISION PENDING

Problem:
The sampled stored eBay buyer purchase payloads do not include listing image or gallery fields.

Impact:
The receiving detail view has a requirement for main eBay listing image, but the first receiving slice cannot display it from existing stored data.

Current mitigation:
- receiving detail links the eBay title to the eBay listing using supplier listing URL, supplier SKU, or raw eBay ItemID
- eBay buyer sync stores supplier listing URLs from transaction ItemID going forward
- listing links are not the same as image URLs

Options:
- add an eBay item-detail lookup during purchase sync or a backfill and store the primary image URL on purchase_items
- add a receiving-only eBay item lookup when opening detail
- defer images until receiving scan/save behavior is validated
