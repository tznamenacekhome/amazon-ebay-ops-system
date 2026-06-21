# Scheduled Job Instrumentation Summary

- Run ID: `20260620-080136`
- Scheduler group run: `all`
- Generated at: `2026-06-20T15:51:09.474490Z`
- Exit code so far/final: `0`
- Jobs captured: `33`
- CSV: `exports\scheduled_job_instrumentation_run.csv`

## Observed Run

| Job | Status | Runtime | Rows read | Inserted | Updated | Skipped/no-op | Log |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| eBay buyer purchases | success | 7.5s | 14 | 0 | 9 | 5 | `logs\scheduled_job_instrumentation\20260620-080136_eBay_buyer_purchases.log` |
| Sourcing purchase matching | success | 8.2s |  |  |  | 16 | `logs\scheduled_job_instrumentation\20260620-080136_Sourcing_purchase_matching.log` |
| EasyPost shipments | success | 40.1s | 98 |  |  | 10 | `logs\scheduled_job_instrumentation\20260620-080136_EasyPost_shipments.log` |
| eBay order problem returns/inquiries | success | 24.7s |  | 0 | 13 | 16 | `logs\scheduled_job_instrumentation\20260620-080136_eBay_order_problem_returns_inquiries.log` |
| EasyPost order problem returns | success | 2.4s | 1 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_EasyPost_order_problem_returns.log` |
| RevSeller enrichment | success | 4.5s | 0 |  | 0 | 0 | `logs\scheduled_job_instrumentation\20260620-080136_RevSeller_enrichment.log` |
| Keepa missing purchase titles | success | 1.9s |  |  | 0 |  | `logs\scheduled_job_instrumentation\20260620-080136_Keepa_missing_purchase_titles.log` |
| Amazon sales orders | success | 8.2s | 92 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_sales_orders.log` |
| Recent Amazon sales finances | success | 225.7s | 125 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Recent_Amazon_sales_finances.log` |
| Veeqo MF label costs | success | 1.8s | 0 |  |  | 0 | `logs\scheduled_job_instrumentation\20260620-080136_Veeqo_MF_label_costs.log` |
| Recent sales profitability | success | 57.4s |  |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Recent_sales_profitability.log` |
| Amazon FBA inventory | success | 100.0s | 6329 | 6329 | 6329 |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_FBA_inventory.log` |
| Amazon FBA shipments | success | 89.3s | 2 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_FBA_shipments.log` |
| FBA EasyPost carrier tracking | success | 3.3s | 4 |  |  | 0 | `logs\scheduled_job_instrumentation\20260620-080136_FBA_EasyPost_carrier_tracking.log` |
| Inventory reconciliation | success | 41.9s | 2811 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Inventory_reconciliation.log` |
| Amazon listing status | success | 6.9s | 1 | 1 | 1 |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_listing_status.log` |
| Amazon inventory planning | success | 36.0s | 367 | 367 |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_inventory_planning.log` |
| YNAB Business transactions | success | 3.5s | 94 |  | 94 |  | `logs\scheduled_job_instrumentation\20260620-080136_YNAB_Business_transactions.log` |
| YNAB cash balance | success | 2.9s |  |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_YNAB_cash_balance.log` |
| Amazon finance balances | success | 17.6s | 1208 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_finance_balances.log` |
| Amazon missing-fee sales finances | success | 76.8s | 38 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_missing-fee_sales_finances.log` |
| Daily missing-fee sales profitability | success | 18.2s |  |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Daily_missing-fee_sales_profitability.log` |
| Amazon sales finances audit | success | 1276.7s | 655 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_sales_finances_audit.log` |
| Sales profitability audit | success | 265.3s |  |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Sales_profitability_audit.log` |
| Amazon listing status audit | success | 178.3s | 365 | 365 | 365 |  | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_listing_status_audit.log` |
| Inventory reconciliation audit | success | 40.4s | 2811 |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Inventory_reconciliation_audit.log` |
| Informed repricing reports | success | 20.8s | 999 | 999 |  | 0 | `logs\scheduled_job_instrumentation\20260620-080136_Informed_repricing_reports.log` |
| Business value snapshot | success | 4.3s |  |  |  |  | `logs\scheduled_job_instrumentation\20260620-080136_Business_value_snapshot.log` |
| Sourcing listing availability | success | 58.5s | 73 |  |  | 0 | `logs\scheduled_job_instrumentation\20260620-080136_Sourcing_listing_availability.log` |
| Matching intelligence refresh | success | 79.0s | 323 | 0 | 323 |  | `logs\scheduled_job_instrumentation\20260620-080136_Matching_intelligence_refresh.log` |
| Keepa active products | success | 55.6s | 10 | 10 |  | 0 | `logs\scheduled_job_instrumentation\20260620-080136_Keepa_active_products.log` |
| Keepa FBA prep pricing | success | 25.1s | 20 | 20 |  | 20 | `logs\scheduled_job_instrumentation\20260620-080136_Keepa_FBA_prep_pricing.log` |
| Amazon Product Fees estimates | success | 66.6s | 40 | 40 | 40 | 0 | `logs\scheduled_job_instrumentation\20260620-080136_Amazon_Product_Fees_estimates.log` |

## AWS Planning Recommendations

### eBay buyer purchases

- Current groups: `core, purchases, dashboard`
- Command: `integrations/ebay_sync_buyer_purchases.py --days-back 7 --missing-tracking-lookback-days 90 --missing-tracking-limit 250`
- External service: eBay + Supabase
- Observed status/runtime: success, 7.5s
- Proposed AWS group: purchase-ingestion-core
- Proposed initial frequency: hourly during operating hours; every 2-4 hours otherwise
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN
- API calls: Trading pages + no-tracking chunks + optional Browse detail calls; estimate from retrieved pages/log.
- Data volume: read/scanned=14, inserted=0, updated=9, skipped/no-op=5, log=762 bytes
- Raw/high-volume writes: yes: stores raw eBay order JSON on purchase rows
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Trading/Browse API quota; 90-day missing-tracking refresh can add reads/API calls.

### Sourcing purchase matching

- Current groups: `core, purchases, dashboard`
- Command: `integrations/match_sourcing_purchases.py --limit 300`
- External service: Supabase-only
- Observed status/runtime: success, 8.2s
- Proposed AWS group: purchase-ingestion-core
- Proposed initial frequency: hourly after purchase ingestion
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=16, log=297 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Supabase read/write load only; bounded by --limit.

### EasyPost shipments

- Current groups: `core, purchases, dashboard`
- Command: `integrations/easypost_sync_shipments.py --limit 150`
- External service: EasyPost + Supabase
- Observed status/runtime: success, 40.1s
- Proposed AWS group: purchase-tracking
- Proposed initial frequency: hourly for inbound shipments
- Trigger mode: EventBridge scheduled now; webhook-driven long term
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY
- API calls: observed estimate: 88; approximately processed rows plus tracker creations/retrievals.
- Data volume: read/scanned=98, inserted=n/a, updated=n/a, skipped/no-op=10, log=5846 bytes
- Raw/high-volume writes: yes: writes tracking detail/events; potentially high-volume tracking events
- Retry/rate-limit behavior: observed retry/rate-limit log signal; EasyPost jobs cap requests and retry 429 with backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Keep <=5 EasyPost requests/sec; retry/backoff on 429.

### eBay order problem returns/inquiries

- Current groups: `core, purchases, dashboard`
- Command: `integrations/ebay_sync_order_problem_returns.py --lookback-days 60 --limit 100 --apply`
- External service: eBay + Supabase
- Observed status/runtime: success, 24.7s
- Proposed AWS group: returns-and-order-problems
- Proposed initial frequency: every 2-4 hours
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN
- API calls: Post-Order returns/inquiries/cases plus Trading refunds.
- Data volume: read/scanned=n/a, inserted=0, updated=13, skipped/no-op=16, log=2504 bytes
- Raw/high-volume writes: yes: writes problem payloads and event rows
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Nonblocking job; event rows can grow with changes.

### EasyPost order problem returns

- Current groups: `core, purchases, dashboard`
- Command: `integrations/easypost_sync_order_problem_returns.py --limit 100`
- External service: EasyPost + Supabase
- Observed status/runtime: success, 2.4s
- Proposed AWS group: returns-and-order-problems
- Proposed initial frequency: every 2-4 hours
- Trigger mode: EventBridge scheduled now; webhook-driven long term
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY
- API calls: observed estimate: 1; approximately processed return tracking rows.
- Data volume: read/scanned=1, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=289 bytes
- Raw/high-volume writes: yes: writes return tracking detail/events
- Retry/rate-limit behavior: EasyPost jobs cap requests and retry 429 with backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: EasyPost quota/rate limit.

### RevSeller enrichment

- Current groups: `core, purchases, dashboard`
- Command: `integrations/sync_revseller_sheet.py --ai-review --ai-review-limit 25`
- External service: Google Sheets/RevSeller + OpenAI optional + Supabase
- Observed status/runtime: success, 4.5s
- Proposed AWS group: purchase-enrichment
- Proposed initial frequency: hourly or every 2 hours
- Trigger mode: EventBridge scheduled
- Cloud mode: yes, if Google/OpenAI credentials are available
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Google Sheets credentials; optional OPENAI_API_KEY
- API calls: Google Sheet read plus up to --ai-review-limit OpenAI calls.
- Data volume: read/scanned=0, inserted=n/a, updated=0, skipped/no-op=0, log=1210 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: AI review limit controls OpenAI usage; sheet access from cloud needs credentials/files.

### Keepa missing purchase titles

- Current groups: `core, purchases, dashboard`
- Command: `integrations/backfill_amazon_titles_from_keepa.py --limit 25 --fetch-missing --min-tokens 25 --apply`
- External service: Keepa + Supabase
- Observed status/runtime: success, 1.9s
- Proposed AWS group: catalog-intelligence-light
- Proposed initial frequency: every 4-6 hours
- Trigger mode: EventBridge scheduled
- Cloud mode: yes with token guard
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY
- API calls: bounded by --limit/--batch-size and token availability.
- Data volume: read/scanned=n/a, inserted=n/a, updated=0, skipped/no-op=n/a, log=354 bytes
- Raw/high-volume writes: yes: Keepa product snapshots
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff; Keepa token threshold guards calls
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Keepa token budget; job skips below min tokens.

### Amazon sales orders

- Current groups: `core, sales-orders`
- Command: `integrations/amazon_sync_sales_orders.py --apply`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 8.2s
- Proposed AWS group: amazon-sales
- Proposed initial frequency: hourly
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 3; order pages plus item calls for changed/unseen orders.
- Data volume: read/scanned=92, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=1360 bytes
- Raw/high-volume writes: yes: Amazon sales order/item rows
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: SP-API throttling; getOrderItems can multiply calls.

### Recent Amazon sales finances

- Current groups: `core, sales-orders`
- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start 2026-06-06T15:51:09.444208Z --order-finance-delay-seconds 1.5 --apply`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 225.7s
- Proposed AWS group: amazon-sales
- Proposed initial frequency: hourly or every 2 hours with finance delay
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 128; retries observed: 2; approximately orders checked plus transaction fallback pages.
- Data volume: read/scanned=125, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=16773 bytes
- Raw/high-volume writes: yes: financial event rows; high-volume possible
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: SP-API finance quotas; raw financial events can grow.

