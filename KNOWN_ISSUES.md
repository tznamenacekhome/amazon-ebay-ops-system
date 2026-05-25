# KNOWN_ISSUES.md

This file tracks active issues, monitor items, and deferred decisions for Midnight Blue Operations Platform (MBOP).

Last reviewed: 2026-05-25

# Active Issues

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
- Purchases Needs Review catches missing ASIN, invalid ASIN placeholder, missing target sell price, missing system, and missing Amazon title for ASIN-bearing rows.
- FBA displays Missing Amazon title instead of silently using the eBay title.
- manual corrections can propagate to matching title/system rows where safe.

Recommended guardrail:
- avoid treating `N/A` as a valid ASIN in future imports/backfills.
- keep Needs Review server-side so cancelled, return, listed, and reporting-excluded rows do not reappear in the review queue.

---

## Purchases Page Performance

Status: MITIGATED / MONITOR

Problem:
The purchases page became slow as the table grew and the frontend loaded, filtered, and sorted every purchase row.

Current mitigation:
- `/api/purchases` owns server-side filtering, sorting, pagination, and summary counts.
- default purchases filter is all statuses except Listed.
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
The first unified inventory reconciliation pass detects many open findings because Amazon FBA inventory contains SKUs/ASINs that are not yet mapped back to MBOP operational purchase items.

Current observed result:
- latest run projected 2,928 MBOP workflow positions
- latest run projected 311 Amazon FBA inventory positions
- latest run created 799 open reconciliation findings
- 310 Amazon positions now carry InventoryLab legacy cost/date context after the active-inventory backfill

Impact:
The dashboard now surfaces inventory visibility gaps, but the initial open-finding count should be treated as a work queue for mapping and confidence-building rather than as a clean defect count.

Current mitigation:
- findings are stored in `inventory_reconciliation_event_items`
- old open findings are deferred when a new reconciliation run is created
- dashboard Inventory Visibility shows open finding counts and top rows
- reconciliation is ASIN-level only for the first slice

Recommended next mitigation:
- add SKU-to-purchase/ASIN mapping review tools.
- incorporate Amazon listing/suppression/stranded signals once SP-API listing reads are expanded.
- add future eBay inventory positions before attempting Amazon-to-eBay transfer reconciliation.
- keep the reconciliation layer read/project first, then route corrections through the owning workflow.

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
- `run_all_syncs.py` now includes eBay buyer purchase sync, EasyPost shipment sync, supplier returns sync, and RevSeller enrichment.
- direct run validation wrote a successful exit code 0 to `logs/scheduler.log`.
- the stale OneDrive working-directory problem has been replaced by AM/PM scheduled tasks that target the `C:\Dev` path.

Recommended guardrail:
- confirm both scheduled tasks append successful runs to `logs/scheduler.log`.
- use the root scheduled-task path when manually triggering, for example `schtasks /Run /TN "\Amazon eBay Ops Sync PM"`.
- keep public EasyPost webhooks on the roadmap so the scheduler is not the only long-term carrier-update mechanism.

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
