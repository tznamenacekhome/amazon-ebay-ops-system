# KNOWN_ISSUES.md

This file tracks active issues, monitor items, and deferred decisions for Midnight Blue Operations Platform (MBOP).

Last reviewed: 2026-06-07

# Active Issues

## Dashboard Remaining MVP Gaps

Status: ACTIVE / MONITORING

Problem:
The dashboard split now has live monitoring tabs for Overview, Financial,
Operations, Inventory, Amazon, Growth, Sourcing, Loss Prevention, and System
Health, but a few pieces are intentionally MVP-level.

Current gaps:
- Some dashboard drill-downs open the owning workflow base route because the
  target page does not yet support the exact requested filter.
- System Health does not automatically query Supabase capacity/disk IO metrics;
  this avoids heavy diagnostics and secret exposure, but means capacity fields
  remain guarded placeholders until a safe source exists.
- Sourcing uses transparent local scoring from existing sales/profit/inventory
  data. It is a manual research queue, not a full sourcing engine.
- Loss Prevention estimated value at risk is approximate where expected refund
  amount is unavailable and falls back to purchase item cost.

Recommended next mitigation:
- Add filter support to owning workflow pages before deep-linking to specific
  dashboard slices.
- Add a safe lightweight capacity source or operator-entered capacity status if
  Supabase exposes plan/IO data without heavy queries.

---

## Scheduled Sync Scope Needs Optimization

Status: MITIGATED / MONITOR

Problem:
The local scheduled runs have grown organically and now sync more domains than
need the same cadence. Some jobs are valuable once or twice per day, while other
data can be refreshed less often or only on demand. Running unnecessary jobs
consumes external API quota, increases Supabase IO/load, lengthens scheduler
runs, and can make troubleshooting harder when an unrelated sync fails.

Current mitigation:
- `run_all_syncs.py` supports grouped core/daily runs, disabled jobs, and
  per-job runtime logging.
- eBay buyer purchases, EasyPost tracking, order-problem return sync,
  RevSeller enrichment, YNAB business transactions, and Amazon sales finance
  syncs have been narrowed toward incremental or missing-data work where the
  integration supports it.
- Windows scheduled MBOP tasks have `MultipleInstances=IgnoreNew` and
  `StartWhenAvailable=False` so laptop wake-up does not stack missed scheduled
  runs.
- scheduler output writes through a per-run temp log and appends to
  `logs/scheduler.log` with retry handling to avoid file-lock collisions.
- screen refresh buttons can run screen-specific scheduled-style refreshes
  without historical backfill.
- legacy supplier returns sync remains disabled while the new Order Problems
  return sync is validated.

Recommended next mitigation:
- Keep jobs that feed the same calculation, such as Business Inventory And Cash
  Value, on the same cadence so freshness indicators stay meaningful.
- Avoid scheduling exploratory/backfill-style syncs; keep those manual and
  resumable.
- Continue moving long-polling tracking updates toward EasyPost webhooks once a
  public HTTPS endpoint exists.

---

## Amazon Orders And Inventory Missing Data

Status: ACTIVE

Problem:
Amazon Sales Orders and Amazon inventory are now substantially backfilled, but
the operating dataset still has a small set of missing order profitability data
and a larger inventory-confidence queue.

Current observed counts as of 2026-06-02:
- 159 Amazon sales profitability rows are still `missing_cogs`.
- 32 Amazon sales profitability rows are still stored as `missing_fees`; the UI
  displays unfulfilled rows as `Pending` and no-charge rows as `Replacement`
  where the API can identify those cases.
- 0 Amazon sales profitability rows are currently
  `missing_fulfillment_cost`.
- 454 inventory reconciliation findings remain open:
  - 253 `amazon_unknown_to_mbop`
  - 126 `amazon_stranded_or_suppressed`
  - 42 `quantity_mismatch`
  - 18 `amazon_reserved`
  - 8 `amazon_unsellable`
  - 7 `amazon_inbound_discrepancy`