### Veeqo MF label costs

- Current groups: `core, sales-orders`
- Command: `integrations/veeqo_sync_sales_labels.py --purchase-date-start 2026-06-06T15:51:09.446698Z --missing-only --apply`
- External service: Veeqo + Supabase
- Observed status/runtime: success, 1.8s
- Proposed AWS group: amazon-sales
- Proposed initial frequency: hourly or every 2 hours
- Trigger mode: EventBridge scheduled
- Cloud mode: yes if Veeqo key is configured; otherwise skipped
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; VEEQO_KEY
- API calls: one or more Veeqo order lookups for candidate Amazon orders.
- Data volume: read/scanned=0, inserted=n/a, updated=n/a, skipped/no-op=0, log=1078 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: Veeqo client retries 429/5xx with Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Veeqo API retry/backoff on 429/5xx.

### Recent sales profitability

- Current groups: `core`
- Command: `integrations/amazon_sales_profitability.py --purchase-date-start 2026-06-06T15:51:09.446698Z --apply`
- External service: Supabase-only
- Observed status/runtime: success, 57.4s
- Proposed AWS group: amazon-sales
- Proposed initial frequency: hourly after sales/finance sync
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=1199 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Supabase CPU/read load; backend-owned cost calculations.

### Amazon FBA inventory

