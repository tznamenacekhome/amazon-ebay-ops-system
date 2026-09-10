# Job failure review — September 10, 2026

Read-only production investigation around 07:50 Pacific. No production data,
configuration, schedules, or job statuses changed; no jobs rerun.

## Sourcing: persistent disk-capacity gate

Run `8d65ef5f-dd12-49a9-b267-7a147df76f32` ran 00:10:41–00:15:43 Pacific
and failed before the first child job started. CloudWatch stream
`scheduled/mbop-scheduler/765cf0c4b8c340a6aa7761690b97dec1` in
`/ecs/mbop-scheduler` records eleven `database_guard_wait` events, each with
`reason=low_disk_headroom`, followed by `DatabasePressureError`.

The data filesystem had 1,235,914,752 bytes available out of 8,416,882,688
bytes (14.68%). `integrations/sourcing_database_guard.py` requires the greater
of 1 GiB or 15% free. The 15% requirement was missed by about 25.9 MB.
The guard retried every 30 seconds for five minutes. Disk capacity did not
recover, so the catalog work never began and consumed no sourcing API quota.
This failure is recorded at group level; there are no child-job failure rows
for this run because the guard precedes `run_job`.

The production schedule remains enabled at 00:10 America/Los_Angeles,
targeting `mbop-scheduler-task:86`. The previous nightly run
`58edec36-f909-4440-9710-a8e94c473113` completed successfully September 9
at 01:58:50 Pacific.

Current metrics still return `low_disk_headroom`: 1,229,185,024 bytes free,
about 14.60%. A retry under those conditions will stop again. Database reads
succeed, `pg_up=1`, and PostgreSQL start time remains
`2026-09-07T08:31:21.844266Z`. The incident has no evidence of a new database
restart or task OOM. The sampled OOM counter is zero. Memory is still worth
monitoring, but the explicit blocking reason here is disk space.

Catalog-based size inspection reports database size 6,626,192,531 bytes.
Largest relations including indexes/TOAST are FBA inventory snapshots
1,817,231,360 bytes, sourcing opportunities 1,113,268,224 bytes, and Keepa
product snapshots 1,044,283,392 bytes. These sizes identify investigation
targets, not proof that all allocated space is reclaimable or which writer
caused the threshold crossing. No full-table history scan was performed.

Next remediation should restore durable disk headroom through capacity
expansion or a reviewed retention/reclamation plan, then recheck the guard
and run sourcing. Do not lower the safety threshold merely to hide the
failure. Deletion alone does not establish that filesystem space is reclaimed.

## Keepa: transient external timeout, recovered

Run `20dd3bcd-42ef-4fdf-b343-4d12ef01635e`, 02:22:36–02:25:26 Pacific,
failed its Keepa `/token` request after three 45-second read timeouts and
2/4-second retry delays. Stream
`scheduled/mbop-scheduler/3c8918ff77af45f0bf6d83b809222688` confirms the
Supabase preflight succeeded. No product retrieval occurred before this
failure. The next scheduled run at 02:52 succeeded, and subsequent observed
runs through 07:22 succeeded. This is a Keepa request timeout; logs do not
distinguish provider-side delay from intervening network delay.

## FBA pricing: rejected duplicates, original work succeeded

In the last 48 hours, nine FBA pricing requests were blocked because run
`e081b983-b1e0-4c66-9c11-fbca5baf4e7a` was already active. Two scheduled
Keepa runs also deferred to that run's quota priority. The original pricing
run succeeded September 8, 18:10:34–19:38:13 Pacific.

The latest-started pricing row is a rejected duplicate, so group-level
latest-run status can remain blocked even though the earlier-started original
finished successfully. The System Health API orders runs by start time and
uses latest-run status for on-demand groups. This is a status presentation
limitation, not evidence that the original pricing operation failed.

## Scope and evidence

Bounded 48-hour scheduler aggregation found one sourcing failure, one Keepa
degraded run, nine FBA duplicate blocks, and two Keepa quota-priority blocks.
All other groups observed in that window had only successful runs. This does
not assert that every row-level operation inside an `ok` job was error-free.

AWS identity verified account `297464765814`, profile `mbop-admin`, region
`us-west-2`. Supabase target verified `froeucjkcepuhgwisped`. Bounded query
evidence is under ignored `logs/diagnostics/job-errors-20260910/`; CloudWatch
streams above provide the original exceptions and measurements.