Impact:
- Sales Orders profitability is not fully complete until remaining COGS and
  fee exceptions are resolved or classified.
- Inventory value and tax-close confidence depends on resolving or explicitly
  classifying remaining open reconciliation findings.

Current mitigation:
- Amazon order sync/backfill is limited to the 2025-forward operating window.
- eBay and non-eBay FIFO allocators have been run after the 2025 Amazon order
  backfill.
- `exports/missing_amazon_cogs_review.csv` is the current review artifact for
  remaining COGS exceptions.
- `integrations/inventory_source_balance_audit.py` provides a secondary
  purchase-source balance control and should be rerun after COGS/import fixes.
- Reconciliation findings are treated as investigation prompts; corrections
  should route through the owning workflow instead of editing derived
  reconciliation rows.

Recommended next mitigation:
- Continue filling missing purchase-source data for Amazon sales COGS,
  prioritizing non-game/eBay rows and quantity-short ASINs.
- Re-run eBay/non-eBay FIFO allocators after adding purchase source records.
- Re-run inventory reconciliation and Inventory Source Balance Audit after each
  meaningful COGS/import correction batch.
- Split future Amazon-side cleanup into first-class workflows for removals and
  inventory discrepancies instead of treating normal reserved/inbound movement
  as purchase cleanup.

---

## Remaining Item Data Completeness Gaps

Status: RESOLVED / MONITOR

Problem:
Most ASIN, sell-price, title, and system gaps have been resolved, but a small set of active non-listed rows still need cleanup before workflows are fully smooth.

Current live counts after the 2026-05-25 clarification cleanup, manual game ASIN fixes, and non-resale exclusion SQL:
- missing ASIN or ASIN placeholder `N/A`: 0 active reportable rows
- missing target sell price: 0
- missing Amazon title while ASIN exists: 0
- missing system: 0

Resolved rows:
- `Delighting in the Lord Terry Briley 2015 Christian Faith Hardcover`, order `25-13638-84763`: confirmed non-resale and excluded.
- `5 Pack Starbucks Reusable Venti 24 OZ Frosted Ice Cold Cup With Lid & Straw`, order `01-13685-25998`: confirmed non-resale and excluded.

Current mitigation:
- purchase detail drawer can edit Amazon title, system, ASIN, purchase price, and target sell price.
- Purchases Missing Data catches missing ASIN, invalid ASIN placeholder, missing target sell price, missing system, and missing Amazon title for ASIN-bearing rows.
- FBA displays Missing Amazon title instead of silently using the eBay title.
- manual corrections can propagate to matching title/system rows where safe.

Recommended guardrail:
- avoid treating `N/A` as a valid ASIN in future imports/backfills.
- keep Missing Data server-side so cancelled, return, listed, and reporting-excluded rows do not reappear in the review queue.

---

## Purchases Page Performance

Status: MITIGATED / MONITOR

Problem:
The purchases page became slow as the table grew and the frontend loaded, filtered, and sorted every purchase row.

Current mitigation:
- `/api/purchases` owns server-side filtering, sorting, pagination, and summary counts.
- default purchases filter is Open Purchase Work: Listed, Cancelled, Return
  Opened, and Return Pending rows are excluded.
- reporting-excluded rows are excluded before database pagination.
- query-aware browser cache support exists but is temporarily disabled while server-side performance is validated.
- Refresh clears any purchases cache entries and reloads from `/api/purchases`.
- detail-only metadata is hydrated only for returned page rows.

Recommended guardrail:
- monitor the page as new monthly volume grows.
- add database indexes or a dedicated lean reporting view if server queries become slow.
- defer TanStack Table until richer table interactions are needed; it is not required for the current performance bottleneck.

---

## RevSeller Matching Ambiguity

Status: ACTIVE / MITIGATED

Problem:
Same game titles exist across multiple systems.

Risks:
- incorrect ASIN assignment
- incorrect sell price enrichment

