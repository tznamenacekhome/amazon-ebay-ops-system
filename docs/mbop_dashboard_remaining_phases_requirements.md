# MBOP Dashboard Remaining Phases Requirements

## Project
Midnight Blue Operations Platform (MBOP)

## Purpose
This document provides Codex-ready requirements for the remaining dashboard phases after Phase 1 of the MBOP dashboard split. It assumes Phase 1 created the dashboard shell, tabbed/segmented dashboard navigation, and initial Overview / Operations / Financial dashboard structure.

The goal of these remaining phases is to add deeper monitoring dashboards without making MBOP bloated, slow, or hard to navigate.

---

# Non-Negotiable Design Rules

## Keep One Top-Level Dashboard Menu Item
Do not add separate top-level left-nav entries for every monitoring dashboard.

Keep the current compact app shell pattern and use one existing left-nav item:

```text
Dashboard
```

Inside `/dashboard`, use tabs or a compact segmented control:

```text
Overview | Financial | Operations | Inventory | Amazon | Growth | Sourcing | Loss Prevention | System Health
```

If that becomes too wide, use grouped secondary navigation:

```text
Overview
Money: Financial | Growth
Inventory: Inventory | Amazon | Sourcing
Risk: Loss Prevention | System Health
```

Preferred MVP: one horizontal tab row with wrapping or overflow support.

## Do Not Turn Dashboards Into Work Queues
Dashboards summarize and prioritize. Operational work stays in existing workspaces.

Dashboard widgets should link to existing workflows:

- Purchases
- Receiving
- Amazon FBA
- Sales Orders
- Repricing
- Inventory Reconciliation
- Order Problems

Avoid embedding full editable operational tables in dashboard tabs.

## Backend Owns Metrics
React must not calculate business logic.

The backend/API must own:

- landed cost
- inventory value
- COGS
- ROI
- profit
- workflow status grouping
- aged inventory tiers
- repricing buckets
- reconciliation finding counts
- cash/value rollups
- sourcing scores

Frontend renders API-provided values only.

## Avoid Dashboard Sprawl
Dashboard design should follow these rules:

- no duplicated tabs with only slightly different filters
- no experimental dashboards left permanently visible
- each dashboard tab must answer a distinct business question
- each tab should have a clear owner question, primary KPIs, and drill-down links
- keep visible KPI cards to roughly 5-9 per tab
- use progressive disclosure: summary first, details by drill-down

Rationale: dashboard UX guidance consistently warns against clutter, excessive KPIs, and dashboard sprawl; keep MBOP focused on actionable monitoring rather than decorative reporting.

## Performance Requirements
Each dashboard tab must load independently.

Do not load all dashboard tabs at once.

Required behavior:

- `/dashboard?view=inventory` loads inventory dashboard data only.
- Switching tabs fetches only the newly selected tab if not already loaded.
- Show skeleton/loading state for the active tab only.
- Do not block the dashboard shell while a heavy tab loads.
- Do not trigger external API calls from dashboard page loads.
- Do not spend Keepa tokens from dashboard UI rendering.
- Do not run full reconciliation or broad sync jobs from tab load.

Recommended API shape:

```text
/api/dashboard/overview
/api/dashboard/financial
/api/dashboard/operations
/api/dashboard/inventory
/api/dashboard/amazon
/api/dashboard/growth
/api/dashboard/sourcing
/api/dashboard/loss-prevention
/api/dashboard/system-health
```

A shared `/api/dashboard?view=...` route is acceptable if it stays maintainable, but separate route files are preferred for AI-assisted edits.

## Freshness Requirements
Each dashboard tab must show a `Last updated` indicator near the refresh control using `/api/screen-data-freshness` or a dashboard-specific freshness API extension.

Dashboard freshness must represent the relevant source data, not browser page-load time.

---

# Phase 2 Dashboard Scope

Phase 2 should implement:

1. Inventory Dashboard
2. Amazon Performance Dashboard
3. Growth Dashboard

These dashboards deepen business monitoring using data already substantially present in MBOP.

---

# Phase 2A: Inventory Dashboard

## Route / Navigation

Use existing dashboard shell:

```text
/dashboard?view=inventory
```

Tab label:

```text
Inventory
```

Do not create a new top-level left-nav item.

## Primary Business Question

Where is business capital tied up, how old is it, and what inventory needs attention?

## Data Sources

Use backend-owned data from existing MBOP tables/views:

- `inventory_positions`
- `vw_inventory_position_summary`
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_inventorylab_inventory_valuation`
- `vw_purchases_dashboard`
- `fba_shipments`
- `fba_shipment_items`
- `purchase_items`
- `business_value_snapshots`
- `vw_open_inventory_reconciliation_items`

Do not query Supabase directly from React.

## API Route

Create:

```text
web/app/api/dashboard/inventory/route.ts
```

The route should return one JSON object:

```ts
type InventoryDashboardResponse = {
  freshness: {
    inventoryPositionsUpdatedAt: string | null
    amazonInventoryUpdatedAt: string | null
    inventoryValuationUpdatedAt: string | null
    reconciliationUpdatedAt: string | null
    oldestRequiredInputAt: string | null
  }
  summary: {
    totalUnits: number
    totalInventoryValue: number
    amazonFbaSellableUnits: number
    amazonFbaValue: number
    outboundToAmazonUnits: number
    outboundToAmazonValue: number
    receivedUnits: number
    receivedValue: number
    orderedNotReceivedUnits: number
    orderedNotReceivedValue: number
    returnPendingUnits: number
    returnPendingValue: number
  }
  byLocation: Array<{
    locationKey: string
    label: string
    units: number
    value: number
    drilldownUrl: string | null
  }>
  ageBuckets: Array<{
    bucket: '0-30' | '31-60' | '61-90' | '91-180' | '181-365' | '365+' | 'unknown'
    units: number
    value: number
    percentOfValue: number
    drilldownUrl: string | null
  }>
  capitalAtRisk: {
    over90DaysValue: number
    over180DaysValue: number
    over365DaysValue: number
    unknownAgeValue: number
  }
  concentration: Array<{
    asin: string | null
    sellerSku: string | null
    title: string
    system: string | null
    units: number
    value: number
    locationSummary: string
    drilldownUrl: string | null
  }>
  attention: Array<{
    severity: 'high' | 'medium' | 'low'
    label: string
    count: number
    value: number | null
    reason: string
    drilldownUrl: string | null
  }>
}
```

## UI Layout

Use dense but readable layout.

### Top Row: KPI Cards

Show no more than 6 KPI cards:

1. Total Inventory Value
2. Total Units
3. Amazon FBA Sellable
4. Outbound To Amazon
5. Received / Ready For FBA
6. Ordered Not Received

Each card should include:

- value
- unit count where relevant
- small secondary label
- optional drill-down link

### Section 1: Inventory Value By Location

Use a compact table, not a huge chart.

Columns:

| Location | Units | Value | % of Total | Action |
|---|---:|---:|---:|---|

Location rows:

- Amazon FBA
- Outbound to Amazon
- Received / Ready for FBA
- Ordered not received
- Return pending
- Other / unknown

Each row should link to the owning workspace where possible.

### Section 2: Inventory Age Buckets

Use a horizontal bar chart or compact table.

Buckets:

- 0-30
- 31-60
- 61-90
- 91-180
- 181-365
- 365+
- Unknown

Show value and units.

Add visual emphasis for 181+ and unknown age.

### Section 3: Capital At Risk

Show a small risk panel:

- Value over 90 days
- Value over 180 days
- Value over 365 days
- Value with unknown age

These should link to Repricing, Inventory Reconciliation, or Purchases depending on source.

### Section 4: Top Inventory Concentration

Show top 10 ASINs/products by inventory value.

Columns:

| ASIN | Title | System | Units | Value | Location | Action |
|---|---|---|---:|---:|---|---|

Purpose: identify too much capital concentrated in a few products.

### Section 5: Inventory Attention

Show a short prioritized list, maximum 8 rows.

Examples:

- Amazon unknown to MBOP
- Quantity mismatch
- Suppressed or stranded with value
- Unsellable Amazon units
- Received inventory aging over X days
- Ordered not received over X days
- Return pending value

Do not show the full reconciliation table here. Link to `/inventory-reconciliation`.

## Backend Rules

- Use existing derived inventory layer where possible.
- Do not write to workflow tables from dashboard route.
- Do not recalculate landed cost from raw purchase rows.
- Use `vw_purchases_dashboard.unit_cost` where purchase cost is needed.
- Use latest InventoryLab valuation snapshot only as legacy Amazon FBA opening-balance context.
- Keep Amazon reserved/FC transfer as inventory detail, not automatically as a problem.
- Ignore Amazon listing/catalog issues when Amazon still reports sellable FBA units unless existing reconciliation logic flags them as actionable.

## Drill-Down Requirements

Examples:

- Amazon FBA value -> `/inventory-reconciliation?filter=amazon_fba`
- Outbound to Amazon -> `/fba?filter=current_shipments`
- Received value -> `/fba?filter=ready`
- Ordered not received -> `/purchases?status=open_purchase_work`
- Return pending -> `/purchases?tab=order-problems&stage=return_needed`
- Age 181+ -> `/repricing?ageBucket=181plus`

Use actual existing query parameter patterns if different. Do not invent broken links if target screens do not support them; add TODO comments or link to the base workspace.

## Acceptance Criteria

- Inventory tab renders without loading other dashboard tabs.
- No full operational table is embedded.
- All values are API-provided.
- KPI cards fit above the fold on a large desktop monitor.
- Location and age sections render quickly with current data volume.
- Drill-down links work or degrade to base workflow routes.
- Dashboard route performs no external API calls.

---

# Phase 2B: Amazon Performance Dashboard

## Route / Navigation

```text
/dashboard?view=amazon
```

Tab label:

```text
Amazon
```

## Primary Business Question

Is the Amazon side of the business healthy, selling, and operationally clean?

## Data Sources

Use existing Amazon-specific tables and advisory views:

- `amazon_sales_orders`
- `amazon_sales_profitability`
- `amazon_sales_cogs_consumption`
- `amazon_fba_inventory_snapshots`
- `vw_latest_amazon_fba_inventory_snapshot`
- `amazon_listing_snapshots`
- `vw_latest_amazon_listing_snapshot`
- `amazon_inventory_planning_snapshots`
- `vw_latest_amazon_inventory_planning_snapshot`
- `vw_latest_informed_listing_snapshot`
- `vw_latest_keepa_product_snapshot`
- `inventory_positions`
- `/api/amazon/repricing-advisor` logic or shared backend helper

Do not duplicate repricing recommendation logic in the frontend.

## API Route

Create:

```text
web/app/api/dashboard/amazon/route.ts
```

Response shape:

```ts
type AmazonDashboardResponse = {
  freshness: {
    salesUpdatedAt: string | null
    inventoryUpdatedAt: string | null
    listingUpdatedAt: string | null
    planningUpdatedAt: string | null
    informedUpdatedAt: string | null
    keepaUpdatedAt: string | null
    oldestRequiredInputAt: string | null
  }
  salesSummary: {
    unitsSold7d: number
    unitsSold30d: number
    revenue30d: number
    grossProfit30d: number
    netProfit30d: number
    roi30d: number | null
    missingCogsCount: number
    missingFeesCount: number
    pendingFeesCount: number
  }
  inventorySummary: {
    activeSkus: number
    sellableUnits: number
    reservedUnits: number
    inboundUnits: number
    unfulfillableUnits: number
    strandedOrSuppressedCount: number
    unsellableCount: number
  }
  listingHealth: Array<{
    severity: 'high' | 'medium' | 'low'
    issueType: string
    count: number
    units: number | null
    value: number | null
    drilldownUrl: string | null
  }>
  repricingSummary: {
    pricingRows: number
    pricingCapital: number
    liquidateRows: number
    liquidateCapital: number
    removeOrEbayRows: number
    missingDataRows: number
    snoozedRows: number
  }
  topSellers: Array<{
    asin: string
    sellerSku: string | null
    title: string
    unitsSold30d: number
    revenue30d: number
    netProfit30d: number
    roi30d: number | null
    currentFbaUnits: number
    drilldownUrl: string | null
  }>
  staleInventory: Array<{
    asin: string
    sellerSku: string | null
    title: string
    units: number
    value: number | null
    ageBucket: string | null
    currentVelocity: number | null
    recommendation: string
    drilldownUrl: string | null
  }>
}
```

## UI Layout

### Top Row: Amazon KPI Cards

Show 6 cards maximum:

1. 30-Day Units Sold
2. 30-Day Revenue
3. 30-Day Net Profit
4. FBA Sellable Units
5. Listing Issues
6. Repricing Action Capital

### Section 1: Sales Performance

Compact chart/table:

- 7-day units
- 30-day units
- 30-day revenue
- 30-day profit
- ROI

Add data-status badges:

- Complete
- Missing COGS
- Missing Fees
- Pending Fees

### Section 2: Listing / Inventory Health

Show grouped issue counts:

| Issue | Count | Units | Value | Action |
|---|---:|---:|---:|---|

Issue examples:

- Suppressed / non-buyable
- Stranded
- Unsellable
- Missing COGS
- Missing fees after shipment
- Inventory mismatch

### Section 3: Repricing Summary

Use summarized repricing advisor output:

- Pricing candidates
- Liquidation candidates
- Remove/eBay candidates
- Missing data
- Snoozed

Do not duplicate the full Repricing page.

Link to `/repricing` with filters.

### Section 4: Top Sellers

Top 10 ASINs by 30-day profit.

Columns:

| ASIN | Title | Units Sold | Revenue | Profit | ROI | FBA Units |
|---|---|---:|---:|---:|---:|---:|

### Section 5: Stale High-Capital Inventory

Top 10 stale/high-capital rows from repricing advisor.

Columns:

| ASIN | Title | Units | Value | Age | Velocity | Recommendation |
|---|---|---:|---:|---|---:|---|

## Backend Rules

- Amazon data stays in Amazon-specific tables.
- Do not write to Amazon, Informed, Keepa, purchases, or workflow tables.
- Use Amazon Sales Orders 2025-forward cutoff.
- Use backend-calculated profitability only.
- Missing fees should display based on fulfillment/order status rules already established by Sales Orders API.
- Repricing data should come from existing repricing advisor backend logic or shared functions, not copied frontend logic.

## Drill-Down Requirements

- Missing COGS -> `/sales-orders?dataStatus=missing_cogs`
- Missing Fees -> `/sales-orders?dataStatus=missing_fees`
- Pending Fees -> `/sales-orders?dataStatus=pending`
- Repricing Candidates -> `/repricing?bucket=pricing`
- Liquidation -> `/repricing?tier=liquidate`
- Listing Issues -> `/inventory-reconciliation?type=amazon_listing_issue`
- Unsellable -> `/inventory-reconciliation?type=amazon_unsellable`

## Acceptance Criteria

- Amazon tab loads independently.
- No external Amazon, Keepa, or Informed calls happen from page load.
- Amazon data is read-only.
- Repricing summary matches Repricing page counts for equivalent filters.
- Sales summary excludes pre-2025 data.
- Top Sellers uses completed backend profitability rows or clearly flags incomplete rows.

---

# Phase 2C: Growth Dashboard

## Route / Navigation

```text
/dashboard?view=growth
```

Tab label:

```text
Growth
```

## Primary Business Question

Is Midnight Blue Enterprises growing in revenue, profit, inventory productivity, and operational efficiency?

## Data Sources

- `amazon_sales_profitability`
- `amazon_sales_orders`
- `business_value_snapshots`
- `vw_purchases_dashboard`
- `inventory_positions`
- `ynab_business_transactions`
- `amazon_finance_balance_snapshots`
- `purchase_items`
- `fba_shipment_items`

## API Route

Create:

```text
web/app/api/dashboard/growth/route.ts
```

Response shape:

```ts
type GrowthDashboardResponse = {
  freshness: {
    salesUpdatedAt: string | null
    purchasesUpdatedAt: string | null
    businessValueUpdatedAt: string | null
    oldestRequiredInputAt: string | null
  }
  summary: {
    revenueMtd: number
    revenueLast30d: number
    revenueYtd: number
    profitMtd: number
    profitLast30d: number
    profitYtd: number
    roiLast90d: number | null
    businessValueCurrent: number | null
    businessValueChange30d: number | null
    unitsPurchasedLast30d: number
    unitsSoldLast30d: number
  }
  monthlyTrends: Array<{
    yearMonth: string
    revenue: number
    grossProfit: number
    netProfit: number
    unitsSold: number
    unitsPurchased: number
    inventorySpend: number
    endingBusinessValue: number | null
  }>
  efficiency: {
    averageBuyCostLast90d: number | null
    averageProfitPerUnitLast90d: number | null
    averageRoiLast90d: number | null
    purchaseToReceivedMedianDays: number | null
    receivedToListedMedianDays: number | null
    purchaseToSoldMedianDays: number | null
  }
  growthSignals: Array<{
    label: string
    currentValue: number
    previousValue: number | null
    changePercent: number | null
    direction: 'up' | 'down' | 'flat' | 'unknown'
    interpretation: string
  }>
}
```

## UI Layout

### Top Row: Growth KPI Cards

Show 6 cards:

1. Revenue Last 30 Days
2. Profit Last 30 Days
3. ROI Last 90 Days
4. Business Value
5. Units Purchased Last 30 Days
6. Units Sold Last 30 Days

### Section 1: Monthly Trend

Line or bar chart by month:

- Revenue
- Net profit
- Inventory spend
- Business value

Do not create an overly complex multi-axis chart if readability suffers. A compact table plus one chart is acceptable.

### Section 2: Month-by-Month Table

Columns:

| Month | Revenue | Profit | Units Sold | Units Purchased | Inventory Spend | Ending Business Value |
|---|---:|---:|---:|---:|---:|---:|

### Section 3: Efficiency Metrics

Show cards or compact table:

- Average buy cost
- Average profit per sold unit
- Average ROI
- Purchase-to-received median days
- Received-to-listed median days
- Purchase-to-sold median days

### Section 4: Growth Signals

Short interpreted list.

Examples:

- Revenue up 18% vs previous 30 days
- Profit down while revenue up, check fee/COGS mix
- Units purchased below units sold, inventory may shrink
- Business value flat despite revenue growth, check cash/inventory conversion

## Backend Rules

- Do not infer profitability from revenue alone.
- Use backend profitability rows where available.
- Flag incomplete metrics when missing COGS/fees materially affect the period.
- Do not mix personal sale proceeds with resale business profit unless explicitly classified.
- Cash accounting/tax reporting is separate from inventory productivity; avoid presenting inventory purchases as immediate profit reduction unless specifically in cash-flow context.

## Acceptance Criteria

- Growth dashboard clearly separates sales/profit, inventory spend, and business value.
- Monthly table loads quickly.
- Incomplete profitability periods are visibly flagged.
- Metrics are useful for business decisions, not vanity-only.

---

# Phase 3 Dashboard Scope

Phase 3 should implement:

1. Sourcing & Replenishment Dashboard
2. Loss Prevention Dashboard
3. System Health Dashboard

These dashboards are more workflow-adjacent and should remain monitoring surfaces unless/until promoted into full workflows.

---

# Phase 3A: Sourcing & Replenishment Dashboard

## Route / Navigation

```text
/dashboard?view=sourcing
```

Tab label:

```text
Sourcing
```

## Primary Business Question

What should I buy next, based on recent sales, profitability, inventory gaps, and replenishment opportunity?

## MVP Scope

Do not build the full eBay sourcing engine in this dashboard unless it already exists.

The dashboard should first surface replenishment candidates from MBOP-owned data:

- recently sold profitable ASINs
- sold recently and now out of stock
- high ROI products with low/no inventory
- products with good sales velocity and low current supply
- products worth researching manually

Future eBay buy opportunity feeds can plug into this tab later.

## Data Sources

- `amazon_sales_profitability`
- `amazon_sales_orders`
- `amazon_sales_cogs_consumption`
- `inventory_positions`
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_keepa_product_snapshot`
- `vw_latest_informed_listing_snapshot`
- `purchase_items`
- `vw_purchases_dashboard`
- future sourcing candidate tables when implemented

