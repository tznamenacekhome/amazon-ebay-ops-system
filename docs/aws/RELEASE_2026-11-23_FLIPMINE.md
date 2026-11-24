# November 23: manual Flipmine sourcing

Application commit: `bd01f2476dbd` (pushed to `main`). See the
[feature and operations guide](../flipmine_sourcing.md) for the pipeline, files,
idempotency, failure handling, schema, configuration and operator verification.

## Included behavior

- Opportunities has a manual **Import Flipmine** control, progress/history and a
  compact **FM** marker inside the existing Opportunity cell in both list views.
- Read-only Google tabs supply proposed eBay/ASIN pairs. Current eBay detail and
  normal Amazon/catalog/Keepa evidence enter the existing matcher and buying
  evaluator. Source titles/prices never confirm identity or drive economics.
- Valid candidates use existing Buy List/Closest Excluded gates and ranking.
  Hard mismatches remain audited exclusions. Existing evaluations/operator holds
  are preserved when a duplicate gains Flipmine provenance.
- Numeric tab IDs, immutable source snapshots, transactional pair/opportunity
  writes and durable row states make repeat/partial imports safe. Interrupted
  workers are fenced. Counts are confirmed through the real list builder before
  completion; unresolved work stays visible and retryable.

## Database and deployment

Migration `20261124022809_mbop_flipmine_sourcing_import.sql` is applied and recorded
in the verified shared project `froeucjkcepuhgwisped`. The entire shared history
was reconciled before `supabase db push --linked`; only this migration was pending.
Remote verification confirmed `(ebay_item_id, asin)` uniqueness, all three audit
tables, and no anonymous execution grant on the new lease RPC. The CLI reported
a post-application catalog-cache certificate warning; direct migration-ledger and
schema checks confirmed the migration succeeded.

- Scheduler: `mbop-scheduler-task:169`, image
  `sha256:7daf2d98857208f0808cfa1bd001e07dbb5d08f5b1217c476c352d4c6ef1949d`.
- Web: `mbop-web-task:227`, image
  `sha256:b29dd698d3f397febb47d2d75250cb680091ab1fe977362af82d338e9aa43ea7`.
  The documented AWS status check confirmed deployment COMPLETED / steady state
  at 7:02:30 p.m. Pacific, desired/running 1/1, pending 0, and build `bd01f2476dbd`.
  The new ALB target was healthy; the old target was draining normally.
- The existing catalog schedule points to revision 169 because its normal writer
  must use the new pair conflict key. Its `cron(10 0 ? * * *)`, Pacific timezone,
  enabled state, command, networking, CPU/memory and launch settings were retained.
  No Flipmine schedule or new infrastructure was created; other schedules were
  untouched. Cloud/local execution flags and existing secret references remain.
- The sheet setting is server-only on the worker. Existing Google authentication
  is reused, with read-only scope. The operator granted Viewer access to the
  existing account. Local source-only plan verification succeeded. Deployed
  worker plan task `848348bd7ab14007a7bec219ce05705a` also exited 0 and read the
  configured source successfully. Remote audit-table reads confirmed zero live
  imports / imported rows after verification; this check did not evaluate pairs.
- Windows Docker credential-helper failure was handled with an ignored,
  task-scoped ECR authentication file, removed after each deployment. Persistent
  Docker credentials and AWS roles were not changed.

## Validation

All 256 targeted Python tests passed: 28 Flipmine fixture tests, 8 disposable
PostgreSQL cases, 188 sourcing tests, 17 Browse tests and 15 wholesale seed tests.
The disposable database had no published port and was removed afterward.
Four web regression scripts passed, covering the actual list API, completion
counts/failure handling, launch authorization/idempotency and the inline FM badge.
TypeScript, targeted ESLint, local production build and release Docker build passed.

Capacity preflight passed a tiny read and fresh metrics: PostgreSQL up, about
1.28 GiB available RAM, 13.6 GiB disk headroom and 50% swap free. No full live
Flipmine evaluation, broad backfill, production fixture insertion, purchase,
marketplace write or return action was used for verification.

Authenticated production browser verification was blocked by the unavailable
browser-access host. AWS rollout/health and source-plan checks do not substitute
for the final browser check. Open Sourcing, explicitly click **Import Flipmine**,
wait for evaluation/presentation completion, inspect both list views and FM
markers, then repeat the import and verify **Nothing new to import** with stable
candidate/opportunity IDs. Keep partial row errors visible and retry manually.

Rollback must coordinate the web and compatible scheduler image. Do not launch
old single-key sourcing writers against the new pair-key schema. Preserve the
additive ledger and source evidence.
