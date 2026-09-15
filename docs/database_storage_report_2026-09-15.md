# Database storage and cleanup assessment - September 15, 2026

## Findings

The MBOP/College Planner database occupies **6.356 GiB**. Its database filesystem has **0.959 GiB free of 7.839 GiB (12.24%)**, below the sourcing guard's 15% minimum. About **222 MiB more free space** would reach that threshold at the observed filesystem size; this would be only a temporary margin. Latest swap headroom is also low, **20.6% free versus the required 25%**. A tiny database read succeeds. No cleanup or resize was performed.

The strongest directly verified cleanup candidate is one duplicate FBA index: **58.55 MiB**. Retired MBOP finance tables total **4.55 MiB** and require retention approval. Together these are insufficient to clear the disk shortfall.

The top three tables occupy **4.029 GiB**, about **63.4%** of the MBOP database. Historical snapshot and diagnostic storage is the large opportunity, but its safe recoverable fraction is **not yet measured**. Preserve business records and audit evidence; archive payloads losslessly before considering deletion or compaction.

## Scope and measurement

- Two accessible Supabase projects were enumerated. Each has one application database named `postgres`, plus PostgreSQL template databases. College Planner is a schema inside the MBOP database, not a separate instance.
- Report includes **all 278 allocated tables/materialized-view/partition relations** exposed by the catalog inventory, including managed schemas. Ordinary views store no independent row data and are not cleanup targets.
- Table sizes include their indexes and TOAST (large-value storage). Table-data and index columns partition that total. Sizes are physical allocation, not proven live payload or guaranteed reclaimable space.
- Row estimates and dead-tuple estimates were collected only as diagnostics; they are not exact counts, bloat measurements or proof of duplicate data. Prior MBOP investigations showed misleading estimates on large snapshot tables.
- Inventory timestamps: MBOP 2026-09-15T17:54:14.042244+00:00; ZFI 2026-09-15T17:54:25.7255+00:00. Separate queries are not one frozen transactional snapshot.
- Source reads were metadata-only except tiny DB health reads and a bounded sample request that returned a connector connection error. That failed sample produced no usable age, payload-size or duplication estimate and was not retried. No personal financial values or transaction contents were pulled from ZFI; its purpose labels below are inferred from names/columns unless documented by MBOP's integration boundary.
- System filesystem usage includes database files, WAL and other overhead; database relation totals do not explain all disk consumption. Supabase Storage object bytes, S3 archives, backups, ECR images and CloudWatch logs are outside these PostgreSQL table sizes. Disk IO Budget was not measured.
- Exact-byte machine-readable inventories are preserved locally in `tmp/ops-20260915/mbop-storage-inventory.json` and `zfi-storage-inventory.json`; dependency/index findings are in `storage-findings.json`.

A portable exact-byte [JSON inventory](database_storage_inventory_2026-09-15.json) accompanies this report.

## Database inventory

| Project / database | What it stores | Size MiB | Size GiB | Capacity relationship |
| --- | --- | ---: | ---: | --- |
| amazon-ebay-ops / template1 | PostgreSQL database-creation template; managed system data | 7.24 | 0.007 | Keep; not an application cleanup target |
| amazon-ebay-ops / template0 | PostgreSQL database-creation template; managed system data | 7.17 | 0.007 | Keep; not an application cleanup target |
| amazon-ebay-ops / postgres | MBOP resale operations, College Planner, shared platform metadata | 6508.92 | 6.356 | This is the constrained MBOP instance |
| zoltarfi / template1 | PostgreSQL database-creation template; managed system data | 7.39 | 0.007 | Keep; not an application cleanup target |
| zoltarfi / template0 | PostgreSQL database-creation template; managed system data | 7.17 | 0.007 | Keep; not an application cleanup target |
| zoltarfi / postgres | ZFI finance/budget/tax/investment data and MBOP summary copies | 63.71 | 0.062 | Separate instance; cleanup cannot free MBOP disk |

## Schema allocation

| Project | Schema | Relations | Allocated MiB | Purpose |
| --- | --- | ---: | ---: | --- |
| MBOP | public | 105 | 6462.23 | Resale operations and retained legacy business data |
| MBOP | college_planner | 40 | 27.87 | Catalogs, courses, degree plans, private student records and import provenance |
| MBOP | supabase_migrations | 1 | 0.15 | Shared schema migration history; never prune as data cleanup. |
| MBOP | auth | 27 | 1.13 | Supabase authentication/session/security infrastructure; keep managed. |
| MBOP | storage | 8 | 0.21 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| MBOP | realtime | 3 | 0.05 | Supabase Realtime infrastructure. |
| MBOP | vault | 1 | 0.02 | Encrypted secrets infrastructure; contents not read. |
| MBOP | Remaining database allocation | - | 17.26 | Catalogs and other allocation outside the listed non-system relations; not measured reclaimable bloat |
| ZFI | public | 58 | 50.98 | Personal/business financial planning |
| ZFI | auth | 23 | 1.31 | Supabase authentication/session/security infrastructure; keep managed. |
| ZFI | storage | 8 | 0.21 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| ZFI | realtime | 3 | 0.05 | Supabase Realtime infrastructure. |
| ZFI | vault | 1 | 0.02 | Encrypted secrets infrastructure; contents not read. |
| ZFI | Remaining database allocation | - | 11.12 | Catalogs and other allocation outside the listed non-system relations; not measured reclaimable bloat |

## Cleanup and prevention candidates

