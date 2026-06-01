# MBOP Sales Orders System Requirements

## Purpose

Add a new Sales Orders subsystem to MBOP for importing, storing, analyzing, and displaying marketplace sales orders.

Initial scope is Amazon seller sales/orders. Future scope includes eBay seller sales/orders.

This subsystem must remain separate from:
- Purchases
- Receiving
- Amazon FBA shipment prep
- Repricing
- Inventory reconciliation

Seller sales/orders must not write to `purchases` or `purchase_items`.

---

## Core Goals

1. Pull Amazon sales orders into MBOP.
2. Store more Amazon API data than the UI initially displays.
3. Preserve raw API payloads for auditability and future feature expansion.
4. Calculate order-level and item-level profitability.
5. Support both FBA and Merchant Fulfilled orders.
6. Use Veeqo label data for Merchant Fulfilled shipping label cost when available.
7. Prepare the data model for future eBay seller order ingestion.
8. Keep canceled/refunded orders in the database, but exclude them from the default UI.

---

## Confirmed Business Rules

### Fulfillment Cost Column

The UI should have two separate fee/cost concepts:

1. `Amazon Fees`
   - Amazon fees excluding FBA fulfillment fees.
   - Examples: referral fees, variable closing fees, other selling fees.

2. `Fulfillment`
   - For FBA orders: Amazon FBA fulfillment fee.
   - For Merchant Fulfilled orders: shipping label cost, preferably from Veeqo.

### Profit Formula

Net profit:

```text
net_profit = sale_price - amazon_fees_excluding_fulfillment - fulfillment_cost - cogs
```

ROI:

```text
roi = net_profit / (cogs + fulfillment_cost)
```

Use all costs in ROI denominator.

### COGS Rule

Use FIFO where possible.

If Amazon inventory units exceed MBOP FIFO-costable units, use legacy InventoryLab valuation/cost basis until MBOP is into FIFO-owned units.

Practical rule:
- MBOP go-forward inventory uses FIFO from MBOP purchase/receiving/FBA shipment data.
- Legacy Amazon FBA inventory uses InventoryLab legacy valuation/backfill until those units are exhausted.
- Do not overwrite `purchase_items` with legacy values.
- Store sales COGS consumption records separately.

### Canceled / Refunded Orders

Capture canceled and refunded Amazon orders in the database.

Default UI should exclude:
- canceled orders
- fully refunded orders

Future UI filters may allow viewing them.

---

## API Sources

### Amazon Orders API

Use Amazon SP-API Orders API to retrieve order headers.

Use `getOrderItems` to retrieve item-level order detail.

Do not request or store restricted customer PII unless a future workflow explicitly requires it.

### Amazon Finances API

Use Amazon SP-API Finances API to retrieve order financial events.

Preferred order-specific endpoint:
- financial events by Amazon order ID

Important timing note:
- Financial events may lag recent orders.
- The sync should allow orders to exist before fees are complete.
- UI should show the fee-lag status as `Pending`.

### Veeqo API

Use Veeqo only for Merchant Fulfilled shipping label cost.

For MF orders:
- match Amazon order to Veeqo order.
- retrieve shipping label charges where available.
- store raw Veeqo order/shipment payloads.
- if Veeqo label cost is missing, keep the sales order but mark data status as `Missing Fulfillment Cost`.

Test order:
- Amazon order ID `112-5670468-5414609`
- Use this as the first MF validation case.

---

## Required Database Tables

Create additive SQL migrations only.

Do not alter existing Purchases/Receiving/FBA workflow ownership.

### `amazon_sales_orders`

One row per Amazon order.