## API Route

Create:

```text
web/app/api/dashboard/sourcing/route.ts
```

Response shape:

```ts
type SourcingDashboardResponse = {
  freshness: {
    salesUpdatedAt: string | null
    inventoryUpdatedAt: string | null
    keepaUpdatedAt: string | null
    informedUpdatedAt: string | null
    oldestRequiredInputAt: string | null
  }
  summary: {
    replenishmentCandidates: number
    outOfStockRecentSellers: number
    lowStockHighRoi: number
    highProfitRepeatBuys: number
    researchQueueValue: number | null
  }
  candidates: Array<{
    priority: 'high' | 'medium' | 'low'
    score: number
    asin: string
    sellerSku: string | null
    title: string
    system: string | null
    unitsSold30d: number
    unitsSold90d: number
    currentAmazonUnits: number
    currentMbopPreAmazonUnits: number
    averageSalePrice90d: number | null
    averageProfit90d: number | null
    averageRoi90d: number | null
    lastPurchaseCost: number | null
    suggestedMaxBuyCost: number | null
    reason: string
    amazonUrl: string | null
    keepaUrl: string | null
    ebaySearchUrl: string | null
  }>
  recentlyOutOfStock: Array<{
    asin: string
    title: string
    system: string | null
    unitsSold90d: number
    averageProfit90d: number | null
    lastSoldDate: string | null
    lastPurchaseCost: number | null
    reason: string
    ebaySearchUrl: string | null
  }>
  repeatWinners: Array<{
    asin: string
    title: string
    system: string | null
    totalUnitsSold: number
    totalProfit: number
    averageRoi: number | null
    timesPurchased: number
    reason: string
  }>
}
```