Current mitigation:
- backend system detection has been centralized.
- eBay import/sync populates `purchase_items.system` from recognized title terms.
- RevSeller enrichment requires system-aware matching before ASIN assignment.
- RevSeller enrichment now scans only Open Purchase Work rows and skips
  reporting-excluded rows, matching the default Purchases list boundary.
- optional OpenAI structured-output review can handle deterministic misses by
  choosing from same-system RevSeller candidates only; it cannot invent ASINs
  and writes AI match diagnostics for audit.
- matched Amazon/RevSeller title is stored separately from the eBay supplier title.
- shared marketplace-title cleaning runs before RevSeller normalized matching.
- legacy Purchases sheet backfill and ASIN validation resolved most historical gaps.
- purchase detail drawer allows system correction from the canonical pick list.

Recommended next mitigation:
- build an explicit ASIN review workflow in the purchases UI.
- surface system/platform prominently.
- rely on backend-provided matching diagnostics and confidence.
- never infer matching confidence in the frontend.

---

## Amazon Inventory Reconciliation Mapping Noise

Status: ACTIVE / EXPECTED FIRST-PASS NOISE

Problem:
The first unified inventory reconciliation pass detects many open findings while MBOP separates current Amazon FBA inventory from historical purchase/listing records and future eBay inventory states.

Current observed result:
- latest run projected 2,923 MBOP workflow positions
- latest run projected 311 Amazon FBA inventory positions
- latest run created 377 open reconciliation findings after adding Amazon listing-status issue visibility
- 55 open findings are Amazon stranded/suppressed-style listing findings from read-only Listings Items snapshots
- 310 Amazon positions now carry InventoryLab legacy cost/date context after the active-inventory backfill

Impact:
The dashboard now surfaces inventory visibility gaps, but the initial open-finding count should be treated as a work queue for mapping and confidence-building rather than as a clean defect count.

Current mitigation:
- findings are stored in `inventory_reconciliation_event_items`
- old open findings are deferred when a new reconciliation run is created
- dashboard Inventory Visibility shows open finding counts and top rows
- reconciliation is ASIN-level only for the first slice
- Amazon listing status and issue data is stored separately in `amazon_listing_snapshots` and does not write to purchases or purchase_items

Recommended next mitigation:
- use ASIN as the primary MBOP product identity for Amazon inventory reconciliation.
- keep MSKU/Seller SKU as Amazon traceability, not as a required MBOP inventory identity layer.
- review Amazon listing/suppression/stranded findings and decide which should become operator workflows.
- add future eBay inventory positions before attempting Amazon-to-eBay transfer reconciliation.
- keep the reconciliation layer read/project first, then route corrections through the owning workflow.

---

## Repricing Advisor Data Coverage Gaps

Status: ACTIVE / IMPROVED WITH AUTOMATED REFRESH AND PRICING BUCKETS

Problem:
The aged Amazon inventory repricing advisor is useful as a manual work queue, but many active Amazon rows still lack enough Keepa/Informed/cost context for confident pricing recommendations.

Current observed result:
- Amazon FBA Inventory Planning report import provides Amazon-native age buckets for active FBA inventory.
- latest all-sync run inserted 295 planning rows and 968 Informed listing snapshots.
- Keepa backfill and scheduled stale-ASIN refresh have substantially reduced missing active-Amazon Keepa coverage, but offer-level competition detail still depends on snapshots captured with `--offers` and `--stock`.
- scheduled Keepa refresh now caps each run, selects stale active-Amazon ASINs first, and skips calls when tokens are below the configured floor.
- Informed `All_Fields_NextGen` report provides repricer rule/price/current-velocity context where seller SKU matches.
- the current Informed report did not include ASIN-shaped values, so matching is by seller SKU for this first slice.
- the current Informed report exposes numeric strategy IDs rather than friendly rule names; `informed_rule_name_overrides` provides the operator-facing display names.
- Amazon FBA inventory detail quantities are now normalized for reserved customer order, FC transfer, FC processing, future supply, researching, and unfulfillable breakdowns.
- the advisor now separates rows into Pricing, Inventory / Listing Issue, and Missing Data buckets.
- buyable/discoverable listings with Amazon catalog metadata issues are ignored because the operator only cares when inventory becomes suppressed/non-buyable or unsellable.
- current bucket counts should be treated as live dashboard/API output because snoozes, Informed velocity, and Keepa refreshes now change the action list frequently.
- Pricing rows now receive a backend-generated manual target price using controlled markdowns against Buy Box/reference price while preserving a cost + 10% floor.
- Informed `current-velocity` is the temporary sales-velocity source for repricing decisions; Amazon planning shipped-unit fields remain stored but are not trusted as the operator's actual sales velocity.
- InventoryLab/MBOP purchase dates are fallback age context only when Amazon planning data is missing.
- competition drawer rows depend on Keepa snapshots captured with offer-level data; snapshots captured without offers can only show summary competition context.