| Priority | Candidate | Measured footprint / savings | Evidence and proposed treatment | Restrictions |
| --- | --- | --- | --- | --- |
| 1 | Duplicate FBA index | **58.55 MiB** candidate recovery | `amazon_fba_inventory_snapshots_sku_idx` and `idx_amazon_fba_inventory_snapshots_latest` both index `(seller_sku, marketplace_id, captured_at DESC)`. Metadata confirms same key/operator/collation/order/access method, both valid, neither unique/primary/constraint-backed, no differing reloptions. Keep one; propose removing the larger redundant index through reviewed maintenance. | Do not remove both. Verify dependencies/replica identity and index health immediately before execution. Zero scans alone is not justification. No DROP was run. |
| 2 | Retired MBOP YNAB/business-value copies | **4.55 MiB** total ceiling | Repository explicitly retired these after ZFI migration. `ynab_business_transactions`, `ynab_category_balance_snapshots`, `business_value_snapshots`. Existing retirement SQL is a proposal, not authorization. | Confirm historical backfill/export, retention and current dependencies first. Small impact; never apply MBOP retirement SQL to ZFI's active tables. |
| 3 | FBA inventory history | **1792.55 MiB** total; safe reduction unknown | Importer inserts a snapshot per SKU per sync, including original payload. Repeated unchanged observations are plausible but not counted here. Design a compact current-state table plus retained change history/periodic checkpoints; archive older payloads to content-addressed storage. | Preserve historical inventory observations, quantity transitions, COGS and latest-per-SKU semantics. Raw payload historical use must be checked across SQL and runtime readers. |
| 4 | Keepa repeated full product payloads | **1085.73 MiB** total; safe reduction unknown | Each snapshot retains full provider JSON, often including overlapping history arrays, plus normalized price/rank/offer fields. Prefer extracting necessary current fields and lossless archival/deduplication of historical payloads. | Active readers need stats, offers, images and price fallback evidence. FBA prep can read older usable offer snapshots. Deletion cascades to `keepa_product_history_points`. Do not blanket-null raw JSON. |
| 5 | Sourcing matching diagnostics | **1246.97 MiB** table; safe reduction unknown | Large persisted diagnostic/evidence objects coexist with candidate and listing-snapshot evidence. Compact canonical evidence references plus retrievable archived diagnostics could reduce repeated payloads. | Protect current rows, all adjudication/review/correction history, business holds, buying eligibility, replay inputs and stale-write guards. Archived readers and round-trip tests must precede removal. |
| 6 | Listing/candidate/seed evidence duplication | **754.45 MiB** combined ceiling | Repeated listing descriptions, specifics, images, raw eBay data and seed context appear in related tables. Content-addressed immutable evidence with retained event references is a design candidate. | A snapshot is evidence at a time, not automatically a redundant copy. Preserve exact source/review event provenance and restore paths. |
| 7 | Other imported snapshot histories | **561.35 MiB** combined ceiling | Daily report/snapshot history may be retained more compactly or archived after a policy-defined hot window. Avoid re-inserting identical reports where source identity proves exact duplication. | Keep latest records and fields used by listing status, repricing and planning. Choose retention policy explicitly; no 30/90-day deletion is preapproved. |
| 8 | Derived reconciliation/position history | **295.20 MiB** combined ceiling | Candidate for archival of superseded derived runs after verifying reproducibility and absence of references. | Preserve current positions, unresolved discrepancies, operator resolutions and all underlying purchase/COGS facts. Derived does not mean safely disposable. |
| 9 | Scheduler diagnostic metadata | **83.56 MiB** table ceiling | Consider reducing repeated verbose diagnostic metadata, retaining concise status/timing/error summaries and external log references. | Preserve run/job audit, failure evidence, locks and freshness. Do not remove telemetry merely because a run failed. |
| Protect | Atomic refresh log | **103.86 MiB** | Contains request IDs and guarded before/after states. This is audit/idempotency evidence, not an ordinary cache. | No pruning without explicit retry-retention semantics and archive/replay design. |
| Not useful | Browser/server caches and legacy tiny placeholders | Small metadata only | List caches reside in web/browser memory; invalidating them will not reclaim the large database tables. Empty-looking tables still require dependency checks. | No blanket cache/database clearing. |
| Already optimized | Finance transaction raw payloads | **23.24 MiB** remaining | September 10 lossless S3 archive already reclaimed 324.46 MiB after verified compaction. Retain archive objects and checksum references. | Do not count the earlier reclaimed space again or delete S3 source evidence. |

These ceilings overlap with database totals and are **not additive guaranteed savings**. An illustrative 25% reduction of FBA + Keepa table allocation would be about **719.57 MiB**, but this is scenario arithmetic, not a measured forecast. A retention/archival dry run must measure actual eligible payloads and validate restore before assigning a savings target.

## Why simple deletion is risky

Catalog foreign keys show `ON DELETE CASCADE` from sourcing opportunities to sourcing actions, purchase matches, batch membership and AI observations. Deleting a sourcing run can cascade through opportunities. Other references use SET NULL, which can sever provenance even when rows survive. Keepa snapshot deletion cascades to normalized history points. These are concrete dependencies, not hypothetical warnings.

Ordinary DELETE/VACUUM generally makes internal space reusable; it does not guarantee immediate filesystem shrinkage. VACUUM FULL/reindex/table rewrites can require locks and extra free disk. With current headroom, do not start broad rewrites. Large-table dead tuple estimates are not a byte-accurate bloat estimate. PostgreSQL maintenance guidance: [routine vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).

## Proposed sequence

1. Preserve the inventory and exact index definitions; review one duplicate-index removal and the small retired-table export separately.
2. Restore durable disk headroom before a broad archive or rewrite. The 59 MiB index candidate alone is smaller than the roughly 222 MiB immediate deficit. Review compute/memory as well: disk expansion does not solve low swap.
3. Prioritize lossless FBA/Keepa archival and write-side duplicate prevention. Use a bounded dry run with latest-record protection, content hashes, restore verification, reader compatibility and exact candidate-byte counts.
4. Address sourcing diagnostics only with explicit preservation of operator evidence, lifecycle, holds and atomic guards. Do not prune parent run/opportunity rows to save space.
5. Measure filesystem free bytes after each approved operation, then require both capacity metrics and a tiny successful read before rerunning sourcing. No rerun is included in this report.