## Candidate Scoring MVP

Backend should compute a simple replenishment score. Keep it transparent.

Suggested score components:

- recent sales velocity
- recent net profit per unit
- ROI
- current inventory gap
- repeat purchase history
- Keepa availability / sales-rank signal if available
- penalize missing COGS, missing fees, missing ASIN, missing cost
- penalize products with known listing suppression/unsellable issues

Do not use opaque AI scoring for MVP.

Example scoring categories:

```text
High priority:
- sold in last 30/90 days
- current inventory <= 0 or low
- positive profit and acceptable ROI
- no major listing issue

Medium priority:
- sold in last 90 days
- lower velocity or incomplete data

Low priority:
- profitable history but stale or missing confidence data
```

## UI Layout

### Top Row: Sourcing KPI Cards

Show 5 cards:

1. Replenishment Candidates
2. Out of Stock Recent Sellers
3. Low Stock / High ROI
4. Repeat Winners
5. Needs Research

### Section 1: Priority Buy Research Queue

Compact table, max 25 rows by default.

Columns:

| Priority | ASIN/Title | System | Sold 30d | Current Units | Avg Profit | ROI | Max Buy Cost | Reason | Links |
|---|---|---|---:|---:|---:|---:|---:|---|---|

Links:

- Amazon listing
- Keepa if available
- eBay search using cleaned title + system

