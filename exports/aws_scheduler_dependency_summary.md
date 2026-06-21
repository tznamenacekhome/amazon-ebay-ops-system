# AWS Scheduler Dependency Summary

This analysis is based on `run_all_syncs.py`, the invoked integration scripts, system-health routes, and the captured instrumentation run from `20260620-080136`. No production jobs were run for this review.

## Recommended AWS Shape

| Group | Jobs | Cadence | Dependency notes |
| --- | --- | --- | --- |
| purchase-ingestion | eBay buyer purchases -> Sourcing purchase matching | hourly workday; 2-4h off-hours | Root purchase source. Avoid overlap with inbound shipment writers. |
| purchase-tracking | EasyPost shipments | hourly | Must follow eBay purchase ingestion. Webhook-driven later. |
| returns-and-order-problems | eBay order problem returns/inquiries -> EasyPost order problem returns | every 2-4h | eBay problem sync creates/updates cases; EasyPost return tracking follows. |
| purchase-enrichment | RevSeller enrichment; Keepa missing purchase titles | hourly/2h, token-aware | Follows eBay purchases. Keepa title fill should not overlap other Keepa jobs. |
| amazon-sales-recent | Amazon sales orders -> Recent Amazon sales finances -> Veeqo labels -> Recent sales profitability | hourly/2h | Keep this as a sequential chain. Profitability must follow orders/finance; labels should precede final profitability when possible. |
| amazon-sales-fee-repair | Missing-fee finances -> missing-fee profitability | daily | Separate from recent chain to avoid SP-API finance overlap. |
| fba-inventory-daily | Amazon FBA inventory; Amazon inventory planning | daily | Feeds reconciliation, listing status, business value, and repricing views. |
| fba-shipments | Amazon FBA shipments -> FBA EasyPost carrier tracking | 2-4h while active; daily otherwise | Keep separate from receiving/purchases. Tracking follows shipment sync. |
| reconciliation | Inventory reconciliation | after purchase/FBA source groups | Use skip-if-unchanged for frequent runs; avoid overlapping broad audits. |
| finance-daily | YNAB transactions; YNAB cash balance; Amazon finance balances | daily | Must finish before business value snapshot. |
| business-value-finalizer | Business value snapshot | daily after finance and reconciliation | Finalizer. Depends on latest inventory_positions, Amazon finance, YNAB cash. |
| repricing-catalog | Amazon listing status; Informed repricing reports | daily | Listing status should follow FBA inventory. Informed is report/polling based. |
| sourcing-catalog | Sourcing listing availability; Matching intelligence refresh | daily or 6h for availability | Move matching intelligence out of the hot core path unless buying workflow requires immediate refresh. |
| keepa-rolling-refresh | Keepa active products | token-paced rolling schedule | Do not overlap any Keepa job. Current offers+stock config is too token-heavy for 1,028 ASIN refresh targets. |
| fba-pricing | Keepa FBA prep pricing -> Amazon Product Fees estimates | on-demand/hourly during prep | Keepa FBA prep must be token-limited; fee estimates follow fresh price points. |
| audits | finance-audit; listing-audit; inventory-audit | manual or weekly off-hours | Do not mix with normal scheduled freshness jobs. |

## Critical Ordering

- eBay buyer purchases must precede EasyPost shipments and sourcing purchase matching.
- eBay order problem returns/inquiries should precede EasyPost order problem returns.
- Amazon sales orders must precede Amazon sales finances, which must precede sales profitability.
- Veeqo label costs should complete before final profitability when MF label cost precision matters.
- Amazon FBA inventory should precede Amazon listing status and inventory reconciliation.
- Amazon FBA shipments should precede FBA EasyPost carrier tracking.
- Inventory reconciliation, YNAB cash balance, and Amazon finance balances should precede business value snapshot.
- Keepa jobs must not overlap each other on the current token plan.

## System Health Implications

- `run_all_syncs.py` writes local `logs/sync_health.json`, `logs/sync_runs.jsonl`, and uses `logs/run_all_syncs.lock` for overlap protection.
- `/api/system-health` combines Supabase freshness signals with local log files. In cloud mode, local file signals become unavailable unless replaced by a cloud-visible sync ledger.
- `/api/sync-refresh` starts local `run_all_syncs.py` groups and refuses to start when the local lock is active. In AWS, replace this with an ECS task invocation or disable local execution.
- Existing health cadences are coarse: core is expected every 12h and daily every 24h. AWS groups should expose their own health records rather than relying only on old group names.

