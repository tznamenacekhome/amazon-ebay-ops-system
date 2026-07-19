# DECISIONS.md

## Provider Costs Use Provider-Native Sources Only

Decision date: 2026-07-19

The MBOP Provider Costs dashboard may display monetary values only when they
come from supported provider APIs, provider-generated reports, or reproducible
calculations over automatically collected provider/MBOP records. It must not
use bank transactions, credit-card transactions, Plaid-style financial account
feeds, manual invoice uploads, or manual provider-cost entries.

Consequences:

- AWS cost collection uses Cost Explorer for the MVP, with
  `NetUnblendedCost` as the selected service-breakdown and period-total metric.
- Supabase totals remain unavailable when the provider does not return billing
  period dates or monetary totals and maintainable pricing-plus-usage inputs
  are not sufficient for a reproducible calculation.
- EasyPost is tracker-only for MBOP. Wallet funding is displayed, when
  available, as wallet movement and never as tracker expense.
- Provider billing periods stay independent; the dashboard must not display a
  combined current-cycle total across AWS, Supabase, and EasyPost.
- The dashboard shows dollar variance only, never percentage variance, and it
  labels partial current-cycle comparisons as current-cycle comparisons rather
  than finalized variance.

## Purchase ASIN Matching May Use Local Catalog Backup After RevSeller

Decision date: 2026-07-17

RevSeller worksheet rows and operator-confirmed manual match memory remain the
preferred sources for purchase-item ASIN enrichment. When those sources miss,
the enrichment job may use existing local Amazon listing snapshots and Keepa
catalog snapshots as a backup match index, but only through the same
same-system/platform matching gates used by RevSeller matching.

Consequences:

- The backup process improves coverage for valid catalog ASINs that are absent
  from the RevSeller worksheet.
- The backup process must not call Amazon catalog APIs or Keepa product fetches
  during the purchases matching pass; it uses already-stored local snapshots.
- The backup process must not match across systems, invent ASINs, change item
  cost, change workflow status, or override an existing different ASIN.
- Transient Google Sheets failures should not prevent the job from using
  manual match memory and local catalog backup rows.
- Operators can run `integrations/sync_revseller_sheet.py --dry-run` to inspect
  match coverage without modifying `purchase_items`.

## Opportunity Sales History Uses Exact Seller Sales Before Demand Estimates

Decision date: 2026-07-16

Sourcing Opportunities should show exact MBOP seller sales history when Amazon
seller order rows exist for the same ASIN. Exact fields come from
`amazon_sales_order_items` joined to `amazon_sales_orders`: last sale price,
last sale date, and 90/120/365-day unit counts. If exact seller sales are not
available for the ASIN, the UI may show seed context or Keepa demand estimates,
but those estimates must remain labeled as estimates and must not be presented
as MBOP sales.

Consequences:

- New-to-catalog ASINs can still be valid sourcing opportunities without exact
  MBOP sales rows.
- Older catalog ASINs may have zero 90/120/365-day exact sales even when Keepa
  shows current marketplace demand.
- Amazon order-date report imports are the preferred historical backfill path
  for exact sales coverage because they avoid high-volume per-order
  `getOrderItems` throttling.
- Report imports must stay in Amazon-specific sales tables and must not write to
  purchases, receiving, sourcing rules, or marketplace matching corrections.

## Daily Sourcing Uses Remaining Quota Across Coverage Cycles

Decision date: 2026-07-16

When daily catalog sourcing completes the active coverage cycle but still has
usable eBay Browse budget, it should immediately create the next coverage cycle
and continue searching. The daily job must keep a same-run ASIN exclusion set so
an ASIN searched earlier in that job is not searched again in the continuation
cycle.

Consequences:

- Remaining eBay quota can be used after a cycle completes.
- Coverage-cycle history remains meaningful because each cycle is still stored
  separately.
- The UI must show recent completed cycles so operators can see why a run
  continued past a cycle boundary.
- Advisory refreshes after sourcing, such as Matching Intelligence refresh,
  should not mark the sourcing-catalog scheduler group failed when daily
  sourcing itself succeeded.

## ASIN Blocking Is A Product-Level Sourcing Control

Decision date: 2026-07-16

When an Amazon ASIN is known to be unsuitable for replenishment, operators block
it from the Sourcing Workspace bulk `Dismiss selected` modal. This is distinct
from dismissing a single eBay listing: `block_asin` records a dismissed sourcing
action with `asin_blocked` and upserts the ASIN into `sourcing_blocked_asins`.

Consequences:

- Future sourcing seed generation excludes blocked ASINs.
- Existing open/watch/ROI-snoozed opportunities for the same ASIN are dismissed.
- Blocking an ASIN must not be treated as a failed eBay listing match or as
  evidence that similar titles on other ASINs are invalid.
- The single-row dismiss modal may still expose Block ASIN for one-off triage,
  but bulk blocking belongs in `Dismiss selected` because operators often
  discover bad ASINs while reviewing several selected opportunities.

## Retire MBOP Financial Planning Layer After ZFI Verification

Decision date: 2026-07-14

ZFI now owns YNAB integration, business cash, business-value history,
financial-planning views, and long-range finance interpretation. MBOP keeps
operational financial facts only: sales/orders, COGS, fees, operational profit,
inventory value by workflow state, Amazon payout/cash source data, and outbound
summary pushes to ZFI.

Consequences:

- Remove active MBOP YNAB sync jobs and scripts.
- Remove MBOP business-value snapshot production.
- Remove Dashboard Financial and Growth tabs and their API routes.
- Keep Sales Orders and sourcing operational profit/ROI views.
- Keep `integrations/push_zfi_business_summary.py`.
- Prepare, but do not apply automatically, SQL cleanup for exclusive legacy
  objects after audit/retention confirmation.

# Product Naming

The tool is named Midnight Blue Operations Platform.

Short form: MBOP.

Business entity: Midnight Blue Enterprises, LLC.

---

# Core Architecture Decisions

## AWS Scheduler Uses Separate ECS Scheduled Tasks

Decision:
Run production sync jobs through EventBridge Scheduler launching ECS/Fargate tasks, using a scheduler-capable Python image separate from the current web image.

Reason:
The deployed web image is intentionally web-only and built from `web/Dockerfile`. It does not include Python, `run_all_syncs.py`, `integrations/`, or `requirements.txt`, so ECS command overrides cannot safely run scheduler jobs in the web image.

Implementation:
- Scheduler image: `Dockerfile.scheduler`
- ECS task definition target: `mbop-scheduler-task`
- Container name: `mbop-scheduler`
- CloudWatch log group: `/ecs/mbop-scheduler`
- Command override: `python run_all_syncs.py --group <GROUP_NAME>`
- cloud web refresh buttons that need production sync work launch the
  appropriate AWS scheduler group rather than attempting local jobs from the
  web container

