# Amazon-backed MF Inventory and Orders release — November 7, 2026

## Delivered behavior

MF Inventory and MF Orders are available through the existing AppShell and API architecture. Amazon offers remain distinct from physical stock. The MF lot ledger retains listing-batch, purchase-item, receipt and acquisition-cost lineage; counted openings can have unknown cost without creating a purchase. FIFO allocations use exact seller/marketplace/MSKU/ASIN/condition and original acquisition chronology.

Unshipped quantities reserve stock; cancellations release the unshipped demand. Cumulative fulfillment increases create immutable shipment effects once. Historical order baselines, out-of-order observations, equal-time conflicts and quantity regressions remain explicit. Refunds have no restocking path. First-seen pre-tracking fulfilled orders cannot consume newly counted stock merely because Amazon updated the order later; ambiguous timing is flagged.

Keep MF is persistent per offer. The reviewed Tilly Tacker ASIN B092FLB415 defaults to Keep MF, as does an exact structured Tilly Tackers brand. Operator choices are never overwritten by default seeding. No location field, Amazon write, shipping-label purchase, return receipt, transfer execution or report-upload workflow was added.

## Deployed artifacts

- Web task: `mbop-web-task:208`; build `7e5103bc9a09`.
- Web image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:97c5dad0fb33304b5346a63a60afb6b407ef997db661420cd0c4ed9dfe77ba00`.
- Final ECS rollout: PRIMARY COMPLETED, desired 1 / running 1 / pending 0.
- Scheduler task: `mbop-scheduler-task:159`.
- Scheduler image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:01920630e3c1fddab23dfc45e9a312f6f0e2375e44a6fba73d1ff5c8d2e1d439`.
- Implemented through the existing repository Dockerfiles and ECR → ECS rollout. Temporary ECR authentication avoided the existing Windows Docker credential-helper issue; token files were removed after push.

## Database and permissions

Verified project: `amazon-ebay-ops` / `froeucjkcepuhgwisped`, ACTIVE_HEALTHY, PostgreSQL 17.

Applied through the repository's linked CLI workflow after full shared-ledger reconciliation and dry runs:

- `20261108042001_mbop_mf_inventory_orders.sql`
- `20261108044257_mbop_mf_historical_order_baseline.sql`

The initial first-file push rejected a UTF-8 marker before statement execution; it was corrected and committed while still unapplied. Both migrations were subsequently verified in the remote ledger. The CLI's existing pg-delta catalog-cache certificate warning occurred after successful pushes; no direct schema application or ledger repair was used. Prior applied migration files and College Planner objects were not changed.

All MF tables have RLS; anonymous table access is revoked. Security advisors reported the expected RLS-without-client-policies notices for these intentionally server-only tables. Privileged functions use invoker security and server-role-only execution. Views use security_invoker. Existing IAM/authentication, LWA secrets, database service-role access and scheduler networking were reused.

Both bounded local permission probes and the actual production ECS sync succeeded for Orders API v2026-01-01 MF fulfillment and Listings Items discovery. No missing Amazon permissions/configuration were found. No BUYER, RECIPIENT or PACKAGES datasets were requested. [Official interface references and operational details](../mf_inventory_orders.md).

## Production synchronization

Initial MF-only task: `a793d9155a1d4f919868df3227264a7c`, scheduler task `mbop-scheduler-task:159`, exited 0.

- Started: 2026-11-08 04:36:18 UTC.
- Completed: 2026-11-08 04:37:01 UTC.
- 9 recent Amazon MF orders / 9 order items.
- 129 MF offers; Amazon listed quantities totaled 20 units.
- Tilly MSKU `1056546450` / ASIN B092FLB415: Amazon-listed quantity 12, Keep MF=true from reviewed identifier.
- No counted opening or physical MF stock lot was created from Amazon quantity snapshots.

The existing database guard passed before discovery: available RAM 1,556,803,584 bytes, free disk 18,048,839,680 bytes, swap free 536,920,064 bytes, PostgreSQL up and tiny read successful. The guard does not measure remaining Disk IO Budget. Discovery was bounded; no full orchestration or historical all-order backfill was launched.

Authenticated browser **Refresh from Amazon** launched a second MF-only task through the existing refresh API. Its sync ran 2026-11-08 04:46:12–04:46:50 UTC and completed without errors, rereading 129 offers and finding no newly updated customer orders/items. Last-success information advanced in the live view. Stock was not added by refresh.

Only existing schedule targets changed to task 159:

- `mbop-amazon-sales-recent-day`: preserved `cron(50 7,9,11,13,15,17,19,21 ? * * *)`, America/Los_Angeles.
- `mbop-amazon-sales-recent-catchup`: preserved `cron(30 4 ? * * *)`, America/Los_Angeles.
- `mbop-reconciliation`: preserved `cron(0 21 ? * * *)`, America/Los_Angeles.

No additional schedule or infrastructure was created. Manual refresh is available between scheduled downloads.

## Focused validation

- 17 real PostgreSQL transaction checks passed using the actual migrations in disposable PostgreSQL 17, including the prior eight listing-batch transaction regressions. Coverage includes partial shipments, cancellation, replacement shortages, concurrent retries, FIFO cost lineage, unknown-cost openings, overlap/revision checks, stale/conflicting observations, failed-sync watermark protection and late historical/refund updates. The final ambiguity-persistence case also passed independently.
- 5 Amazon MF normalization/scope tests passed, including PII exclusion, cancellation-request semantics, source timestamp precision, missing fulfillment data and live-versus-submitted offer quantities.
- 14 existing Orders 2026 tests passed.
- 3 MF/FBA inventory projection tests and 2 existing FBA inventory tests passed.
- Existing InventoryLab export and listing API checks passed.
- Focused ESLint, TypeScript and production builds passed.
- Authenticated browser verification confirmed separate inventory and customer-order views, last-success timestamps, physical-vs-offer differences, default Keep MF, and an explicitly empty physical-count/unknown-cost opening dialog that closes without saving. The 12-unit Tilly offer was displayed alongside zero recorded physical units and an explicit discrepancy; no physical count was inferred.

## Operator follow-up and boundaries

Existing MF stock is a reconciliation preview until an operator counts it. Count total existing MF stock including previously recorded MF listing units, excluding unlisted Received preparation inventory. Only the surplus over recorded stock becomes an opening lot; stale previews are rejected. Initial order history covers recent 30-day updates plus outstanding orders within Amazon's supported history window. Unknown live offer quantity is displayed as unknown and does not prevent an explicit count for a fresh identified MF offer.

Inspection and FBA-transfer allocation columns are independent and initially zero; receiving returns, executing transfers, shipment confirmation and automatic quantity writes remain outside this release. Historical shipment timing ambiguities and stock deficits require reconciliation rather than guessed inventory changes.

The earlier shipping-reconciliation working-tree changes were preserved outside this phase's commits.

Opening lots use their explicit count timestamp as the FIFO date when original acquisition timing is unknown; no purchase date or purchase record is inferred.

Final-build browser refresh verification: completed successfully at 2026-11-08 04:54:32 UTC (started 04:53:53 UTC), 129 offers refreshed, zero new orders/items, no error. The final live notice reads “MF synchronization complete. Reloaded latest data.” The live last-success timestamp advanced to 8:54:32 PM Pacific. Existing balances remained unconfirmed and no physical stock was inferred.
