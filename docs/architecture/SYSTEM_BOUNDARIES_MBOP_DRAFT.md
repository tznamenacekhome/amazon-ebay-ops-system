# System Boundaries: MBOP Relative To ZFI

Status: Draft  
Last updated: 2026-06-26

## Purpose

This document defines MBOP's responsibilities relative to ZoltarFI / ZFI.

MBOP's mission is to run the Amazon/eBay resale business. ZFI's mission is to
optimize the household and business financial future.

MBOP should publish operational financial facts. ZFI should preserve,
normalize, interpret, compare, and plan from those facts.

## Boundary Summary

MBOP owns operational truth:

- What was bought.
- What was received.
- What is on order, in transit, delivered-not-received, received, listed, at
  Amazon FBA, outbound to Amazon, merchant-fulfilled, return-pending, or
  cancelled/refund-follow-up.
- What the item cost.
- What sold.
- What Amazon charged.
- What fulfillment/shipping cost.
- What COGS layer was consumed.
- What return/refund operational case needs action.
- What inventory exists and where it operationally sits.

ZFI owns financial planning:

- YNAB.
- Business cash in financial-planning context.
- Business value history after one-time MBOP backfill.
- Household net worth.
- Business net worth in household context.
- Tax planning.
- Schedule C categories.
- Quarterly tax support.
- Cash-flow planning.
- Owner draws/contributions.
- Accounting profit and taxable profit.

## 1. What MBOP Owns

MBOP owns the operational resale platform and remains source of truth for:

- Purchases and purchase items.
- Receiving workflow and warehouse verification.
- Inventory states and inventory value.
- FBA prep, inbound shipment workflow, and outbound-to-Amazon value.
- On-order, shipped-not-delivered, delivered-not-received, received, listed, and
  return-pending states.
- Amazon seller/FBA operational snapshots.
- Amazon Sales Orders operational records.
- Item-level profitability.
- Sales/order profitability.
- COGS allocation and COGS diagnostics.
- Shipping label and fulfillment cost inputs used for operational
  profitability.
- Returns, refunds, cancellation/refund follow-up, and order-problem workflow.
- Repricing, aged inventory action queues, sourcing ROI, and marketplace
  operational metrics.
- Amazon payout/cash status as source data to push outward to ZFI.

Operational profitability in MBOP means resale operating performance:

```text
sales
- marketplace fees
- shipping / fulfillment costs
- COGS
- return/refund impact where modeled
= operational profit
```

MBOP does not turn this into accounting profit or taxable profit.

## 2. What MBOP Should Not Own

MBOP should not own:

- Household net worth.
- Business net worth in household context.
- Permanent business value history after ZFI backfill is verified.
- YNAB integration as the long-term finance source.
- Business cash-flow planning.
- Owner draws/contributions.
- Recurring expense review.
- Schedule C category mapping.
- Quarterly tax estimates.
- Annual tax packet support.
- Tax return intelligence.
- Paystub, mortgage, HELOC, retirement, or household finance planning.
- Accounting profit or taxable profit.
- Receipt intelligence and personal/business expense classification.
- ZFI users, auth, roles, or sessions.

MBOP must not query ZFI for personal finance or household finance data.

## 3. Temporary MBOP Ownership To Migrate To ZFI

These MBOP features exist today because MBOP bootstrapped early financial
visibility. They should be treated as transitional.

### YNAB

Temporary MBOP items:

- `integrations/ynab_sync_cash_balance.py`
- `integrations/ynab_sync_business_transactions.py`
- `ynab_category_balance_snapshots`
- `ynab_business_transactions`
- `vw_latest_ynab_category_balance_snapshot`
- `run_all_syncs.py` jobs:
  - `YNAB Business transactions`
  - `YNAB cash balance`

Migration rule:

- Keep MBOP YNAB sync temporarily for parallel comparison.
- Do not turn it off until ZFI business finance is verified.
- After verification, freeze MBOP YNAB jobs, mark MBOP YNAB features legacy,
  then archive/remove only after confirmation that no MBOP operational workflow
  depends on YNAB.

### Business Value History

Temporary MBOP items:

- `integrations/business_value_snapshot.py`
- `business_value_snapshots`
- Dashboard Overview business value trend.
- Dashboard Growth business-value trend.
- `run_all_syncs.py` job: `Business value snapshot`.

Migration rule:

- MBOP should provide a one-time historical backfill of existing
  `business_value_snapshots` to ZFI.