- Current groups: `daily, dashboard, reconciliation, repricing, fba`
- Command: `integrations/amazon_sync_fba_inventory.py --page-delay-seconds 0.25`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 100.0s
- Proposed AWS group: fba-inventory-daily
- Proposed initial frequency: daily, plus manual on demand
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 129; retries observed: 2; inventory summary pages.
- Data volume: read/scanned=6329, inserted=6329, updated=6329, skipped/no-op=n/a, log=32260 bytes
- Raw/high-volume writes: yes: inserts inventory snapshot rows each run
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Snapshot row growth and SP-API pagination.

### Amazon FBA shipments

- Current groups: `daily, dashboard, reconciliation, fba`
- Command: `integrations/amazon_sync_fba_shipments.py`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 89.3s
- Proposed AWS group: fba-shipments
- Proposed initial frequency: every 2-4 hours when shipping; daily otherwise
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 22; selected shipments times status/items/availability calls.
- Data volume: read/scanned=2, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=18711 bytes
- Raw/high-volume writes: yes: shipment workflow events
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: SP-API shipment calls per selected shipment; event row growth.

### FBA EasyPost carrier tracking

- Current groups: `daily, dashboard, reconciliation, fba`
- Command: `integrations/easypost_sync_fba_shipments.py --limit 25 --max-new-trackers 10`
- External service: EasyPost + Supabase
- Observed status/runtime: success, 3.3s
- Proposed AWS group: fba-shipments
- Proposed initial frequency: every 2-4 hours while shipments are in transit
- Trigger mode: EventBridge scheduled now; webhook-driven long term
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EASYPOST_API_KEY
- API calls: observed estimate: 4; approximately processed rows plus new tracker creations.
- Data volume: read/scanned=4, inserted=n/a, updated=n/a, skipped/no-op=0, log=608 bytes
- Raw/high-volume writes: yes: FBA carrier tracking details
- Retry/rate-limit behavior: EasyPost jobs cap requests and retry 429 with backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: EasyPost request cap and max-new-trackers guard.

