# DECISIONS.md

# Product Naming

The tool is named Midnight Blue Operations Platform.

Short form: MBOP.

Business entity: Midnight Blue Enterprises, LLC.

---

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

## Shared Navigation Shell

Decision:
Use a compact shared left-side navigation shell for major operational modes.

Reason:
Purchases and Receiving are separate workflows, but operators need fast switching without turning either page into a landing page.

Implementation:
- `web/app/AppShell.tsx`
- current entries are Dashboard, Purchases, and Receiving
- active mode is highlighted
- the shell remains narrow so dense operational tables keep most of the viewport

---

## Dashboard Aggregations Are Backend-Owned

Decision:
Dashboard totals are produced by API routes, not recalculated in React components.

Reason:
The dashboard is intended to validate completeness and accuracy against legacy spreadsheet reporting. Cost totals must use the same authoritative backend landed-cost values as the purchases table.

Implementation:
- `/api/dashboard/purchases` reads `vw_purchases_dashboard`
- monthly units are summed from `quantity`
- monthly cost is summed from `unit_cost * quantity`
- rows with `current_status = return_opened` or `cancelled` are excluded
- rows with `purchase_items.exclude_from_purchase_reporting = true` are excluded
- `/dashboard` renders the returned aggregates only

Rule:
Do not add frontend-only cost math or alternate landed-cost formulas to dashboard components.

---

## Purchase Item Cost Is Net Inventory Cost

Decision:
`purchase_items.unit_cost` represents the item-level inventory cost MBOP should report, not necessarily the visible card/cash payment amount in eBay order history.

Rules:
- eBay reward points or payment method effects must not reduce inventory cost to zero
- for foreign-currency purchases, use eBay-provided USD payment totals when available
- for single-item partial refunds where the item is kept, reduce the purchase item cost by the refund amount
- item-level manual cost corrections set `manual_unit_cost_override = true` and must be preserved by later syncs

Reason:
Dashboard totals need the actual resale inventory cost. eBay payment displays can reflect rewards, currency conversion, refunds, or payment methods that do not map one-to-one to item cost.

Current implementation:
- eBay buyer purchase sync uses transaction price plus shipping/handling by default
- if transaction currency is non-USD and eBay exposes a positive USD payment total, the sync allocates that USD total to item costs
- if a single-item order has a refund total, the sync uses payment plus refund as the net item cost
- multi-item partial refunds are left to explicit return/refund workflow or manual item-level correction to avoid misallocating a refund across unrelated items

---

## Non-Resale Purchases Use Explicit Reporting Exclusions

Decision:
Personal purchases, business supplies, and other non-resale eBay purchases should remain traceable in purchase history but be excluded from purchase reporting with an explicit item-level flag.

Reason:
The eBay buyer account may rarely include purchases that are not resale inventory. Title/system inference is not safe because some real games still have incomplete system data.

Implementation:
- `purchase_items.exclude_from_purchase_reporting`
- `purchase_items.exclusion_reason`
- dashboard API excludes flagged rows from units and cost totals

Rule:
Do not auto-exclude rows from reporting only because they lack ASIN, system, or a recognized game title.

---

## Legacy Spreadsheet Reconciliation Checks Purchases And Returns

Decision:
When reconciling dashboard totals against the legacy reference spreadsheet, compare MBOP purchase items to both the Purchases tab and the Returns tab before excluding or reclassifying a row.

Reason:
Some rows absent from the Purchases tab are legitimate return/case/cancellation rows in the Returns tab. Those should be treated as workflow/status discrepancies, not as personal or non-resale exclusions.

Current rule:
- if an eBay purchase item is on the legacy Purchases tab, leave it reportable unless another explicit rule applies
- if it is absent from Purchases but present on Returns, review/update the MBOP return or cancellation status
- if it is absent from both tabs and confirmed outside the reporting baseline, set `purchase_items.exclude_from_purchase_reporting = true` with a reason

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