For context, the database measured 6,286,740,627 bytes after the September 10 archive and 6825102483 bytes in this inventory: about **513.42 MiB net growth** in roughly five days. This is a net allocation comparison, not an attribution to one job or a stable daily growth forecast.

## Complete table inventory

Purpose descriptions for MBOP use repository documentation/runtime references where available. College Planner uses database comments where present; other labels and ZFI labels are schema-name/column inferences, not a full application-retention audit. Managed schema descriptions are generic infrastructure roles. Sizes are MiB; 1 MiB = 1,048,576 bytes.

### MBOP / College Planner: public

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `amazon_fba_inventory_snapshots` | 1792.55 | 1623.52 | 169.03 | Time-stamped Amazon FBA quantities, inventory states and original API payloads. |
| `sourcing_opportunities` | 1246.97 | 1235.15 | 11.82 | Scored eBay/Amazon pairs, profitability, routing state and full matching diagnostics. |
| `keepa_product_snapshots` | 1085.73 | 1075.60 | 10.13 | Point-in-time read-only Keepa product snapshots for catalog intelligence, price history, sales-rank history, and sales-frequency signals. |
| `sourcing_listing_snapshots` | 401.48 | 386.60 | 14.88 | Point-in-time evidence snapshots for sourced eBay listings that became MBOP opportunities or received operator/system actions. |
| `sourcing_ebay_candidates` | 226.44 | 221.59 | 4.84 | Discovered eBay listings, prices, availability, shipping and original listing payload. |
| `sourcing_coverage_cycle_items` | 212.49 | 173.54 | 38.95 | Durable per-ASIN sourcing queue and progress state for the unified daily coverage cycle. |
| `amazon_listing_snapshots` | 210.38 | 186.77 | 23.62 | Point-in-time read-only Amazon Listings Items snapshots for listing status, issues, and fulfillment availability. |
| `informed_listing_snapshots` | 203.63 | 174.71 | 28.92 | Point-in-time read-only Informed Repricer listing/pricing report rows used by MBOP repricing advisor. |
| `inventory_reconciliation_event_items` | 174.59 | 161.44 | 13.16 | Item-level reconciliation findings. Used to answer what MBOP believes is owned, what Amazon/eBay believe exists, what is in transition, and what needs operator review. |
| `amazon_inventory_planning_snapshots` | 147.34 | 135.03 | 12.30 | Point-in-time read-only Amazon FBA Inventory Planning report rows. Used for Amazon-native aged-inventory buckets in the repricing advisor. |
| `sourcing_seed_asins` | 126.53 | 115.05 | 11.48 | Run-specific Amazon product seeds, demand/inventory context and queue provenance. |
| `inventory_positions` | 120.61 | 97.37 | 23.24 | Derived current inventory positions for MBOP. Workflow tables remain authoritative; this layer normalizes location, marketplace intent, listing channel, operational state, and disposition for reconciliation. |
| `sourcing_decision_refresh_log` | 103.86 | 102.75 | 1.11 | Atomic decision-refresh audit and idempotency records; before/after guarded state. |
| `matching_intelligence_examples` | 84.52 | 76.04 | 8.48 | Rebuildable labeled examples for matching diagnostics and future scoring. Business-only labels must not poison ASIN identity matching. |
| `scheduler_run_jobs` | 83.56 | 77.91 | 5.66 | Per-job execution telemetry, logs/metadata, errors and result counts. |
| `amazon_sales_financial_events` | 59.51 | 52.99 | 6.52 | Amazon sales charges, fees and financial event evidence. |
| `order_problem_events` | 24.98 | 24.21 | 0.77 | Append-only order-problem workflow actions, messages and audit history. |
| `amazon_finance_balance_snapshots` | 23.24 | 23.16 | 0.08 | Point-in-time read-only Amazon Finance balance snapshots for Amazon-held cash, available withdrawal cash, and Amazon-to-bank in-transit cash. |
| `amazon_skus` | 21.79 | 20.27 | 1.52 | Canonical Amazon seller SKU/ASIN catalog. |
| `amazon_sales_finance_transactions` | 15.40 | 14.03 | 1.37 | Amazon finance transaction records used by sales reconciliation. |
| `sourcing_actions` | 11.68 | 11.09 | 0.59 | Operator review, dismissal, watch, offer, purchase and hold history. |
| `purchases` | 9.18 | 9.02 | 0.16 | Supplier/eBay order headers and source order evidence. |
| `amazon_sales_orders` | 8.95 | 7.19 | 1.77 | Amazon seller order headers imported from SP-API Orders. This table must not store buyer name, address, email, or phone. |
| `amazon_sales_order_items` | 7.54 | 6.13 | 1.41 | Amazon seller sales line items. |
| `scheduler_runs` | 7.18 | 4.66 | 2.52 | Scheduler invocation status, timing, task identity and errors. |
| `purchase_items` | 4.77 | 3.88 | 0.88 | Purchased units, ASIN, authoritative cost, manual corrections and workflow status. |
| `ynab_business_transactions` | 4.09 | 3.38 | 0.71 | Read-only local copy of YNAB transactions categorized as Business for future P&L, Schedule C, and cash reconciliation reporting. |
| `sourcing_runs` | 3.95 | 3.92 | 0.03 | Sourcing execution summaries, settings, quotas, counts and errors. |
| `veeqo_sales_orders` | 3.86 | 3.74 | 0.12 | Veeqo seller-order and label-cost source records. |
| `inbound_shipments` | 3.63 | 2.67 | 0.95 | Inbound tracking, carrier enrichment and delivery evidence. |
| `amazon_sales_profitability` | 3.19 | 1.65 | 1.54 | Backend sales profitability and COGS/fee outcomes. |
| `sourcing_seller_intelligence` | 2.59 | 1.68 | 0.91 | Derived seller intelligence for sourcing diagnostics. Avoid status is advisory only until hide-by-default is explicitly enabled. |
| `provider_usage_snapshots` | 2.30 | 1.80 | 0.50 | Provider API usage/quota snapshots. |
| `sourcing_opportunity_batch_items` | 2.08 | 1.10 | 0.98 | Stable membership of scored sourcing opportunities presented in each progressive batch. |
| `amazon_sales_cogs_consumption` | 1.91 | 1.21 | 0.70 | Sales allocation/consumption against inventory cost layers. |
| `fba_shipment_items` | 1.73 | 1.01 | 0.73 | Purchase-item quantities allocated to Amazon outbound shipments. |
| `non_ebay_purchase_cogs_sources` | 1.58 | 1.17 | 0.41 | Non-eBay inventory cost evidence and import provenance. |
| `inbound_shipment_items` | 1.51 | 0.59 | 0.92 | Purchase-unit allocation and receipt resolution per inbound package. |
| `provider_raw_payloads` | 1.22 | 1.18 | 0.04 | Original provider billing/usage source payloads. |
| `veeqo_sales_shipments` | 1.20 | 1.04 | 0.16 | Veeqo shipment, tracking and label-cost evidence. |
| `amazon_fee_estimates` | 1.16 | 1.02 | 0.15 | Cached SP-API Product Fees v0 estimates used for pre-FBA shipment pricing and ROI review. |
| `matching_intelligence_receiving_outcomes` | 1.12 | 0.98 | 0.13 | Receiving-owned item verification outcomes consumed by Matching Intelligence as explicit labeled evidence. |
| `order_problem_cases` | 0.96 | 0.70 | 0.26 | Order exceptions, returns/refunds/replacements and operator workflow state. |
| `amazon_fba_customer_return_rows` | 0.78 | 0.59 | 0.19 | Raw and normalized rows from GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA. Return reason, disposition, status, LPN, and customer comments are preserved for Amazon Return Recovery evidence. |
| `provider_cost_line_items` | 0.69 | 0.39 | 0.30 | Normalized provider billing charges. |
| `amazon_report_runs` | 0.51 | 0.38 | 0.13 | Audit table for read-only Amazon SP-API report requests and imports. No Amazon seller order/customer data should be requested for MBOP inventory workflows. |
| `sourcing_blocked_asins` | 0.48 | 0.38 | 0.10 | Operator/restriction product blocks; preserved business protection. |
| `amazon_fba_reimbursement_rows` | 0.48 | 0.34 | 0.14 | Amazon reimbursement report evidence. |
| `revseller_import_rows` | 0.46 | 0.20 | 0.26 | Imported RevSeller catalog/price enrichment rows. |
| `inventorylab_active_inventory_backfill` | 0.40 | 0.25 | 0.15 | Historical InventoryLab active inventory backfill data. Stores legacy cost/date context separately from MBOP purchase_items. |
| `fba_shipments` | 0.39 | 0.30 | 0.09 | Amazon outbound shipment headers, progress and value. |
| `import_batches` | 0.37 | 0.28 | 0.09 | Source import provenance and processing summaries. |
| `sourcing_purchase_matches` | 0.33 | 0.27 | 0.05 | Links sourcing decisions/listings to imported buyer purchases. |
| `inventorylab_inventory_valuation_snapshots` | 0.28 | 0.16 | 0.13 | InventoryLab valuation export snapshots used as a legacy opening-balance valuation layer for current Amazon FBA inventory. This table does not update purchase_items. |
| `ynab_category_balance_snapshots` | 0.27 | 0.20 | 0.07 | Point-in-time read-only YNAB category balance snapshots. MBOP uses the Business category available balance as cash on hand. |
| `amazon_return_recovery_cases` | 0.22 | 0.07 | 0.15 | Amazon-side workflow cases for FBA customer returns and removals returned to the business. This table must not write to purchases, purchase_items, receiving, Order Problems, or FBA shipment prep workflow rows. |
| `amazon_catalog_item_identity_snapshots` | 0.19 | 0.16 | 0.03 | Cached read-only Amazon Catalog Items identity evidence for sourcing diagnostics. Exact-ASIN structured evidence is preferred over title inference. |
| `informed_report_runs` | 0.19 | 0.14 | 0.05 | Audit table for read-only Informed Repricer Reports API requests and imports. Signed download links are intentionally not persisted. |
| `amazon_fba_removal_shipment_detail_rows` | 0.19 | 0.05 | 0.13 | Amazon FBA removal shipment report evidence. |
| `provider_cost_sync_runs` | 0.19 | 0.10 | 0.09 | Billing/usage sync execution records. |
| `business_value_snapshots` | 0.19 | 0.14 | 0.05 | Daily backend-computed MBOP business value snapshots for trend reporting. Values are derived from existing inventory, Amazon Finance, and YNAB snapshot sources. |
| `amazon_inventory_cogs_layers` | 0.15 | 0.07 | 0.08 | Inventory cost layers consumed by sales COGS. |
| `fba_shipment_source_items` | 0.15 | 0.05 | 0.09 | Shipment source/cost allocation records. |
| `fba_shipment_events` | 0.15 | 0.10 | 0.05 | Amazon outbound shipment lifecycle/audit events. |
| `amazon_fba_removal_order_detail_rows` | 0.15 | 0.06 | 0.09 | Amazon removal-order report evidence. |
| `inventory_reconciliation_events` | 0.14 | 0.09 | 0.05 | Run-level reconciliation records comparing MBOP projected inventory positions to external inventory sources such as Amazon FBA snapshots. |
| `sourcing_opportunity_batches` | 0.14 | 0.08 | 0.06 | Durable sourcing opportunity batches used by the progressive Find 100 More workflow. |
| `supplier_returns` | 0.13 | 0.02 | 0.11 | Supplier-return operational records. |
| `inventory_movements` | 0.11 | 0.02 | 0.09 | Append-only audit trail for inventory state/location/marketplace transitions. Existing workflow tables still own their own transitions; this table records normalized inventory movement projections. |
| `sourcing_coverage_cycles` | 0.11 | 0.06 | 0.05 | Durable daily sourcing coverage-cycle header. One active cycle represents one pass through eligible ASINs. |
| `sourcing_sales_velocity_suppressions` | 0.10 | 0.05 | 0.05 | Dynamic ASIN-level suppression for valid products dismissed because sales velocity is too low. Suppression releases only when the current sourcing velocity threshold is met. |
| `mbop_purchase_ingestion_requests` | 0.10 | 0.07 | 0.03 | Idempotent ZFI-triggered purchase-ingestion requests/status. |
| `amazon_return_recovery_events` | 0.10 | 0.07 | 0.03 | Return-recovery operator/workflow audit. |
| `amazon_repricing_advisor_snoozes` | 0.08 | 0.02 | 0.06 | Operator snooze state for Aged Amazon Inventory recommendations. A snoozed SKU remains hidden from the default advisor list until snoozed_until. |
| `manual_item_matches` | 0.08 | 0.02 | 0.06 | Operator-corrected title/platform to ASIN match memory. |
| `scheduler_job_definitions` | 0.07 | 0.05 | 0.02 | Scheduler job definitions, cadence and freshness expectations. |
| `amazon_sales_fulfillment_cost_overrides` | 0.06 | 0.02 | 0.05 | Operator fulfillment-cost overrides used in profitability. |
| `informed_rule_name_overrides` | 0.06 | 0.02 | 0.05 | Manual display-name mapping for Informed Repricer strategy/rule IDs when report exports only provide numeric IDs. |
| `provider_billing_periods` | 0.06 | 0.02 | 0.05 | Billing-period metadata. |
| `sourcing_declined_ebay_offers` | 0.06 | 0.05 | 0.02 | Highest observed buyer-declined USD item offer per eBay listing. Absence from later API responses never clears evidence. Not a complete offer history. |
| `amazon_seller_feedback_snapshots` | 0.05 | 0.02 | 0.03 | Seller-feedback aggregate snapshots. |
| `amazon_account_health_snapshots` | 0.05 | 0.02 | 0.03 | Amazon account-health snapshots. |
| `sync_logs` | 0.05 | 0.02 | 0.03 | Integration execution logs. |
| `listings` | 0.04 | 0.01 | 0.03 | Legacy marketplace listing records; active usage requires verification. |
| `informed_rule_snapshots` | 0.04 | 0.01 | 0.03 | Point-in-time read-only Informed Repricer rule/settings report rows, populated only if a rule definition report is available. |
| `sourcing_cache_dirty` | 0.04 | 0.02 | 0.02 | Small transactional cache invalidation markers; not stored list payloads. |
| `return_reasons` | 0.03 | 0.02 | 0.02 | Return reason reference values. |
| `sourcing_settings` | 0.03 | 0.02 | 0.02 | Operator sourcing configuration and thresholds. |
| `inventory_locations` | 0.03 | 0.02 | 0.02 | Inventory location reference data. |
| `item_images` | 0.02 | 0.01 | 0.02 | Item image references/metadata. |
| `sourcing_cache_state` | 0.02 | 0.01 | 0.02 | Small committed-source revision for read caches. |
| `sales` | 0.02 | 0.01 | 0.02 | Legacy sales records; active usage requires verification. |
| `tracking_events` | 0.02 | 0.01 | 0.02 | Shipment tracking event history. |
| `keepa_product_history_points` | 0.02 | 0.01 | 0.02 | Optional normalized Keepa time-series points extracted from Keepa CSV history arrays. The raw Keepa payload remains stored on keepa_product_snapshots. |
| `amazon_seller_feedback_items` | 0.02 | 0.01 | 0.02 | Individual seller-feedback records. |
| `alerts` | 0.02 | 0.01 | 0.01 | Operational alerts; active usage requires verification. |
| `customer_returns` | 0.02 | 0.01 | 0.01 | Legacy customer-return records; separate from current Amazon report rows. |
| `fulfillment_shipments` | 0.02 | 0.01 | 0.01 | Legacy fulfillment shipment records; active usage requires verification. |
| `sourcing_ai_observations` | 0.02 | 0.01 | 0.01 | Advisory AI observations linked to sourcing opportunities. |
| `asin_metrics` | 0.02 | 0.01 | 0.01 | ASIN advisory metrics; active usage requires verification. |
| `item_condition_history` | 0.02 | 0.01 | 0.01 | Item condition history. |
| `scheduler_locks` | 0.02 | 0.01 | 0.01 | Scheduler concurrency leases/locks. |
| `profitability_snapshots` | 0.02 | 0.01 | 0.01 | Legacy profitability snapshots; active usage requires verification. |
| `scheduler_domain_freshness` | 0.02 | 0.01 | 0.01 | Scheduler domain freshness markers. |
| `amazon_inventory` | 0.02 | 0.01 | 0.01 | Legacy Amazon inventory structure; active usage requires verification. |