Rules:
- Keep `CLOUD_DEPLOYMENT=true`.
- Keep `LOCAL_SYNC_ENABLED=false`.
- Do not use `all`, `core`, or `daily` as AWS production schedules.
- Do not re-enable web/API-triggered local sync execution in cloud.
- Apply scheduler telemetry SQL before replacing local health files with Supabase-backed scheduler health.

---

## EasyPost Webhook Uses ALB Path Bypass Plus Route Secret

Decision:
Expose only `/api/easypost/webhook` without Cognito authentication at the ALB,
then authenticate the webhook inside the Next.js route with the configured
EasyPost HMAC secret and/or outbound token.

Reason:
EasyPost cannot complete Cognito login, but the webhook endpoint still needs a
shared secret before writing shipment state to Supabase.

Implementation:
- ALB listener priority 10 forwards `/api/easypost/webhook` directly to the web target group.
- The route remains POST-only.
- The web ECS task receives `/mbop/prod/easypost/webhook-token` as
  `EASYPOST_WEBHOOK_TOKEN` and `EASYPOST_WEBHOOK_SECRET`.

Rule:
Do not make broader unauthenticated ALB path rules for MBOP APIs.

---

## Shared Shell Owns Logout

Decision:
All MBOP screens expose logout from the shared `AppShell`, routing through
`/api/logout` and Cognito hosted UI logout.

Reason:
Authentication is provided by Cognito/ALB, so logout should clear ALB session
cookies and use the Cognito app-client logout URL rather than adding
page-specific auth controls.

---

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
- current entries are Dashboard, Purchases, Receiving, Send to Amazon, Repricing, Sales Orders, Sourcing, and Reconciliation
- active mode is highlighted
- the shell remains narrow so dense operational tables keep most of the viewport

---

## Dashboard Aggregations Are Backend-Owned

Decision:
Dashboard totals and monitoring summaries are produced by API routes, not recalculated in React components.

Reason:
The dashboard is intended to validate completeness and accuracy against legacy spreadsheet reporting. Cost totals must use the same authoritative backend landed-cost values as the purchases table.

Implementation:
- `/api/dashboard/purchases` reads `vw_purchases_dashboard`
- monthly units are summed from `quantity`
- monthly cost is summed from `unit_cost * quantity`
- rows with `current_status = return_opened` or `cancelled` are excluded
- rows with `purchase_items.exclude_from_purchase_reporting = true` are excluded
- `/dashboard` renders the returned aggregates only
- split dashboard tabs use focused API routes such as
  `/api/dashboard/inventory`, `/api/dashboard/amazon`,
  `/api/dashboard/sourcing`,
  `/api/dashboard/loss-prevention`, and `/api/dashboard/system-health`
- `/dashboard` remains one top-level monitoring workspace; Operations,
  Inventory, Amazon, Sourcing, Loss Prevention, and System Health are tabs
  inside Dashboard, not separate left-nav entries. The former Financial and
  Growth tabs are retired after ZFI verification.

Rule:
Do not add frontend-only cost math or alternate landed-cost formulas to dashboard components.

Do not let dashboard page loads trigger external API calls, sync jobs, workflow
state changes, Amazon price changes, Informed rule changes, or Keepa token
spending. Dashboards summarize and link to owning workflows; they do not become
work queues.

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
When reconciling dashboard totals against the legacy reference spreadsheet, compare MBOP purchase items to both the Purchases tab and the Returns tab before excluding or reclassifying a historical row.

Reason:
Some rows absent from the Purchases tab are legitimate return/case/cancellation rows in the Returns tab. Those should be treated as workflow/status discrepancies, not as personal or non-resale exclusions.

Current rule:
- if an eBay purchase item is on the legacy Purchases tab, leave it reportable unless another explicit rule applies
- if it is absent from Purchases but present on Returns, review/update the MBOP return or cancellation status
- for purchases before 2026-05-16, if it is absent from both tabs and confirmed outside the reporting baseline, set `purchase_items.exclude_from_purchase_reporting = true` with a reason
- for purchases on or after 2026-05-16, MBOP is canonical; absence from the legacy spreadsheet is not an exclusion reason

---

## Purchases Frontend Uses Component + Hook Boundaries

Decision:
Keep the purchases page as a composition layer and move reusable UI and derived logic into web/app/purchases.

Current structure:
- page.tsx composes the workspace
- page.tsx owns UI-local query state such as search, filters, sort, and page
- usePurchases owns API loading, API mutations, save state, and error state
- PurchasesTable, PurchaseDetailDrawer, EditablePriceCell, PurchaseFilters, and PurchaseMetrics own focused UI sections

Reason:
The previous page.tsx monolith increased maintenance risk, truncation risk, and regression risk during AI-assisted edits.

Rule:
Do not place landed cost calculations, matching logic, or receiving workflow behavior in the purchases frontend.

---

## Purchases List Is Server-Driven

Decision:
Purchases table filtering, sorting, pagination, and summary counts are owned by `/api/purchases`, not by the React table.

Reason:
The purchases list is expected to grow by hundreds of rows per month. Loading every row into React and repeatedly filtering/sorting on the client made the screen slow and fragile.

Implementation:
- `/api/purchases` reads a lean page of rows from `vw_purchases_dashboard`
- reporting-excluded purchase items are excluded before database pagination
- status filters use backend-normalized `purchase_items.current_status`
- detail-only metadata such as `amazon_title` and eBay raw payload-derived fields are hydrated only for the returned page
- the default status filter is `active`, meaning all statuses except `listed`
- Missing Data excludes listed, cancelled, return opened, and return pending rows
- browser caching code exists, but it is currently disabled while server-side performance is validated
- Refresh clears any purchases cache entries and reloads from `/api/purchases`

Rule:
Do not reintroduce full-table client-side filtering or sorting for the purchases page. Add backend query parameters or database indexes/views when the list needs new filter/sort behavior.

---

## Screen Data Freshness Is Backend-Owned

Decision:
MBOP screens show screen-specific `Last updated` timestamps near refresh
controls, and those timestamps are provided by API routes rather than frontend
Supabase queries.

Reason:
Different screens are fresh for different reasons. A single page load time or
the newest related sync can be misleading when a screen depends on multiple
operational source timestamps.

Implementation:
- `/api/screen-data-freshness` reads lightweight timestamp signals from source
  tables and local sync files.
- `web/app/DataFreshness.tsx` renders the shared indicator.
- most screens show the newest relevant source timestamp.
- Dashboard uses operational MBOP source timestamps and no longer depends on
  MBOP-owned YNAB or business-value snapshots.

