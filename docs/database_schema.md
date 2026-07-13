# Database Schema Overview

Last updated: 2026-07-12

This document is a high-level map of MBOP's schema. SQL migrations remain the source of exact column definitions.

## Core Purchase Workflow

- `purchases`: supplier/eBay buyer order-level records.
- `purchase_items`: item/unit-level resale purchase records, current workflow status, ASIN, Amazon title, system, target sell price, reporting exclusion flags, received date, marketplace, operator notes, and manual override flags.
- `inbound_shipments`: inbound tracking and carrier enrichment records linked to purchases/items.
- `manual_item_matches`: reusable title/system ASIN and sell-price corrections.

Authoritative cost for dashboards and purchase reporting comes through `vw_purchases_dashboard.unit_cost`.

## Receiving And FBA Workflow

- `fba_shipments`: operator-entered Amazon shipment batches, enriched with Amazon inbound status, fulfillment center, carrier/tracking fields, milestone timestamps, FBA availability metrics, and outbound remaining value.
- `fba_shipment_items`: item-level links between purchase items and FBA shipments, enriched with Amazon expected/received/available quantities and remaining outbound cost.
- `fba_shipment_source_items`: non-purchase FBA shipment source links, currently
  for Amazon Return Recovery items routed back to FBA. This lets Amazon-return
  units join FBA shipment detail and InventoryLab export without pretending
  they are eBay purchase items.
- `fba_shipment_events`: milestone history for FBA shipment pickup, delivery, check-in, receiving, closure, and all-units-available events.

Receiving state is stored on `purchase_items`; shipment prep links included quantities to FBA shipment rows and moves those included quantities to `listed`.

Current non-historical `fba_shipment_items` links are projected into `inventory_positions.inventory_state = outbound_to_amazon` for inventory valuation. Historical links using `legacy_listed_no_shipment_id` remain historical markers and are not valued as current outbound inventory.

## Order Problems And Return Workflow

- `order_problem_cases`: persistent workflow cases for purchase-item problems,
  including late/stale shipment candidates, return-needed items, eBay return/case
  metadata, cancelled/refund follow-up, missing-item/replacement follow-up, local
  workflow state, refund amounts, escalation/action dates, replacement tracking,
  buyer return-label tracking, return EasyPost tracker enrichment, episode
  metadata, supersession links, notes, and raw eBay JSON.
- `order_problem_events`: append-only timeline for system, operator, eBay API,
  and tracking events tied to an order problem case.

There is at most one open `order_problem_cases` row per purchase item. Resolved
history remains queryable through closed case rows and the event timeline.
Episode fields (`episode_kind`, `episode_sequence`, `opened_reason`,
`resolved_reason`, `source_artifact_type`, `superseded_by_case_id`) let the same
purchase item move through separate delivery-delay, INR, damaged-item,
incomplete-item, cancellation, and refund-follow-up episodes over time.

## Amazon Snapshot Tables

- `amazon_skus`: seller SKU/MSKU traceability, ASIN, FNSKU, fulfillment
  channel, listing/pricing fields, active and inactive merchant-listing
  coverage where imported, and raw listing/pricing payloads.
- `amazon_fba_inventory_snapshots`: point-in-time FBA inventory summaries, including fulfillable, inbound, reserved, FC transfer, FC processing, researching, and unfulfillable breakdowns.
- `amazon_listing_snapshots`: point-in-time Listings Items status/issues/fulfillment availability.
- `amazon_report_runs`: audit metadata for Amazon report requests/imports.
- `amazon_inventory_planning_snapshots`: `GET_FBA_INVENTORY_PLANNING_DATA` rows for Amazon-native age buckets and inventory-health context.
- `amazon_finance_balance_snapshots`: Amazon-held cash, available/open balance, deferred/reserved cash, and Amazon-to-bank in-transit cash.
- `amazon_account_health_snapshots`: manual Seller Central Account Health Rating snapshots for dashboard history.
- `amazon_seller_feedback_snapshots`: manual Seller Central Feedback Manager star-rating/count snapshots.
- `amazon_seller_feedback_items`: Seller Central / SP-API seller feedback rows with date, rating, order ID, and comment; dashboard alerts focus on 1-3 star feedback.
- `amazon_fee_estimates`: cached read-only SP-API Product Fees estimates keyed by ASIN, marketplace, fulfillment channel, listing price, shipping price, and currency. MBOP stores total, referral, FBA, variable closing, raw breakdown, and status fields for FBA prep pricing/ROI review.
- `amazon_return_recovery_cases`: Amazon-specific workflow cases for customer
  returns/removals returned to the business, including normalized return
  evidence, manual inspection/disposition, reimbursement review, and FBA
  routing state.
- `amazon_return_recovery_events`: append-only event timeline for Amazon Return
  Recovery inspection, decision, case-review, and FBA routing actions.
- `amazon_fba_customer_return_rows`: raw and normalized
  `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` rows, preserving return reason,
  customer comments, disposition, LPN, order identifiers, ASIN/SKU/FNSKU, and
  raw row JSON.