Suggested columns:
- `amazon_order_id` primary unique external ID
- `purchase_date`
- `last_update_date`
- `order_status`
- `fulfillment_channel`
- `sales_channel`
- `marketplace_id`
- `buyer_requested_cancel`
- `is_replacement_order`
- `is_business_order`
- `is_prime`
- `number_of_items_shipped`
- `number_of_items_unshipped`
- `order_total_amount`
- `order_total_currency`
- `payment_method`
- `shipment_service_level_category`
- `earliest_ship_date`
- `latest_ship_date`
- `earliest_delivery_date`
- `latest_delivery_date`
- `raw_order_json`
- `import_batch_id`
- `created_at`
- `updated_at`

Do not store buyer name, address, email, or phone.

### `amazon_sales_order_items`

One row per Amazon order item.

Suggested columns:
- `amazon_order_item_id` primary unique external ID when available
- `amazon_order_id`
- `asin`
- `seller_sku`
- `title`
- `quantity_ordered`
- `quantity_shipped`
- `item_price_amount`
- `item_price_currency`
- `item_tax_amount`
- `shipping_price_amount`
- `shipping_tax_amount`
- `gift_wrap_price_amount`
- `gift_wrap_tax_amount`
- `item_promotion_discount_amount`
- `ship_promotion_discount_amount`
- `condition_id`
- `condition_subtype_id`
- `raw_order_item_json`
- `created_at`
- `updated_at`

### `amazon_sales_financial_events`

Store raw and normalized financial events related to Amazon sales.

Suggested columns:
- `financial_event_id`
- `amazon_order_id`
- `amazon_order_item_id`
- `event_type`
- `posted_date`
- `amount`
- `currency`
- `fee_type`
- `charge_type`
- `promotion_type`
- `source`
- `raw_financial_event_json`
- `created_at`

Store enough detail to support recalculation.

### `amazon_sales_profitability`

Derived or materialized rollup per order item.

Suggested columns:
- `amazon_order_id`
- `amazon_order_item_id`
- `asin`
- `seller_sku`
- `title`
- `quantity`
- `sale_price`
- `amazon_fees_excluding_fulfillment`
- `fulfillment_cost`
- `fulfillment_cost_source`
  - `amazon_fba_fee`
  - `veeqo_label`
  - `manual`
  - `missing`
- `cogs`
- `cogs_source`
  - `mbop_fifo`
  - `inventorylab_legacy`
  - `manual`
  - `missing`
- `net_profit`
- `roi`
- `data_status`
  - `complete`
  - `missing_fees` stored status, displayed as `Pending`
  - `missing_fulfillment_cost`
  - `missing_cogs`
  - `refunded`
  - `cancelled`
- `calculated_at`

### `amazon_sales_cogs_consumption`

Track which inventory cost layer was consumed for each sale.

Suggested columns:
- `consumption_id`
- `amazon_order_id`
- `amazon_order_item_id`
- `asin`
- `seller_sku`
- `quantity_consumed`
- `unit_cogs`
- `total_cogs`
- `cost_source`
  - `mbop_fifo`
  - `inventorylab_legacy`
  - `manual`
- `source_reference_type`
  - `purchase_item`
  - `inventorylab_legacy_valuation`
  - `manual_adjustment`
- `source_reference_id`
- `consumed_at`
- `created_at`

### `veeqo_sales_orders`

Store Veeqo order linkage for MF orders.

Suggested columns:
- `veeqo_order_id`
- `amazon_order_id`
- `status`
- `channel`
- `raw_veeqo_order_json`
- `created_at`
- `updated_at`

### `veeqo_sales_shipments`

Store Veeqo shipment / label data.

Suggested columns:
- `veeqo_shipment_id`
- `veeqo_order_id`
- `amazon_order_id`
- `carrier`
- `service`
- `tracking_number`
- `label_cost_amount`
- `label_cost_currency`
- `label_cost_source_field`
- `raw_veeqo_shipment_json`
- `created_at`
- `updated_at`

---

## Required Views

### `vw_amazon_sales_orders_recent`

Frontend-facing lean view.

Default excludes:
- canceled orders
- fully refunded orders

