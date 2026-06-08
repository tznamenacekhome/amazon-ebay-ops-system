# Backend Architecture

Last updated: 2026-06-04

## Core Flow

MBOP follows one primary architecture:

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend never talks directly to Supabase and must render backend/API-provided values rather than rebuilding business logic in React.

## Ownership Boundaries

Purchases, receiving, order problems/returns, Amazon FBA shipment prep,
inventory reconciliation, sourcing, repricing advice, and external intelligence
are separate domains.

- `purchases` and `purchase_items` own acquired eBay buyer purchase inventory.
- Sourcing owns advisory replenishment opportunities, eBay candidate discovery,
  operator sourcing actions, and links to imported purchases only after the
  eBay buyer purchase exists in MBOP.
- Receiving owns physical verification, received quantities, return-pending decisions, marketplace assignment, received dates, and the transition to `received`.
- Order Problems owns return/refund follow-up, eBay return/case metadata,
  cancelled-refund follow-up, missing-item/replacement follow-up, and local
  operator action history in `order_problem_cases` and `order_problem_events`.
- Amazon FBA shipment prep owns grouping received Amazon-bound items for export, shipment ID assignment, and moving included units to `listed`.
- Non-historical FBA shipment item links remain workflow-owned by FBA prep and are projected into inventory value as outbound to Amazon.
- Amazon SP-API snapshot tables own read-only Amazon inventory, listing, planning, and finance data.
- Keepa tables own read-only catalog, offer, price-history, sales-rank, and competition intelligence.
- Informed tables own read-only repricer report snapshots and advisory rule/price context.
- YNAB tables own read-only category balance snapshots and Business-category
  transaction history.
- `inventory_positions` and reconciliation tables are derived and rebuildable; they do not replace workflow ownership.

## Integration Orchestration

`run_all_syncs.py` is the local orchestrator. It supports grouped runs so Task
Scheduler can keep operational data fresh without running heavyweight snapshots
twice per day.

- `core`: eBay buyer purchases, EasyPost tracking, RevSeller enrichment with
  optional AI same-system review, guarded Keepa missing-purchase-title repair,
  recent Amazon sales orders, new MF Veeqo label costs, recent sales
  profitability, and inventory reconciliation. This group is intended for
  2x/day runs.
- `daily`: Amazon FBA inventory, Amazon listing status, Amazon inventory
  planning, Amazon finance balances, 60-day Amazon sales finance refresh,
  daily sales profitability, Informed Repricer reports, YNAB Business cash,
  YNAB Business transactions, and the daily business value snapshot. This group
  is intended for 1x/day runs.
- `catalog`: guarded Keepa active-Amazon stale refresh. This group is
  token-aware and can run daily or less often.

The legacy eBay supplier returns sync is intentionally disabled. The new Order
Problems return workflow uses `integrations/ebay_sync_order_problem_returns.py`
as a scheduled, read-only eBay Post-Order importer for returns, INR inquiries,
inquiry detail records, and open cases. It writes only to `order_problem_cases`
and `order_problem_events`. Inquiry detail enrichment is required because
seller make-it-right/escalation dates and replacement tracking are not present
in the inquiry search summary. Cancellation/refund exceptions can be represented
locally as `ebay_cancellation_sync` rows while first-class cancellation search
automation is evaluated.

`integrations/inventory_source_balance_audit.py` is a secondary control, not a
freshness sync. It should run after FIFO allocator runs, after large purchase or
sales backfills, and as a monthly close check. It verifies that purchase source
units reconcile to sales COGS consumption, active inventory COGS layers,
opening-history boundary adjustments, and other explicit adjustments. The local
monthly scheduler entry point is `inventory_source_balance_audit.bat`, with
latest report files written to `exports/inventory_source_balance_audit.csv` and
`logs/inventory_source_balance_audit_latest.json`.

Independent integration failures are collected and reported while later syncs continue running. This prevents one external API failure from blocking unrelated freshness work.