## Main Risks

- Supabase load: FBA inventory snapshots, listing audits, inventory reconciliation, matching intelligence, and profitability audits are broad/read-heavy or high-write jobs. Do not run these together on constrained Supabase IO.
- Amazon SP-API quotas: sales finances, FBA inventory, listing status/audit, inventory planning, and fee estimates should be separated by endpoint family where practical.
- EasyPost: polling is bounded and has 429 backoff, but active tracking should eventually move to webhooks.
- Keepa: current active listing refresh configuration costs roughly 9.8 tokens/ASIN observed; FBA prep observed 11.4 tokens/ASIN and hit 429 on the second batch.
- Local files: RevSeller diagnostics and sync health logs are local-machine artifacts unless redirected to S3/CloudWatch/Supabase.

## Per-Job Detail

### eBay buyer purchases

- Command: `integrations/ebay_sync_buyer_purchases.py --days-back 7 --missing-tracking-lookback-days 90 --missing-tracking-limit 250`
- Current groups: core; purchases; dashboard
- Reads: purchases; purchase_items; inbound_shipments
- Writes: import_batches; purchases; purchase_items; inbound_shipments; inbound_shipment_items
- Must run after: none
- Must not overlap with: itself; EasyPost shipments; eBay order problem returns/inquiries; receiving edits that update purchase_items.current_status
- AWS group/frequency: purchase-ingestion / hourly during workday; every 2-4 hours off-hours
- Parallelization: limited: can run beside Amazon/YNAB/Informed jobs, but avoid parallel purchase/inbound shipment writers
- Cloud mode: yes
- Notes: Root purchase source. Downstream purchase matching and inbound tracking depend on fresh purchase/inbound rows. eBay quota and 90-day missing-tracking query are the main external/load risks.

### Sourcing purchase matching

- Command: `integrations/match_sourcing_purchases.py --limit 300`
- Current groups: core; purchases; dashboard
- Reads: sourcing_opportunities; sourcing_ebay_candidates; sourcing_seed_asins; vw_latest_keepa_product_snapshot; sourcing_actions; purchases; purchase_items
- Writes: sourcing_purchase_matches; purchase_items; sourcing_opportunities; sourcing_actions
- Must run after: eBay buyer purchases
- Must not overlap with: itself; other sourcing match/rescore jobs that mutate sourcing_opportunities
- AWS group/frequency: purchase-ingestion / hourly, immediately after eBay purchase ingestion
- Parallelization: limited: avoid parallel sourcing mutation jobs
- Cloud mode: yes
- Notes: Connects accepted sourcing opportunities to imported eBay purchases. Keepa data improves target price context but is not a hard dependency.

### EasyPost shipments

- Command: `integrations/easypost_sync_shipments.py --limit 150`
- Current groups: core; purchases; dashboard
- Reads: purchases; purchase_items; inbound_shipments; inbound_shipment_items
- Writes: inbound_shipments; inbound_shipment_items; purchase_items
- Must run after: eBay buyer purchases
- Must not overlap with: itself; eBay buyer purchases; eBay order problem returns/inquiries, because all can create/update inbound_shipments
- AWS group/frequency: purchase-tracking / hourly for inbound purchases
- Parallelization: limited: avoid other inbound shipment writers
- Cloud mode: yes
- Notes: Has 5 requests/sec cap and 429 backoff. Long-term, EasyPost webhooks should replace frequent polling for active trackers.

### eBay order problem returns/inquiries

- Command: `integrations/ebay_sync_order_problem_returns.py --lookback-days 60 --limit 100 --apply`
- Current groups: core; purchases; dashboard
- Reads: purchases; purchase_items; inbound_shipments; order_problem_cases
- Writes: order_problem_cases; order_problem_events; inbound_shipments; inbound_shipment_items; purchase_items
- Must run after: eBay buyer purchases
- Must not overlap with: itself; EasyPost order problem returns; EasyPost shipments; eBay buyer purchases
- AWS group/frequency: returns-and-order-problems / every 2-4 hours
- Parallelization: limited: avoid order_problem_cases/inbound shipment writers
- Cloud mode: yes
- Notes: Nonblocking in current scheduler. Writes order-problem events and can set purchase item statuses such as Return Opened/Pending.