- `amazon_fba_reimbursement_rows`: raw and normalized
  `GET_FBA_REIMBURSEMENTS_DATA` rows, preserving reimbursement IDs, case/order
  identifiers, ASIN/SKU/FNSKU, reason, approval date, quantity, amount,
  currency, and raw row JSON.
- `amazon_fba_removal_order_detail_rows` and
  `amazon_fba_removal_shipment_detail_rows`: foundation tables for Amazon
  removal reports. The reports remain unreliable from Amazon as of 2026-06-28,
  so these tables are present but not a dependable data source yet.

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

## Sourcing Workspace

- `sourcing_settings`: operator-configurable sourcing thresholds, buyer ZIP,
  allowed item-location countries, Best Offer threshold, and excluded keywords.
- `sourcing_coverage_cycles`: durable daily catalog coverage-cycle headers,
  including total eligible ASINs, priority bucket counts, searched/remaining
  counts, completion percentage, last run, last stop reason, and quota reset
  context.
- `sourcing_coverage_cycle_items`: one row per ASIN in a coverage cycle,
  including priority bucket, queue position, processing status, source evidence,
  last eBay check, Browse calls used, candidate counts, qualifying opportunity
  counts, and retry/error context.
- `sourcing_runs`: one row per sourcing scan, including mode, counts, status,
  settings snapshot, API call count, errors, optional coverage-cycle link, stop
  reason, Browse quota snapshots, per-priority coverage metrics, and
  `raw_summary_json.ebay_search` call-type/detail diagnostics.
- `sourcing_seed_asins`: ASINs selected for a sourcing run from the coverage
  queue, recent Amazon sales, purchased-not-sent Amazon-bound items, or active
  listings, including Amazon title/image, target sale context, velocity,
  inventory need, queue position, and warning flags.
- `sourcing_ebay_candidates`: eBay Browse candidate listings with raw payload,
  buying options, item location, shipping quote state, price, landed cost,
  quantity, auction, and Best Offer metadata.
- `sourcing_opportunities`: scored candidate rows shown to the operator with
  opportunity type, workflow status, profit/ROI context, offer/bid guidance,
  flags, and score.
- `sourcing_opportunity_batches`: durable sourcing batches for the
  Replenishment queue, including requested/current counts, cumulative seed
  cursor, eBay Browse API-call count, stop reason, quota diagnostics, and
  funnel diagnostics. Unified coverage-cycle runs use
  `requested_opportunity_count = 0` to mean "spend available daily Browse
  quota" rather than "stop after N opportunities"; quota stops are recorded as
  `ebay_out_of_quota`, `ebay_rate_limited`, or `quota_reserve_reached` and
  displayed as "Out of quota".
- `sourcing_opportunity_batch_items`: stable membership of opportunities
  presented in each progressive sourcing batch so later batches do not repeat
  rows already shown to the operator.
- `sourcing_actions`: operator action history for dismiss, watch, ROI snooze,
  and purchased/offer-made workflows.
- `sourcing_purchase_matches`: links sourced opportunities to imported eBay
  buyer purchases after the purchase exists in MBOP.
- `sourcing_listing_snapshots`: point-in-time eBay/Amazon evidence snapshots
  for opportunities, sourcing actions, and best-effort historical/manual
  purchase backfill.
- `matching_intelligence_examples`: rebuildable labeled examples for match,
  non-match, condition, business, availability, and review evidence.
- `matching_intelligence_receiving_outcomes`: receiving-owned verification
  outcomes for correct item, wrong item, wrong condition, packaging issue,
  incomplete item, listed successfully, structured image clues, and notes.
- `sourcing_seller_intelligence`: derived advisory seller metrics and seller
  status used by sourcing diagnostics.

Sourcing remains advisory until a matched eBay buyer purchase is imported.
Only the purchase matcher may enrich matched `purchase_items` rows with sourced
ASIN, Amazon title, and target sell price.

## Inventory Reconciliation And Valuation

- `inventory_positions`: derived current inventory positions with separate physical location, marketplace intent, listing channel, operational status, condition/disposition, and explicit inventory state.
- `inventory_movements`: reserved append-only inventory transition audit table.
- `inventory_reconciliation_events`: reconciliation run summaries.
- `inventory_reconciliation_event_items`: item-level reconciliation findings.
- `inventorylab_active_inventory_backfill`: historical InventoryLab active-inventory cost/date context.
- `inventorylab_inventory_valuation_snapshots`: InventoryLab valuation opening-balance snapshots for legacy Amazon FBA inventory.
- `ynab_category_balance_snapshots`: YNAB Business category cash-balance snapshots.
- `ynab_business_transactions`: read-only local copy of YNAB transactions
  categorized as Business, currently backfilled from 2026-01-01 for future P&L,
  Schedule C, and cash reconciliation features.
- `business_value_snapshots`: daily backend-computed total business value rollups.

ZFI is a separate application/repo with separate auth and its own Supabase
database. MBOP does not store ZFI personal finance data. The manual
`integrations/push_zfi_business_summary.py` job writes summarized
business-operational payloads into a ZFI-owned table documented in
`docs/ZFI_INTEGRATION.md`.

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