### MBOP / College Planner: college_planner

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `source_records` | 8.88 | 6.11 | 2.77 | Row- or document-level provenance for imported and manually confirmed records. |
| `course_sections` | 8.02 | 6.70 | 1.32 | Registration sections for a term offering; section restrictions are MVP columns/JSONB until detailed filtering requires a child table. |
| `course_offerings` | 3.97 | 3.08 | 0.89 | course offerings records (purpose inferred from schema). |
| `section_meetings` | 3.45 | 1.58 | 1.88 | section meetings records (purpose inferred from schema). |
| `courses` | 1.31 | 0.78 | 0.53 | Catalog courses; not semester offerings or registration sections. |
| `import_errors` | 0.42 | 0.37 | 0.05 | import errors records (purpose inferred from schema). |
| `subjects` | 0.12 | 0.07 | 0.05 | subjects records (purpose inferred from schema). |
| `planned_courses` | 0.11 | 0.09 | 0.02 | planned courses records (purpose inferred from schema). |
| `requirement_option_courses` | 0.10 | 0.05 | 0.05 | requirement option courses records (purpose inferred from schema). |
| `degree_requirement_options` | 0.08 | 0.05 | 0.03 | degree requirement options records (purpose inferred from schema). |
| `degree_plans` | 0.08 | 0.02 | 0.06 | degree plans records (purpose inferred from schema). |
| `academic_terms` | 0.07 | 0.02 | 0.05 | academic terms records (purpose inferred from schema). |
| `import_batches` | 0.06 | 0.02 | 0.05 | import batches records (purpose inferred from schema). |
| `student_profiles` | 0.06 | 0.02 | 0.05 | Private student planning profile owned by an application user. |
| `application_users` | 0.06 | 0.02 | 0.05 | Future Cognito-linked users for College Planner access control. |
| `degree_requirement_groups` | 0.06 | 0.02 | 0.05 | Flexible requirement areas for program, core, elective, recurring, and residency rules. |
| `degree_program_versions` | 0.06 | 0.02 | 0.05 | degree program versions records (purpose inferred from schema). |
| `term_parts` | 0.06 | 0.02 | 0.05 | term parts records (purpose inferred from schema). |
| `student_academic_records` | 0.06 | 0.02 | 0.05 | Private student coursework history, registrations, transfer credit, test credit, and planned placeholders if needed. |
| `academic_years` | 0.05 | 0.02 | 0.04 | academic years records (purpose inferred from schema). |
| `course_relationship_groups` | 0.05 | 0.02 | 0.03 | course relationship groups records (purpose inferred from schema). |
| `planned_terms` | 0.05 | 0.02 | 0.03 | planned terms records (purpose inferred from schema). |
| `core_curriculum_versions` | 0.05 | 0.02 | 0.03 | core curriculum versions records (purpose inferred from schema). |
| `degree_programs` | 0.05 | 0.02 | 0.03 | degree programs records (purpose inferred from schema). |
| `university_catalogs` | 0.05 | 0.02 | 0.03 | university catalogs records (purpose inferred from schema). |
| `universities` | 0.05 | 0.02 | 0.03 | universities records (purpose inferred from schema). |
| `student_programs` | 0.05 | 0.02 | 0.03 | student programs records (purpose inferred from schema). |
| `import_files` | 0.05 | 0.02 | 0.03 | import files records (purpose inferred from schema). |
| `requirement_option_tags` | 0.05 | 0.02 | 0.03 | requirement option tags records (purpose inferred from schema). |
| `confidence_levels` | 0.05 | 0.02 | 0.03 | confidence levels records (purpose inferred from schema). |
| `student_access_grants` | 0.04 | 0.01 | 0.03 | student access grants records (purpose inferred from schema). |
| `academic_record_statuses` | 0.03 | 0.02 | 0.02 | academic record statuses records (purpose inferred from schema). |
| `user_roles` | 0.03 | 0.02 | 0.02 | user roles records (purpose inferred from schema). |
| `delivery_methods` | 0.03 | 0.02 | 0.02 | delivery methods records (purpose inferred from schema). |
| `source_types` | 0.03 | 0.02 | 0.02 | source types records (purpose inferred from schema). |
| `plan_statuses` | 0.03 | 0.02 | 0.02 | plan statuses records (purpose inferred from schema). |
| `import_statuses` | 0.03 | 0.02 | 0.02 | import statuses records (purpose inferred from schema). |
| `course_relationship_options` | 0.03 | 0.02 | 0.02 | course relationship options records (purpose inferred from schema). |
| `course_aliases` | 0.02 | 0.01 | 0.02 | course aliases records (purpose inferred from schema). |
| `requirement_exceptions` | 0.02 | 0.01 | 0.01 | requirement exceptions records (purpose inferred from schema). |