Rule:
Do not show browser reload time as business data freshness. When a screen's data
dependencies change, update `/api/screen-data-freshness` with the relevant
backend-owned source signals.

---

## Purchase Item Status Is Backend-Owned

Decision:
`purchase_items.current_status` is the canonical operational status for purchase items.

Reason:
Filtering and display drifted when the UI derived status from a mix of item, shipment, carrier, and eBay metadata. Status calculation belongs in backend sync/workflow code so every screen filters and displays the same value.

Status writers:
- eBay buyer purchase sync writes initial non-locked statuses.
- EasyPost sync and webhook update linked purchase items from carrier state.
- Receiving owns `received` and `return_pending`.
- FBA/listing workflow owns `listed`.
- Order Problems / return-refund workflow owns `return_opened` and cancellation/refund follow-up.

Workflow-locked statuses:
- `cancelled`
- `listed`
- `received`
- `return_opened`
- `return_pending`

Carrier/status precedence for non-locked rows:
- delivered carrier state or delivered date -> `delivered`
- carrier exception / return to sender -> `exception`
- out for delivery -> `out_for_delivery`
- pickup available -> `available_for_pickup`
- in transit -> `in_transit`
- usable tracking with no carrier scan -> `awaiting_carrier_scan`
- seller shipped without usable tracking -> `shipped_no_tracking`
- no tracking and no shipped signal -> `no_tracking`

Implementation:
- shared Python logic lives in `integrations/status_logic.py`
- one-time backfill lives in `integrations/backfill_purchase_item_statuses.py`
- purchases UI displays and filters stored status values instead of deriving status locally

Rule:
Do not add new UI-only status derivation. Add or update backend status writers when status semantics change.

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

## Sourcing Match Evidence Is Backend-Owned

Decision:
Amazon ASIN -> eBay sourcing matching normalizes and evaluates structured
listing evidence in backend scoring code, not in the frontend.

Implementation:
- Amazon seed platform resolution uses first-class seed `system`, then
  `sourcing_seed_asins.raw_context_json.inferred_system`, then Amazon title
  detection.
- eBay candidate matching parses raw Browse payload evidence, including
  `localizedAspects.Platform`, `Game Name`, `Region Code`,
  `Country of Origin`, `Format`, `Type`, `Features`, `Release Year`, category
  IDs/names, seller description text, and image URL availability.
- `score_sourcing_opportunities.py` writes the resulting backend diagnostics to
  `sourcing_opportunities.matching_diagnostics_json`.
- `/api/sourcing/opportunities` may expose those diagnostics for display, but
  the React workspace must not calculate match decisions itself.

Rule:
Clear wrong-platform, non-game/accessory, digital/service, incomplete-product,
foreign-region, sequel/year, Game Name, and edition/version conflicts should be
hard-blocked before profitability can make a row open. Ambiguous
game-plus-accessory bundles should route to Review.

---

## Sourcing Discovery Uses A Unified Coverage Cycle

Decision:
Daily Amazon ASIN -> eBay sourcing discovery is one quota-driven catalog
coverage cycle, not separate Recent Sales and Full Listings jobs.

Implementation:
- `integrations/run_daily_catalog_sourcing.py` owns the daily runner.
- `integrations/sourcing_coverage_cycle.py` builds the durable ASIN queue and
  coverage metrics.
- Queue priority is recently sold ASINs, purchased Amazon-bound items not yet
  sent to Amazon, then remaining eligible catalog ASINs.
- Queue eligibility is backend-scoped to video game catalog ASINs before rows
  are persisted; frontend code must render the saved queue and diagnostics only.
- The runner reads eBay Developer Analytics for the Browse quota and spends the
  usable daily budget instead of trying to fill a fixed count of opportunities.
- `/api/sourcing/runs` starts `daily_catalog_sourcing`; the Coverage Cycle UI
  renders backend cycle, queue, quota, and run diagnostics.

Rule:
This remains advisory Amazon-to-eBay replenishment sourcing only. MBOP must not
auto-purchase, bid, submit offers, or add eBay-to-Amazon sourcing through this
workflow.

Production deployment note:
As of the 2026-07-14 deployment verification, the production
`mbop-sourcing-catalog` EventBridge schedule targets digest-pinned
`mbop-scheduler-task:21`, built from repository HEAD
`56a34347dd8eb515161e32ef88bdcd24d92a3fcb`. This deployment moves the daily
coverage-cycle scheduler from the older pre-optimization scheduler image to the
image that includes one platform-aware eBay Browse query per ASIN, category
`139973`, 200-result searches, pre-detail filtering, lazy detail enrichment,
and persisted `raw_summary_json.ebay_search` diagnostics. The deployment did
not change sourcing business rules or production data.

---

## Matched Amazon Title Is Stored Separately

Decision:
Store the matched Amazon/RevSeller title in purchase_items.amazon_title while preserving the eBay supplier title in purchase_items.title.

Reason:
Operators need to review the matched Amazon identity without losing the original supplier listing title used for traceability and ambiguity checks.

Display:
The purchases table uses amazon_title as the primary item title for matched ASIN rows when available, and shows the eBay title underneath prefixed with "ebay: ".

Rule:
If an ASIN exists but no Amazon title is stored, the operator may manually fill `purchase_items.amazon_title` from the purchase detail drawer. FBA should not silently substitute the eBay supplier title as an Amazon title.

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
- operators may correct a purchase item system from the canonical pick list in the purchase detail drawer

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
Manual source-title, system, and purchase-price edits are item-specific overrides. They must not be used as broad title/system propagation updates.

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

## Amazon FBA Shipment Workflow Is Separate

Decision:
Use a separate Amazon FBA workflow for preparing Received Amazon-bound inventory for Amazon shipment creation and tracking Amazon receiving/availability after the shipment is saved.

Reason:
FBA shipment preparation happens after receiving and before/while listing. It should not be mixed into purchase review or receiving verification.

Implementation:
- `/fba` displays the Send to Amazon workspace with prep and shipment tabs
- `/api/fba-shipments` owns Supabase reads/writes
- Received Amazon-bound purchase items are grouped by ASIN
- grouped cost per unit is quantity-weighted from `vw_purchases_dashboard.unit_cost`
- grouped purchase date uses the oldest purchase date
- grouped title is the stored Amazon title only
- if the current Received row has a blank Amazon title, the API may use another purchase item with the same ASIN as the display-title fallback
- grouped sell price uses the highest non-null target sell price

Save behavior:
- operator enters the Amazon shipment ID
- included quantities are linked to `fba_shipments` and `fba_shipment_items`
- Amazon Return Recovery source rows are linked through
  `fba_shipment_source_items` so non-purchase return inventory can be saved in
  FBA shipments without writing to `purchase_items`
