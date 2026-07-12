# Backend Architecture

Last updated: 2026-06-28

## Core Flow

MBOP follows one primary architecture:

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend never talks directly to Supabase and must render backend/API-provided values rather than rebuilding business logic in React.

## Ownership Boundaries

Purchases, receiving, order problems/returns, Amazon Return Recovery, Amazon
FBA shipment prep, inventory reconciliation, sourcing, repricing advice, and
external intelligence are separate domains.

- `purchases` and `purchase_items` own acquired eBay buyer purchase inventory.
- Sourcing owns advisory replenishment opportunities, eBay candidate discovery,
  operator sourcing actions, and links to imported purchases only after the
  eBay buyer purchase exists in MBOP.
- Matching Intelligence owns reusable sourcing evidence, listing snapshots,
  labeled match/non-match examples, and advisory seller intelligence. It is a
  foundation for improving Amazon-to-eBay replenishment matching and must not
  launch eBay-to-Amazon sourcing by itself.
- Receiving owns physical verification, received quantities, return-pending decisions, marketplace assignment, received dates, and the transition to `received`.
- Order Problems owns return/refund follow-up, eBay return/case metadata,
  cancelled-refund follow-up, missing-item/replacement follow-up, and local
  operator action history in `order_problem_cases` and `order_problem_events`.
- Amazon FBA shipment prep owns grouping received Amazon-bound items for export, shipment ID assignment, and moving included units to `listed`.
- Amazon Return Recovery owns Amazon customer returns/removals returned to the
  business, reimbursement-review evidence, manual inspection/disposition, and
  non-purchase routing back into FBA through `fba_shipment_source_items`.
- Non-historical FBA shipment item links remain workflow-owned by FBA prep and are projected into inventory value as outbound to Amazon only for quantities Amazon has not yet received or made available.
- Amazon FBA shipment sync reads Amazon inbound shipment status and shipment-item quantities, stores fulfillment center, carrier ETA/tracking context, FBA availability metrics, and milestone timestamps on FBA shipment workflow tables.
- Amazon FBA shipment sync also attempts a cached Fulfillment Inbound v2024
  identity bridge from Amazon shipment confirmation ID to inbound plan/internal
  shipment IDs. The bridge stores raw payload context and any tracking details
  returned, but missing v2024 identity/tracking does not fail status or item
  quantity refreshes.
- Amazon SP-API snapshot tables own read-only Amazon inventory, listing, planning, and finance data.
- Keepa tables own read-only catalog, offer, price-history, sales-rank, and competition intelligence.
- Informed tables own read-only repricer report snapshots and advisory rule/price context.
- YNAB tables own read-only category balance snapshots and Business-category
  transaction history.
- ZFI owns personal finance, household/business net worth, cash-flow planning,
  tax classification, owner draws/contributions, and long-range financial
  planning. MBOP may push summarized business-operational finance payloads to
  ZFI Supabase, but MBOP must not query ZFI or import ZFI personal finance data.
- eBay draft search-link sheet support is a spreadsheet utility, not a marketplace
  write workflow. See `docs/subsystems/ebay_draft_pricing.md`.
- `inventory_positions` and reconciliation tables are derived and rebuildable; they do not replace workflow ownership.

## Integration Orchestration

`run_all_syncs.py` is the scheduler orchestrator. In production, AWS
EventBridge Scheduler launches ECS/Fargate `mbop-scheduler-task` runs using
explicit group names. Local Windows Task Scheduler jobs are retired and should
not be recreated unless a local disaster-recovery fallback is intentionally
designed.

- `core`: eBay buyer purchases, sourcing purchase matching for opportunities
  marked Purchased / Offer Made, EasyPost tracking, RevSeller enrichment with
  optional AI same-system review, guarded Keepa missing-purchase-title repair,
  recent Amazon sales orders, new MF Veeqo label costs, recent sales
  profitability, and inventory reconciliation. This group is intended for
  2x/day runs.
- `daily`: Amazon FBA inventory, Amazon FBA shipments, Amazon listing status,
  Amazon inventory planning, YNAB Business transactions/cash, Amazon finance
  balances, 60-day Amazon sales finance refresh, daily sales profitability,
  Informed Repricer reports, sourcing listing availability cleanup, Matching
  Intelligence refresh, and the daily business value snapshot. YNAB runs before
  Amazon finance so completed Amazon payouts already visible in YNAB are not
  also counted as Amazon-to-bank in-transit cash; genuine unmatched payout gaps
  still remain in transit. This group is intended for 1x/day runs.