The orchestrator writes the latest per-job state to `logs/sync_health.json`,
appends run history to `logs/sync_runs.jsonl`, uses a local lock file to prevent
overlapping scheduled runs, and performs a tiny Supabase read before launching
work.

## UI Data Freshness

Each MBOP screen with a refresh control shows a nearby `Last updated` indicator.
The frontend reads these values through `/api/screen-data-freshness`; it does
not query Supabase directly. Most screens display the newest relevant source
timestamp for that screen. Dashboard is stricter: because Business Inventory And
Cash Value depends on multiple cash/value inputs, its freshness indicator shows
the oldest of the required business value, Amazon cash, and YNAB cash snapshots
so a fresh reconciliation run cannot hide stale cash data.

Purchases freshness includes eBay purchase import batches, tracking updates,
Order Problems case/event updates, and RevSeller enrichment diagnostics because
the Purchases workspace now contains both the editable purchases table and the
Order Problems queue.

Roadmap:

- Add a resumable Keepa backfill runner, similar to the Amazon sales history
  backfill, for controlled capture of Keepa data for out-of-stock inventory
  items without spending tokens from frontend page loads.
- Add a non-eBay purchases workspace as the go-forward source for supplier,
  prep-center, and direct-to-Amazon purchase cost entry. InventoryLab imports
  should be treated as completed legacy bridge/backfill data; future purchase
  costs should come from either the eBay purchase sync or MBOP-entered non-eBay
  purchases. The future direction for the TIM spreadsheet is MBOP -> TIM export
  or update, not scheduled TIM -> MBOP sync.
- Complete Sales Orders COGS handling:
  - eBay purchase FIFO allocation has been implemented in
    `integrations/apply_ebay_purchase_fifo_cogs.py` and run after the 2025
    Amazon sales-order backfill. It can include explicitly Listed legacy
    purchase-item lots from non-eBay suppliers when those lots have ASIN,
    quantity, and cost.
  - non-eBay FIFO allocation and targeted rebalancing have been implemented in
    `integrations/apply_non_ebay_fifo_cogs.py`.
  - rerun the missing COGS review export and manually review only the remaining
    no-match or quantity-short exceptions.
  - track legacy InventoryLab/opening inventory drawdown separately from MBOP
    FIFO-owned inventory.
  - prevent cost-layer over-consumption and preserve separate
    `amazon_sales_cogs_consumption` records.
- Expand Sales Orders refund handling beyond basic canceled/refunded exclusion,
  including full versus partial refund classification from Amazon finance
  events.
- Add Sales Orders order-level drilldown/rollup views on top of the current
  item-level profitability rows.
- Add manual adjustment workflows for exceptional fulfillment cost and COGS
  corrections using the existing `manual` source values.
- Continue Amazon order and inventory missing-data cleanup until remaining
  Sales Orders COGS/fee exceptions and open inventory reconciliation findings
  are either resolved or explicitly classified.
- Extend Order Problems return handling with full case/event drawer timelines,
  scheduled cancellation search import if more refund-follow-up cancellations
  appear, and controlled partial refund cost adjustment when the item is kept.
- Add an Amazon FBA removals workflow for damaged/unsellable units that Amazon
  automatically returns. The workflow should track removal orders, receiving
  returned units, deciding whether they are still new/sellable, and routing good
  units back into the send-to-Amazon workflow.
- Add an Amazon Inventory Discrepancy workflow for Amazon receiving shortages,
  lost inventory, warehouse-damaged inventory, and customer returns that do not
  come back to the business. This should be separate from Purchases, Receiving,
  and FBA shipment prep because Amazon-side discrepancies have different
  evidence and resolution paths.
- Add future eBay seller-order ingestion in separate seller-sales tables without
  writing to `purchases` or `purchase_items`.
- Mature the Sourcing workspace with UI-run orchestration, AI image/title
  observations, expired listing detection, ROI snooze reactivation, and API
  quota/cache cadence for dismissed and snoozed listings.

