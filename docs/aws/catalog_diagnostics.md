# Catalog production diagnostics

Enabled September 6, 2026 for `mbop-sourcing-catalog`, scheduler revision 82:
`sha256:cc311434934a34b2ec0acf1facf4a62045a38e535f30482cb7e486075920aee1`.
The schedule remains enabled at 00:10 America/Los_Angeles. Other schedules
retain their existing task revisions.

## Evidence retained

- `/ecs/mbop-scheduler`: streamed child and grandchild stdout/stderr, including
  output before abnormal exit. Ordinary output is temporarily spooled to disk
  for existing job metric parsing; diagnostic lines are not retained in that
  spool. Job timeouts terminate the child process group on Linux.
- `CATALOG_DIAGNOSTIC` records correlate run UUID, PID, parent PID, process,
  timestamps, 15-second process/RSS/container-memory heartbeats, and cgroup
  v1/v2 usage, limits, peaks and available OOM counters.
- Database HTTP traces contain request ID, method, table/RPC endpoint,
  application caller names, numeric pagination, elapsed time, status, response
  bytes and memory. Headers, credentials, payloads, SQL text, and identifier
  filter values are excluded from these added traces.
- The root process samples the authenticated Supabase metrics endpoint every
  60 seconds with an 8-second request timeout. It logs available/committed RAM,
  swap, swap activity, host OOM count, available/total data disk and pg_up when
  exported. Sampling errors are explicitly logged without exception payloads.
- `/ecs/mbop-scheduler-events`: independent EventBridge STOPPED events for
  scheduler-family tasks in `mbop-cluster1`, recording task ARN, definition,
  main-container exit code, stop code and reason. It does not log task command
  overrides or environment values. Rule: `mbop-scheduler-stopped-task-diagnostics`.

Both CloudWatch log groups retain records for 30 days. Capture is deployed in
AWS and does not depend on an open Codex session or the operator's computer.
This is capture, not an automatic diagnosis or notification service.

## Investigation

Find the scheduler run UUID and task ARN in `scheduler_runs`. In CloudWatch,
open `scheduled/mbop-scheduler/<task ID>` under `/ecs/mbop-scheduler`. Filter on
the run UUID to correlate process/request records. An unmatched
`db_request_start` identifies an in-flight operation at termination. Compare
the last memory heartbeats and database-pressure records with the independent
task exit entry. Query `/ecs/mbop-scheduler-events` for the complete task ARN.

SIGTERM and ordinary failures attempt to finish scheduler telemetry. A hard
kill cannot guarantee a final Python log or database update. Use the retained
ECS event as evidence, then `scripts/reconcile-stopped-scheduler.py --task-arn
<ARN> --apply` to back up and correct running telemetry after verifying STOPPED.

The database sampler stops with the task and has 60-second resolution. It does
not capture Supabase kernel logs, server SQL text or a complete active-query
history. A database-host crash can still require Supabase's internal evidence;
do not claim these diagnostics prove every possible root cause.

## Verification

Five tests passed locally and in the Linux image, covering immediate output,
abrupt child exit, timeout metrics, trace privacy and Fargate cgroup v1 counters.

Read-only revision 82 task `84fe411052434c16b825ac76f3588638` used
`python run_all_syncs.py --group sourcing-catalog --diagnostics-check`. It ran
one tiny database read, no sync jobs and no telemetry writes. Logs confirmed
three instrumented processes, nine container-memory records, heartbeats,
request timing/size, database pressure and zero initialization errors.
Evidence: `logs/diagnostics/persistent-logging-check-20260907T005802Z`.

Independent task `321bda3713694163b79ed9ede68f54ff` deliberately called
`os._exit(9)` without database work. Its last diagnostic line survived and the
corrected EventBridge target persisted `exit=9` and its ECS stop reason.
Evidence: `logs/diagnostics/persistent-logging-check-20260907T010011Z`.

Earlier probe events did not deliver because the CloudWatch input transformer
was unsuitable. The final target uses the documented timestamp/message format
and a policy scoped to the single diagnostic log group. References:
[AWS target input transformation](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-transform-target-input.html),
[AWS CloudWatch target permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html).

## Recovery

Exact prior schedule: `logs/diagnostics/catalog-schedule-before-persistent-logging.json`.
Previous scheduler revision: 80 (includes the verified matching-memory fixes).
Use `scripts/update-scheduler-schedules.ps1` with that revision and
`-ScheduleNamePrefix mbop-sourcing-catalog` to revert runtime diagnostics.
Event-rule, target and log-policy pre-change backups are under
`logs/diagnostics/event-logging-config-*`. Disable the named EventBridge rule
to stop independent exit capture; retain the log groups and existing evidence.

## September 7 follow-up

The next nightly run reproduced a Supabase restart while inserting sourcing
opportunities. See [incremental scoring and recovery](../sourcing_catalog_recovery_2026-09-07.md)
for the evidence, capacity gate, retry behavior, deployment and outstanding work.
The new synchronous gate emits database_guard_ready/database_guard_wait records;
the original 60-second sampler remains independent observational logging.