Impact:
Rows with missing cost, pricing, Keepa, Informed, or sales context cannot safely produce fully confident repricing-floor recommendations. Pricing-bucket target prices are first-pass advisory values and should be reviewed manually before changing Informed floors or Seller Central prices.

Current mitigation:
- `/api/amazon/repricing-advisor` marks incomplete rows as Needs Data.
- `/repricing` includes filters for Missing Data and No Keepa Data.
- Amazon Inventory Planning age buckets are now preferred over purchase-date age for active Amazon FBA inventory.
- Informed report snapshots are used to flag stale inventory where repricing is disabled, price is above Buy Box, min price appears above Buy Box, or rule assignment is missing.
- FC transfer and normal inbound movement are displayed as detail, not treated as action issues by themselves.
- aged sellable inventory without listing issues is kept in the Pricing bucket instead of being treated as removal/eBay work.
- sell-through signal keeps moving inventory from getting overly aggressive markdowns while still prioritizing high-capital stale inventory.
- rows with any Informed sales in the last 30 days are excluded from the aged inventory action list even when Amazon planning age is over 90 days.
- Keepa sync has `--plan-only`, `--missing-only`, `--stale-days`, `--min-tokens`, dry-run default, and staged write support.

Recommended next mitigation:
- monitor scheduled Keepa stale refreshes and run targeted Keepa sync with offer detail for high-capital aged ASINs before deep competitor review.
- add Amazon Product Pricing sync if current/list prices remain sparse.
- keep manual Informed rule-name overrides current unless another Informed report exposes friendly rule names.
- use Amazon planning data for a while before deciding whether ledger-level available-for-sale inference is worth the complexity.

---

## Legacy Spreadsheet Import Missing Order Dates

Status: ACTIVE

Problem:
Many historical spreadsheet-imported purchases have `purchases.order_date = null`, even though their stored raw import JSON contains `Purchased Date`.

Current observed count after `sql/2026-05-25_known_issue_data_cleanup.sql`:
- 0 purchases with null `order_date`

Impact:
- date-based queries can miss or mis-order historical purchases.
- future received/listed/analytics drill-downs may not sort legacy rows correctly.

Current mitigation:
- one-time backfill parsed `raw_import_json -> Purchased Date` and wrote `purchases.order_date`.
- parser was limited to rows with valid legacy spreadsheet-style `Purchased Date` values.

Recommended next mitigation:
- treat as monitor item if dashboard/monthly totals continue to look correct.

---

## Multi-Item Partial Refund Allocation

Status: ACTIVE / FUTURE WORKFLOW

Problem:
Single-item partial refunds can be safely applied to purchase item cost, but multi-item partial refunds may apply to only one line or quantity and should not be automatically spread across unrelated items.

Current mitigation:
- eBay buyer purchase sync applies net payment/refund totals only for single-item partial refunds.
- item-level manual cost corrections set `manual_unit_cost_override = true`.

