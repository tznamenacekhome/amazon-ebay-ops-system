# MBOP Dashboard Split Requirements

Status: historical/superseded as of 2026-07-14. Financial and Growth dashboard
requirements below describe the pre-ZFI-retirement dashboard plan and are no
longer active MBOP scope. Current dashboard tabs are Overview, Operations,
Inventory, Amazon, Sourcing, Loss Prevention, and System Health.

## Project
Midnight Blue Operations Platform (MBOP)

## Goal
Refactor the current overloaded Dashboard into a small set of focused, high-performance dashboard views that improve business monitoring without making the application slow, cluttered, or difficult to navigate.

The current dashboard has grown to include business value, purchases, inventory, operations, exceptions, and reconciliation concerns. This work should split dashboard responsibilities into focused dashboard sections while preserving MBOP's dense, operational, low-click UI philosophy.

---

# Guiding Principles

## 1. Do Not Create Navigation Bloat
The application should not gain a large number of new top-level menu items.

Use one top-level navigation item:

```text
Dashboard
```

Inside `/dashboard`, add lightweight dashboard tabs or segmented navigation:

```text
Overview | Financial | Operations | Inventory | Amazon | Growth | Sourcing | Loss Prevention | System Health
```

Do not add separate left-nav entries for every dashboard unless a dashboard becomes a full workflow surface later.

Existing full workflows remain separate left-nav items:

- Purchases
- Receiving
- Amazon FBA
- Sales Orders
- Repricing
- Reconciliation

The dashboard area is for monitoring and drill-down, not for replacing operational workspaces.

## 2. Backend Owns Metrics
Do not calculate business metrics in React components.

All dashboard values must come from API routes, database views, or backend-owned aggregation code.

Frontend components should only:

- render API-provided values
- manage filters/tabs
- open drill-down links
- display loading/error states

Do not reimplement:

- landed cost math
- inventory value math
- profit calculations
- workflow status logic
- repricing recommendation logic
- reconciliation logic

## 3. Fast First Paint
Each dashboard tab should load only the data needed for that tab.

Do not load all dashboard data when `/dashboard` first renders.

Recommended pattern:

```text
/dashboard?view=overview
/dashboard?view=financial
/dashboard?view=operations
/dashboard?view=inventory
/dashboard?view=amazon
/dashboard?view=growth
/dashboard?view=sourcing
/dashboard?view=loss-prevention
/dashboard?view=system-health
```

Each tab should call its own endpoint or a shared endpoint with a `view` parameter.

Example:

```text
/api/dashboard/overview
/api/dashboard/financial
/api/dashboard/operations
/api/dashboard/inventory
/api/dashboard/amazon
/api/dashboard/growth
/api/dashboard/system-health
```

or:

```text
/api/dashboard?view=overview
```

Either is acceptable. Prefer separate route files if that keeps implementation simpler and easier for AI-assisted development.

## 4. Summary First, Detail By Drill-Down
Dashboards should show summary metrics and short prioritized lists.

Do not embed full operational tables inside dashboards.

Instead, dashboard rows/cards should link to the owning workspace with filters applied.

Examples:

- Delivered Not Received -> `/receiving?...`
- Missing Data -> `/purchases?...`
- Return Pending -> `/purchases?tab=order-problems...`
- Repricing Candidates -> `/repricing?...`
- Reconciliation Findings -> `/inventory-reconciliation?...`
- Missing COGS -> `/sales-orders?...`

Dashboard should answer: “What needs attention?”
Operational screens should answer: “Let me work the queue.”

## 5. Preserve Dense MBOP UI
Use compact tables, small KPI cards, and tight spacing.

Avoid:

- large consumer-style cards
- big empty spacing
- duplicate charts
- animation-heavy components
- mobile-first layouts that waste desktop space

Optimize for a large desktop monitor and daily operations.

---

# Proposed Dashboard Structure

## Top-Level Dashboard Page

Route:

```text
/dashboard
```

Keep the existing left-nav Dashboard entry.

Inside `/dashboard`, add a compact tab bar:

```text
Overview | Financial | Operations | Inventory | Amazon | Growth | System Health
```

Tab state should be URL-addressable so links can open directly to a dashboard section.

Preferred URL approach:

```text
/dashboard?view=financial
```

Alternative acceptable approach:

```text
/dashboard/financial
```

Use whichever is simpler given the current Next.js structure.

---

# Dashboard 1: Overview

## Purpose
A one-minute executive snapshot of the business.

## Primary Question
Is the business healthy right now?

## Sections

### A. Business Value Summary
Show compact KPI cards:

- Total Business Value
- Amazon Inventory Value
- Pre-Amazon Inventory Value
- Amazon Cash
- Amazon-to-Bank In Transit
- YNAB Business Cash

Use the existing backend-owned business value snapshot logic where available.

### B. Current Attention Summary
Show status indicators:

- Receiving Backlog
- FBA Prep Backlog
- Open Order Problems
- Repricing Action Items
- Missing Sales COGS / Fees
- Open Inventory Reconciliation Findings

Use color-coded severity:

- Green: normal
- Yellow: attention
- Red: urgent / blocking

### C. Trend Snapshot
Show a compact trend chart for:

- Total Business Value over time

Optional later:

- 30-day revenue
- 30-day profit
- inventory value

Do not put every trend chart on Overview. Keep it lightweight.

### D. Drill-Down Links
Each KPI/attention row should link to the owning detailed screen.

---

# Dashboard 2: Financial

## Purpose
Monitor profitability, cash flow, payout status, and reporting readiness.

## Primary Question
Am I making money, and is my financial data complete enough to trust?

## Sections

### A. Profitability Summary
Date filters:

- 7 days
- 30 days
- 90 days
- Month to Date
- Year to Date

Metrics:

- Gross Sales
- Amazon Fees
- Fulfillment Costs
- Shipping Label Costs
- COGS
- Gross Profit
- Net Profit
- ROI
- Average Profit Per Unit

Use backend-owned Sales Orders profitability data.

### B. Cash Position
Metrics:

- YNAB Business Cash
- Amazon Held Cash
- Amazon-to-Bank In Transit
- Deferred / Reserved Amazon Cash
- Total Available Business Cash

### C. Payout Reconciliation
Show counts and dollars for:

- Amazon payouts in transit
- completed Amazon payouts not yet matched to YNAB deposit
- YNAB Amazon-looking deposits without matched Amazon payout

### D. Data Completeness
Show financial blockers:

- Sales Orders missing COGS
- Sales Orders missing fees
- Sales Orders pending fees
- Missing fulfillment cost

Each row should drill to Sales Orders with matching filters.

### E. Tax / Schedule C Readiness Placeholder
Future section for YNAB Business transaction classification.

Do not build full Schedule C reporting in this first pass unless existing category mapping is ready.

---

# Dashboard 3: Operations

## Purpose
Daily work queue summary.

## Primary Question
What should I work on today?

## Sections

### A. Receiving
Metrics:

- Delivered Not Received
- Shipped With No Tracking
- Arriving Today
- Arriving This Week
- Oldest Delivered Not Received

Drill to Receiving.

### B. FBA Prep
Metrics:

- Received Amazon-bound Units Ready for FBA
- Distinct ASINs Ready for FBA
- Estimated Cost Ready for FBA
- Oldest Received Not Listed

Drill to Amazon FBA workspace.

### C. Purchase Cleanup
Metrics:

- Missing ASIN
- Missing Sell Price
- Missing Amazon Title
- Missing System

Drill to Purchases Missing Data filter.

### D. Order Problems
Metrics:

- Late Delivery Candidates
- Stale / No Tracking Candidates
- Carrier Exceptions
- Return Pending
- Return Opened
- Refund Pending
- Missing Item / Replacement Follow-up

