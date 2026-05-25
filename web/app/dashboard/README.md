# Dashboard Workspace

The Dashboard workspace is the first MBOP reporting view for purchase data completeness and cost accuracy.

## Routes

- UI: `/dashboard`
- API: `/api/dashboard/purchases`

## Current Reports

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

`unit_cost` is the authoritative backend landed-cost value. Dashboard React components should render API-provided aggregates and should not introduce their own landed-cost calculations.

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