Recommended next mitigation:
- model refunds explicitly in the future Return and Refund workflow.
- record refund amount, refund date, source, and affected purchase item or quantity.
- use refund records to adjust item cost or reporting intentionally.

---

## EasyPost FedEx Tracking Credentials

Status: ACTIVE / EXTERNAL

Problem:
Two FedEx tracking numbers from the 2026-05-01+ backfill failed in EasyPost with "Credentials not found for the specified carrier", even when retried without passing carrier.

Affected orders:
- `06-14656-35281`, tracking `381367337613`, order date `2026-05-17`
- `27-14629-25992`, tracking `381418656302`, order date `2026-05-18`

Risk:
FedEx shipments may remain at unknown or awaiting-carrier status unless EasyPost FedEx credentials are configured or a separate FedEx/direct-carrier path is added.

Recommended next mitigation:
- verify FedEx tracking support/credentials in the EasyPost account.
- decide whether to configure FedEx credentials in EasyPost or add a carrier-direct fallback later.

---

## EasyPost Webhook Requires Public HTTPS Hosting

Status: ACTIVE / EXTERNAL

Problem:
The webhook route exists locally, but EasyPost cannot deliver production webhooks to localhost.

Risk:
Until the app is deployed publicly and registered with EasyPost, tracking updates still require running the sync script manually or on a scheduler.

Recommended next mitigation:
- deploy the Next.js app to a public HTTPS server.
- configure `EASYPOST_WEBHOOK_SECRET`.
- register `/api/easypost/webhook` in EasyPost.
- test webhook HMAC validation with a real EasyPost event.

---

## Local Windows Scheduler Validation

Status: MONITOR

Problem:
The repo moved from a OneDrive path to `C:\Dev\amazon-ebay-ops-system`, so the local Windows scheduled tasks had to be recreated with the new batch path.

Current mitigation:
- `run_all_syncs.bat` runs successfully when launched directly from the repo.
- `run_all_syncs.bat` writes to a per-run temp log and then appends to
  `logs/scheduler.log` with retries to avoid transient Windows file-lock
  failures.
- `run_all_syncs.py` now includes eBay buyer purchase sync, EasyPost shipment sync, RevSeller enrichment, Amazon FBA inventory, Amazon listing status, Amazon inventory planning, Amazon Finance, Informed reports, YNAB cash balance, guarded Keepa refresh, and business value snapshot.
- legacy supplier returns sync remains disabled while the new Order Problems
  return sync is validated.
- direct full-orchestrator validation completed with exit code 0.
- the stale OneDrive working-directory problem has been replaced by AM, PM,
  Daily, and Catalog scheduled tasks that target the `C:\Dev` path.
- all MBOP scheduled tasks have Task Scheduler catch-up disabled
  (`StartWhenAvailable = False`) and overlap handling set to
  `MultipleInstances = IgnoreNew`.

Recommended guardrail:
- monitor the next scheduled runs to confirm laptop sleep no longer causes
  missed runs to replay together on wake.
- use the root scheduled-task path when manually triggering, for example `schtasks /Run /TN "\Amazon eBay Ops Sync PM"`.
- keep public EasyPost webhooks on the roadmap so the scheduler is not the only long-term carrier-update mechanism.

---

## Order Problems eBay Return Sync Needs Live Validation

Status: ACTIVE / NEW WORKFLOW

Problem:
The new Order Problems workflow has a read-only eBay Post-Order return sync, but
it has not yet been validated against live eBay return/case data or scheduled.

Risk:
Operator-entered local workflow state is available now, but eBay status/deadline
automation may be incomplete until live return payloads confirm buyer-side
Post-Order API fields and scopes.

Current mitigation:
- old supplier returns data was cleared and the legacy supplier returns sync is
  disabled.
- `integrations/ebay_sync_order_problem_returns.py` is read-only and writes only
  to `order_problem_cases` and `order_problem_events`.
- marketplace actions still happen manually on ebay.com.

Recommended next mitigation:
- run the new sync in dry-run mode against known open eBay returns.
- inspect mapped return IDs, statuses, due dates, action URLs, refund amounts,
  and raw JSON.
