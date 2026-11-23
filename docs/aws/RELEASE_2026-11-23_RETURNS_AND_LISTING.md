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

Task revisions, image digests, migration confirmation, service health and browser
observations will be recorded after rollout. Verification uses read-only page/API
checks and normal scheduler evidence; no test returns or listing exports are created.