- included quantities move from `received` to `listed`
- excluded quantities remain `received`
- partial included quantities split the purchase item so only the included quantity becomes `listed`
- non-historical saved shipment links are projected into `inventory_positions` as `outbound_to_amazon` only for quantities Amazon has not yet received or made available
- `integrations/amazon_sync_fba_shipments.py` reads Amazon inbound shipment status and item quantities, then updates fulfillment center, receiving counts, FBA availability, milestone timestamps, and remaining outbound value on FBA shipment workflow rows
- SP-API carrier/tracking fields are stored when Amazon exposes them, but legacy v0 transport details currently return an Amazon deprecation error for the current shipment and v2024 inbound-plan discovery did not expose useful carrier details in June 2026 testing

Historical marker:
Use `legacy_listed_no_shipment_id` for already Listed items that predate MBOP shipment ID tracking. This value is not a real Amazon shipment ID.

Rule:
Do not mark excluded or damaged units Listed during FBA save. They must remain Received or move through a later exception workflow.

Amazon Return Recovery items may be routed into FBA only through the
non-purchase bridge after manual inspection confirms the observed condition is
New and the final disposition is Send to Amazon.

---

## Amazon Return Recovery Is Separate From Purchases

Decision:
Use Amazon-specific return recovery tables and workflow state for FBA customer
returns, reimbursements, and removals returned to the business.

Reason:
Amazon customer returns and removals are not eBay purchases, Receiving rows, or
Order Problems cases. They have different evidence sources, identifiers, and
case/reimbursement paths.

Implementation:
- `/amazon-return-recovery` displays the Amazon Returns queue and detail drawer
- `/api/amazon/return-recovery` and related action routes own backend reads and
  workflow mutations
- customer return and reimbursement report rows are imported into
  Amazon-specific raw row tables
- manual inspection/disposition is stored in `amazon_return_recovery_cases`
  with append-only events in `amazon_return_recovery_events`
- FBA shipment routing uses `fba_shipment_source_items` instead of
  `purchase_items`

Rule:
Amazon return reason/disposition is evidence only. Final condition and
disposition require manual inspection, and Seller Central cases remain manual
unless a future approved Amazon write workflow is designed.

---

## Amazon SP-API Foundation Is Read-Only And Separate

Decision:
Add Amazon SP-API support as a Python integration foundation for approved read-only Amazon inventory, listing, pricing, shipment, finance, reports, and non-PII order reads.

Reason:
MBOP needs Amazon seller/FBA visibility for inventory confidence and future Keepa/Amazon matching work, but Amazon seller sales/orders and customer data are separate operational domains and must not contaminate purchase history.

Implementation:
- `integrations/amazon_spapi_client.py` handles Login with Amazon refresh-token exchange and sends SP-API requests with the LWA access token header.
- AWS SigV4 signing is optional legacy compatibility and is used only when `AMAZON_SP_API_USE_SIGV4=true`.
- `integrations/amazon_test_connection.py` smoke-tests LWA auth and a safe FBA inventory summary read.
- `integrations/amazon_sync_fba_inventory.py` paginates FBA inventory summaries, upserts `amazon_skus`, and inserts point-in-time `amazon_fba_inventory_snapshots`.
- `integrations/amazon_sync_listing_status.py` reads Listings Items status/issues for Amazon SKUs and inserts point-in-time `amazon_listing_snapshots`.
- `integrations/amazon_sync_fba_shipments.py` reads Fulfillment Inbound shipment status and item quantities for saved Amazon shipment IDs.
- the client allow-list is limited to approved read-only Amazon paths, including FBA inventory, Fulfillment Inbound, Listings Items, Product Pricing, Orders, Finance, and Reports.
- no restricted-data-token flow is implemented.
- buyer, address, and other PII-oriented endpoint usage is not allowed.
- Amazon seller/FBA/listing/shipment data belongs in Amazon-specific or FBA workflow tables, not purchases or purchase_items.

Rule:
Do not write Amazon seller sales/orders into `purchases` or `purchase_items`. Purchase history remains supplier-purchase data; Amazon seller inventory/listing/pricing data gets its own tables and later API/UI surfaces.

---

## Keepa Is Read-Only Catalog Intelligence

Decision:
Use Keepa as a separate read-only catalog intelligence source for price history, sales-rank history, sales-rank drop frequency, offer context, reviews, and ratings.

Reason:
Keepa can improve pricing confidence, sales-frequency review, ASIN validation, and future catalog candidate workflows, but it is not an operational purchase, receiving, shipment, or seller-order source of truth.

Implementation:
- `keepa_product_snapshots` stores point-in-time product snapshots and the raw Keepa payload.
- `keepa_product_history_points` can store selected normalized time-series points when explicitly requested.
- `vw_latest_keepa_product_snapshot` exposes the latest product snapshot per ASIN/domain.
- `integrations/keepa_client.py` owns API auth, token status, and safe request handling.
- `integrations/keepa_sync_products.py` defaults to dry-run and requires `--write` before inserting rows.
- `--plan-only` must be used before broad syncs to inspect ASIN count and token availability.

Rule:
Keepa data must not write to `purchases`, `purchase_items`, receiving rows, FBA shipment rows, or Amazon SP-API seller workflow tables. Future use of Keepa for ASIN matching must produce operator-review candidates before any workflow-owned correction is applied.

---

## Informed Repricer Is Read-Only Advisory Intelligence

Decision:
Use Informed Repricer Reports API snapshots as advisory input for manual repricing decisions, not as a workflow or pricing source of truth.

Reason:
The aged inventory workflow needs visibility into current Informed price, Buy Box context, assigned rule, and min/max floor behavior. However, changing repricer settings or prices is operationally risky and should remain manual until recommendations prove reliable.

Implementation:
- `informed_report_runs` stores read-only report request/import metadata.
- `informed_listing_snapshots` stores point-in-time listing/pricing report rows and raw row payloads.
- `informed_rule_snapshots` is available for rule/settings reports if a suitable report is used later.
- `informed_rule_name_overrides` stores manual rule ID -> friendly name display mappings when reports only expose numeric strategy IDs.
- `integrations/informed_sync_reports.py` uses only the Reports API request/status/download endpoints.
- `/api/amazon/repricing-advisor` joins latest Informed listing snapshots by seller SKU where ASIN is unavailable.
- `/api/amazon/repricing-advisor` maps known Informed strategy IDs to friendly rule names for display while preserving the raw ID.

Rule:
Do not call Informed Listings Management API feed/upload endpoints, modify Informed rules, modify min/max prices, modify Amazon prices, or write Informed data into purchases, purchase_items, Amazon SP-API tables, Keepa tables, receiving rows, or FBA workflow tables.

---

## Aged Amazon Inventory Repricing Advisor Is Manual-Only

Decision:
Build the aged Amazon inventory repricing advisor as a read-only recommendation layer generated by backend API logic.

