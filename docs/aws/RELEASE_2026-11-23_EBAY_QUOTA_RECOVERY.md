# November 23: shared eBay quota and Flipmine checkpoint recovery

Code commits: `f80b151cc429` and `651a9d389028`, both pushed to `main`.
The [diagnosis and implementation report](../flipmine_rate_limit_recovery_2026-11-23.md)
contains actual production quotas, reset time, response evidence, bulk restrictions,
consumers, expected savings, recovery design, tests and follow-up guidance.

## Deployed state

- Shared migration `20261124033839_mbop_ebay_quota_and_flipmine_recovery.sql`
  is applied and recorded in verified MBOP project `froeucjkcepuhgwisped`.
  Complete shared migration history was reconciled before push; this was the only
  pending migration. Direct checks confirmed the resource/cache tables and no
  anonymous RPC execution. The CLI's post-apply catalog-cache certificate warning
  did not prevent application or ledger registration.
- Final scheduler revision: `mbop-scheduler-task:171`, application `651a9d389028`,
  digest `sha256:8d8627d7ecd611e4c4ca7a2f9b1dd70c7159f2e2777acd48d75ffd536b3be2ce`.
- Web revision: `mbop-web-task:229`, application `651a9d389028`, digest
  `sha256:83585f31f895f9ff0989d031e7c1bc92a805ca83454b89d7beee05cca66735e1`.
  AWS status confirmed COMPLETED / steady state at 8:20:02 p.m. Pacific,
  desired/running 1/1, pending 0, matching build SHA and a healthy new ALB target.
  CLOUD_DEPLOYMENT=true and LOCAL_SYNC_ENABLED=false were verified.
- Existing `mbop-sourcing-catalog`, `mbop-keepa-catalog-priority`,
  `mbop-purchase-ingestion-hourly` and `mbop-purchase-ingestion-catchup` targets
  now use revision 171. Their timings, commands, state, timezone, CPU/memory,
  networking and launch configuration were preserved. No new schedule was added.
- The web's existing ZFI on-demand purchase-ingestion pin was upgraded from
  revision 106 to 171 using `deploy-web.ps1 -ZfiPurchaseTaskDefinition`. It invokes
  the same purchase-ingestion group as the hourly schedule. This closes an old
  Browse consumer outside the shared guard. Existing RunTask permissions already
  allowed the revision; IAM was not changed. Receipt extraction's unrelated pin
  and all unrelated schedules remain unchanged.
- New resource coordination is private, app-scoped and fail-closed. No eBay
  credentials, permissions, paid service or infrastructure were added/changed.
  Temporary Docker authentication files were removed after deployment.

## Live checkpoint verification

Original import: `c7ba90ae-7cdd-4b87-a831-c2ff33682adf`.
Original tab: `97fc964e-a4f2-43bb-a5ca-90381d1352b8`.
Snapshot hash before and after recovery:
`f60131aafdf2ccd6908fc2239f3942f0972166502f870ea26ba142eae4c1c13c`.

The original 558 rows were retained; the six previous quota errors were made
pending for retry, with source evidence and last error retained. No Google tabs
were read or discovered by recovery. No opportunities were added or duplicated.

The first cloud recovery check exposed unnecessary offer-history loading before
the quota check. Revision 171 moves this behind the quota check, defers matching
context loading and records the current ECS task ARN on resume.

Final check task `8a068e167b334141a90d6c08d8359692` exited 0. Its logs contain
database guard ready and `FLIPMINE_PAUSED` for `daily_quota_exhausted`, with no
offer-history refresh or Browse request. Remote state confirmed:

- status **paused**, resource `buy.browse`;
- next retry `2026-11-24T08:00:00Z` = **Nov 24, 12:00:00 a.m. Pacific**;
- 558 retained rows, 558 pending, zero evaluated, failed, invalid or excluded;
- zero metered Browse attempts / linked opportunities during verification;
- current task ARN correctly updated to this recovery task.

Existing 30-minute Keepa wakes and the 12:10 a.m. Pacific catalog wake can claim
this saved checkpoint once eligible. Recovery is nonblocking, time-bounded and
does not discover new tabs. Dynamic quota reservation protects its outstanding
listing count from catalog/buyer-enrichment consumers. Completed candidates and
operator-owned opportunity states remain protected by existing idempotent writes.

## Validation and limits

316 targeted Python tests passed, including 13 disposable PostgreSQL transaction
and concurrency tests. The web regressions, TypeScript, targeted ESLint, local
production build and Docker release builds passed. No fixture data was written
to production, and no real return, purchase, listing action or offer placement
was performed.

Read-only memory check task `a0bc9bab426f4dc59f4ad017f2eecfa3` used the existing
512 CPU / 1 GiB scheduled-worker size and exited 0. Full matching/history context
loaded with peak RSS 238,100,480 bytes (about 227 MiB), no OOM event, and fresh
database capacity checks. This verifies context loading fits the existing worker;
it is not a completed live sourcing evaluation.

The exact OpenAPI `getItems` path `/buy/browse/v1/item/` was also tested and
returned the same HTTP 403 / error 1100 as the non-trailing-slash request.
Unused bulk quota does not establish access or sufficient identity evidence.

Authenticated browser verification could not run because the browser-access host
was unavailable. AWS health and worker checks do not replace that final UI check.
Full evaluation / Buy List / Closest Excluded / provenance and completion
verification must wait for real quota capacity. Current pending work is not
reported as a successful empty import. Once capacity returns, inspect all 558
terminal outcomes and require zero pending/failed rows before claiming full
recovery. Actual review failures must remain visible rather than forced complete.

Rollback should preserve the additive quota/cache/checkpoint schema. Rolling back
to an unguarded worker also removes quota coordination/recovery; do not do so
while assuming the checkpoint will continue automatically.