### MBOP / College Planner: supabase_migrations

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `schema_migrations` | 0.15 | 0.13 | 0.02 | Shared schema migration history; never prune as data cleanup. |

### MBOP / College Planner: auth

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `users` | 0.13 | 0.01 | 0.12 | Supabase authentication/session/security infrastructure; keep managed. |
| `scim_users` | 0.09 | 0.01 | 0.08 | Supabase authentication/session/security infrastructure; keep managed. |
| `one_time_tokens` | 0.09 | 0.01 | 0.08 | Supabase authentication/session/security infrastructure; keep managed. |
| `refresh_tokens` | 0.06 | 0.01 | 0.05 | Supabase authentication/session/security infrastructure; keep managed. |
| `custom_oauth_providers` | 0.05 | 0.01 | 0.05 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_factors` | 0.05 | 0.01 | 0.05 | Supabase authentication/session/security infrastructure; keep managed. |
| `scim_tokens` | 0.05 | 0.01 | 0.04 | Supabase authentication/session/security infrastructure; keep managed. |
| `sessions` | 0.05 | 0.01 | 0.04 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_consents` | 0.05 | 0.01 | 0.04 | Supabase authentication/session/security infrastructure; keep managed. |
| `saml_relay_states` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `flow_state` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_authorizations` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `identities` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `sso_providers` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `sso_domains` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `webauthn_challenges` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `saml_providers` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `webauthn_credentials` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_recovery_codes` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `schema_migrations` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_challenges` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_amr_claims` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_recovery_code_sets` | 0.02 | 0.00 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `audit_log_entries` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_client_states` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_clients` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `instances` | 0.02 | 0.01 | 0.01 | Supabase authentication/session/security infrastructure; keep managed. |

### MBOP / College Planner: storage

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `objects` | 0.05 | 0.01 | 0.04 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `migrations` | 0.04 | 0.01 | 0.03 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `s3_multipart_uploads` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `vector_indexes` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets_analytics` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `s3_multipart_uploads_parts` | 0.02 | 0.01 | 0.01 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets_vectors` | 0.02 | 0.01 | 0.01 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |

### MBOP / College Planner: realtime

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `subscription` | 0.03 | 0.01 | 0.02 | Supabase Realtime infrastructure. |
| `schema_migrations` | 0.02 | 0.01 | 0.02 | Supabase Realtime infrastructure. |
| `messages` | 0.00 | 0.00 | 0.00 | Supabase Realtime infrastructure. |

### MBOP / College Planner: vault

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `secrets` | 0.02 | 0.01 | 0.02 | Encrypted secrets infrastructure; contents not read. |

### ZoltarFI: public

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `ynab_budget_category_snapshots` | 14.27 | 6.05 | 8.22 | ynab budget category snapshots records (purpose inferred from schema). |
| `transactions` | 9.22 | 5.64 | 3.58 | transactions records (purpose inferred from schema). |
| `ynab_raw_payloads` | 5.59 | 5.54 | 0.05 | ynab raw payloads records (purpose inferred from schema). |
| `plaid_investment_holdings` | 5.49 | 4.78 | 0.71 | plaid investment holdings records (purpose inferred from schema). |
| `mbop_business_summaries` | 3.68 | 1.08 | 2.60 | mbop business summaries records (purpose inferred from schema). |
| `budget_lines` | 1.88 | 1.11 | 0.77 | budget lines records (purpose inferred from schema). |
| `business_transaction_tax_assignments` | 1.87 | 1.38 | 0.48 | business transaction tax assignments records (purpose inferred from schema). |
| `account_balances` | 1.21 | 0.80 | 0.41 | account balances records (purpose inferred from schema). |
| `business_value_snapshots` | 0.89 | 0.33 | 0.56 | business value snapshots records (purpose inferred from schema). |
| `budget_plan_lines` | 0.83 | 0.45 | 0.38 | budget plan lines records (purpose inferred from schema). |
| `paystub_line_items` | 0.71 | 0.45 | 0.27 | paystub line items records (purpose inferred from schema). |
| `paystubs` | 0.55 | 0.48 | 0.07 | paystubs records (purpose inferred from schema). |
| `sync_runs` | 0.46 | 0.25 | 0.21 | sync runs records (purpose inferred from schema). |
| `rsu_withholding_lines` | 0.32 | 0.22 | 0.10 | rsu withholding lines records (purpose inferred from schema). |
| `plaid_liabilities` | 0.24 | 0.17 | 0.07 | plaid liabilities records (purpose inferred from schema). |
| `budget_variable_bill_candidates` | 0.23 | 0.14 | 0.09 | budget variable bill candidates records (purpose inferred from schema). |
| `ynab_budget_movements` | 0.22 | 0.15 | 0.07 | ynab budget movements records (purpose inferred from schema). |
| `manual_import_uploads` | 0.19 | 0.10 | 0.09 | manual import uploads records (purpose inferred from schema). |
| `rsu_vest_event_grants` | 0.18 | 0.13 | 0.05 | rsu vest event grants records (purpose inferred from schema). |
| `ynab_budget_snapshots` | 0.18 | 0.10 | 0.08 | ynab budget snapshots records (purpose inferred from schema). |
| `rsu_sales` | 0.16 | 0.11 | 0.05 | rsu sales records (purpose inferred from schema). |
| `recurring_plan_items` | 0.14 | 0.06 | 0.08 | recurring plan items records (purpose inferred from schema). |
| `transaction_splits` | 0.13 | 0.07 | 0.06 | transaction splits records (purpose inferred from schema). |
| `manual_liability_details` | 0.13 | 0.08 | 0.05 | manual liability details records (purpose inferred from schema). |
| `business_tax_category_rules` | 0.12 | 0.07 | 0.05 | business tax category rules records (purpose inferred from schema). |
| `manual_liability_statements` | 0.12 | 0.07 | 0.05 | manual liability statements records (purpose inferred from schema). |
| `budget_plan_months` | 0.11 | 0.05 | 0.06 | budget plan months records (purpose inferred from schema). |
| `financial_accounts` | 0.11 | 0.06 | 0.05 | financial accounts records (purpose inferred from schema). |
| `rsu_vest_events` | 0.10 | 0.05 | 0.05 | rsu vest events records (purpose inferred from schema). |
| `manual_liability_transactions` | 0.10 | 0.05 | 0.05 | manual liability transactions records (purpose inferred from schema). |
| `budget_category_planning_settings` | 0.09 | 0.05 | 0.05 | budget category planning settings records (purpose inferred from schema). |
| `data_sources` | 0.09 | 0.05 | 0.05 | data sources records (purpose inferred from schema). |
| `rsu_security_quotes` | 0.09 | 0.05 | 0.05 | rsu security quotes records (purpose inferred from schema). |
| `ynab_categories` | 0.09 | 0.06 | 0.03 | ynab categories records (purpose inferred from schema). |
| `budget_months` | 0.08 | 0.05 | 0.03 | budget months records (purpose inferred from schema). |
| `budget_variable_bill_providers` | 0.06 | 0.02 | 0.05 | budget variable bill providers records (purpose inferred from schema). |
| `budget_rta_checkpoints` | 0.06 | 0.02 | 0.05 | budget rta checkpoints records (purpose inferred from schema). |
| `budget_other_income_reviews` | 0.06 | 0.02 | 0.05 | budget other income reviews records (purpose inferred from schema). |
| `budget_income_detail_lines` | 0.06 | 0.02 | 0.05 | budget income detail lines records (purpose inferred from schema). |
| `rsu_grants` | 0.06 | 0.02 | 0.05 | rsu grants records (purpose inferred from schema). |
| `budget_month_closes` | 0.06 | 0.02 | 0.05 | budget month closes records (purpose inferred from schema). |
| `budget_variable_bill_provider_allocations` | 0.06 | 0.02 | 0.05 | budget variable bill provider allocations records (purpose inferred from schema). |
| `plaid_mapping_targets` | 0.06 | 0.02 | 0.05 | plaid mapping targets records (purpose inferred from schema). |
| `debt_actual_balance_points` | 0.06 | 0.02 | 0.05 | debt actual balance points records (purpose inferred from schema). |
| `plaid_items` | 0.06 | 0.02 | 0.05 | plaid items records (purpose inferred from schema). |
| `plaid_account_mappings` | 0.06 | 0.02 | 0.05 | plaid account mappings records (purpose inferred from schema). |
| `budget_income_captures` | 0.06 | 0.02 | 0.05 | budget income captures records (purpose inferred from schema). |
| `budget_bill_rules` | 0.05 | 0.02 | 0.03 | budget bill rules records (purpose inferred from schema). |
| `budget_scheduled_payments` | 0.05 | 0.02 | 0.03 | budget scheduled payments records (purpose inferred from schema). |
| `business_tax_categories` | 0.05 | 0.02 | 0.03 | business tax categories records (purpose inferred from schema). |
| `household_members` | 0.04 | 0.01 | 0.03 | household members records (purpose inferred from schema). |
| `schema_migrations` | 0.03 | 0.02 | 0.02 | schema migrations records (purpose inferred from schema). |
| `budget_lifecycle_months` | 0.03 | 0.01 | 0.02 | budget lifecycle months records (purpose inferred from schema). |
| `households` | 0.03 | 0.02 | 0.02 | households records (purpose inferred from schema). |
| `budget_month_close_adjustments` | 0.02 | 0.01 | 0.02 | budget month close adjustments records (purpose inferred from schema). |
| `review_items` | 0.02 | 0.01 | 0.02 | review items records (purpose inferred from schema). |
| `business_tax_classification_review_items` | 0.02 | 0.01 | 0.02 | business tax classification review items records (purpose inferred from schema). |
| `recurring_transactions` | 0.02 | 0.01 | 0.01 | recurring transactions records (purpose inferred from schema). |

### ZoltarFI: auth

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `users` | 0.21 | 0.02 | 0.20 | Supabase authentication/session/security infrastructure; keep managed. |
| `refresh_tokens` | 0.16 | 0.05 | 0.11 | Supabase authentication/session/security infrastructure; keep managed. |
| `sessions` | 0.13 | 0.05 | 0.08 | Supabase authentication/session/security infrastructure; keep managed. |
| `one_time_tokens` | 0.09 | 0.01 | 0.08 | Supabase authentication/session/security infrastructure; keep managed. |
| `identities` | 0.08 | 0.02 | 0.06 | Supabase authentication/session/security infrastructure; keep managed. |
| `flow_state` | 0.08 | 0.02 | 0.06 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_factors` | 0.05 | 0.01 | 0.05 | Supabase authentication/session/security infrastructure; keep managed. |
| `custom_oauth_providers` | 0.05 | 0.01 | 0.05 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_consents` | 0.05 | 0.01 | 0.04 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_amr_claims` | 0.05 | 0.02 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `saml_relay_states` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_authorizations` | 0.04 | 0.01 | 0.03 | Supabase authentication/session/security infrastructure; keep managed. |
| `webauthn_credentials` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `saml_providers` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `webauthn_challenges` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `sso_domains` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `sso_providers` | 0.03 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `audit_log_entries` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `mfa_challenges` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_client_states` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `schema_migrations` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `oauth_clients` | 0.02 | 0.01 | 0.02 | Supabase authentication/session/security infrastructure; keep managed. |
| `instances` | 0.02 | 0.01 | 0.01 | Supabase authentication/session/security infrastructure; keep managed. |