### EasyPost order problem returns

- Command: `integrations/easypost_sync_order_problem_returns.py --limit 100`
- Current groups: core; purchases; dashboard
- Reads: order_problem_cases
- Writes: order_problem_cases; order_problem_events
- Must run after: eBay order problem returns/inquiries
- Must not overlap with: itself; eBay order problem returns/inquiries
- AWS group/frequency: returns-and-order-problems / every 2-4 hours; webhook-driven later
- Parallelization: limited: avoid order_problem_cases writers
- Cloud mode: yes
- Notes: Should follow the eBay problem sync so new return tracking rows are visible.

### RevSeller enrichment

- Command: `integrations/sync_revseller_sheet.py --ai-review --ai-review-limit 25`
- Current groups: core; purchases; dashboard
- Reads: manual_item_matches; purchase_items; vw_latest_keepa_product_snapshot; vw_latest_amazon_listing_snapshot
- Writes: purchase_items; local diagnostics CSV
- Must run after: eBay buyer purchases
- Must not overlap with: itself; manual purchase-item correction tools
- AWS group/frequency: purchase-enrichment / hourly or every 2 hours after purchase ingestion
- Parallelization: limited: avoid purchase_items enrichment writers
- Cloud mode: yes if Google service-account credential is supplied as an ECS secret/file; local diagnostics are unavailable unless redirected
- Notes: System/title matching must remain platform-specific. OpenAI use is capped by --ai-review-limit.

### Keepa missing purchase titles

- Command: `integrations/backfill_amazon_titles_from_keepa.py --limit 25 --fetch-missing --min-tokens 25 --apply`
- Current groups: core; purchases; dashboard
- Reads: purchase_items; purchases; vw_latest_keepa_product_snapshot
- Writes: purchase_items; keepa_product_snapshots via Keepa fetch path when needed
- Must run after: eBay buyer purchases
- Must not overlap with: other Keepa jobs; RevSeller enrichment/manual title edits
- AWS group/frequency: purchase-enrichment / every 4-6 hours or after purchase ingestion when missing-title count is nonzero
- Parallelization: no with other Keepa jobs; limited with purchase_items writers
- Cloud mode: yes, but token-budget sensitive
- Notes: Despite backfill name it is part of current normal scheduler and bounded by --limit. Keepa token guard is low at 25.

### Amazon sales orders

- Command: `integrations/amazon_sync_sales_orders.py --apply`
- Current groups: core; sales-orders
- Reads: amazon_sales_orders; amazon_sales_order_items
- Writes: amazon_sales_orders; amazon_sales_order_items
- Must run after: none
- Must not overlap with: itself; Amazon sales finance/profit jobs for same recent window if strict snapshot consistency is needed
- AWS group/frequency: amazon-sales-recent / hourly
- Parallelization: limited: avoid overlapping with downstream sales-finance/profit chain; can run beside purchase/FBA jobs
- Cloud mode: yes
- Notes: Downstream sales finance and profitability should follow it. Item calls multiply SP-API usage for changed orders.

### Recent Amazon sales finances

- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start days_ago(14) --order-finance-delay-seconds 1.5 --apply`
- Current groups: core; sales-orders
- Reads: amazon_sales_orders; vw_amazon_sales_orders_recent
- Writes: amazon_sales_financial_events; amazon_sales_transactions
- Must run after: Amazon sales orders
- Must not overlap with: itself; Amazon missing-fee sales finances; Amazon sales finances audit
- AWS group/frequency: amazon-sales-recent / hourly or every 2 hours after sales orders
- Parallelization: no with other sales-finance jobs; yes with unrelated domains
- Cloud mode: yes
- Notes: Observed as one of the long recent jobs. Raw financial event rows can be high volume. SP-API 429/retry behavior observed.

### Veeqo MF label costs

- Command: `integrations/veeqo_sync_sales_labels.py --purchase-date-start days_ago(14) --missing-only --apply`
- Current groups: core; sales-orders
- Reads: amazon_sales_orders; veeqo_sales_orders
- Writes: veeqo_sales_orders; veeqo_sales_shipments
- Must run after: Amazon sales orders
- Must not overlap with: itself
- AWS group/frequency: amazon-sales-recent / hourly or every 2 hours after sales orders
- Parallelization: yes with non-Veeqo jobs; avoid duplicate Veeqo runs
- Cloud mode: yes; exits skipped if Veeqo key missing
- Notes: Retries 429/5xx. Needed before best MF profitability numbers.

### Recent sales profitability

- Command: `integrations/amazon_sales_profitability.py --purchase-date-start days_ago(14) --apply`
- Current groups: core
- Reads: amazon_sales_orders; vw_amazon_sales_orders_recent; amazon_sales_order_items; amazon_sales_financial_events; veeqo_sales_shipments; amazon_sales_fulfillment_cost_overrides; amazon_sales_cogs_consumption; vw_latest_inventorylab_inventory_valuation; inventorylab_active_inventory_backfill
- Writes: amazon_sales_profitability; amazon_sales_cogs_consumption
- Must run after: Amazon sales orders; Recent Amazon sales finances
- Must not overlap with: itself; Daily missing-fee sales profitability; Sales profitability audit; FIFO COGS repair scripts
- AWS group/frequency: amazon-sales-recent / hourly after finance/label jobs
- Parallelization: no with other profitability writers
- Cloud mode: yes
- Notes: Backend-owned cost/profit calculation. Do not move landed/profit calculation to frontend.

### Amazon FBA inventory

- Command: `integrations/amazon_sync_fba_inventory.py --page-delay-seconds 0.25`
- Current groups: daily; dashboard; reconciliation; repricing; fba
- Reads: none before write, aside from Supabase connection
- Writes: amazon_skus; amazon_fba_inventory_snapshots
- Must run after: none
- Must not overlap with: itself; Amazon listing status if both update amazon_skus heavily
- AWS group/frequency: fba-inventory-daily / daily; optional manual pre-reconciliation refresh
- Parallelization: limited: can run beside sales/purchase jobs; avoid multiple amazon_skus writers
- Cloud mode: yes
- Notes: Observed 6,329 summaries and snapshots. Snapshot table growth and SP-API 429s are real; keep separate from listing audit.

### Amazon FBA shipments

- Command: `integrations/amazon_sync_fba_shipments.py`
- Current groups: daily; dashboard; reconciliation; fba
- Reads: fba_shipments; fba_shipment_items; amazon_skus
- Writes: fba_shipments; fba_shipment_items; fba_shipment_events
- Must run after: none
- Must not overlap with: itself; FBA EasyPost carrier tracking; manual FBA workflow edits
- AWS group/frequency: fba-shipments / every 2-4 hours while shipment prep/transit is active; daily otherwise
- Parallelization: limited: avoid FBA shipment writers
- Cloud mode: yes
- Notes: Writes workflow events and shipment/item state. Should stay separate from purchases/receiving workflow.

### FBA EasyPost carrier tracking

- Command: `integrations/easypost_sync_fba_shipments.py --limit 25 --max-new-trackers 10`
- Current groups: daily; dashboard; reconciliation; fba
- Reads: fba_shipments
- Writes: fba_shipments; fba_shipment_events
- Must run after: Amazon FBA shipments, once tracking numbers exist
- Must not overlap with: itself; Amazon FBA shipments
- AWS group/frequency: fba-shipments / every 2-4 hours for in-transit FBA shipments; webhook-driven later
- Parallelization: limited: avoid FBA shipment writers
- Cloud mode: yes
- Notes: Bounded by --max-new-trackers. Uses EasyPost quota but small volume.

### Inventory reconciliation

- Command: `integrations/inventory_reconcile.py --skip-if-unchanged`
- Current groups: core; dashboard; reconciliation; fba
- Reads: purchase_items; vw_purchases_dashboard; fba_shipments; fba_shipment_items; amazon_skus; amazon_fba_inventory_snapshots; amazon_listing_snapshots; inventorylab_active_inventory_backfill
- Writes: inventory_positions; inventory_reconciliation_events; inventory_reconciliation_event_items
- Must run after: Amazon FBA inventory
- Must not overlap with: itself; Inventory reconciliation audit
- AWS group/frequency: reconciliation / hourly after core purchase tracking and daily after FBA inventory; consider event-triggered fan-in
- Parallelization: limited: read-heavy; avoid running with broad Supabase scans/audits
- Cloud mode: yes
- Notes: Reads many operational tables. Do not run concurrently with dashboard-heavy broad scans on constrained Supabase IO.

### Amazon listing status

- Command: `integrations/amazon_sync_listing_status.py --active-only --stale-days 3`
- Current groups: daily; dashboard; repricing
- Reads: amazon_skus; amazon_listing_snapshots
- Writes: amazon_listing_snapshots; amazon_skus
- Must run after: Amazon FBA inventory
- Must not overlap with: itself; Amazon listing status audit; Amazon FBA inventory if amazon_skus load is high
- AWS group/frequency: repricing-catalog / daily with stale-days=3; manual/audit weekly
- Parallelization: limited: one Listings call per selected SKU; avoid other Listings-heavy jobs
- Cloud mode: yes
- Notes: Listings Items API is rate-limited. Normal job selected only stale rows; audit selected hundreds.

### Amazon inventory planning

- Command: `integrations/amazon_sync_inventory_planning.py`
- Current groups: daily; dashboard; repricing
- Reads: amazon_report_runs
- Writes: amazon_report_runs; amazon_inventory_planning_snapshots
- Must run after: none
- Must not overlap with: itself; other Amazon report request/poll jobs if report quota is tight
- AWS group/frequency: fba-inventory-daily / daily
- Parallelization: limited: avoid concurrent report-heavy jobs
- Cloud mode: yes
- Notes: Report polling can hold ECS task time. Writes point-in-time snapshot rows.

### YNAB Business transactions

- Command: `integrations/ynab_sync_business_transactions.py --incremental --apply`
- Current groups: daily; dashboard
- Reads: ynab_business_transactions
- Writes: ynab_business_transactions
- Must run after: none
- Must not overlap with: itself
- AWS group/frequency: finance-daily / daily
- Parallelization: yes
- Cloud mode: yes
- Notes: Low volume. Should finish before business value snapshot if cash/transaction context is part of downstream reporting.

### YNAB cash balance

- Command: `integrations/ynab_sync_cash_balance.py --apply`
- Current groups: daily; dashboard
- Reads: none significant before write
- Writes: ynab_category_balance_snapshots
- Must run after: none
- Must not overlap with: itself
- AWS group/frequency: finance-daily / daily before business value snapshot
- Parallelization: yes
- Cloud mode: yes
- Notes: Low volume. Business value snapshot reads latest YNAB balance view.

### Amazon finance balances

- Command: `integrations/amazon_sync_finance_balances.py --apply`
- Current groups: daily; dashboard
- Reads: ynab_business_transactions
- Writes: amazon_finance_balance_snapshots
- Must run after: none
- Must not overlap with: itself; heavy Amazon finance jobs when SP-API quota is tight
- AWS group/frequency: finance-daily / daily before business value snapshot
- Parallelization: limited: avoid Amazon finance-heavy jobs
- Cloud mode: yes
- Notes: Feeds business value snapshot. SP-API finance calls are moderate.

### Amazon missing-fee sales finances

- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start days_ago(60) --order-finance-delay-seconds 1.5 --missing-fees-only --apply`
- Current groups: daily; sales-orders; dashboard
- Reads: amazon_sales_orders; vw_amazon_sales_orders_recent
- Writes: amazon_sales_financial_events; amazon_sales_transactions
- Must run after: Amazon sales orders
- Must not overlap with: Recent Amazon sales finances; Amazon sales finances audit
- AWS group/frequency: amazon-sales-fee-repair / daily
- Parallelization: no with other sales-finance jobs
- Cloud mode: yes, but isolate as quota-sensitive
- Notes: Nonblocking today. Use lower priority/capacity than current sales freshness chain.