### Inventory reconciliation

- Current groups: `core, dashboard, reconciliation, fba`
- Command: `integrations/inventory_reconcile.py --skip-if-unchanged`
- External service: Supabase-only
- Observed status/runtime: success, 41.9s
- Proposed AWS group: reconciliation
- Proposed initial frequency: after inventory/FBA updates; hourly or daily depending source freshness
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=2811, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=721 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Can scan multiple operational tables; skip-if-unchanged reduces load.

### Amazon listing status

- Current groups: `daily, dashboard, repricing`
- Command: `integrations/amazon_sync_listing_status.py --active-only --stale-days 3`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 6.9s
- Proposed AWS group: repricing-catalog
- Proposed initial frequency: daily with stale-days guard
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed estimate: 1; one Listings Items call per selected SKU.
- Data volume: read/scanned=1, inserted=1, updated=1, skipped/no-op=n/a, log=1035 bytes
- Raw/high-volume writes: yes: listing status snapshots
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Listings Items calls are rate limited; default delay stays near 4 requests/sec.

### Amazon inventory planning

- Current groups: `daily, dashboard, repricing`
- Command: `integrations/amazon_sync_inventory_planning.py`
- External service: Amazon SP-API Reports + Supabase
- Observed status/runtime: success, 36.0s
- Proposed AWS group: fba-inventory-daily
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 4; create/get report plus polling/document download.
- Data volume: read/scanned=367, inserted=367, updated=n/a, skipped/no-op=n/a, log=1724 bytes
- Raw/high-volume writes: yes: planning snapshot rows
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Report polling time and snapshot row growth.

### YNAB Business transactions

- Current groups: `daily, dashboard`
- Command: `integrations/ynab_sync_business_transactions.py --incremental --apply`
- External service: YNAB + Supabase
- Observed status/runtime: success, 3.5s
- Proposed AWS group: finance-daily
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; YNAB_ACCESS_TOKEN; YNAB_BUDGET_ID
- API calls: YNAB budget/transactions call(s).
- Data volume: read/scanned=94, inserted=n/a, updated=94, skipped/no-op=n/a, log=1555 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: YNAB API availability; low volume.

### YNAB cash balance

- Current groups: `daily, dashboard`
- Command: `integrations/ynab_sync_cash_balance.py --apply`
- External service: YNAB + Supabase
- Observed status/runtime: success, 2.9s
- Proposed AWS group: finance-daily
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; YNAB_ACCESS_TOKEN; YNAB_BUDGET_ID
- API calls: YNAB budget/category call(s).
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=425 bytes
- Raw/high-volume writes: yes: cash balance snapshot row
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Low volume snapshot growth.

### Amazon finance balances

- Current groups: `daily, dashboard`
- Command: `integrations/amazon_sync_finance_balances.py --apply`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 17.6s
- Proposed AWS group: finance-daily
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 4; financial event group/transaction pages.
- Data volume: read/scanned=1208, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=1368 bytes
- Raw/high-volume writes: yes: finance balance snapshot row
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: SP-API finance calls; low row volume.