Training rule:
Corrections and notes from the title-cleaning training sheet may establish broad rules. A note such as "remove Microsoft" applies to later rows with the same noise pattern even if those rows were not individually edited.

Current use:
- purchases UI Search Amazon links
- RevSeller enrichment normalized title preprocessing

Future use:
Amazon catalog search automation should use this cleaner before searching for candidate ASINs.

---

## Manual Matches Become Reusable Match Memory

Decision:
When an operator manually corrects an ASIN or target sell price in the purchases UI, the backend propagates that correction to other purchase_items with the same normalized title and system, and stores the correction as reusable match memory.

Reason:
Manual review should improve future automation. If a game is missing from the RevSeller sheet, correcting it once should help both current duplicate purchases and later purchases of the same title/system.

Rules:
- never propagate across systems
- do not overwrite rows with a different existing ASIN
- use the same normalized title semantics as RevSeller matching
- store reusable corrections in manual_item_matches

---

## Legacy Purchase Sheet Backfill Is A Controlled Import Path

Decision:
Use the historical "ebay purchases" Google Sheet Purchases tab as a controlled backfill source for missing purchase_items ASINs and target sell prices.

Reason:
The spreadsheet contains historical operator-reviewed ASIN and list price data that can reduce manual review work in the new system.

Implementation:
- script: integrations/backfill_purchase_items_from_purchase_sheet.py
- exported workbook is parsed locally with openpyxl
- matching starts with eBay order number
- multi-row orders require title/system disambiguation
- ambiguous or missing order matches are skipped

Rule:
This is a backfill/import aid, not a new operational source of truth. Supabase remains authoritative after import.

---

## Manual Purchase Item Overrides Are Protected

Decision:
Allow operators to manually edit a purchase item eBay title and purchase price, and preserve those edits through later sync/enrichment processing.

Reason:
Some eBay listings contain multiple games or supplier-title noise that must be corrected at the purchase item level. Purchase price corrections are item-specific accounting inputs and should not be overwritten by a later import pass.

Implementation:
- `manual_title_override` protects edited purchase_items.title values
- `manual_unit_cost_override` protects edited purchase_items.unit_cost values
- eBay buyer purchase sync preserves those protected values when updating an existing item
- ASIN and target sell price can still propagate to same title/system rows, but eBay title and purchase price edits do not propagate

Rule:
Manual source-title and purchase-price edits are item-specific overrides. They must not be used as broad title/system propagation updates.

---

## Multi-Game eBay Listings Use Split Purchase Items

Decision:
Represent a single eBay listing containing multiple games as multiple purchase_items rows under the relevant purchase.

Reason:
Receiving, ASIN review, resale pricing, and future listing workflows operate at the game/item level, not always at the original eBay listing level.

Implementation:
- the purchases drawer can create a manual split item row from an existing purchase item
- split child rows inherit purchase/shipment context
- split child rows are flagged with `manual_split_child`
- eBay buyer purchase sync skips manual split child rows during fallback transaction matching so they are not overwritten by later eBay syncs

Rule:
Do not model multiple games in one eBay listing as a single combined game title when they need separate ASIN, price, receiving, or listing outcomes.

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

## eBay Listing Links Are Derived From Item ID

Decision:
Link supplier/eBay titles to the eBay item listing when a supplier listing URL or eBay item ID is available.

Reason:
Receiving and review workflows benefit from one-click access to the exact supplier listing.

Implementation:
- eBay buyer sync stores `supplier_listing_url` from transaction `ItemID` going forward
- receiving API derives `ebay_listing_url` from `supplier_listing_url`, `supplier_sku`, or raw eBay transaction `ItemID`
- receiving detail links the eBay title to `ebay_listing_url`

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

---

## Received Is A Receiving Workflow Status

Decision:
Add Received as an operational status displayed by the purchases UI when `purchase_items.current_status = received`.

Reason:
After delivery, the operator needs a separate state indicating the item was physically verified as correct. This status belongs to the receiving workflow, but the purchases screen should display it for operational visibility.

Rule:
Purchases may display and filter Received, but the receiving workflow must own the action that sets it.