Reason:
The operator needs a capital-recovery work queue for aged FBA inventory, but repricing automation is risky until recommendations prove reliable. The first slice should support manual decisions in Informed.co or Seller Central.

Implementation:
- `/api/amazon/repricing-advisor` computes recommendations from latest stored Amazon FBA inventory, Amazon listing snapshots, InventoryLab backfill, inventory positions, and latest Keepa snapshots.
- `/repricing` renders API-provided recommendation rows and summary metrics only.
- recommendation thresholds are backend constants near the top of the API route.
- rows are evaluated into Healthy, Watch, Reprice, Liquidate, Remove / eBay, or Needs Data.
- no recommendation rows are persisted yet; the first version is generated from current stored source data.

Rule:
Do not write prices to Amazon, call Amazon write endpoints, modify Informed.co settings, or write recommendation outcomes into purchases, purchase_items, receiving, or FBA shipment workflow rows. Frontend components must not recalculate recommendation tiers, capital, or cost basis.

---

## Repricing Advisor Separates Pricing Work From Inventory Exceptions

Decision:
Separate aged Amazon inventory into advisor buckets: Pricing, Inventory / Listing Issue, and Missing Data.

Reason:
The operator wants aged but otherwise sellable inventory to become a repricing work queue, not an automatic removal/liquidation queue. Suppressed, unsellable, restricted, or otherwise broken inventory needs a different operational workflow than normal aged inventory.

Implementation:
- `/api/amazon/repricing-advisor` assigns the advisor bucket.
- `Pricing` rows are aged sellable inventory without listing/condition exceptions.
- `Inventory / Listing Issue` rows have unsellable quantity or non-buyable/suppressed listing status where repricing alone may not help.
- buyable/discoverable listings with Amazon catalog metadata issues are not treated as action issues and are not surfaced in MBOP.
- `Missing Data` rows are missing required ASIN, cost, age, Keepa, Informed, or pricing context.
- Reprice target price uses a 3% markdown below Buy Box/reference while respecting a cost + 10% floor.
- Liquidate target price uses an 8% markdown below Buy Box/reference while respecting a cost + 10% floor.
- Amazon Inventory Planning 30/90-day shipped-unit fields classify sales velocity as Strong, Moving, Slow, No recent sales, or Unknown.
- target markdowns are adjusted by sales velocity so strong sellers receive gentler recommendations and no-recent-sales rows receive firmer recommendations.
- `/repricing` renders the API-provided bucket and target price only.

Rule:
Target prices are manual advisory outputs for Informed.co/Seller Central review. They must not be written to Amazon, Informed, purchase_items, receiving, or FBA workflow tables.

---

## Repricing Competition Detail Comes From Stored Keepa Offers First

Decision:
Use stored Keepa offer-level payloads as the first competition-detail source for the Aged Amazon Inventory page.

Reason:
The operator needs competitor seller, price, fulfillment, Buy Box, and estimated stock context while reviewing aged inventory. Keepa can provide richer seller/offer detail than the current Amazon FBA inventory and listing snapshots, but Keepa tokens are limited and should not be spent automatically by dashboard page loads.

Implementation:
- `/api/amazon/repricing-advisor` reads `raw_keepa_json` from the latest Keepa product snapshot.
- `/repricing` opens a row-level Competition drawer that renders API-provided seller/offer details.
- if the stored Keepa snapshot does not contain offer-level rows, the drawer shows summary data and recommends targeted Keepa offer sync.
- Amazon Product Pricing can be added later as a supplemental current-pricing validation source, but it should not replace Keepa as the richer competitor-depth source.

Rule:
The frontend must not call Keepa directly or trigger token-spending syncs. Keepa competitor data remains read-only catalog intelligence and must not write to purchase, receiving, FBA workflow, Amazon snapshot, or Informed snapshot tables.

---

## Repricing Snoozes Are Advisory Workflow State

Decision:
Store Aged Amazon Inventory snoozes in an Amazon repricing-advisor-specific table.

Reason:
The operator needs to temporarily remove reviewed rows from the default work queue without changing Amazon, Informed, Keepa, inventory, purchase, receiving, or FBA workflow ownership. Snooze is page workflow state, not inventory state.

Implementation:
- `amazon_repricing_advisor_snoozes` stores seller SKU, ASIN, snoozed timestamp, and snoozed-until timestamp.
- `/api/amazon/repricing-advisor` reads active snoozes and marks rows as snoozed.
- `/api/amazon/repricing-advisor` `POST` upserts a 30-day snooze.
- `/repricing` defaults to Not Snoozed and can switch to All.
- summary metrics split active/not-snoozed and snoozed counts/capital.

Rule:
Snoozes must not write to Amazon, Informed, Keepa, purchases, purchase_items, receiving rows, FBA workflow rows, or inventory positions.

---

## Amazon Inventory Planning Is The Repricing Age Source

Decision:
Use Amazon's `GET_FBA_INVENTORY_PLANNING_DATA` report as the preferred active-FBA inventory age signal for the aged Amazon inventory repricing advisor.

Reason:
The operator wants age to reflect when Amazon considers current units aged in FBA, not simply the oldest purchase date. Amazon planning data is not exact per-unit available-for-sale history, but it is Amazon's native inventory-health view and is a better first-pass signal than InventoryLab purchase dates for repricing decisions.

Implementation:
- `integrations/amazon_sync_inventory_planning.py` requests and imports the read-only planning report.
- `amazon_report_runs` stores report request/import audit metadata.
- `amazon_inventory_planning_snapshots` stores point-in-time SKU-level planning rows.
- `vw_latest_amazon_inventory_planning_snapshot` exposes the latest planning row per seller SKU and marketplace.
- `/api/amazon/repricing-advisor` prefers Amazon planning age buckets over InventoryLab/MBOP fallback dates.

Rule:
InventoryLab and MBOP dates remain fallback context only for repricing age. Do not infer exact per-unit FBA available-for-sale dates from ledger or shipment history until the planning-data approach proves insufficient.

---

## Repricing Advisor Is An Action List

Decision:
The Aged Amazon Inventory page should show inventory requiring operator action, not every active FBA unit.

Reason:
Inventory under 90 days old and normal Amazon movement states such as inbound or FC transfer do not usually require manual repricing or operational action. Showing those rows adds noise.

Implementation:
- rows under 90 days old are filtered out unless they have an actionable issue.
- rows with Informed `current-velocity` greater than zero are filtered out because recent sales mean the item is moving and does not need aged-inventory action.
- FC transfer is normalized from Amazon reserved inventory detail and displayed as inventory detail.
- FC transfer, inbound movement, future supply, and FC processing are not treated as issues by themselves.
- actionable issues remain unsellable quantity, Amazon listing issues/suppression, aged price review, liquidation age, and missing data needed for safe repricing.

