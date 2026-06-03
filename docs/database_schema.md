# Database Schema Overview

Last updated: 2026-06-02

This document is a high-level map of MBOP's schema. SQL migrations remain the source of exact column definitions.

## Core Purchase Workflow

- `purchases`: supplier/eBay buyer order-level records.
- `purchase_items`: item/unit-level resale purchase records, current workflow status, ASIN, Amazon title, system, target sell price, reporting exclusion flags, received date, marketplace, and manual override flags.
- `inbound_shipments`: inbound tracking and carrier enrichment records linked to purchases/items.
- `manual_item_matches`: reusable title/system ASIN and sell-price corrections.

Authoritative cost for dashboards and purchase reporting comes through `vw_purchases_dashboard.unit_cost`.

## Receiving And FBA Workflow

- `fba_shipments`: operator-entered Amazon/InventoryLab shipment batches.
- `fba_shipment_items`: item-level links between purchase items and FBA shipments.

Receiving state is stored on `purchase_items`; shipment prep links included quantities to FBA shipment rows and moves those included quantities to `listed`.

Current non-historical `fba_shipment_items` links are projected into `inventory_positions.inventory_state = outbound_to_amazon` for inventory valuation. Historical links using `legacy_listed_no_shipment_id` remain historical markers and are not valued as current outbound inventory.

## Order Problems And Return Workflow

- `order_problem_cases`: persistent workflow cases for purchase-item problems,
  including late/stale shipment candidates, return-needed items, eBay return/case
  metadata, cancelled/refund follow-up, missing-item/replacement follow-up, local
  workflow state, refund amounts, replacement tracking, notes, and raw eBay JSON.
- `order_problem_events`: append-only timeline for system, operator, eBay API,
  and tracking events tied to an order problem case.

There is at most one open `order_problem_cases` row per purchase item. Resolved
history remains queryable through closed case rows and the event timeline.

## Amazon Snapshot Tables

- `amazon_skus`: seller SKU/MSKU traceability, ASIN, FNSKU, listing/pricing fields, and raw listing/pricing payloads.
- `amazon_fba_inventory_snapshots`: point-in-time FBA inventory summaries, including fulfillable, inbound, reserved, FC transfer, FC processing, researching, and unfulfillable breakdowns.
- `amazon_listing_snapshots`: point-in-time Listings Items status/issues/fulfillment availability.
- `amazon_report_runs`: audit metadata for Amazon report requests/imports.
- `amazon_inventory_planning_snapshots`: `GET_FBA_INVENTORY_PLANNING_DATA` rows for Amazon-native age buckets and inventory-health context.
- `amazon_finance_balance_snapshots`: Amazon-held cash, available/open balance, deferred/reserved cash, and Amazon-to-bank in-transit cash.

Amazon seller/FBA data stays in Amazon-specific tables and must not be written into purchases or purchase_items.

## Catalog And Repricing Intelligence

- `keepa_product_snapshots`: point-in-time Keepa product snapshots, normalized summary metrics, and raw Keepa payloads.
- `keepa_product_history_points`: optional normalized Keepa history points.
- `informed_report_runs`: Informed report request/download/import audit rows.
- `informed_listing_snapshots`: read-only Informed listing/pricing/repricing report rows.
- `informed_rule_snapshots`: reserved for read-only rule report rows when available.
- `informed_rule_name_overrides`: manual display-name mapping for Informed numeric strategy/rule IDs.
- `amazon_repricing_advisor_snoozes`: page-specific snooze state for aged inventory recommendations.

Keepa and Informed data are advisory intelligence only.

## Inventory Reconciliation And Valuation

- `inventory_positions`: derived current inventory positions with separate physical location, marketplace intent, listing channel, operational status, condition/disposition, and explicit inventory state.
- `inventory_movements`: reserved append-only inventory transition audit table.
- `inventory_reconciliation_events`: reconciliation run summaries.
- `inventory_reconciliation_event_items`: item-level reconciliation findings.
- `inventorylab_active_inventory_backfill`: historical InventoryLab active-inventory cost/date context.
- `inventorylab_inventory_valuation_snapshots`: InventoryLab valuation opening-balance snapshots for legacy Amazon FBA inventory.
- `ynab_category_balance_snapshots`: YNAB Business category cash-balance snapshots.
- `business_value_snapshots`: daily backend-computed total business value rollups.

`business_value_snapshots.raw_rollup_json.amazon_outbound_value` includes MBOP outbound FBA shipment cost plus Amazon inbound cost not already covered by a saved MBOP outbound shipment ASIN.

Inventory reconciliation tables are derived and additive. Workflow corrections must route through the workflow that owns the underlying state.

## Frontend Support APIs

- `/api/screen-data-freshness`: backend-only freshness map used by MBOP screens
  to display screen-specific `Last updated` timestamps near refresh controls.
  The route reads lightweight timestamp signals from source tables and local
  sync files; it does not create schema objects.
- `/api/order-problems`: backend-owned unified problem/return queue with
  candidate detection, stage filtering, sorting, pagination, and summary counts.
- `/api/order-problems/[id]/actions`: MBOP-local order-problem workflow actions.

## Important Views

- `vw_purchases_dashboard`: authoritative purchase dashboard/list view including `unit_cost`.
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_amazon_listing_snapshot`
- `vw_latest_amazon_inventory_planning_snapshot`
- `vw_latest_keepa_product_snapshot`
- `vw_latest_informed_listing_snapshot`
- `vw_latest_inventorylab_inventory_valuation`
- `vw_latest_ynab_category_balance_snapshot`
- `vw_latest_amazon_finance_balance_snapshot`
- `vw_inventory_position_summary`
- `vw_open_inventory_reconciliation_items`