- only add the new sync to scheduled groups after mapping is validated.

---

## System Health Signal Gaps

Status: MITIGATED / MONITOR

Problem:
The System Health page previously did not reliably report every sync after direct `run_all_syncs.py` runs because some checks depended on schema fields or snapshot semantics that did not match the current database.

Current mitigation:
- Amazon FBA inventory, Amazon listing status, Amazon inventory planning, Informed repricing reports, and YNAB cash balance updated correctly from Supabase signal tables.
- eBay buyer purchases now uses `import_batches.imported_at`.
- RevSeller enrichment now uses the latest local `data/revseller_enrichment_diagnostics_*.csv` file as its run signal.
- EasyPost shipments and eBay supplier returns ignore null timestamp rows when selecting their latest signal.
- Keepa products can remain on the previous snapshot timestamp when the guarded scheduled run selects 0 ASINs and writes no new snapshot rows.
- `run_all_syncs.py` now writes `logs/sync_health.json`, so direct orchestrator runs can overlay a newer success/failure when a domain table does not write a fresh row.
- Business value snapshot upserts now refresh `captured_at`.
- Inventory reconciliation is now included in `run_all_syncs.py` so its health expectation matches the orchestrator.

Impact:
The health page is less likely to make completed syncs look stale or unknown when the underlying integration ran successfully.

Recommended next mitigation:
- monitor the next scheduled/direct all-sync to confirm Keepa and business value use `logs/sync_health.json` when no newer product snapshot is written.
- consider a future Supabase sync-run ledger if local-only health records become insufficient.

---

## Legacy Multi-Row Purchase Shape

Status: ACTIVE / LOW RISK

Problem:
Some historical multi-game eBay listings were imported from the legacy spreadsheet as duplicate purchases with one purchase_item each instead of one purchase with multiple purchase_items.

Examples:
- order `04-14542-23405` currently exists as two purchase records with the same eBay order ID.
- order `08-14527-65268` had duplicate excluded item rows; the extra excluded rows were removed in the 2026-05-25 cleanup.

Current mitigation:
- manual split item support can represent multi-game listings as multiple purchase_items under one purchase going forward.
- eBay sync preserves manual item overrides and skips manual split child rows during fallback matching.

Recommended next mitigation:
- decide whether historical duplicate purchases should be merged into one purchase with multiple purchase_items.
- avoid bulk merging until receiving, inbound shipment, and FBA shipment side effects are reviewed.

---

## Receiving eBay Listing Images

Status: DECISION PENDING

Problem:
The sampled stored eBay buyer purchase payloads do not include listing image or gallery fields.

Impact:
The receiving detail view has a requirement for main eBay listing image, but the first receiving slice cannot display it from existing stored data.

Current mitigation:
- receiving detail links the eBay title to the eBay listing using supplier listing URL, supplier SKU, or raw eBay ItemID.
- eBay buyer sync stores supplier listing URLs from transaction ItemID going forward.
- listing links are not the same as image URLs.

Options:
- add an eBay item-detail lookup during purchase sync or a backfill and store the primary image URL on purchase_items.
- add a receiving-only eBay item lookup when opening detail.
- defer images until receiving scan/save behavior is validated.

# Monitor Items

## Amazon Sales Missing COGS Needs Ongoing Source Cleanup

Status: ACTIVE / POST-FIFO CLEANUP

Problem:
The Sales Orders page still has a smaller set of Amazon sales rows with missing
COGS after the 2025-forward Amazon order backfill and broad FIFO allocation.
Remaining exceptions generally need missing purchase-source rows, corrected
ASIN/quantity/cost, or explicit classification.

Current analysis:
- current review export: `exports/missing_amazon_cogs_review.csv`
- broad eBay and non-eBay FIFO allocators have already been run after the 2025
  sales-order backfill.