### ZoltarFI: storage

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `objects` | 0.05 | 0.01 | 0.04 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `migrations` | 0.04 | 0.01 | 0.03 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets_analytics` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `s3_multipart_uploads` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `vector_indexes` | 0.02 | 0.01 | 0.02 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `buckets_vectors` | 0.02 | 0.01 | 0.01 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |
| `s3_multipart_uploads_parts` | 0.02 | 0.01 | 0.01 | Supabase Storage object/bucket metadata; object bytes live outside PostgreSQL. |

### ZoltarFI: realtime

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `subscription` | 0.03 | 0.01 | 0.02 | Supabase Realtime infrastructure. |
| `schema_migrations` | 0.02 | 0.01 | 0.02 | Supabase Realtime infrastructure. |
| `messages` | 0.00 | 0.00 | 0.00 | Supabase Realtime infrastructure. |

### ZoltarFI: vault

| Table | Total MiB | Data/TOAST MiB | Index MiB | What it stores |
| --- | ---: | ---: | ---: | --- |
| `secrets` | 0.02 | 0.01 | 0.02 | Encrypted secrets infrastructure; contents not read. |

## Related evidence

- [Purchase/cache fixes and the two failed sourcing jobs](purchase_metrics_sourcing_fixes_2026-09-15.md)
- [Previous lossless finance payload archive](FINANCE_PAYLOAD_STORAGE_2026-09-10.md)
- [Capacity guardrails](supabase_capacity.md)
- [Shared MBOP/College Planner migration ownership](shared_supabase_migration_ownership.md)
- [ZFI ownership boundary](ZFI_INTEGRATION.md)

No database cleanup, personal-data extraction, scheduler change, provider search, marketplace write or sourcing rerun was performed for this assessment.