Drill to Purchases -> Order Problems tab.

### E. Workflow Aging
Show compact aging buckets for:

- Purchase to Delivered
- Delivered to Received
- Received to Listed

Use this to identify bottlenecks.

---

# Dashboard 4: Inventory

## Purpose
Monitor owned inventory, capital allocation, age, and risk.

## Primary Question
Where is my money tied up, and what inventory is at risk?

## Sections

### A. Inventory Value By Location
Use backend-owned inventory position/value rollups.

Rows:

- Amazon FBA Sellable
- On the Way to Amazon FBA
- Received / Ready for FBA
- Ordered Not Received
- eBay Intended Inventory
- Return Pending / Problem Inventory
- Total

Columns:

- Units
- Cost Value
- Percent of Total Inventory Value

### B. Inventory Age
Buckets:

- 0-30 days
- 31-60 days
- 61-90 days
- 91-180 days
- 181-365 days
- 365+ days

Show units and cost value.

### C. Capital At Risk
Show prioritized list:

- High-value aged inventory
- Unsellable Amazon inventory
- Suppressed / stranded inventory
- Inventory with missing cost/date context

Keep list short, such as top 10.

### D. Concentration Risk
Show top ASINs by:

- total units
- total cost value
- aged value

### E. Reconciliation Summary
Show counts only:

- Amazon unknown to MBOP
- Quantity mismatch
- Stranded / suppressed
- Unsellable
- Inbound discrepancy

Drill to Inventory Reconciliation page.

Do not show full reconciliation table on dashboard.

---

# Dashboard 5: Amazon

## Purpose
Monitor Amazon marketplace performance and listing health.

## Primary Question
How healthy is my Amazon sales channel?

## Sections

### A. Sales Summary
Filters:

- 7 days
- 30 days
- 90 days
- Month to Date

Metrics:

- Units Sold
- Revenue
- Net Profit
- Average ROI
- Average Selling Price

### B. Listing Health
Metrics:

- Active SKUs
- FBA Sellable Units
- Suppressed / Non-buyable Listings
- Stranded Inventory
- Unsellable Units
- Listing Issue Count

### C. Repricing Summary
Metrics:

- Reprice Candidates
- Liquidate Candidates
- Remove / eBay Candidates
- Needs Data
- Snoozed Repricing Rows
- High-Capital Pricing Rows

Drill to Repricing page.

### D. Inventory Planning
Metrics:

- 91-180 day FBA units
- 181+ day FBA units
- Inventory with no recent Informed velocity
- Inventory missing Keepa/Informed data

Do not duplicate the full Repricing Advisor table here.

---

# Dashboard 6: Growth

## Purpose
Track business growth and efficiency over time.

## Primary Question
Is Midnight Blue Enterprises becoming larger, more profitable, and more efficient?

## Sections

### A. Monthly Trend Table
Rows by month:

- Units Purchased
- Purchase Cost
- Units Sold
- Revenue
- Gross Profit
- Net Profit
- Ending Inventory Value
- Ending Business Value

### B. Growth Metrics
Show:

- Revenue month-over-month
- Profit month-over-month
- Inventory value month-over-month
- Business value month-over-month
- Units sold month-over-month

### C. Efficiency Metrics
Show:

- Inventory Turn Rate
- Average ROI
- Average Profit per Unit
- Average Days Purchase to Received
- Average Days Received to Listed
- Average Days Listed to Sold, if available

### D. Source Mix
Future:

- eBay-sourced inventory
- non-eBay supplier inventory
- personal item sales
- returned inventory resold on eBay

---

# Dashboard 7: System Health

## Purpose
Monitor MBOP technical health and data freshness.

## Primary Question
Can I trust the data I am seeing?

## Sections

### A. Integration Freshness
Rows:

- eBay Purchases
- EasyPost Tracking
- Order Problems / eBay Returns
- RevSeller
- Amazon FBA Inventory
- Amazon Sales Orders
- Amazon Finance
- Amazon Inventory Planning
- Informed
- Keepa
- YNAB Business Cash
- YNAB Business Transactions
- Inventory Reconciliation
- Business Value Snapshot

Columns:

- Last successful run
- Last failure
- Current status
- Freshness age
- Notes

Use existing `logs/sync_health.json`, sync tables, and `/api/screen-data-freshness` logic where appropriate.

### B. External API Guardrails
Show:

- Keepa token status
- Amazon throttling / recent 429 count, if available
- EasyPost errors
- eBay auth errors

### C. Database Health Guardrails
Show:

- Supabase connection status
- database size if available
- Disk IO warning if available

If these are not available programmatically yet, create placeholder UI and backend TODO notes rather than fake values.

### D. Scheduler Health
Show:

- last core run
- last daily run
- last catalog run
- whether lock file indicates a stuck run
- latest scheduler log path or summary

---

# UI / Navigation Requirements

## Left Navigation
Keep the current compact AppShell left navigation.

Do not add top-level left-nav entries for Financial, Operations, Inventory, Amazon, Growth, or System Health dashboards.

Only keep:

- Dashboard
- Purchases
- Receiving
- Amazon FBA
- Sales Orders
- Repricing
- Reconciliation

Adjust exact menu list to match current app state, but keep the dashboard split inside Dashboard.

## Dashboard Tab Bar
Inside `/dashboard`, add a compact tab bar near the top.

Suggested style:

```text
[Overview] [Financial] [Operations] [Inventory] [Amazon] [Growth] [System Health]
```

Requirements:

- active tab visually highlighted
- tab state stored in URL
- keyboard/mouse friendly
- no dropdown unless screen width forces it
- preserve dense table-first layout

## Drill-Down Links
Dashboard cards and rows should link to operational pages with filters.

Use clear links like:

- “Open Receiving”
- “Review Missing COGS”
- “Open Order Problems”
- “Open Repricing Queue”

Avoid embedding full operational workflows in dashboard tabs.

## Shared Components
Create reusable dashboard components:

- `DashboardTabs`
- `MetricCard`
- `MetricGrid`
- `CompactStatusTable`
- `DashboardSection`
- `TrendSparkline` or lightweight chart wrapper
- `FreshnessBadge`
- `DrilldownLink`

Do not over-abstract in the first pass. Favor simple components that reduce duplication.

---

# Performance Requirements

## API Loading
Each dashboard view should make a focused API call.

Do not call every dashboard endpoint on initial page load.

## Query Design
Prefer:

- SQL views
- server-side aggregation
- indexed filters
- limited result sets
- top-N lists

Avoid:

- loading raw purchase rows into the dashboard
- client-side full-table filtering
- joining large raw snapshot tables in React
- charting huge datasets in the browser

## Default Row Limits
For dashboard lists:

- Top attention rows: 5-10
- Top risk rows: 10
- Trend history: 12-24 monthly points or daily points only where already snapshotted

## Caching / Revalidation
Use lightweight frontend state caching if already consistent with the current app.

Do not cache stale business data without a visible freshness indicator.

## Freshness Indicator
Every dashboard tab should show a `Last updated` indicator.

Use backend-owned freshness signals.

Dashboard Overview should use the strictest freshness logic where value depends on multiple sources.

---

# Data Ownership / Source Requirements

## Purchase Costs
Use:

```text
vw_purchases_dashboard.unit_cost
```

Do not compute landed cost in frontend.

## Inventory Value
Use backend inventory rollups from:

- `inventory_positions`
- `vw_inventory_position_summary`
- latest Amazon FBA snapshots
- InventoryLab valuation snapshots
- business value snapshots

Do not recalculate inventory value in React.

## Sales Profitability
Use backend-owned Amazon sales profitability tables/API.

Do not calculate fees, COGS, fulfillment cost, or ROI in frontend.

## Cash
Use backend snapshots:

- YNAB Business category balance
- Amazon Finance balance snapshots
- business value snapshots

## Order Problems
Use:

- `order_problem_cases`
- `order_problem_events`
- `/api/order-problems` summary counts where possible

## Repricing
Use:

- `/api/amazon/repricing-advisor`
- or a lightweight summary endpoint derived from the same backend logic

Do not duplicate repricing bucket logic in the dashboard.

---

# Suggested API Endpoints

Implement either separate routes or one `view`-parameterized route.

Preferred for maintainability:

```text
GET /api/dashboard/overview
GET /api/dashboard/financial
GET /api/dashboard/operations
GET /api/dashboard/inventory
GET /api/dashboard/amazon
GET /api/dashboard/growth
GET /api/dashboard/system-health
```

Each endpoint should return:

```ts
{
  refreshedAt: string | null,
  metrics: Record<string, number | string | null>,
  sections: Array<...>,
  warnings?: Array<string>,
  drilldowns?: Array<...>
}
```

Do not force every endpoint into an identical schema if that makes implementation awkward. Consistency is good, but simplicity matters more.

---

# Implementation Phases

## Phase 1: Navigation + Overview + Operations

Build:

- Dashboard tab shell
- Overview dashboard
- Operations dashboard
- shared compact components
- drill-down links
- per-tab API loading

This phase should immediately reduce dashboard overload.

## Phase 2: Financial + Inventory

Build:

- Financial dashboard
- Inventory dashboard
- backend aggregation endpoints
- data completeness panels
- inventory risk panels

## Phase 3: Amazon + Growth + System Health

Build:

- Amazon dashboard
- Growth dashboard
- System Health dashboard
- scheduler/API health rollups

## Phase 4: Refinement

Add:

- saved time ranges
- sparklines
- CSV export for selected summaries
- deeper drill-down filters
- comparison periods

---

# Acceptance Criteria

## Navigation
- Dashboard remains one top-level left-nav item.
- Dashboard subviews are accessible from compact tabs or URL-addressable sections.
- Existing operational workspaces remain separate.

## Performance
- Initial `/dashboard` load does not request all dashboard data.
- Each tab loads only its own data.
- No dashboard tab fetches full purchase/sales/inventory tables for client-side aggregation.
- Dashboard lists are top-N or summary-only.

## Business Logic
- Frontend does not calculate landed cost, inventory value, sales profit, ROI, repricing tiers, or workflow status.
- All dashboard metrics come from backend/API/database-owned logic.

## Usability
- Overview gives a one-minute business health check.
- Operations clearly shows today’s work queues.
- Financial clearly shows profit/cash/data-completeness status.
- Inventory clearly shows capital location and risk.
- Drill-down links take the operator to the correct workflow screen.

## Safety
- No external marketplace write actions.
- No Amazon price changes.
- No Informed rule changes.
- No Keepa token-spending calls triggered by dashboard page loads.
- No workflow state changes from dashboard summary cards.

---

# Important Guardrails For Codex

- Keep the UI dense and operational.
- Do not make the dashboard card-heavy or marketing-style.
- Do not add seven new left-nav items.
- Do not merge dashboard monitoring with workflow execution.
- Do not duplicate tables already owned by Purchases, Receiving, Sales Orders, Repricing, or Reconciliation.
- Do not reintroduce client-side full-table aggregation.
- Use backend/API-provided values only.
- Keep changes incremental and testable.
- Prefer Phase 1 first before building every dashboard.

---

# Recommended First Codex Task

Implement Phase 1 only:

1. Refactor `/dashboard` into a tabbed dashboard shell.
2. Add `Overview` and `Operations` tabs.
3. Create focused API routes for overview and operations summaries.
4. Move current dashboard content into the closest matching tab without deleting useful existing logic.
5. Replace large embedded detail sections with compact summary rows and drill-down links.
6. Ensure production build passes.
7. Update relevant documentation after implementation.