### Section 2: Recently Out Of Stock

Shows products sold recently but currently have zero sellable Amazon units and no MBOP pre-Amazon units.

### Section 3: Repeat Winners

Shows products that have been purchased and sold multiple times with good results.

## Backend Rules

- Do not write purchase recommendations into purchase_items.
- Do not auto-buy anything.
- Do not call eBay buy APIs.
- Do not trigger Keepa token spending from page load.
- Do not infer ASIN matches across video game systems.
- Use backend title cleaner for eBay search URL generation.
- Make scoring explainable in the returned `reason` field.

## Future Extension Hooks

Leave room for future tables:

```text
sourcing_candidates
sourcing_candidate_events
sourcing_watchlist
sourcing_candidate_scores
```

Do not create these unless needed for MVP. If created, make them additive and read-only from this dashboard.

## Acceptance Criteria

- Dashboard produces a useful manual buy research queue from existing sales/inventory data.
- Candidate rows explain why they were selected.
- No external marketplace actions occur.
- No AI or Keepa calls occur during render.
- Links help the operator research efficiently.

---

# Phase 3B: Loss Prevention Dashboard

## Route / Navigation

```text
/dashboard?view=loss-prevention
```

Tab label:

```text
Loss Prevention
```

## Primary Business Question

Where is money at risk because of returns, refunds, missing items, late shipments, Amazon discrepancies, or unrecovered value?