---

## Listed Is A Workflow-Owned Status

Decision:
Use `purchase_items.current_status = listed` when an item has moved beyond receiving and has been listed on eBay or sent/listed through the Amazon workflow.

Reason:
Listed items should remain part of purchase/inventory reporting, but carrier-derived syncs should not downgrade them back to delivered or in-transit.

Implementation:
- Purchases UI displays and filters Listed
- eBay buyer purchase sync treats Listed as workflow-locked
- legacy status normalization treats Listed as workflow-locked
- the one-time reference spreadsheet status backfill applies explicit `Listed` values from the `status` tab

Rule:
Blank values in the reference `status` tab are not a new status. They leave the existing MBOP status in place, usually a carrier/shipment-derived status such as Ordered, Delivered, No Tracking, or similar.

---

## Receiving Owns Marketplace Assignment

Decision:
Add nullable `purchase_items.marketplace` and set it only during receiving.

Reason:
Marketplace selection is an operational decision made after physical verification. Before receipt, the item may still be wrong, missing, damaged, or return-bound.

Implementation:
- allowed marketplace values are `Amazon` and `eBay`
- receiving detail defaults marketplace to Amazon
- received items save the selected marketplace
- Return Pending and missing split rows leave marketplace unset

---

## Amazon Receiving Requires ASIN And Sell Price

Decision:
Require ASIN and sell price before the receiving workflow can mark an item `Received` when marketplace is `Amazon`.

Reason:
The next workflow after receiving is Amazon shipment/listing preparation. Amazon-bound received items need an ASIN and sell price before they are operationally ready for that handoff.

Implementation:
- receiving detail has editable ASIN and sell price fields at item level
- the Received button is disabled while any Amazon-bound received item is missing ASIN or sell price
- `/api/receiving` enforces the same rule server-side
- marketplace `eBay` does not require Amazon title, ASIN, or sell price

---

## Receiving Metadata Hydration Is Chunked

Decision:
The receiving API fetches purchase item metadata in chunks instead of one large `in (...)` request.

Reason:
The receiving queue can include many rows. A single large PostgREST `in (...)` query may exceed URL/request limits and return incomplete metadata, causing missing Amazon titles and eBay listing links.

Implementation:
- `fetchItemMeta` chunks purchase item metadata lookups
- `fetchPurchaseMeta` chunks purchase metadata lookups
- receiving rows are hydrated with stored `amazon_title`, marketplace, received date, supplier SKU, supplier listing URL, and derived eBay listing URL

---

## Receiving Date Is Stored On Purchase Items

Decision:
Store `purchase_items.received_date` when the receiving workflow marks an item `Received`.

Reason:
Received date is useful for future reporting, listing prioritization, and operational queries that are independent from carrier delivered date.

Implementation:
- receiving API defaults received date to the current America/Los_Angeles local date
- received rows save `received_date`
- Return Pending rows do not set `received_date`
- missing/unreceived split rows do not set `received_date`

---

## Return Pending Is Separate From Return Opened

Decision:
Use `Return Pending` for items identified during receiving as needing return, and keep `Return Opened` for eBay return/case workflow state.

Reason:
An item can be physically received and flagged for return before any marketplace return is opened.

Rule:
Receiving may set `purchase_items.current_status = return_pending`. eBay return sync may set or preserve `return_opened` when a return/case exists.

---

## Cancelled Requires Refund Follow-Up

Decision:
Use `purchase_items.current_status = cancelled` for purchase items cancelled by eBay/seller or identified as cancelled during reconciliation.

Reason:
Cancelled rows should not count as resale purchases, but they still need operational follow-up to ensure the refund was received.

Implementation:
- purchases UI includes Cancelled in the status filter
- dashboard totals exclude Cancelled rows
- eBay buyer sync preserves Cancelled instead of downgrading it to shipment-derived statuses
- status normalization scripts must preserve Cancelled

Future workflow:
The return/refund workflow must include Cancelled items and track refund received / refund missing outcomes.