Rule:
Do not classify FC transfer as sold, missing, or a removal/eBay issue unless another source indicates a real problem.
Use Informed `current-velocity` as a temporary sales-velocity signal only. Replace it with Amazon order/sales data when the Amazon Orders And Sales integration is built.

---

## Inventory State Is A Derived Reconciliation Layer

Decision:
Add a unified inventory-position and reconciliation layer, but keep existing workflow tables authoritative for their own domains.

Reason:
MBOP needs to reconcile operational inventory against Amazon FBA inventory, support future eBay inventory, and track transfers between Amazon and eBay without collapsing every workflow into one giant status field.

Implementation:
- `inventory_positions` stores derived current positions.
- `inventory_movements` is reserved for append-only inventory transition audit records.
- `inventory_reconciliation_events` records reconciliation runs.
- `inventory_reconciliation_event_items` records item-level findings.
- `integrations/inventory_reconcile.py` projects current positions and compares MBOP Amazon-intended inventory to latest Amazon FBA snapshots.
- latest Amazon listing snapshots feed stranded/suppressed-style reconciliation findings without adding duplicate inventory quantities.
- dashboard Inventory Visibility reads API-provided inventory metrics and findings.

State model:
Inventory is represented with separate dimensions:
- physical location
- marketplace intent
- listing channel
- operational status
- inventory condition/disposition
- explicit inventory state label

Ownership boundary:
- purchases/purchase_items remain authoritative for acquired inventory.
- receiving owns receiving verification and marketplace assignment.
- Amazon FBA workflow owns shipment prep/listed transitions.
- Amazon SP-API tables own external Amazon inventory and listing snapshots.
- inventory_positions is derived from those sources and can be rebuilt.

Rule:
Do not write reconciliation corrections directly into workflow tables unless a specific workflow action owns that correction. Reconciliation findings should surface review work first.

Refinements:
- Amazon-unknown-to-MBOP and quantity-mismatch cleanup was held until the 2025
  Amazon sales backfill and eBay purchase FIFO allocator ran. After rerunning
  reconciliation, examples such as `B002BRYXRQ` still show that some Amazon FBA
  units have eBay purchase records but no current MBOP FBA shipment/active
  inventory lineage; those belong to future inventory-position resolution, not
  sales COGS allocation.
- Amazon reserved inventory is normal Amazon processing and should not be
  treated as a problem queue item by itself.
- Amazon listing/catalog issue signals are not actionable when Amazon reports
  your FBA units as sellable; these should be ignored as reconciliation
  problems unless inventory becomes non-buyable, stranded without sellable
  quantity, or unsellable.
- Amazon removal orders for damaged/unsellable units need a future workflow that
  tracks the removal, receiving the returned unit, deciding whether it is still
  new/sellable, and sending it back to Amazon when appropriate.
- Amazon receiving discrepancies, lost inventory, warehouse damage, and customer
  return exceptions belong in a future Amazon Inventory Discrepancy workflow.

Canonical inventory definition:
Current canonical inventory equals current Amazon FBA inventory plus MBOP purchase inventory that has not yet reached the Listed workflow state, plus current non-historical FBA shipment links that are on the way to Amazon. Purchase rows with `purchase_items.current_status = listed` remain useful for purchase amount/frequency and historical analysis. Listed rows without a current FBA shipment link are treated as sold-through/history in the purchase projection; listed rows with a current FBA shipment link are projected as `outbound_to_amazon`. Current active Amazon inventory is represented by Amazon SP-API snapshot positions.

---

## InventoryLab Active Inventory Backfill Is Historical Context Only

Decision:
Store InventoryLab active inventory cost/date data in a separate legacy backfill table and use it as an overlay for Amazon FBA inventory positions.

Reason:
InventoryLab contains historical cost basis and purchase-date context for active Amazon FBA inventory that predates MBOP as the operational source of truth. That context is useful for reconciliation and valuation, but it should not overwrite MBOP purchase_items or workflow-owned costs.

Implementation:
- `inventorylab_active_inventory_backfill` stores the original CSV row payload, match method, match status, MSKU, ASIN, FNSKU, quantity, cost, supplier, and purchase date.
- `integrations/inventorylab_active_inventory_backfill.py` defaults to dry-run and active On Hand rows only.
- matching order is MSKU first; ASIN/title fallback only creates review candidates; ambiguous rows are not auto-matched.
- `integrations/inventory_reconcile.py` reads matched MSKU backfill rows and applies cost/date context to derived Amazon FBA positions.

Rule:
Going forward, MBOP purchase_items, receiving, and FBA workflows own purchase cost, receipt date, marketplace assignment, and listing transitions. InventoryLab backfill is historical context only.

---

## InventoryLab Valuation Is The Legacy Amazon FBA Opening Balance

Decision:
Store InventoryLab inventory valuation exports in a separate snapshot table and use the latest valuation snapshot as the preferred current value for legacy inventory already at Amazon FBA.

Reason:
InventoryLab's active inventory export contains an `Active Cost/Unit` field, but its inventory valuation report uses InventoryLab's current remaining on-hand cost basis by MSKU. For replenished SKUs, `Active Cost/Unit * Amazon quantity` can overstate or understate the current value compared with InventoryLab's valuation report. The 2026-05-26 valuation reconciliation showed MBOP and InventoryLab both had 761 Amazon units, but MBOP was $143.47 higher because it was multiplying active cost/unit by current quantity.

Implementation:
- `inventorylab_inventory_valuation_snapshots` stores the raw InventoryLab valuation rows with MSKU, fulfillment, inbound quantity, on-hand quantity, unlisted quantity, cost/unit, and total value.
- `vw_latest_inventorylab_inventory_valuation` exposes the latest imported valuation row per MSKU.
- `integrations/inventorylab_inventory_valuation_import.py` defaults to dry-run and imports only into the InventoryLab valuation snapshot table when `--apply` is passed.
- dashboard Inventory Visibility uses the latest InventoryLab valuation snapshot for the "At Amazon FBA" value when available, and uses MBOP-derived costs for outbound-to-Amazon, received, ordered, and other non-Amazon-held inventory.

Rule:
Do not write InventoryLab valuation values into `purchase_items`. Treat the valuation snapshot as the opening balance for legacy Amazon FBA inventory. MBOP-owned purchase/receiving/FBA workflows are authoritative for go-forward inventory cost.

---

## YNAB Business Category Is Cash On Hand

Status:
Superseded by "Retire MBOP Financial Planning Layer After ZFI Verification"
on 2026-07-14. ZFI now owns YNAB integration and business cash. MBOP YNAB sync
jobs and dashboard dependencies have been removed from active operation.