## Data Sources

- `order_problem_cases`
- `order_problem_events`
- `purchase_items`
- `vw_purchases_dashboard`
- `inbound_shipments`
- `inventory_reconciliation_event_items`
- `amazon_sales_profitability`
- `amazon_fba_inventory_snapshots`
- future Amazon removals/discrepancy workflow tables

## API Route

Create:

```text
web/app/api/dashboard/loss-prevention/route.ts
```

Response shape:

```ts
type LossPreventionDashboardResponse = {
  freshness: {
    orderProblemsUpdatedAt: string | null
    trackingUpdatedAt: string | null
    reconciliationUpdatedAt: string | null
    salesUpdatedAt: string | null
    oldestRequiredInputAt: string | null
  }
  summary: {
    openProblemCases: number
    estimatedValueAtRisk: number
    refundPendingValue: number
    returnPendingCount: number
    lateShipmentCount: number
    carrierExceptionCount: number
    amazonUnsellableUnits: number
    amazonDiscrepancyCount: number
  }
  byRiskType: Array<{
    riskType: string
    count: number
    valueAtRisk: number | null
    oldestAgeDays: number | null
    drilldownUrl: string | null
  }>
  urgentCases: Array<{
    severity: 'high' | 'medium' | 'low'
    caseId: string
    orderNumber: string | null
    title: string
    status: string
    stage: string
    ageDays: number | null
    valueAtRisk: number | null
    nextAction: string | null
    actionDueDate: string | null
    drilldownUrl: string | null
  }>
  lossTrend: Array<{
    yearMonth: string
    refundsReceived: number | null
    closedNoRefundValue: number | null
    returnCount: number
    cancelledCount: number
    problemCaseCount: number
  }>
}
```

## UI Layout

### Top Row: Loss Prevention KPI Cards

Show 6 cards:

1. Open Problem Cases
2. Estimated Value At Risk
3. Refund Pending
4. Return Pending
5. Late / Stale Shipments
6. Amazon Discrepancies

### Section 1: Risk Type Summary

Compact table:

| Risk Type | Count | Value At Risk | Oldest | Action |
|---|---:|---:|---:|---|

Risk types:

- Return pending
- Refund pending
- Late delivery
- Stale/no tracking
- Carrier exception
- Cancelled awaiting refund
- Missing item / replacement pending
- Amazon unsellable
- Amazon discrepancy

### Section 2: Urgent Cases

Show top 10 urgent cases by severity/action date/age.

Columns:

| Severity | Order | Item | Stage | Age | Value | Next Action |
|---|---|---|---|---:|---:|---|

Link each row to Purchases -> Order Problems or relevant drawer route if supported.

### Section 3: Loss / Recovery Trend

Monthly table or simple chart:

- returns opened
- refunds received
- closed no refund value
- cancellations
- problem cases opened

## Backend Rules

