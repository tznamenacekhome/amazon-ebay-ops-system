# Dashboard Workspace

The Dashboard workspace is the MBOP operational value and backlog view.

## Routes

- UI: `/dashboard`
- Dashboard APIs:
  - `/api/dashboard/overview`
  - `/api/dashboard/operations`
  - `/api/dashboard/financial`
  - `/api/dashboard/inventory`
  - `/api/dashboard/amazon`
  - `/api/dashboard/growth`
  - `/api/dashboard/sourcing`
  - `/api/dashboard/loss-prevention`
  - `/api/dashboard/system-health`
- Legacy purchase dashboard API retained temporarily: `/api/dashboard/purchases`
- Reconciliation work queue UI: `/inventory-reconciliation`

## Current Reports

The Dashboard workspace is now split into URL-addressable monitoring tabs under
one top-level left navigation item:

- `/dashboard?view=overview`
- `/dashboard?view=financial`
- `/dashboard?view=operations`
- `/dashboard?view=inventory`
- `/dashboard?view=amazon`
- `/dashboard?view=growth`
- `/dashboard?view=sourcing`
- `/dashboard?view=loss-prevention`
- `/dashboard?view=system-health`

Overview, Financial, Operations, Inventory, Amazon, Growth, Sourcing, Loss
Prevention, and System Health fetch focused dashboard summaries.

The Overview tab shows:

- latest backend-owned business value snapshot totals
- compact business value trend from `business_value_snapshots`
- current attention summary with drill-down links to Receiving, FBA, Purchases,
  Repricing, and Reconciliation

The Operations tab shows:

- receiving backlog and arriving-today/this-week counts
- FBA prep ready/blocked counts
- purchase cleanup counts for missing ASIN, sell price, Amazon title, and system
- order problem buckets from `order_problem_cases`
- compact workflow aging buckets
- short top attention list

The Financial tab shows:

- profitability windows for 7-day, 30-day, 90-day, month-to-date, and
  year-to-date sales
- latest YNAB Business cash and Amazon cash buckets
- Amazon payout reconciliation status from finance balance snapshots
- financial data completeness counts for recent sales rows
- placeholder area for future Schedule C category export

The remaining tabs show:

- Inventory: value by location, age buckets, capital at risk, concentration,
  and reconciliation attention.
- Amazon: sales/profitability summary, FBA/listing health, repricing advisor
  rollup, top sellers, stale high-capital inventory, Seller Central account
  health, Feedback Manager summary, and 1-3 star feedback alerts.
- Growth: monthly sales/profit/inventory spend trends, business value movement,
  and basic efficiency metrics.
- Sourcing: manual replenishment research candidates from existing
  sales/profit/inventory data with transparent scoring.
- Loss Prevention: problem-case risk, estimated value at risk, urgent cases,
  and loss/recovery trend.
- System Health: integration freshness, recent sync runs, and safe guardrail
  placeholders.

The focused dashboard APIs read backend-owned views/tables and aggregate:

- purchase completeness gaps: missing ASIN, sell price, system, and Amazon title
- receiving backlog: Delivered and Shipped (No Tracking) rows waiting to be received
- shipment prep backlog: Received Amazon-bound rows waiting for FBA shipment preparation
- workflow aging buckets for receiving and FBA prep
- order problem counts from persistent workflow cases

The old `/api/dashboard/purchases` route still contains historical purchase
month/status/inventory reporting logic while the remaining dashboard tabs are
split into smaller APIs.

`unit_cost` is the authoritative backend landed-cost value. Dashboard React components should render API-provided aggregates and should not introduce their own landed-cost calculations.

Inventory value semantics:
- current Amazon FBA value uses the latest `vw_latest_inventorylab_inventory_valuation` snapshot when available because it represents InventoryLab's remaining on-hand cost basis for legacy Amazon inventory
- saved current FBA shipment links are valued as outbound-to-Amazon using MBOP inventory-position costs
- Amazon inbound rows are included in outbound-to-Amazon value only when their ASIN is not already covered by a saved MBOP outbound shipment, preventing double counting while Amazon is also reporting the shipment as inbound
- received, ordered, and other non-Amazon-held inventory values use MBOP inventory-position costs
- InventoryLab valuation data is an opening-balance snapshot only and must not be written into `purchase_items`
- cash on hand uses the latest `vw_latest_ynab_category_balance_snapshot` row for the YNAB `Business` category
- YNAB cash data is read-only budget context and must not be written into inventory or purchase workflow tables
- Amazon cash uses the latest `vw_latest_amazon_finance_balance_snapshot` row
- Amazon cash-in-transit uses Finance financial event groups with `FundTransferStatus = Processing`
- Amazon account health and seller feedback values are Seller Central
  observations stored in Amazon-specific dashboard tables. Use
  `integrations/amazon_record_seller_account_health.py` to record future score
  changes and feedback rating/count changes.
- `integrations/amazon_sync_seller_feedback.py` can request Amazon's
  `GET_SELLER_FEEDBACK_DATA` report, but Amazon documents that report as
  neutral/negative seller feedback only (1-3 stars). The Amazon dashboard uses
  imported rows from that report as alert rows.
- the business inventory/cash value total is API-provided and sums Amazon inventory value, pre-Amazon purchased inventory value, Amazon cash, Amazon-to-bank in-transit cash, and YNAB cash on hand
- total business value is snapshotted once per day in `business_value_snapshots`
- total business value trend is backed by API-provided snapshot history
- dashboard date-only values, including business value snapshot dates, display as
  Pacific Time business dates and must not shift backward because JavaScript
  parsed a `YYYY-MM-DD` value as UTC midnight
- the total business value trend uses explicit hover/focus targets and an
  in-chart tooltip for each data point instead of relying on native SVG title
  behavior

Inventory reconciliation:
- open reconciliation findings are not shown on the main dashboard
- `/inventory-reconciliation` is the dedicated work queue for normalized inventory-position findings against external snapshots such as Amazon FBA
- reconciliation findings are investigation prompts; fixes should be made in the owning workflow/source data, not by editing the finding row

Cost semantics:
- reward points and payment method effects should not zero out resale inventory cost
- foreign-currency purchases should use eBay-provided USD payment totals when available
- single-item partial refunds where the item is kept should reduce purchase item cost
- multi-item partial refunds should be handled by explicit item-level correction or the future return/refund workflow

## Intended Use

This view is meant to improve operational confidence and throughput by showing which parts of the workflow need attention. It is also still useful for comparing MBOP totals against the legacy Excel pivot table while the system is being validated.

Current reconciliation state:
- 2024 and 2025 match the legacy pivot exactly.
- active unit count has been reconciled to 4,806 units.
- active cost is within a $4.05 MBOP-over-spreadsheet variance currently attributed to known spreadsheet mistakes.
- purchases on or after 2026-05-16 are MBOP-canonical because the legacy spreadsheet was no longer maintained for new purchases.

Use explicit reporting exclusions for personal purchases, business supplies, and other non-resale purchases. Do not infer exclusion from missing system or ASIN data.