### Daily missing-fee sales profitability

- Command: `integrations/amazon_sales_profitability.py --purchase-date-start days_ago(60) --missing-fees-only --apply`
- Current groups: daily; sales-orders; dashboard
- Reads: amazon sales/order/finance/COGS/label tables
- Writes: amazon_sales_profitability; amazon_sales_cogs_consumption
- Must run after: Amazon missing-fee sales finances
- Must not overlap with: Recent sales profitability; Sales profitability audit
- AWS group/frequency: amazon-sales-fee-repair / daily after missing-fee finance
- Parallelization: no with profitability writers
- Cloud mode: yes
- Notes: Supabase-heavy relative to simple snapshots; keep out of hourly critical path.

### Amazon sales finances audit

- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start days_ago(60) --order-finance-delay-seconds 1.5 --apply`
- Current groups: finance-audit
- Reads: amazon_sales_orders; vw_amazon_sales_orders_recent
- Writes: amazon_sales_financial_events; amazon_sales_transactions
- Must run after: Amazon sales orders
- Must not overlap with: Recent Amazon sales finances; Amazon missing-fee sales finances; itself
- AWS group/frequency: finance-audit / manual-only initially; weekly off-hours if needed
- Parallelization: no with sales-finance jobs
- Cloud mode: yes, but manual/weekly only
- Notes: Longest observed job at ~21 minutes. Major SP-API quota/cost/runtime candidate.

### Sales profitability audit

- Command: `integrations/amazon_sales_profitability.py --purchase-date-start days_ago(60) --apply`
- Current groups: finance-audit
- Reads: amazon sales/order/finance/COGS/label tables
- Writes: amazon_sales_profitability; amazon_sales_cogs_consumption
- Must run after: Amazon sales finances audit
- Must not overlap with: Recent sales profitability; Daily missing-fee sales profitability; itself
- AWS group/frequency: finance-audit / manual-only initially; weekly after finance audit if needed
- Parallelization: no with profitability writers
- Cloud mode: yes, but manual/weekly only
- Notes: Observed ~4.4 minutes. Supabase-heavy and not required for hourly freshness.

### Amazon listing status audit

- Command: `integrations/amazon_sync_listing_status.py --active-only`
- Current groups: listing-audit
- Reads: amazon_skus
- Writes: amazon_listing_snapshots; amazon_skus
- Must run after: Amazon FBA inventory
- Must not overlap with: Amazon listing status; itself
- AWS group/frequency: listing-audit / manual-only initially; weekly off-hours if needed
- Parallelization: no with listing-status jobs
- Cloud mode: yes, but manual/weekly only
- Notes: One Listings Items call per active SKU. Observed 365 rows and 429/retry signals.

### Inventory reconciliation audit

- Command: `integrations/inventory_reconcile.py`
- Current groups: inventory-audit
- Reads: same as Inventory reconciliation
- Writes: inventory_positions; inventory_reconciliation_events; inventory_reconciliation_event_items
- Must run after: Amazon FBA inventory; Amazon FBA shipments; Amazon listing status
- Must not overlap with: Inventory reconciliation; itself
- AWS group/frequency: inventory-audit / manual-only or weekly off-hours
- Parallelization: limited: avoid broad Supabase jobs
- Cloud mode: yes
- Notes: No skip-if-unchanged. Keep off the critical scheduler unless explicitly auditing.

### Informed repricing reports

- Command: `integrations/informed_sync_reports.py --write`
- Current groups: daily; repricing
- Reads: informed_report_runs
- Writes: informed_report_runs; informed_listing_snapshots/informed_rule_snapshots depending report category
- Must run after: none
- Must not overlap with: itself; other Informed report jobs
- AWS group/frequency: repricing-catalog / daily
- Parallelization: limited: report polling task can run beside non-repricing jobs
- Cloud mode: yes
- Notes: Read-only advisory intelligence. Must not use Informed Listings Management upload/feed APIs.

### Business value snapshot

- Command: `integrations/business_value_snapshot.py --apply`
- Current groups: daily; dashboard; fba
- Reads: inventory_positions; vw_latest_amazon_finance_balance_snapshot; vw_latest_ynab_category_balance_snapshot; business_value_snapshots
- Writes: business_value_snapshots
- Must run after: Inventory reconciliation; YNAB cash balance; Amazon finance balances
- Must not overlap with: itself; inventory reconciliation writes if strict value snapshot consistency matters
- AWS group/frequency: business-value-finalizer / daily after finance and inventory groups complete
- Parallelization: limited: run after finance/inventory fan-in for best numbers
- Cloud mode: yes
- Notes: This is a finalizer, not a source sync. Bad ordering gives stale value, not corrupt data.

### Sourcing listing availability

- Command: `integrations/refresh_sourcing_listing_availability.py --apply --limit 250`
- Current groups: daily; catalog
- Reads: sourcing_opportunities; sourcing_ebay_candidates; sourcing_settings
- Writes: sourcing_ebay_candidates; sourcing_opportunities; sourcing_actions
- Must run after: none
- Must not overlap with: itself; sourcing opportunity scoring/matching jobs
- AWS group/frequency: sourcing-catalog / daily or every 6 hours during buying windows
- Parallelization: limited: avoid sourcing_opportunities writers
- Cloud mode: yes
- Notes: Bounded eBay Browse calls. Keeps stale/ended sourcing candidates from polluting buy decisions.

### Matching intelligence refresh

- Command: `integrations/refresh_matching_intelligence.py --runs-per-mode 1`
- Current groups: core; daily; catalog; purchases
- Reads: sourcing_runs; sourcing_actions; sourcing_opportunities; sourcing_ebay_candidates; sourcing_seed_asins; manual_item_matches; purchase_items; order_problem_cases; matching_intelligence_examples; vw_latest_keepa_product_snapshot
- Writes: matching_intelligence_examples; sourcing_listing_snapshots; sourcing_seller_intelligence; sourcing_opportunities; sourcing_runs
- Must run after: Sourcing purchase matching, for latest positive match examples
- Must not overlap with: itself; Sourcing purchase matching; Sourcing listing availability; scoring jobs
- AWS group/frequency: sourcing-catalog / daily, off the hot purchase ingestion path
- Parallelization: limited: avoid sourcing writers and broad Supabase scans
- Cloud mode: yes
- Notes: Currently included in core and daily; for AWS cost/load, move to a separate sourcing-catalog task unless purchasing freshness requires it.

### Keepa active products

- Command: `integrations/keepa_sync_products.py --source amazon_active --limit 10 --batch-size 10 --stale-days 7 --min-tokens 100 --offers 20 --stock --no-history --write`
- Current groups: catalog; repricing
- Reads: vw_latest_amazon_fba_inventory_snapshot; vw_latest_keepa_product_snapshot
- Writes: keepa_product_snapshots; optional keepa_product_history_points when --write-history and history enabled
- Must run after: Amazon FBA inventory
- Must not overlap with: any other Keepa job
- AWS group/frequency: keepa-rolling-refresh / every 2 hours with --limit 10 only if target cadence accepts ~120 ASIN/day; otherwise lower offers/stock or upgrade Keepa tokens
- Parallelization: no with Keepa jobs; yes with unrelated low-load Supabase jobs
- Cloud mode: yes, but token budget requires central scheduling
- Notes: Observed active config consumed 98 tokens for 10 ASINs (~9.8/ASIN). With 5 token/min refill, this cannot refresh ~1,028 ASINs every 3/5/7 days using offers=20+stock.

### Keepa FBA prep pricing

- Command: `integrations/keepa_sync_products.py --source received_fba_prep --batch-size 20 --min-tokens 25 --offers 20 --stock --no-history --write`
- Current groups: fba-pricing
- Reads: purchase_items; vw_latest_keepa_product_snapshot
- Writes: keepa_product_snapshots; optional keepa_product_history_points when --write-history and history enabled
- Must run after: Receiving marks Amazon-bound items received; optional Amazon FBA inventory
- Must not overlap with: any other Keepa job
- AWS group/frequency: fba-pricing / manual/on-demand during FBA prep, or hourly with --limit 5-10 and min-tokens >=100
- Parallelization: no with Keepa jobs
- Cloud mode: yes only after adding per-batch token checks or a safer limit
- Notes: Observed 20-ASIN batch consumed 228 tokens and the second 20-ASIN batch hit HTTP 429. Current scheduler command is too aggressive for 300 max/5 per minute token plan.

### Amazon Product Fees estimates

- Command: `integrations/amazon_sync_fee_estimates.py`
- Current groups: fba-pricing
- Reads: purchase_items; vw_latest_keepa_product_snapshot; amazon_fee_estimates
- Writes: amazon_fee_estimates
- Must run after: Keepa active products or Keepa FBA prep pricing, so price points are current
- Must not overlap with: itself; other Product Fees jobs
- AWS group/frequency: fba-pricing / hourly during FBA prep; daily otherwise
- Parallelization: limited: Product Fees v0 is rate-limited; avoid other SP-API heavy calls
- Cloud mode: yes
- Notes: Should follow Keepa/price refresh. Observed 40 selected price points and 40 cached estimates.