- Do not perform marketplace actions.
- Do not create eBay returns.
- Do not issue refunds.
- Do not update order problem workflow from dashboard route.
- Estimate value at risk using backend unit cost from `vw_purchases_dashboard.unit_cost * quantity` unless a more specific refund amount exists.
- Partial refunds where item is kept must not automatically adjust cost here.
- Amazon discrepancies should be read from reconciliation findings until future dedicated workflows exist.

## Drill-Down Requirements

- Return pending -> `/purchases?tab=order-problems&stage=return_needed`
- Refund pending -> `/purchases?tab=order-problems&stage=refund_pending`
- Late shipment -> `/purchases?tab=order-problems&type=late_delivery_candidate`
- Carrier exception -> `/purchases?tab=order-problems&type=carrier_exception_candidate`
- Amazon discrepancy -> `/inventory-reconciliation`

## Acceptance Criteria

- Loss Prevention tab summarizes risk without duplicating the Order Problems screen.
- Estimated value at risk is clearly labeled as estimated.
- Urgent cases are prioritized and actionable.
- No workflow state changes happen from dashboard route.

---

# Phase 3C: System Health Dashboard

## Route / Navigation

```text
/dashboard?view=system-health
```

Tab label:

```text
System Health
```

## Primary Business Question

Is MBOP fresh, healthy, and safe to rely on today?

## Data Sources

- `logs/sync_health.json`
- `logs/sync_runs.jsonl`
- `logs/scheduler.log`
- source table latest timestamps
- `/api/screen-data-freshness`
- import batches
- Amazon snapshot timestamps
- YNAB snapshot timestamps
- Keepa snapshot timestamps
- Informed report timestamps
- inventory reconciliation run timestamps
- Supabase health checks if already implemented safely

Do not expose secrets or raw tokens.

## API Route

Create:

```text
web/app/api/dashboard/system-health/route.ts
```

Response shape:

```ts
type SystemHealthDashboardResponse = {
  summary: {
    overallStatus: 'healthy' | 'warning' | 'error' | 'unknown'
    staleDomains: number
    failedJobsLastRun: number
    lastOrchestratorRunAt: string | null
    lastSuccessfulCoreRunAt: string | null
    lastSuccessfulDailyRunAt: string | null
  }
  domains: Array<{
    domain: string
    label: string
    status: 'fresh' | 'stale' | 'failed' | 'unknown' | 'skipped'
    lastSuccessAt: string | null
    lastAttemptAt: string | null
    expectedCadence: string
    ageHours: number | null
    message: string | null
  }>
  recentRuns: Array<{
    runId: string | null
    startedAt: string | null
    finishedAt: string | null
    group: string | null
    status: 'success' | 'partial' | 'failed' | 'unknown'
    failedJobs: number
    summary: string | null
  }>
  capacity: {
    supabaseStatus: 'ok' | 'warning' | 'unknown'
    databaseSizeMb: number | null
    diskIoWarning: boolean | null
    message: string | null
  }
  externalLimits: {
    keepaTokens: number | null
    keepaTokenStatus: 'ok' | 'low' | 'unknown'
    amazonThrottleWarnings: number | null
    easyPostErrors: number | null
    message: string | null
  }
}
```

## UI Layout

### Top Row: Health KPI Cards

Show 5 cards:

1. Overall Status
2. Last Core Run
3. Last Daily Run
4. Failed Jobs
5. Stale Domains

### Section 1: Domain Freshness

Compact table:

| Domain | Status | Last Success | Cadence | Age | Message |
|---|---|---|---|---:|---|

Domains:

- eBay Purchases
- EasyPost Tracking
- Order Problems Returns
- RevSeller
- Amazon Sales
- Amazon FBA Inventory
- Amazon Listing Status
- Amazon Inventory Planning
- Amazon Finance
- Informed
- YNAB Cash
- YNAB Transactions
- Keepa
- Inventory Reconciliation
- Business Value Snapshot

### Section 2: Recent Runs

Show latest 10 orchestrator runs.

### Section 3: Capacity / Guardrails

Show warnings only, not noisy details.

Examples:

- Supabase disk IO risk
- database size approaching plan limit
- Keepa tokens low
- EasyPost FedEx credential errors
- Amazon throttling warnings

## Backend Rules

- Never expose environment variables or secrets.
- Never expose raw API tokens.
- Do not run syncs from page load.
- Do not run Supabase-heavy diagnostic queries automatically.
- Use existing `logs/sync_health.json` where possible.
- If log files are unavailable in deployed environment, degrade gracefully and show source table freshness instead.

## Acceptance Criteria

- Health tab identifies stale/failed integrations without requiring log-file spelunking.
- It does not run external syncs.
- It does not expose secrets.
- It clearly distinguishes stale, failed, skipped, and unknown.

---

# Shared Dashboard Component Requirements