Suggested fields:
- `purchase_date`
- `amazon_order_id`
- `asin`
- `title`
- `quantity`
- `sale_price`
- `fulfillment_channel`
- `amazon_fees_excluding_fulfillment`
- `fulfillment_cost`
- `fulfillment_cost_source`
- `cogs`
- `cogs_source`
- `net_profit`
- `roi`
- `data_status`

### `vw_amazon_sales_summary`

Summary cards for selected date range.

Suggested fields:
- total revenue
- Amazon fees excluding fulfillment
- fulfillment cost
- COGS
- net profit
- average ROI
- order count
- unit count
- pending fee count
- missing COGS count
- missing fulfillment cost count
- MF order count
- FBA order count

---

## Backend Integrations

### New scripts

Create:

```text
integrations/amazon_sync_sales_orders.py
integrations/amazon_sync_sales_finances.py
integrations/veeqo_sync_sales_labels.py
integrations/amazon_sales_profitability.py
```

### Sync order

Recommended orchestration order:

```text
amazon_sync_sales_orders.py
amazon_sync_sales_finances.py
veeqo_sync_sales_labels.py
amazon_sales_profitability.py
```

Add to `run_all_syncs.py` after Amazon Finance balance sync, but guard failures so one failed sales step does not stop independent syncs.

### Sync behavior

Must support:
- dry-run mode
- write/apply mode
- date range arguments
- incremental sync by `LastUpdatedAfter`
- targeted order sync by Amazon order ID
- safe retry/backoff for throttling
- raw payload preservation
- idempotent upserts

Required test command:

```powershell
python integrations/amazon_sync_sales_orders.py --order-id 112-5670468-5414609 --dry-run
```

Then:

```powershell
python integrations/amazon_sync_sales_orders.py --order-id 112-5670468-5414609 --apply
python integrations/amazon_sync_sales_finances.py --order-id 112-5670468-5414609 --apply
python integrations/veeqo_sync_sales_labels.py --amazon-order-id 112-5670468-5414609 --apply
python integrations/amazon_sales_profitability.py --order-id 112-5670468-5414609 --apply
```

---

## Frontend Requirements

Create a new Sales Orders workspace.

Suggested route:

```text
/sales-orders
```

Add navigation item to AppShell:

```text
Sales Orders
```

Do not put this inside Purchases.

### Default view

Default filters:
- last 30 days
- exclude canceled
- exclude fully refunded
- all fulfillment channels

### Date filters

Provide:
- 7 days
- 14 days
- 30 days
- 60 days
- 90 days
- custom date range

Default:
- 30 days

### Other filters

Provide:
- Fulfillment: All, FBA, MF
- Profitability: All, Profitable, Low ROI, Loss
- Data Status: All, Complete, Pending, Missing Fulfillment Cost, Missing COGS
- Search: Amazon order ID, ASIN, SKU, title

### Table columns

Required columns:
- Date
- Amazon Order ID
- ASIN
- Title
- Qty
- Sale Price
- Fulfillment Method
- Amazon Fees
- Fulfillment
- COGS
- Net Profit
- ROI
- Data Status

Column definitions:
- `Amazon Fees` excludes FBA fulfillment fees.
- `Fulfillment` shows:
  - FBA fulfillment fee for FBA orders
  - Veeqo shipping label cost for MF orders

### Summary cards

Above the table show:
- Revenue
- Amazon Fees
- Fulfillment
- COGS
- Net Profit
- Avg ROI
- Pending
- Missing COGS
- Missing Fulfillment Cost

### Saved views / quick filters

Add quick filter buttons:
- Recent Orders
- Profit Exceptions
- Missing Data
- MF Label Missing
- Losses

Definitions:
- `Profit Exceptions`: ROI below target, negative profit, missing COGS, or missing fulfillment cost.
- `MF Label Missing`: Merchant Fulfilled orders with missing Veeqo label cost.
- `Missing Data`: pending fees, missing COGS, or missing fulfillment cost.

---

## API Routes

Create:

```text
web/app/api/sales-orders/route.ts
web/app/sales-orders/page.tsx
```