Decision:
Use the current available balance of the YNAB category named `Business` as MBOP's cash-on-hand dashboard value.

Reason:
The Business category is the operator-defined envelope for business cash flow in YNAB. It includes resale purchases and non-inventory business expenses such as software licensing and insurance, so its category balance is a better fit for MBOP's current cash-on-hand concept than summing bank account balances.

Implementation:
- `YNAB_PERSONAL_TOKEN` authorizes read-only YNAB access.
- `ynab_category_balance_snapshots` stores point-in-time category balance snapshots.
- `integrations/ynab_sync_cash_balance.py` reads YNAB plans/categories and writes the selected category balance when `--apply` is used.
- dashboard Inventory Visibility reads `vw_latest_ynab_category_balance_snapshot` for the `Business` category and renders the backend-provided cash value.

Rule:
YNAB data must stay in YNAB-specific snapshot tables. Do not write YNAB balances into purchases, purchase_items, inventory_positions, Amazon snapshots, or workflow tables.

---

## ZFI Owns Financial Planning And Tax Reporting

Architecture docs:
See `docs/architecture/README.md`,
`docs/architecture/SYSTEM_BOUNDARIES.md`,
`docs/architecture/DATA_FLOW.md`, and
`docs/architecture/INTEGRATION_PRINCIPLES.md`.

Decision:
MBOP remains the operational source of truth for the resale business. ZFI is the
go-forward owner for household finance, business cash planning, business value
history after one-time MBOP backfill, business net worth in household context,
cash-flow planning, Schedule C/tax classification, quarterly taxes, owner
draws/contributions, and long-range financial planning.

Implementation:
- MBOP may compute and display operational profitability, inventory value,
  Amazon cash state, COGS diagnostics, and item/order-level resale metrics.
- MBOP must not become the personal finance or tax system.
- MBOP-to-ZFI integration is summary-first. MBOP pushes summarized
  business-operational finance payloads outward to ZFI Supabase through
  `integrations/push_zfi_business_summary.py`.
- MBOP does not query ZFI and does not import ZFI personal finance data.
- ZFI auth, user tables, and service-role credentials stay separate from MBOP.
- Existing MBOP YNAB, business value, and Schedule C planning surfaces are
  retired after ZFI verification.
- MBOP YNAB sync has been removed from active orchestration; do not
  reintroduce it.

---

## Amazon Finance Cash Is Separate From Inventory

Decision:
Use read-only Amazon Finance data to represent value that has moved out of inventory and into Amazon-held cash or Amazon-to-bank in-transit cash.

Reason:
After Amazon sells and ships an item, the business no longer considers that unit's cost basis part of inventory value. The value should move to Amazon cash once Amazon reports the net proceeds in its payments/finance bucket, and then to cash-in-transit when Amazon sends funds to the bank.

Implementation:
- `amazon_finance_balance_snapshots` stores point-in-time Amazon Finance balance snapshots.
- `integrations/amazon_sync_finance_balances.py` reads read-only Finances endpoints only.
- total Amazon cash is calculated as `DEFERRED` transaction total plus Open financial event group totals.
- Amazon-to-bank in-transit cash is calculated from financial event groups with `ProcessingStatus = Closed` and `FundTransferStatus = Processing`.
- dashboard Inventory Visibility reads `vw_latest_amazon_finance_balance_snapshot`.

Current dashboard use:
MBOP stores Amazon's open/available finance balance as `available_to_withdraw` and displays it as Seller Central Funds Available. The dashboard links that value to Seller Central Payments so the operator can request transfer manually.

Rule:
Amazon Finance data must stay in Amazon-specific finance snapshot tables. Do not write it into purchases, purchase_items, inventory_positions, Amazon inventory snapshots, or workflow tables.

---

## Seller Central Account Health And Feedback Are Amazon Dashboard Signals

Decision:
Display Seller Central account-health and feedback signals on the Amazon dashboard, not System Health.

Reason:
System Health is for MBOP job/database/API freshness. Seller Central Account Health and Feedback Manager values are marketplace trust/risk signals for the Amazon selling channel.

Implementation:
- `amazon_account_health_snapshots` stores manual account-health score snapshots.
- `amazon_seller_feedback_snapshots` stores manual Feedback Manager lifetime star-rating and rating-count snapshots.
- `amazon_seller_feedback_items` stores seller feedback rows.
- `integrations/amazon_record_seller_account_health.py` records manual account-health and feedback observations.
- `integrations/amazon_sync_seller_feedback.py` requests the read-only Amazon Reports API `GET_SELLER_FEEDBACK_DATA` report when available.
- Amazon documents `GET_SELLER_FEEDBACK_DATA` as neutral/negative seller feedback only, so the dashboard treats imported 1-3 star rows as alerts instead of trying to show all recent positive feedback.

Rule:
Seller Central account-health and feedback data must stay in Amazon-specific dashboard/snapshot tables. Do not write it into purchases, purchase_items, inventory positions, or workflow-owned tables.

---

## Total Business Value Is Snapshotted Daily

Status:
Superseded by "Retire MBOP Financial Planning Layer After ZFI Verification"
on 2026-07-14. Historical `business_value_snapshots` are retained only as
migration/audit context until cleanup; ongoing business value history belongs
in ZFI.

Decision:
Store one backend-computed total business value snapshot per day for trend reporting.

Reason:
The dashboard's total business value is a rollup across multiple sources: Amazon inventory valuation, MBOP pre-Amazon inventory, Amazon Finance cash, Amazon-to-bank in-transit cash, and YNAB cash on hand. Persisting one daily point makes the trend auditable and avoids trying to reconstruct historical totals from changing source snapshots.

Implementation:
- `business_value_snapshots` stores daily rollups and the raw component context used to calculate the total.
- `integrations/business_value_snapshot.py` computes and upserts the daily row.
- `/api/dashboard/purchases` returns business value history from `business_value_snapshots`.
- the dashboard Total row opens a graph modal using API-provided history values.
- Amazon outbound value uses MBOP cost for saved current FBA shipment links and includes only Amazon inbound cost whose ASIN is not already covered by a saved MBOP outbound shipment.

Rule:
Business value snapshots are reporting snapshots only. They do not write back to purchases, purchase_items, inventory_positions, Amazon Finance snapshots, YNAB snapshots, or workflow tables.

---

## ASIN Is The Primary Amazon Inventory Identity

Decision:
Use ASIN as MBOP's primary product identity for Amazon inventory reconciliation. Keep MSKU/Seller SKU for Amazon traceability and InventoryLab import matching, but do not build a required SKU-to-MBOP mapping framework as a core product identity layer.

Reason:
The operation usually has one active Amazon listing per ASIN. Multiple listings for the same ASIN are rare and mostly limited to a future edge case where FBA and Merchant Fulfilled inventory exist for the same product.

