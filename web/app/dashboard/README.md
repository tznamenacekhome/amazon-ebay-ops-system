# Dashboard Workspace

The Dashboard workspace is the MBOP operational value and backlog view.

## Routes

- UI: `/dashboard`
- API: `/api/dashboard/purchases`
- Reconciliation work queue UI: `/inventory-reconciliation`

## Current Reports

The dashboard puts Inventory Visibility first and shows inventory/cash value before purchase-history reporting. The top-level total-units, total-cost, and months cards were removed because those totals are already represented in the lower monthly/pivot sections.

The dashboard shows purchase units and purchase cost by year/month, excluding purchase items with `current_status = return_opened`, `current_status = cancelled`, or `exclude_from_purchase_reporting = true`.

The API reads `vw_purchases_dashboard` and aggregates:

- units: sum of `quantity`
- cost: sum of `unit_cost * quantity`
- status breakdown: sum of `quantity` by `purchase_items.current_status`
- purchase completeness gaps: missing ASIN, sell price, system, and Amazon title
- receiving backlog: Delivered and Shipped (No Tracking) rows waiting to be received
- shipment prep backlog: Received Amazon-bound rows waiting for FBA shipment preparation
- workflow aging buckets for receiving and FBA prep
- exception visibility: past-ETA rows, stale/no-tracking rows, exception rows, and return-pending rows
- stale/no-tracking visibility ignores rows more than 90 days old because those historical tracking gaps are not actionable
- order problem counts:
  - Past ETA: supplier delivery estimate has passed and the item is not delivered/received/listed/cancelled/return-opened
  - Tracking stale/no tracking: no usable carrier movement after a week, excluding rows older than 90 days
  - Exceptions: carrier exception or return-pending statuses requiring operator follow-up

`unit_cost` is the authoritative backend landed-cost value. Dashboard React components should render API-provided aggregates and should not introduce their own landed-cost calculations.

Inventory value semantics:
- current Amazon FBA value uses the latest `vw_latest_inventorylab_inventory_valuation` snapshot when available because it represents InventoryLab's remaining on-hand cost basis for legacy Amazon inventory
- outbound-to-Amazon, received, ordered, and other non-Amazon-held inventory values use MBOP inventory-position costs
- InventoryLab valuation data is an opening-balance snapshot only and must not be written into `purchase_items`
- cash on hand uses the latest `vw_latest_ynab_category_balance_snapshot` row for the YNAB `Business` category
- YNAB cash data is read-only budget context and must not be written into inventory or purchase workflow tables
- Amazon cash uses the latest `vw_latest_amazon_finance_balance_snapshot` row
- Amazon cash-in-transit uses Finance financial event groups with `FundTransferStatus = Processing`
- the business inventory/cash value total is API-provided and sums Amazon inventory value, pre-Amazon purchased inventory value, Amazon cash, Amazon-to-bank in-transit cash, and YNAB cash on hand
- total business value is snapshotted once per day in `business_value_snapshots`
- clicking the total value opens a modal graph backed by API-provided snapshot history

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
