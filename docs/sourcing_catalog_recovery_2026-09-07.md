# Catalog incremental scoring and capacity recovery

## Incident evidence

The September 7 00:10 Pacific scheduler run
`c79c5f53-baf6-4c4b-af5c-f33ac2fc593f` searched 1,050 ASINs before
`score_sourcing_opportunities.upsert_opportunities` received HTTP 520 on an
INSERT at 08:31:18 UTC, after 40.956 seconds. PostgreSQL restarted at
08:31:21.844266 UTC. Committed database memory reached 3.36 GB versus a
2.04 GB commit limit, and swap free fell to 561,152 bytes. Samples do not
prove an OOM kill: the sampled OOM counter was zero and the metrics request
during the outage timed out. Host counters reset afterward.

The task itself survived, peaked at 846,118,912 bytes cgroup memory, and
finished exit 0 with degraded scheduler telemetry. The independent ECS
event confirms revision 82. Matching refresh completed afterward. Raw
evidence is retained locally under
`logs/diagnostics/catalog-20260907-investigation` and in CloudWatch.

The remaining amplification was that each 50-seed chunk rescored and rewrote
all candidates already accumulated in the run (1,899 at failure). This is
confirmed unnecessary work, not proof that the failing INSERT alone caused
the database restart.

## Changes

- Daily scoring receives explicit seed IDs for the current searched chunk.
  Seeds, candidates and initial snapshot reads are filtered to that scope.
  Historical matching rescoring retains the full-run behavior.
- Opportunity write batches decrease from 250 to 25. Snapshot reads are
  paginated in groups of 25. Run opportunity counts remain cumulative.
- A fresh metrics sample and tiny database read gate each catalog stage,
  each discovery chunk, scoring startup, and each opportunity write batch.
  Proceed only with at least max(256 MiB, 15%) available RAM, 25% free swap
  when swap exists, max(1 GiB, 15%) free data disk, and pg_up=1.
  Missing metrics, HTTP failures and failed tiny reads block work.
- The gate waits at most 11 attempts, spaced 30 seconds, with 8-second
  metrics request timeouts. A persistent failure stops work; the scheduler
  does not launch a subsequent catalog stage until the same gate passes.
  These thresholds are operational safeguards, not an OOM guarantee or a
  replacement for Disk IO Budget monitoring.
- Failed scoring retries the same saved seed scope up to twice, after a
  fresh capacity check. It re-reads existing opportunities before writing,
  covering an INSERT committed before its response was lost. It does not
  repeat eBay search during these scoring retries or blindly replay INSERTs.
- Exhausted scoring retries return affected queue items to retryable_failed
  and fail the daily run. Searches left in searching for over six hours are
  requeued on the next run only when no other running catalog telemetry
  exists. Hard-killed scheduler telemetry must first be reconciled against
  ECS using the existing recovery tool. Requeued searches can consume new
  Browse calls; this is queue recovery, not exactly-once external search.

## Verification and deployment

Unit coverage includes seed scope on every page, a committed INSERT with a
lost response, identical-scope retries, active-run recovery exclusion, low
RAM/swap/disk and missing metrics, bounded waits, and tiny-read gating.
Existing sourcing, matching, diagnostics, and blocked-ASIN tests are retained.
No new schema migration is required. The September 6 index migration was
already applied and is included unchanged in the committed migration history.

Only the catalog schedule should switch scheduler revisions; other schedules
retain their existing revisions. Deploy through deploy-scheduler.ps1 and
update-scheduler-schedules.ps1 with prefix mbop-sourcing-catalog. Rebuild the
web deployment from this commit to include the previously deployed blocked
ASIN and accurate delayed-status fixes. Pre-change rollback targets are
scheduler 82 and web 132; these restore prior behavior, including its known
catalog failure risk. Save schedule/task metadata before deployment.

## Outstanding

- Validate a capped live discovery chunk after deployment, then observe a
  complete nightly run before claiming catalog coverage is current.
- Capacity pressure may persist from other workloads on this shared database.
  If optimized normal work still reaches the guard, review concurrent jobs,
  SQL plans and Supabase compute sizing. Do not silently raise thresholds.
- Supabase host evidence is still required to conclusively explain the
  restart; the captured workload and pressure correlation are not kernel logs.
- An abrupt outage can prevent final telemetry/queue writes. Independent ECS
  exit records and the reconciliation procedure remain necessary.
- Browser verification of Cognito-protected web behavior was previously
  blocked by browser access policy; build and ECS stability alone do not
  verify interactive application behavior.

## Deployment result

Implementation commit: `5e57a3c2df3f`, pushed to origin/main.
Scheduler revision 83 image:
`sha256:36998783f587c35a301ce7d980ffd3ba49e490e0c0236433f79b1c9c02bf3ac8`.
Only mbop-sourcing-catalog was updated from 82 to 83; its enabled
00:10 America/Los_Angeles schedule is retained. Web revision 133 is stable
with desired/running 1/1, build SHA 5e57a3c2df3f, image
`sha256:b2b00a20621e4d76e3bccc3e8267aa1569b594d167eb4bd594df05bfa943cab3`.

Validation: 114 Python tests passed (84 sourcing, 16 matching, 5 diagnostic,
9 catalog); the 9 catalog tests also passed in the deployed Linux image.
Blocked-ASIN Node tests and the local and container Next.js builds passed.
Interactive Cognito-protected browser behavior remains unverified under the
previously encountered browser access restriction.

The first capped task stopped without catalog writes because a scheduler
record from August 16 was still running. The complete ECS active-task
inventory excluded its task. Original telemetry was backed up and reconciled
as failed; its actual stop time is unknown, so reconciliation time is clearly
identified in the record. The September 7 interrupted sourcing run was also
backed up and marked failed using its actual scheduler-job completion time.

Successful capped task: `3e2d0b5fab65429f865d639672194506`.
Sourcing run: `6026fc11-92e8-43b8-956f-ff052d322230`.
It recovered 50 abandoned searching items, searched 10 ASINs using 24 Browse
calls, scored and inserted 7 candidate opportunities (none qualified as an
open buying opportunity), and exited 0 with manual_chunk_limit. Six capacity
gates passed, with no waits or HTTP errors. PostgreSQL start time remained
2026-09-07 08:31:21.844266 UTC throughout the check. The remaining recovered
items are eligible for later queue processing. This check does not establish
full nightly completion; scheduler health was not manually marked fresh.

Supabase reports a completed physical backup at 2026-09-07 11:55:01.961 UTC.
Local rollback and evidence files are under
`logs/diagnostics/catalog-deploy-20260907`, including schedule before/after,
web before-state, backup inventory, reconciled rows, queue before-state,
ECS task state, and the capped run's complete logs. Logs and secrets are not
committed. No new schema SQL was applied in this change.