- After ZFI verifies the backfill and begins calculating ongoing business value,
  ZFI owns business value history.
- MBOP may continue to calculate current inventory value and Amazon cash source
  components, but should not remain responsible for long-term business value
  history.

### Financial Dashboard Planning Surfaces

Temporary MBOP items:

- `web/app/api/dashboard/financial/route.ts`
- `web/app/api/dashboard/growth/route.ts`
- `web/app/api/dashboard/overview/route.ts`
- `web/app/dashboard/page.tsx`
- `web/app/dashboard/components.tsx`
- `web/app/dashboard/README.md`

Migration rule:

- Keep operational metrics needed for daily MBOP decisions.
- Move/copy broader financial planning views to ZFI.
- After ZFI is trusted, mark MBOP Financial dashboard as legacy or narrow it to
  operational gaps only.
- Remove or hide the Schedule C placeholder from MBOP once ZFI replaces it.

### Amazon Payout/Cash UI

Temporary MBOP items:

- Financial dashboard cash position.
- Overview/Financial dashboard Amazon Funds Available widgets.
- Payout reconciliation display.
- `amazon_finance_balance_snapshots`
- `vw_latest_amazon_finance_balance_snapshot`
- `integrations/amazon_sync_finance_balances.py`

Migration rule:

- MBOP should continue collecting Amazon payout/cash source data if needed to
  support ZFI and operational diagnostics.
- MBOP should push Amazon payout/cash status to ZFI.
- MBOP should not show payout status as a broad MBOP finance UI after ZFI has a
  verified cash/payout view.
- MBOP may keep Seller Central links or minimal operational status where needed
  for seller action/troubleshooting.

## 4. What MBOP Should Push To ZFI

MBOP should push summarized business-operational financial payloads to ZFI
Supabase through:

- `integrations/push_zfi_business_summary.py`
- ZFI table: `public.mbop_business_summaries`
- Upsert key: `(source, period_start, period_end)`

Minimum payload categories:

- Reporting period.
- Gross sales.
- Marketplace sales by channel where MBOP owns the channel.
- Refunds/returns summaries where modeled.
- Marketplace fees.
- Shipping label / fulfillment costs.
- COGS.
- Inventory purchases.
- Current inventory value.
- Aged inventory value.
- Inventory count and value by operational state.
- FBA inventory value.
- Merchant-fulfilled inventory value.
- Purchased-not-received value.
- Delivered-not-received value where available.
- Shipment-to-Amazon value.
- Operational gross profit.
- Operational estimated net profit.
- Amazon available-to-withdraw balance.
- Amazon-to-bank in-transit cash.
- Amazon deferred/reserved cash where available.
- Source timestamps.
- Alerts and confidence notes.
- Data completeness status.

Future push/backfill work:

- One-time export of historical `business_value_snapshots` to ZFI.
- Ongoing inventory value snapshots by state if ZFI needs trend fidelity beyond
  period summaries.
- Ongoing Amazon cash/payout snapshots for ZFI cash/payout history.

MBOP should stay summary-first. Item-level detail should not be pushed by
default unless a clear reporting/audit need emerges.

## 5. What MBOP Should Never Receive From ZFI

MBOP should never receive or store:

- ZFI household net worth.
- ZFI business net worth calculations.
- YNAB account balances, transactions, or category mappings sourced from ZFI.
- Tax return data.
- Schedule C category decisions.
- Quarterly tax estimate data.
- Paystub data.
- Mortgage, HELOC, retirement, or household planning data.
- Owner draws/contributions.
- ZFI user records, auth/session records, or role assignments.
- Ask Zoltar analysis containing personal finance data.

If ZFI needs operational detail, it should call a future scoped MBOP drilldown
API and receive only the requested operational records. MBOP should not ingest
ZFI's planning data in response.

## 6. Involved MBOP Files, Tables, Routes, Jobs, And Dashboards

### Python Integrations / Jobs

Operational source-of-truth jobs:

- `integrations/ebay_sync_buyer_purchases.py`
- `integrations/easypost_sync_shipments.py`
- `integrations/easypost_sync_order_problem_returns.py`
- `integrations/ebay_sync_order_problem_returns.py`
- `integrations/amazon_sync_sales_orders.py`
- `integrations/amazon_sync_sales_finances.py`
- `integrations/veeqo_sync_sales_labels.py`
- `integrations/amazon_sales_profitability.py`
- `integrations/apply_ebay_purchase_fifo_cogs.py`
- `integrations/apply_non_ebay_fifo_cogs.py`
- `integrations/import_non_ebay_cogs_sources.py`
- `integrations/amazon_sync_fba_inventory.py`
- `integrations/amazon_sync_fba_shipments.py`
- `integrations/easypost_sync_fba_shipments.py`
- `integrations/inventory_reconcile.py`
- `integrations/amazon_sync_listing_status.py`
- `integrations/amazon_sync_inventory_planning.py`
- `integrations/inventory_source_balance_audit.py`

Temporary/financial-planning bridge jobs:

- `integrations/ynab_sync_cash_balance.py`
- `integrations/ynab_sync_business_transactions.py`
- `integrations/business_value_snapshot.py`
- `integrations/amazon_sync_finance_balances.py`

ZFI outbound integration:

- `integrations/push_zfi_business_summary.py`

Orchestration:

- `run_all_syncs.py`
  - current groups include `finance-refresh` and `business-value-finalizer`
  - ZFI push is manual today and intentionally not scheduled yet

### Tables And Views

Operational source-of-truth or operational derived data:

- `purchases`
- `purchase_items`
- `inbound_shipments`
- `manual_item_matches`
- `fba_shipments`
- `fba_shipment_items`
- `fba_shipment_events`
- `order_problem_cases`
- `order_problem_events`
- `amazon_sales_orders`
- `amazon_sales_order_items`
- `amazon_sales_financial_events`
- `amazon_sales_finance_transactions`
- `amazon_sales_profitability`
- `amazon_sales_cogs_consumption`
- `amazon_sales_fulfillment_cost_overrides`
- `veeqo_sales_orders`
- `veeqo_sales_shipments`
- `non_ebay_purchase_cogs_sources`
- `amazon_inventory_cogs_layers`
- `amazon_skus`
- `amazon_fba_inventory_snapshots`
- `amazon_listing_snapshots`
- `amazon_inventory_planning_snapshots`
- `amazon_fee_estimates`
- `inventory_positions`
- `inventory_movements`
- `inventory_reconciliation_events`
- `inventory_reconciliation_event_items`
- `inventorylab_active_inventory_backfill`
- `inventorylab_inventory_valuation_snapshots`
- `vw_purchases_dashboard`
- `vw_amazon_sales_orders_recent`
- `vw_amazon_sales_summary`
- `vw_current_amazon_inventory_cogs`
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_amazon_listing_snapshot`
- `vw_latest_amazon_inventory_planning_snapshot`
- `vw_latest_inventorylab_inventory_valuation`
- `vw_inventory_position_summary`
- `vw_open_inventory_reconciliation_items`

Temporary financial-planning data to migrate/de-emphasize:

- `ynab_category_balance_snapshots`
- `ynab_business_transactions`
- `vw_latest_ynab_category_balance_snapshot`
- `business_value_snapshots`

Operational Amazon cash/payout source data pushed to ZFI:

- `amazon_finance_balance_snapshots`
- `vw_latest_amazon_finance_balance_snapshot`

### API Routes

Operational MBOP routes:

- `web/app/api/purchases/route.ts`
- `web/app/api/receiving/route.ts`
- `web/app/api/fba-shipments/route.ts`
- `web/app/api/order-problems/route.ts`
- `web/app/api/order-problems/[id]/actions/route.ts`
- `web/app/api/sales-orders/route.ts`
- `web/app/api/amazon/repricing-advisor/route.ts`
- `web/app/api/dashboard/operations/route.ts`
- `web/app/api/dashboard/inventory/route.ts`
- `web/app/api/dashboard/amazon/route.ts`
- `web/app/api/dashboard/loss-prevention/route.ts`
- `web/app/api/dashboard/sourcing/route.ts`
- `web/app/api/dashboard/system-health/route.ts`
- `web/app/api/screen-data-freshness/route.ts`

Financial-planning/dashboard routes to migrate or narrow:

- `web/app/api/dashboard/overview/route.ts`
- `web/app/api/dashboard/financial/route.ts`
- `web/app/api/dashboard/growth/route.ts`

### Frontend Dashboards / Screens

Operational screens MBOP keeps:

- `web/app/page.tsx`
- `web/app/purchases/*`
- `web/app/receiving/page.tsx`
- `web/app/fba/page.tsx`
- `web/app/sales-orders/page.tsx`
- `web/app/inventory-reconciliation/page.tsx`
- `web/app/repricing/page.tsx`
- `web/app/sourcing/page.tsx`
- `web/app/system-health/page.tsx`

Dashboard areas to move/copy/de-emphasize after ZFI verification:

- Dashboard Overview business value summary.
- Dashboard Financial cash/profit/payout/Schedule C areas.
- Dashboard Growth business value and financial trend areas.

## 7. Operational Source-Of-Truth Data

The following are MBOP operational source-of-truth categories:

- Item acquisition records and item cost.
- Current purchase item workflow state.
- Receiving verification.
- Marketplace assignment after receiving.
- FBA shipment grouping and included quantities.
- Amazon inbound shipment status and quantities.
- Current inventory state and inventory value.
- Amazon FBA inventory/listing/planning operational snapshots.
- Sales order records.
- Sales financial events and marketplace fees.
- Fulfillment/shipping label costs.
- COGS allocation.
- Operational item/order profitability.
- Missing-data queues for COGS, fees, fulfillment costs, ASINs, titles, system,
  and sell price.
- Order-problem/return/refund workflow records.
- Repricing and aged-inventory operational action queues.

ZFI may display financial interpretations of these facts, but MBOP remains the
place to fix or change them.

## 8. Financial-Planning Data That Should Move To ZFI

The following should move to ZFI or become ZFI-owned:

- Business cash from YNAB business category balance.
- YNAB Business transactions.
- Long-term business value history after one-time MBOP backfill.
- Business value trend/reporting.
- Household net worth.
- Business net worth in household context.
- Cash-flow planning.
- Owner draws/contributions.
- Software/tool expense review.
- Schedule C mapping.
- Tax category classification.
- Quarterly tax estimate support.
- Annual tax packet support.
- Accounting profit.
- Taxable profit.
- Paystub, mortgage, HELOC, retirement, tax return, and household finance
  intelligence.

MBOP may provide operational estimates to ZFI. ZFI decides how those estimates
roll into accounting and tax views.

## Migration Guidance

### Phase 1: Parallel Operation

- Keep MBOP YNAB sync active.
- Keep MBOP financial dashboards available.
- Push current summaries to ZFI.
- Build ZFI business finance views.
- Compare MBOP and ZFI values.

### Phase 2: Historical Backfill

- Export existing `business_value_snapshots` to ZFI.
- Preserve original dates, component values, raw rollup JSON, and confidence
  notes where available.
- Mark imported rows in ZFI as migrated from MBOP.

### Phase 3: ZFI Verification

- Verify ZFI YNAB business cash against MBOP legacy YNAB values.
- Verify ZFI business value trend against MBOP historical trend.
- Verify ZFI operational profit against MBOP Sales Orders summaries.
- Verify ZFI cash/payout view against MBOP Amazon finance snapshots.

### Phase 4: MBOP De-Emphasis

- Freeze MBOP YNAB jobs.
- Mark MBOP YNAB and business-value trend surfaces as legacy.
- Narrow MBOP Financial dashboard to operational gaps only.
- Remove Schedule C placeholder from MBOP.
- Keep operational source routes and dashboards intact.

## Future ZFI-To-MBOP Drilldown

ZFI should remain summary-first. If ZFI or Ask Zoltar needs operational detail,
it should use future scoped MBOP APIs rather than copying all MBOP operational
tables into ZFI.

Potential drilldown targets:

- Sales orders.
- Purchase items.
- Returns/order problems.
- Inventory state details.
- COGS corrections.
- FBA shipment details.
- Shipping label details.
- Marketplace fee details.
- Sourcing and purchase history.

Principles:

- Drilldown is on-demand.
- Drilldown is scoped to an explicit user question/report.
- Drilldown returns operational data only.
- MBOP still does not receive ZFI personal finance data.
- ZFI should not duplicate full MBOP operational datasets unless a clear
  reporting/audit need emerges.

## Implementation Guardrails

- Do not add shared MBOP/ZFI auth.
- Do not expose ZFI service-role keys to browser code.
- Do not add ZFI frontend routes inside MBOP.
- Do not make MBOP query ZFI.
- Do not remove MBOP financial dashboards until ZFI replacements are verified.
- Do not make MBOP responsible for accounting or taxable profit.
- Do not let frontend components recalculate MBOP landed cost, COGS, or
  operational profit.
- Treat `integrations/push_zfi_business_summary.py` as outbound-only.
