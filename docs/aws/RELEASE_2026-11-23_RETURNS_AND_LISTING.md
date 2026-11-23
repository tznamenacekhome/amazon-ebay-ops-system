# November 23 release: MF return recovery and Amazon listing exports

## Included changes

- List on Amazon shows **Pricing last updated**, sourced from the backend's
  oldest pricing/fee cache among queued items. Empty queues show **No items in
  queue**; shipment/inventory refresh times no longer imply price refreshes.
- MF exports retain an existing fulfillment/condition-scoped MF MSKU. Otherwise
  they generate `MF-` plus the matching FBA MSKU, or a stable numeric `MF-`
  identity when neither exists. Ambiguous mappings, known conflicts and oversized
  SKUs block export. CSV and saved allocation snapshots use the same SKU;
  re-export returns the original snapshot. No Amazon listing is created here.
- System Health expects Recent Amazon Sales at :50 every two hours from
  7:50 a.m. through 9:50 p.m. Pacific, plus the 4:30 a.m. catch-up, matching
  the existing AWS schedules rather than the previous :00 assumption.
- MF return finances exclude explicitly AFN/FBA transactions before Orders
  verification. Confirmed FBA report rows are skipped without failing a report;
  invalid/unverified rows and Orders errors remain visible and retryable.
- PARTIAL reports retain original report IDs and are discovered across UTC
  rollover/lookback changes, even without normalized returns. Safe rows continue;
  replay is idempotent. More than six pending reports prevents full success.
- Account-scoped finance work is saved before verification/import. Pending
  normalized payloads survive the rolling feed, with retries independent of
  posted dates. Import and acknowledgement are atomic. A final pending-work check
  and database finish guard prevent last-success advancing with unresolved work.
  More than 100 pending finance items forces incomplete status.
- Logs/stats distinguish report import, partial progress and full sync success.
  Fixture and PostgreSQL tests cover empty reports, valid returns, FBA skips,
  mixed failures, rollover recovery, rejected SQL imports and duplicate-free replay.

See the [full investigation](../mf_returns_sync_diagnosis_2026-11-23.md).
Historical failures previously recorded only as IDs are not automatically
backfilled; the new queue protects payloads observed by the new worker.

## Files and validation

Worker/projections: `integrations/amazon_sync_mf_returns.py`,
`integrations/amazon_mf_returns.py`.

Web/API: `web/app/fba/page.tsx`, `web/app/api/system-health/route.ts`,
`web/app/api/amazonSkuIdentity.ts`, `web/app/api/amazon-listing-batches/route.ts`,
`web/app/api/fba-shipments/route.ts`.

Tests: `tests/test_amazon_mf_returns.py`, `tests/test_amazon_mf_returns_sync.py`,
`tests/test_mf_returns_sync_postgres.py`, `tests/fixtures/mf_returns/`,
`web/app/fba/amazonSkuIdentity.test.mjs`, `web/app/fba/listingBatchApi.test.mjs`.

- 28 returns Python tests and 14 Orders contract tests passed.
- 10 existing PostgreSQL returns tests and 4 worker tests passed in disposable
  postgres:17 containers with fixture-only Amazon responses.
- Three web suites passed: SKU identity, listing batch API, InventoryLab CSV.
- TypeScript `tsc --noEmit` and `git diff --check` passed.
- Production checks are recorded separately; local checks alone are not proof.

## Migration and rollout

Apply `20261123213947_mbop_mf_return_finance_work.sql` from MBOP's canonical
`supabase/migrations` history before deploying the scheduler. It adds the
RLS-enabled, service-role-only work table and enqueue/completion RPCs, and updates
the sync-finish guard. It preserves data and other applications' migrations.

Preflight verified project `amazon-ebay-ops` (`froeucjkcepuhgwisped`),
ACTIVE_HEALTHY, and AWS account `297464765814`. The complete shared migration
ledger matched except for this new local migration. No ledger repair is needed.

Commit/push, apply the reviewed migration through the linked CLI workflow, then
use `scripts/deploy-web.ps1` and `scripts/deploy-scheduler.ps1` with
`-BaseTaskDefinition mbop-scheduler-task:167` and
`-ScheduleNamePrefix mbop-amazon-sales-recent-`. Preserve cadence, environment,
networking, secrets and roles. Keep CLOUD_DEPLOYMENT=true and LOCAL_SYNC_ENABLED=false.

Pre-release rollback references: web `mbop-web-task:225`; both Recent Amazon
Sales schedules `mbop-scheduler-task:167`. Rollback restores the previous ECS
references. Keep the additive migration and pending work; do not revert the shared
ledger or discard unresolved work. The checkpoint guard remains intentionally active.

## Deployment evidence

Application commit `13401a63fccb` was pushed to `origin/main` and deployed.

- Migration `20261123213947` applied through the linked CLI push after complete
  ledger reconciliation. The subsequent linked list showed 49 matching entries
  and zero mismatches. Remote reads confirmed the work table, enqueue/completion
  RPCs and RLS. The CLI emitted a post-apply pg-delta catalog-cache certificate-path
  warning; application and ledger recording succeeded. No ledger repair was used.
- Web: `mbop-web-task:226`, digest
  `sha256:8aa76106d0851131889bc220ad22669e223604a9d85c2046a89f4362890433a2`.
  The ECS stability wait completed; rollout is COMPLETED, desired/running 1,
  pending 0, and the new ALB target is healthy. Build SHA is `13401a63fccb`.
- Scheduler: `mbop-scheduler-task:168`, digest
  `sha256:7260dc422fee051af3692dd03465a3ae2d27d515fd87d28671fef498924c1eb0`.
  Both Recent Amazon Sales schedules point to 168. Read-back comparison confirmed
  cadence, timezone, launch settings, roles, secret references and environment
  were preserved. Both tasks retain CLOUD_DEPLOYMENT=true and LOCAL_SYNC_ENABLED=false.
- ECS `mf-returns --list` task `1feb7ce1c70549249e90199db08102aa` exited 0 on
  the deployed scheduler digest and selected only the intended returns worker.
- One bounded live `mf-returns` verification was explicitly approved after
  automatic approval review initially withheld it under the earlier production
  restriction. Task `032e5c3ad44e4175882455dfb7be6459` started on revision 168.
  Database guard passed: PostgreSQL up, about 1.44 GiB available RAM, 13.62 GiB
  disk free and 48% swap free. It exited 0. Returns run
  `0ea01c26-2526-4757-aae4-3558584ae539` completed at
  `2026-11-23T22:03:20Z` (2:03 p.m. Pacific), with no error: one imported report,
  zero MF returns/financial transactions/packages, 21 explicit FBA transactions
  skipped, 11 non-customer financial references excluded and no unresolved work.
  Logs explicitly excluded the recurring order `114-8866055-7493009` as FBA.
  Remote reads confirmed completed status, zero pending finance work and zero
  normalized MF returns. This advances the last-success timestamp without
  inventing a return or disguising a failed sync as an empty success.
- Authenticated browser verification could not complete because the browser host
  was unavailable. Automatic review rejected inspecting an unrelated private
  Chrome page; it was left untouched. AWS/worker checks do not substitute for
  production browser verification of the pricing/MSKU UI.
- Docker's Windows credential helper initially failed ECR login. Deployment used
  an ignored task-scoped Docker auth configuration instead of changing the
  existing credential-store settings. The temporary ECR auth file was removed
  after both deployments. No persistent credential/role changes, production test
  returns or listing exports were made.