Implementation rule:
- Amazon SP-API inventory still stores `seller_sku`, `fnsku`, and `amazon_sku_id`.
- InventoryLab backfill may match by MSKU because that is the safest row-level import key.
- dashboard and reconciliation should answer product/inventory questions primarily by ASIN.
- only add deeper MSKU-level workflow mapping if FBA/MFN split inventory becomes operationally important.

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

Implementation:
Order Problems seeds cancelled rows as `cancelled_refund_followup` cases and
keeps them visible until the operator confirms refund receipt or closes the
case.

---

## Order Problems Is The Return/Refund Workflow Surface

Decision:
Do not create a separate Returns left-nav item for the MVP. Purchases -> Order
Problems is the unified queue for delivery problem candidates, return-needed
items, eBay return/case follow-up, missing-item/replacement follow-up, and
cancelled/refund confirmation.

Reason:
Late deliveries, stale tracking, receiving return decisions, eBay returns, and
refund follow-up are all purchase-item exceptions. Keeping them in one queue
preserves operator context and avoids splitting related work across screens.

Implementation:
- `order_problem_cases` stores one persistent open workflow row per purchase
  item, plus closed/resolved history.
- `order_problem_events` stores the append-only timeline.
- `/api/order-problems` owns candidate detection, stage filtering, sorting,
  pagination, and summary counts.
- `/api/order-problems/[id]/actions` supports MBOP-local workflow actions.
- `integrations/ebay_sync_order_problem_returns.py` is read-only and writes only
  local case/event records.

Safety:
MBOP does not create eBay returns, send messages, accept offers, escalate cases,
issue refunds, or upload files in this MVP. Marketplace actions happen manually
on ebay.com.

---

## Dashboard Separates Value, Problems, And Reconciliation

Decision:
Keep the main dashboard focused on inventory/cash value and operational backlog counts, and move detailed inventory reconciliation findings to a dedicated Reconciliation page.

Reason:
The dashboard was mixing value summary, purchase cleanup, order problems, and reconciliation rows in one screen. Reconciliation findings have different source semantics and resolution paths than purchase missing-data/order-problem rows, so they should not compete with the main inventory value view.

Implementation:
- Dashboard starts with Inventory Visibility.
- The old top Total Units / Total Cost / Months cards were removed.
- Inventory By Location was renamed Inventory Value By Location.
- Amazon Sellable is labeled Amazon FBA Sellable and clarified as Amazon-reported fulfillable/sellable units.
- Open reconciliation findings live on `/inventory-reconciliation`.
- Purchases review-state filter keeps `Missing Data` in the normal editable table.
- Order Problems uses a dedicated Purchases tab with issue/age-focused columns.

Reason:
Missing data cleanup benefits from the normal editable purchase columns, while order problems need issue, age, ETA, tracking, and follow-up guidance.

---

## Amazon Sales Orders Are 2025-Forward

Decision:
Treat `2025-01-01` as the operating cutoff for Amazon Sales Orders data in MBOP.

Reason:
The business has much older Amazon history, but MBOP's go-forward analytics and
COGS work should not require reconstructing ten years of purchases. Amazon can
return old orders during incremental syncs when those orders receive a recent
`LastUpdatedDate`, so relying only on `LastUpdatedAfter` can import orders
outside the intended operating window.

Implementation:
- Amazon sales order sync skips orders whose `PurchaseDate` is before
  `2025-01-01T00:00:00Z`
- the sales history backfill rejects start dates before 2025-01-01
- finance, Veeqo label, and profitability jobs clamp broad order selection to
  2025-01-01 or later
- the Sales Orders API clamps requested start dates to 2025-01-01 or later
- pre-2025 cleanup SQL exists for the two old orders imported before the
  guardrail was added

---

## Sales Missing Fees Display Depends On Fulfillment Status

Decision:
Keep the stored `amazon_sales_profitability.data_status = missing_fees` value,
but split the UI display by Amazon order status.

Reason:
For newly ordered Amazon items, fees can be absent until Amazon ships the item
and posts financial events. Calling those rows "Missing Fees" made normal
in-flight orders look like data defects. Once an order is shipped or otherwise
fulfilled, missing financial events are more likely to represent a sync/data
gap that needs follow-up.

Implementation:
- `missing_fees` plus `Pending`, `PendingAvailability`, or `Unshipped` displays
  as `Pending`
- `missing_fees` plus `PartiallyShipped`, `Shipped`, or `InvoiceUnconfirmed`
  displays as `Missing Fees`
- the Sales Orders API exposes separate summary counts and filter options for
  Pending and Missing Fees

---

## Sales Finance Uses Transactions API As Missing-Fee Fallback

Decision:
Keep the legacy order-specific financial-events endpoint as the first source
for Amazon Sales Orders fees, but also store rows from
`/finances/2024-06-19/transactions` and use them as a fallback when the legacy
endpoint is empty.

Reason:
Seller Central can show a `DEFERRED` transaction with a full order fee
breakdown while the legacy `listFinancialEventsByOrderId` response is still
empty. The Transactions API exposes the transaction status and nested
`AmazonFees` breakdown, which lets MBOP calculate profitability before the
transaction is released.

Implementation:
- `amazon_sales_finance_transactions` stores raw transaction rows and status
- `amazon_sync_sales_finances.py` scans Transactions API rows for selected
  order IDs and upserts matching transactions
- transaction-derived normalized fee rows are inserted into
  `amazon_sales_financial_events` only when the legacy endpoint returned no
  rows for that order
- the 2026 repair pass reduced the shipped missing-fee set to mostly no-charge
  replacement orders, plus a small refund/adjustment edge case

---

## Sales Orders Fulfillment Cost Sources

Decision:
Use a source hierarchy for Sales Orders fulfillment cost instead of only Veeqo
for Merchant Fulfilled orders.

Reason:
Some Merchant Fulfilled labels are bought in Seller Central or another shipping
platform. Veeqo is still preferred when it has the shipment label cost, but
Seller Central label charges can appear as Amazon adjustment events, and
operator-supplied external label costs need to survive profitability
recalculations.

Implementation:
- `amazon_sales_fulfillment_cost_overrides` stores active manual fulfillment
  cost overrides
- AFN/FBA orders use Amazon FBA fulfillment fee rows
- MFN orders use Veeqo label cost first
- if Veeqo is missing, MFN orders can use negative Amazon
  `AdjustmentEventList` rows without fee/charge/promotion type as
  `amazon_shipping_label`
- no-charge Amazon replacement orders display as `Replacement`, not
  `Missing Fees`
- full refund rows are classified as `refunded` when refund principal equals or
  exceeds the item sale price, even if Amazon order status remains `Shipped`
