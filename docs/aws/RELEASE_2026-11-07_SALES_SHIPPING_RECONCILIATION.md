# November 7, 2026 Amazon shipping-cost recovery

Shipping reconciliation now retries existing pre-shipment Veeqo imports,
processes an independently bounded historical backlog, preserves actual cost
evidence, allocates order shipping once across items, and repairs affected
profitability outside the recent purchase window. Amazon adjustments require
explicit outbound postage evidence. COGS and workflow tables are unchanged.
See [the reconciliation runbook](../sales_shipping_reconciliation.md).

## Recovery results

| Check | Before | After |
|---|---:|---:|
| Tilly Tacker shipped units audited | 25 across 24 orders | 25 across 24 orders |
| Tilly units missing actual shipping | 22 | 0 |
| Stored Veeqo orders without label cost | 60 of 363 | 27 of 363 |
| Eligible shipped orders requiring shipping reconciliation | unresolved | 0 of 324 |

Thirty-three orders gained Veeqo label amounts. The remaining 27 Veeqo label
gaps are 21 cancelled orders, two fully refunded orders, three orders covered by
verified Amazon postage events, and one existing operator-provided external
label override. These are not an unresolved actual-cost backlog.

The four alternative-source orders are:

| Order | Actual cost | Evidence |
|---|---:|---|
| 112-6690483-0608255 | $5.16 | Amazon outbound postage |
| 113-1326117-2034660 | $5.15 | Amazon outbound postage |
| 114-8402831-1602613 | $5.80 | Amazon `PostageBilling_Postage` |
| 114-6021948-3727407 | $4.14 | Active manual external-label override; operator evidence recorded May 31 |

All 25 Tilly units were checked individually against their source evidence and
stored item-level fulfillment cost. Twenty-four units use Veeqo evidence and
one uses Amazon postage. COGS values compare unchanged before/after; all 25
remain missing COGS. Shipping recovery therefore does not mean their full net
profitability is complete.

The Google Sheets-compatible UTF-8 CSV is
`artifacts/shipping-reconciliation/tilly-reconciliation.csv`. Baseline and final
unit JSON/CSV, ECS task/log records, schedule readback, source hashes and an
aggregate summary are in the same directory. Repeated order totals on unit rows
must not be summed; use the allocated-unit cost column.

## Capacity and execution

Production project `amazon-ebay-ops` / `froeucjkcepuhgwisped` was verified healthy
and a tiny SQL read succeeded. PostgreSQL size was approximately 14 GB. Initial
metrics showed about 16.8 GiB disk available, 1.56 GiB available memory and 45%
free swap. The existing fail-closed capacity gate passed again in every apply
task. Remaining Disk IO Budget is not exposed by that gate; recovery stayed
bounded to the reviewed order cohort and small subsequent batch, with no raw
history expansion or schema changes.

The ECS production dry run selected 24 Tilly orders, expecting 24 detail GETs
normally and at most 96 attempts with retries. The Tilly apply task made exactly
24 requests, matched all 24 orders, and exited zero with no retries, rate limits,
API failures or write failures. The next shipping-only task attempted the
remaining 16 candidate orders, recovered 12 more Veeqo costs, and identified the
four alternative-source costs above. It also exited zero with 16 requests and
no retries or failures. The final eligibility calculation verifies those
alternative sources instead of generating a false backlog.

Final production task `1e05d76bdde04b54bd730326cc197e93`, scheduler revision 157,
ran `python run_all_syncs.py --group amazon-shipping-reconciliation` and exited
zero. It checked eligibility for 324 orders, selected/attempted zero orders,
made zero Veeqo calls, reported zero unresolved orders and backlog age zero,
and persisted `queue_status=empty` in scheduler telemetry. Its run ID is
`dac1f839-27e7-40c9-a9f8-5db46ea6fdc9`.

The deduplicated `sales-shipping:unresolved` notification was resolved after
recovery and retained occurrence count one. An already-running regular sales
task was allowed to finish before final shipping verification; it was not
terminated or overlapped with another recovery worker.

## Deployment and verification

- Scheduler: `mbop-scheduler-task:157`, image digest
  `sha256:9d477d52f75f7c29727e334e10625f2fff6649f18da0c85e0ab1418a756ed66a`.
- Web: `mbop-web-task:202`, image digest
  `sha256:6e809ba3432c5441d1d1ac6743cc682931fee960cb6b29a6c6630aac6a6f25f1`.
  The repository status helper confirmed the rollout completed at 5:59 PM PST,
  with one desired/running task and no pending tasks.
- Only `mbop-amazon-sales-recent-day` and
  `mbop-amazon-sales-recent-catchup` changed from scheduler147 to scheduler157.
  All 21 schedule definitions were compared: cadence, state, networking,
  permissions and other schedule configuration are unchanged.
- Cloud web/scheduler flags remain `CLOUD_DEPLOYMENT=true` and
  `LOCAL_SYNC_ENABLED=false`. The scheduler uses `Dockerfile.scheduler` and the
  web uses `web/Dockerfile`. Existing task configuration/secrets were preserved.
- The repository AWS deployment flow was followed: build, push, resolve digest,
  register task and update scoped targets/service. Docker's Windows credential
  helper rejected ECR login; isolated temporary ECR auth files were used for the
  same Docker/ECR steps. Tokens were not printed; temporary auth files were
  removed. User Docker settings were preserved.
- Production browser verification at
  `https://mbop.midnightblueenterprises.com/system-health` showed build
  `898067e5d021-shipping-health`, a Healthy Veeqo job, 324 eligible orders,
  zero unresolved orders/API failures/backlog age, and the explicit empty-queue
  message. This is authenticated production verification, not a localhost test.

The release was built from the working tree based on `898067e5d021`;
`source-sha256.json` records the deployed implementation files. No migration,
marketplace order modification, label purchase or price change was performed.

Validation: 32 focused unittest cases passed, covering reconciliation,
profitability fees and scheduler streaming; Python compilation and
`git diff --check` passed. `npm run build` passed locally and inside the web
image. Production scheduler executions, telemetry readback, schedule comparison
and authenticated browser checks were performed in addition to local checks.

## Rollback

For code rollback, restore the two Amazon-sales task references to revision 147
using the existing `update-scheduler-schedules.ps1` workflow scoped to
`mbop-amazon-sales-recent-`. Restore web task200 for the original pre-release
web behavior, or task201 for the intermediate shipping-group health view.
Do not undo recovered actual shipping evidence or COGS. No schema rollback is
needed. Restoring the old worker reintroduces its missing-cost reconciliation
bug, so prefer a forward fix if a new issue is found.