- `catalog`: sourcing listing availability cleanup and guarded Keepa
  active-Amazon stale refresh plus Matching Intelligence refresh. Keepa work is
  token-aware and can run daily or less often.
- AWS production schedules use the cloud-specific groups documented in
  `docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`. System Health reads Supabase
  `scheduler_runs` and `scheduler_run_jobs` telemetry for those groups,
  including detail-drawer history and parsed per-job metrics from scheduler
  output.

On-demand Sourcing Workspace runs use a progressive batch runner. The web API
creates a `sourcing_runs` row, ECS runs
`integrations/run_sourcing_workflow.py --target-opportunities 100`, and the
runner searches seed chunks until it can persist the current
`sourcing_opportunity_batches` membership or reaches a stop condition. The
frontend renders the saved backend batch and uses
`POST /api/sourcing/runs/[runId]/continue` for Find 100 More; it does not
calculate matching, profitability, or batch eligibility in React.

The legacy eBay supplier returns sync has been removed from active
orchestration and System Health. The Order Problems return workflow uses
`integrations/ebay_sync_order_problem_returns.py` as a scheduled, read-only eBay
Post-Order importer for returns, INR inquiries, inquiry detail records, and
open cases. It writes only to `order_problem_cases` and `order_problem_events`.
Inquiry detail enrichment is required because seller make-it-right/escalation
dates and replacement tracking are not present in the inquiry search summary.
When replacement tracking for an item-not-received inquiry shows progress, MBOP
keeps the case in replacement follow-up; when the replacement tracking is
delivered, MBOP closes the case as `resolved_received_item` and moves the
purchase item back to `delivered` for Receiving verification.
Order Problems is episode-based: a single purchase item can have multiple
closed historical episodes and at most one open episode. Closed late-delivery or
INR episodes do not suppress future episodes for the same item. Receiving
exceptions can open a new return-needed episode, and later eBay return syncs
enrich that active episode instead of being treated as a continuation of an old
closed inquiry.
Cancellation/refund exceptions can be represented locally as
`ebay_cancellation_sync` rows while first-class cancellation search automation
is evaluated.

`integrations/inventory_source_balance_audit.py` is a secondary control, not a
freshness sync. It should run after FIFO allocator runs, after large purchase or
sales backfills, and as a monthly close check. It verifies that purchase source
units reconcile to sales COGS consumption, active inventory COGS layers,
opening-history boundary adjustments, and other explicit adjustments. It is
manual/on-demand after the AWS scheduler migration; the legacy local monthly
Windows task has been removed.

Independent integration failures are collected and reported while later syncs continue running. This prevents one external API failure from blocking unrelated freshness work.

`integrations/push_zfi_business_summary.py` is an outbound-only export to ZFI
Supabase. It defaults to dry run for manual use, and production scheduler
groups that refresh Amazon/SP-API sales, finance, inventory, shipment, or
business-value source data run it with `--apply` as a nonblocking final push.

The orchestrator writes the latest per-job state to Supabase scheduler
telemetry in cloud runs and to `logs/sync_health.json` for local/manual runs,
appends run history to `logs/sync_runs.jsonl`, uses a lock to prevent
overlapping scheduled runs, and performs a tiny Supabase read before launching
work. Each job writes a `running` health record when it starts and replaces it
with `ok` or `failed` at completion. If a scheduled wake-up causes multiple
groups to start at once, lock losers write `blocked` health records so System
Health shows the missed work instead of appearing stale or silently successful.

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
- Continue Amazon Return Recovery/removals work after the operational first
  slice: resolve or work around unreliable Amazon removal reports, add manual
  removal order creation, expand reimbursement case prep, add eBay/disposal
  closeout paths, and project states into inventory/dashboard summaries.
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

Inventory value rollups treat saved current FBA shipment links as MBOP outbound-to-Amazon cost only while the shipment item has remaining outbound quantity. Once Amazon shipment sync shows units received or available, the received quantity is no longer projected as MBOP outbound inventory. InventoryLab snapshots remain audit context only and do not replace MBOP/Amazon source-of-truth tables.

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