API route owns:
- filtering
- sorting
- pagination
- summary counts

Frontend must not recalculate:
- fees
- COGS
- net profit
- ROI

Frontend renders backend-provided values only.

---

## Implementation Boundaries

Do not:
- write seller orders into `purchases`
- write seller order items into `purchase_items`
- request restricted customer PII
- merge sales orders with receiving workflow
- use frontend-only profitability formulas
- use Amazon sales data to overwrite purchase cost
- use Veeqo data for FBA orders
- show canceled/refunded orders in default UI

Do:
- preserve raw API payloads
- keep tables Amazon-specific
- make all syncs idempotent
- make broad syncs incremental
- expose missing-data status clearly
- keep sales profitability backend-owned
- use FIFO plus legacy valuation fallback for COGS
- use test order `112-5670468-5414609` for MF label-cost validation

---

## MVP Acceptance Criteria

1. SQL migration creates all required Amazon sales and Veeqo sales tables.
2. Targeted sync imports Amazon order `112-5670468-5414609`.
3. Order item rows are imported with ASIN, SKU, title, quantity, and price.
4. Amazon financial events are imported and separated into:
   - Amazon fees excluding fulfillment
   - FBA fulfillment fee where applicable
5. Veeqo sync attempts to match the MF order and capture label cost.
6. Profitability rollup calculates:
   - sale price
   - Amazon fees
   - fulfillment cost
   - COGS
   - net profit
   - ROI
7. Pending fees, missing COGS, or missing fulfillment cost are visible as data status values.
8. `/sales-orders` displays recent non-canceled, non-refunded orders.
9. Default date range is 30 days.
10. UI includes configurable date filters.
11. UI separates `Amazon Fees` from `Fulfillment`.
12. Canceled/refunded orders are stored but hidden by default.
13. Existing Purchases, Receiving, FBA, Repricing, and Dashboard pages still build and function.

---

## Recommended Development Sequence

1. Create SQL migration.
2. Implement Amazon sales order targeted sync.
3. Validate test order import.
4. Implement Amazon order item import.
5. Implement Amazon financial event import.
6. Implement Veeqo label-cost targeted lookup.
7. Implement profitability calculation.
8. Add sales-orders API route.
9. Add Sales Orders UI.
10. Add summary cards and quick filters.
11. Add orchestration to `run_all_syncs.py`.
12. Run production build.
13. Commit and push.

---

## Git Checkpoint Reminder

After SQL migration and targeted sync validation:

```powershell
git status
git add .
git commit -m "Add Amazon sales order foundation"
git push
```

---

## Implementation Notes As Of 2026-05-31

Implemented:
- Amazon sales schema and Sales Orders UI/API first slice
- Amazon order sync, finance sync, Veeqo label sync, profitability calculator,
  and resumable historical backfill runner
- on-demand Sales Orders refresh through the shared sync-refresh API
- 2025-01-01 sales operating cutoff in sales sync, backfill, profitability,
  finance, Veeqo, and Sales Orders API paths
- UI display text changed from `Missing Fees` to `Pending`
- non-eBay purchase COGS source table and manual importer for TIM/prep-center
  and Merchant Fulfilled supplier purchase sheets
- non-eBay FIFO COGS allocation support for current inventory and matching sales
- Merchant Fulfilled inventory states `merchant_available` and
  `merchant_allocated`

Known remaining work:
- after the 2025 Amazon sales backfill completes, run an eBay purchase FIFO
  allocator so costed eBay `purchase_items` consume into
  `amazon_sales_cogs_consumption`
- rerun `exports/missing_amazon_cogs_review.csv` and manually review the smaller
  no-match / quantity-short exception set
- add a first-class non-eBay purchases MBOP screen as the go-forward source for
  supplier and prep-center purchase cost entry

After UI implementation and successful build:

```powershell
git status
git add .
git commit -m "Add sales orders UI"
git push
```