Create or reuse shared components under:

```text
web/app/dashboard/components/
```

Recommended components:

```text
DashboardTabs.tsx
DashboardKpiCard.tsx
DashboardSection.tsx
DashboardDataFreshness.tsx
DashboardStatusBadge.tsx
DashboardMiniTable.tsx
DashboardEmptyState.tsx
DashboardErrorState.tsx
DashboardSkeleton.tsx
```

Do not over-engineer. Build only what is needed by multiple dashboard tabs.

## Shared Styling

- dense layout
- minimal cards
- compact tables
- left-aligned text
- right-aligned numbers
- consistent currency/number formatting
- clear severity badges
- avoid oversized charts
- optimize for large desktop monitor

## Loading / Error States

Each tab must show:

- loading skeleton
- empty state
- API error state
- stale data warning if freshness is old

Do not blank the entire dashboard shell on one tab failure.

---

# Backend Implementation Guidance

## Prefer Aggregation Views or Lean API Queries

For heavier dashboards, consider database views or SQL functions if route-level queries become too complex.

Potential future views:

```text
vw_dashboard_inventory_summary
vw_dashboard_amazon_summary
vw_dashboard_growth_monthly
vw_dashboard_sourcing_candidates
vw_dashboard_loss_prevention_summary
vw_dashboard_system_health_sources
```

Do not create these unless useful. Route-level queries are acceptable for MVP if fast and readable.

## Add Indexes If Needed

If dashboard queries are slow, add targeted indexes rather than moving aggregation to React.

Potentially useful index areas:

- `purchase_items.current_status`
- `purchase_items.asin`
- `purchase_items.received_date`
- `purchase_items.marketplace`
- `amazon_sales_orders.purchase_date`
- `amazon_sales_profitability.order_id`
- `amazon_sales_profitability.asin`
- `inventory_positions.asin`
- `inventory_positions.inventory_state`
- `order_problem_cases.stage`
- `order_problem_cases.status`
- `order_problem_cases.updated_at`

Only add indexes after checking existing schema/migrations.

## API Performance Targets

Target response times on local/dev data:

- Overview: under 500ms preferred
- Inventory: under 1.5s
- Amazon: under 1.5s
- Growth: under 2s
- Sourcing: under 2s
- Loss Prevention: under 1.5s
- System Health: under 1s

If a route exceeds targets, first optimize query shape and indexes. Avoid loading row-level data when summaries are enough.

---

# Implementation Order

## Recommended Order

1. Inventory Dashboard
2. Amazon Performance Dashboard
3. Growth Dashboard
4. Loss Prevention Dashboard
5. System Health Dashboard
6. Sourcing Dashboard

Reason:

- Inventory and Amazon use existing mature data.
- Growth uses existing sales/profit/business value data but needs careful interpretation.
- Loss Prevention uses order problem workflow data and can be added once summaries are clear.
- System Health is important but can be built from existing health signals.
- Sourcing has highest future value but depends most on candidate scoring and clean sales/inventory data.

If operator priority is buying more product, Sourcing can move earlier, but keep it MVP and manual-research oriented.

---

# Testing Checklist

For each dashboard tab:

- route loads without errors
- no unrelated dashboard API calls are made on initial load
- refresh reloads only active tab data
- `Last updated` displays source freshness, not browser time
- empty states work when arrays are empty
- currency formatting is consistent
- drill-down links open valid MBOP routes
- backend returns values already aggregated
- frontend does not recalculate business logic
- production build passes

Recommended commands:

```powershell
cd web
npm run build
```

If backend scripts or SQL are added, also run relevant Python syntax checks:

```powershell
python -m py_compile integrations/<script>.py
```

---

# Documentation Updates Required

After implementation, update:

```text
CURRENT_STATE.md
ROADMAP.md
DECISIONS.md
KNOWN_ISSUES.md
```

Add notes for:

- which dashboard tabs were implemented
- what API routes were added
- any new views or indexes
- known incomplete metrics
- any performance concerns
- any deferred drill-down links

---

# Definition of Done

The remaining dashboard phases are complete when:

1. `/dashboard` remains a single top-level monitoring workspace.
2. Dashboard tabs are fast and independently loaded.
3. Inventory, Amazon, Growth, Sourcing, Loss Prevention, and System Health tabs exist or are implemented according to the selected phase order.
4. Each tab has clear KPI cards, short summary sections, and drill-down links.
5. No dashboard tab duplicates a full operational workflow table.
6. No frontend component calculates backend-owned business metrics.
7. No dashboard page load triggers external API calls, Keepa token spending, or heavy sync jobs.
8. Freshness indicators are meaningful and source-driven.
9. Production build passes.
10. Project docs are updated.
