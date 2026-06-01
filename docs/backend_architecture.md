# Backend Architecture

Last updated: 2026-05-31

## Core Flow

MBOP follows one primary architecture:

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend never talks directly to Supabase and must render backend/API-provided values rather than rebuilding business logic in React.

## Ownership Boundaries

Purchases, receiving, Amazon FBA shipment prep, inventory reconciliation, repricing advice, and external intelligence are separate domains.

- `purchases` and `purchase_items` own acquired eBay buyer purchase inventory.
- Receiving owns physical verification, received quantities, return-pending decisions, marketplace assignment, received dates, and the transition to `received`.
- Amazon FBA shipment prep owns grouping received Amazon-bound items for export, shipment ID assignment, and moving included units to `listed`.
- Non-historical FBA shipment item links remain workflow-owned by FBA prep and are projected into inventory value as outbound to Amazon.
- Amazon SP-API snapshot tables own read-only Amazon inventory, listing, planning, and finance data.
- Keepa tables own read-only catalog, offer, price-history, sales-rank, and competition intelligence.
- Informed tables own read-only repricer report snapshots and advisory rule/price context.
- YNAB tables own read-only category balance snapshots.
- `inventory_positions` and reconciliation tables are derived and rebuildable; they do not replace workflow ownership.

## Integration Orchestration

`run_all_syncs.py` is the local orchestrator. It supports grouped runs so Task
Scheduler can keep operational data fresh without running heavyweight snapshots
twice per day.

- `core`: eBay buyer purchases, EasyPost tracking, RevSeller enrichment, recent
  Amazon sales orders, new MF Veeqo label costs, recent sales profitability, and
  inventory reconciliation. This group is intended for 2x/day runs.
- `daily`: Amazon FBA inventory, Amazon listing status, Amazon inventory
  planning, Amazon finance balances, 60-day Amazon sales finance refresh,
  daily sales profitability, Informed Repricer reports, YNAB Business cash, and
  the daily business value snapshot. This group is intended for 1x/day runs.
- `catalog`: guarded Keepa active-Amazon stale refresh. This group is
  token-aware and can run daily or less often.

The eBay supplier returns sync is intentionally disabled while the returns
feature is redesigned.

Independent integration failures are collected and reported while later syncs continue running. This prevents one external API failure from blocking unrelated freshness work.

The orchestrator writes the latest per-job state to `logs/sync_health.json`,
appends run history to `logs/sync_runs.jsonl`, uses a local lock file to prevent
overlapping scheduled runs, and performs a tiny Supabase read before launching
work.

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
  - run the eBay purchase FIFO allocator after the 2025 Amazon sales-order
    backfill finishes.
  - allocate costed eBay `purchase_items` into
    `amazon_sales_cogs_consumption` by ASIN and FIFO order.
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
- Add future eBay seller-order ingestion in separate seller-sales tables without
  writing to `purchases` or `purchase_items`.

## External API Safety

All external API integrations are read-only unless explicitly documented otherwise.

- Amazon SP-API uses LWA auth and an explicit read-only path allow-list.
- Amazon write endpoints, restricted PII flows, and seller order/customer PII are not used.
- Keepa token-spending calls are never triggered by frontend page loads.
- Informed Listings Management upload/write paths are not used.
- YNAB data is cash/budget context only.

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