## External API Safety

All external API integrations are read-only unless explicitly documented otherwise.

- Amazon SP-API uses LWA auth and an explicit read-only path allow-list.
- Amazon write endpoints, restricted PII flows, and seller order/customer PII are not used.
- Amazon Seller Central account-health and feedback observations stay in
  Amazon-specific dashboard tables. `GET_SELLER_FEEDBACK_DATA` is allowed only
  as a read-only Reports API source for 1-3 star feedback alerts.
- Keepa token-spending calls are never triggered by frontend page loads.
- Informed Listings Management upload/write paths are not used.
- YNAB data is read-only cash/budget and transaction context only.
- Sourcing marketplace integrations are read-only; MBOP does not purchase,
  bid, submit Best Offers, or create eBay actions automatically.

## Backend-Owned Business Logic

Backend/API layers own:

- landed cost and dashboard cost totals
- purchase status filtering and pagination
- receiving validation
- FBA grouping and cost aggregation
- inventory value rollups
- repricing recommendation tiers, buckets, target prices, and reasons
- business value snapshots

Inventory value rollups treat saved current FBA shipment links as MBOP outbound-to-Amazon cost, while Amazon SP-API and InventoryLab snapshots represent inventory already in Amazon's inventory layers. The rollup avoids double-counting Amazon inbound rows for ASINs already covered by a saved MBOP outbound shipment.

Frontend components render API-provided values and manage UI workflow state only.

## Sales Orders Operating Cutoff

Amazon Sales Orders is a 2025-forward MBOP operating dataset. The sales sync and
backfill scripts enforce a 2025-01-01 purchase-date cutoff because Amazon can
surface old orders through recent `LastUpdatedAfter` activity. The Sales Orders
API also clamps requested start dates to 2025-01-01.

`missing_fees` remains the stored profitability status for compatibility. The
Sales Orders API uses Amazon `order_status` to split display status: unfulfilled
orders show `Pending`, while shipped/fulfilled orders show `Missing Fees`.

Amazon sales finance sync uses the legacy order-specific financial-events
endpoint first. It also stores newer `/finances/2024-06-19/transactions` rows in
`amazon_sales_finance_transactions` and derives normalized fee rows from the
transaction `AmazonFees` breakdown only when the legacy endpoint is empty for
that order. This covers Seller Central `DEFERRED` transactions whose fee
breakdown is visible before the older endpoint returns order events.

Fulfillment cost for Sales Orders is backend-owned. Active manual overrides in
`amazon_sales_fulfillment_cost_overrides` are applied first for external label
purchases. Otherwise, AFN/FBA orders use Amazon FBA fulfillment fee rows, and
MFN orders prefer Veeqo label costs before falling back to Amazon Seller Central
shipping-label adjustment events when Veeqo is missing. Sales Orders displays
no-charge Amazon replacements as
`Replacement`, while fully refunded rows are classified as `refunded` from
refund principal events even if the Amazon order status still says `Shipped`.

## Business Cash Value

Amazon cash valuation uses two Amazon Finance concepts:

- Amazon-held cash: deferred transactions plus open financial event groups.
- Amazon-to-bank in-transit cash: fund transfers still marked `Processing` plus
  completed/succeeded fund transfers that do not yet have a matching YNAB
  Business deposit transaction.

Completed payout matching uses the local `ynab_business_transactions` history,
matching Amazon fund transfers to positive Business-category YNAB transactions
by amount, date window, and Amazon payee/import text. Completed payouts remain
in `in_transit_to_bank` only while no matching YNAB deposit is present. The
unmatched-completed-payout review window defaults to 14 days and can be
overridden with `AMAZON_UNMATCHED_COMPLETED_TRANSFER_LOOKBACK_DAYS` or
`amazon_sync_finance_balances.py --unmatched-completed-transfer-lookback-days`.