### Amazon missing-fee sales finances

- Current groups: `daily, sales-orders, dashboard`
- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start 2026-04-21T15:51:09.457083Z --order-finance-delay-seconds 1.5 --missing-fees-only --apply`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 76.8s
- Proposed AWS group: amazon-sales-fee-repair
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes, but keep separate from hourly sales
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 41; orders missing fees plus transaction fallback pages.
- Data volume: read/scanned=38, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=5662 bytes
- Raw/high-volume writes: yes: financial event rows; high-volume possible
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Longer 60-day lookback; SP-API quotas and Supabase write volume.

### Daily missing-fee sales profitability

- Current groups: `daily, sales-orders, dashboard`
- Command: `integrations/amazon_sales_profitability.py --purchase-date-start 2026-04-21T15:51:09.457083Z --missing-fees-only --apply`
- External service: Supabase-only
- Observed status/runtime: success, 18.2s
- Proposed AWS group: amazon-sales-fee-repair
- Proposed initial frequency: daily after missing-fee finance
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=1211 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Supabase scan/write load over 60-day window.

### Amazon sales finances audit

- Current groups: `finance-audit`
- Command: `integrations/amazon_sync_sales_finances.py --purchase-date-start 2026-04-21T15:51:09.458082Z --order-finance-delay-seconds 1.5 --apply`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 1276.7s
- Proposed AWS group: finance-audit
- Proposed initial frequency: weekly or manual
- Trigger mode: manual-only initially
- Cloud mode: yes, but isolate from normal hourly jobs
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 760; retries observed: 102; all eligible orders in 60-day window plus transaction fallback pages.
- Data volume: read/scanned=655, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=94603 bytes
- Raw/high-volume writes: yes: financial event rows; high-volume possible
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Potentially long runtime and SP-API quota pressure.

### Sales profitability audit

- Current groups: `finance-audit`
- Command: `integrations/amazon_sales_profitability.py --purchase-date-start 2026-04-21T15:51:09.463080Z --apply`
- External service: Supabase-only
- Observed status/runtime: success, 265.3s
- Proposed AWS group: finance-audit
- Proposed initial frequency: weekly or manual after finance audit
- Trigger mode: manual-only initially
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=1183 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Supabase read/write load over 60-day window.

### Amazon listing status audit

- Current groups: `listing-audit`
- Command: `integrations/amazon_sync_listing_status.py --active-only`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 178.3s
- Proposed AWS group: listing-audit
- Proposed initial frequency: weekly or manual
- Trigger mode: manual-only initially
- Cloud mode: yes, but quota-sensitive
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed logged HTTP calls: 365; one Listings Items call per active SKU.
- Data volume: read/scanned=365, inserted=365, updated=365, skipped/no-op=n/a, log=43975 bytes
- Raw/high-volume writes: yes: listing status snapshots
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: One SP-API Listings call per active SKU; can be long.

### Inventory reconciliation audit

- Current groups: `inventory-audit`
- Command: `integrations/inventory_reconcile.py`
- External service: Supabase-only
- Observed status/runtime: success, 40.4s
- Proposed AWS group: inventory-audit
- Proposed initial frequency: weekly or manual
- Trigger mode: manual-only initially
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=2811, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=529 bytes
- Raw/high-volume writes: no
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Broad Supabase scan across inventory tables.

### Informed repricing reports

- Current groups: `daily, repricing`
- Command: `integrations/informed_sync_reports.py --write`
- External service: Informed + Supabase
- Observed status/runtime: success, 20.8s
- Proposed AWS group: repricing-catalog
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; INFORMED_API_KEY or Informed credentials
- API calls: observed logged HTTP calls: 3; report request/status/download calls.
- Data volume: read/scanned=999, inserted=999, updated=n/a, skipped/no-op=0, log=1858 bytes
- Raw/high-volume writes: yes: repricing report snapshot rows
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Report request/polling delay and snapshot growth.

### Business value snapshot

- Current groups: `daily, dashboard, fba`
- Command: `integrations/business_value_snapshot.py --apply`
- External service: Supabase-only
- Observed status/runtime: success, 4.3s
- Proposed AWS group: finance-daily
- Proposed initial frequency: daily after finance/inventory jobs
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=n/a, inserted=n/a, updated=n/a, skipped/no-op=n/a, log=508 bytes
- Raw/high-volume writes: yes: business value snapshot row
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Reads inventory/value tables; low write volume.

### Sourcing listing availability

- Current groups: `daily, catalog`
- Command: `integrations/refresh_sourcing_listing_availability.py --apply --limit 250`
- External service: eBay Browse + Supabase
- Observed status/runtime: success, 58.5s
- Proposed AWS group: catalog-intelligence-light
- Proposed initial frequency: daily or every 6 hours
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; EBAY_CLIENT_ID; EBAY_CLIENT_SECRET; EBAY_REFRESH_TOKEN
- API calls: observed estimate: 53; one Browse item call per unique eBay item checked.
- Data volume: read/scanned=73, inserted=n/a, updated=n/a, skipped/no-op=0, log=411 bytes
- Raw/high-volume writes: yes: may update raw eBay JSON for candidates
- Retry/rate-limit behavior: none observed in run; no script-specific retry found during inspection
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: eBay Browse calls bounded by --limit.

### Matching intelligence refresh

- Current groups: `core, daily, catalog, purchases`
- Command: `integrations/refresh_matching_intelligence.py --runs-per-mode 1`
- External service: Supabase-only
- Observed status/runtime: success, 79.0s
- Proposed AWS group: catalog-intelligence-light
- Proposed initial frequency: daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY
- API calls: 0 external API calls.
- Data volume: read/scanned=323, inserted=0, updated=323, skipped/no-op=n/a, log=2176 bytes
- Raw/high-volume writes: yes: matching examples/listing snapshots may be inserted
- Retry/rate-limit behavior: observed retry/rate-limit log signal
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Can scan multiple sourcing/history tables; keep isolated from hot purchase ingestion.

### Keepa active products

- Current groups: `catalog, repricing`
- Command: `integrations/keepa_sync_products.py --source amazon_active --limit 10 --batch-size 10 --stale-days 7 --min-tokens 100 --offers 20 --stock --no-history --write`
- External service: Keepa + Supabase
- Observed status/runtime: success, 55.6s
- Proposed AWS group: repricing-catalog
- Proposed initial frequency: daily or several times daily, token permitting
- Trigger mode: EventBridge scheduled
- Cloud mode: yes with token guard
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY
- API calls: observed estimate: 1; bounded by --limit/--batch-size and tokens.
- Data volume: read/scanned=10, inserted=10, updated=n/a, skipped/no-op=0, log=1418 bytes
- Raw/high-volume writes: yes: Keepa snapshots and optional history rows
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff; Keepa token threshold guards calls
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Keepa token budget; stock/offers cost extra tokens.

### Keepa FBA prep pricing

- Current groups: `fba-pricing`
- Command: `integrations/keepa_sync_products.py --source received_fba_prep --batch-size 20 --min-tokens 25 --offers 20 --stock --no-history --write`
- External service: Keepa + Supabase
- Observed status/runtime: success, 25.1s
- Proposed AWS group: fba-pricing
- Proposed initial frequency: hourly while prepping shipments; otherwise daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes with token guard
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; KEEPA_API_KEY
- API calls: observed estimate: 2; bounded by source selection/batch-size and tokens.
- Data volume: read/scanned=20, inserted=20, updated=n/a, skipped/no-op=20, log=2040 bytes
- Raw/high-volume writes: yes: Keepa snapshots and optional history rows
- Retry/rate-limit behavior: observed retry/rate-limit log signal; Keepa token threshold guards calls
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Keepa token budget; unbounded source may select all eligible received FBA prep rows.

### Amazon Product Fees estimates

- Current groups: `fba-pricing`
- Command: `integrations/amazon_sync_fee_estimates.py`
- External service: Amazon SP-API + Supabase
- Observed status/runtime: success, 66.6s
- Proposed AWS group: fba-pricing
- Proposed initial frequency: hourly while pricing/prepping; otherwise daily
- Trigger mode: EventBridge scheduled
- Cloud mode: yes
- Required secrets/env: SUPABASE_URL; SUPABASE_SERVICE_ROLE_KEY; Amazon SP-API credentials
- API calls: observed estimate: 40; one fee estimate call per selected price point.
- Data volume: read/scanned=40, inserted=40, updated=40, skipped/no-op=0, log=5530 bytes
- Raw/high-volume writes: yes: fee estimate cache rows
- Retry/rate-limit behavior: Amazon SP-API client retries 429/5xx using Retry-After/backoff
- Lock behavior: run_all_syncs local file lock; this instrumentation run used the same lock unless --no-lock was passed
- Concerns: Product Fees v0 is rate-limited; keep separate from other SP-API heavy jobs.