- targeted legacy-listed FIFO cleanup on 2026-06-04 marked three old source
  orders as Listed and applied 25 additional Amazon sales COGS rows.
- the eBay FIFO allocator can now include explicitly Listed legacy
  purchase-item lots from non-eBay suppliers, which keeps old resale source
  records out of Purchases open work while still allowing them to support COGS.

Current blocker:
- remaining rows need source-data cleanup or classification, not another broad
  historical order backfill.

Recommended next step:
- rerun the missing COGS review export
- manually review only the remaining exception buckets:
  - no purchase ASIN match
  - purchase quantity short
  - purchase rows missing cost

---

## eBay Seller Orders In Purchases

Status: RESOLVED / MONITOR

Resolution:
- removed 50 seller orders from purchases.
- removed their 50 purchase_items.
- verified no seller-style eBay payloads remain in purchases.
- disabled `integrations/ebay_sync_orders.py` from writing seller orders to purchases.

Guardrail:
Future eBay seller-order functionality must use separate tables/workflows and must not write to purchases or purchase_items.

---

## page.tsx Monolith

Status: RESOLVED / MONITOR

Resolution:
- extracted purchases table.
- extracted detail drawer.
- extracted editable price cell.
- extracted filter bar.
- extracted metrics.
- moved purchase API state into `usePurchases`.
- moved filtering into `usePurchaseFilters`.
- moved metric calculation into `purchaseStats`.

Recommended guardrail:
Keep `web/app/page.tsx` focused on composition and UI-local workflow state.

---

## Reference Spreadsheet ASIN Mismatches

Status: RESOLVED / MONITOR

Current validation:
- script: `integrations/validate_asins_against_purchase_sheet.py`
- cleanup script: `integrations/apply_sheet_asin_validation_fixes.py`
- spreadsheet ASINs were treated as authoritative when MBOP conflicted or was blank.
- 31 purchase item ASINs were corrected from the spreadsheet.
- latest report: `data/asin_validation_20260524_201926.csv`
- 2,825 of 2,825 compared orders matched exactly.

Recommended guardrail:
- rerun the validator after future ASIN enrichment or large manual correction passes.
- keep the cleanup script as a controlled spreadsheet-authoritative repair path.

---

## Dashboard / Legacy Spreadsheet Variance

Status: MOSTLY RESOLVED / MONITOR

Current reconciliation:
- 2024 and 2025 match the legacy Excel pivot exactly.
- 2026-05-16+ purchases are MBOP-canonical because the legacy spreadsheet was no longer maintained for new purchases.
- a prior exclusion of 13 post-2026-05-15 MBOP-only resale rows was reversed.
- no after-2026-05-15 MBOP-only rows were found on the Returns tab during the original check.
- 39 2026 MBOP-active rows found on the legacy Returns tab were normalized: 26 Return Opened and 13 Cancelled.
- one-time cleanup corrected duplicate rows, split-row quantities, partial-return quantities, one returned/refunded spreadsheet-missing order, one single-item partial refund, and three CAD purchase costs.
- active unit count now matches the legacy pivot exactly: 4,806 units.
- active cost is $84,840.36 in MBOP versus $84,836.31 in the legacy pivot, leaving a $4.05 MBOP-over-spreadsheet variance.
- the remaining small cost variance is currently treated as legacy spreadsheet error unless new evidence appears.
- order `16-14113-30387` had historical zero-cost NBA 2K22 rows that were excluded from reporting after corrected received quantities were confirmed.
- order `19-14476-44107` is a confirmed personal Tommy Bahama shirt purchase.
- order `11-14441-71152` is a confirmed business supply padded-mailer purchase, not resale inventory.

Recommended guardrail:
- create a repeatable reconciliation report that classifies differences as MBOP-only, spreadsheet-only, Returns-tab, and same-order amount/quantity mismatch.
- treat purchases on or after 2026-05-16 as MBOP-canonical instead of spreadsheet-missing discrepancies.
- keep partial refunds and foreign-currency examples in regression checks for future eBay sync changes.
