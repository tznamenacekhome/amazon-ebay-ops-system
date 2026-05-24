# Dashboard Workspace

The Dashboard workspace is the first MBOP reporting view for purchase data completeness and cost accuracy.

## Routes

- UI: `/dashboard`
- API: `/api/dashboard/purchases`

## Current Report

The first dashboard report shows purchase units and purchase cost by year/month, excluding purchase items with `current_status = return_opened`.

The API reads `vw_purchases_dashboard` and aggregates:

- units: sum of `quantity`
- cost: sum of `unit_cost * quantity`

`unit_cost` is the authoritative backend landed-cost value. Dashboard React components should render API-provided aggregates and should not introduce their own landed-cost calculations.

## Intended Use

This view is meant to compare MBOP totals against the legacy Excel pivot table while the system is being validated. May 2026 is expected to vary until missing spreadsheet-only history is reconciled.
