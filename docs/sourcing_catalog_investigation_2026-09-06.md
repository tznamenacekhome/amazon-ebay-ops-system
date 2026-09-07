# Recurring Sourcing Catalog delay: production investigation

Investigated September 6, 2026 against repository HEAD `2976604`, production
AWS account `297464765814`, and MBOP Supabase project
`froeucjkcepuhgwisped`. Production access was read-only. No sync, backfill,
schema change, deployment, or schedule change was performed.

## Finding

The daily schedule is firing. The group repeatedly finishes with real partial
failures, which System Health labels `delayed`. The strongest new evidence is
repeated **unclean PostgreSQL shutdowns and crash recovery during sourcing**.
Retries have treated symptoms without establishing why the database is failing.
There are also separate matching-process kills, expensive rebuild behavior,
unprotected database calls, and misleading success/freshness reporting.

This is not fixed. A successful image deployment or one successful child job is
not evidence that the whole daily workflow has recovered.

## Production execution and deployment

- `mbop-sourcing-catalog` is enabled, daily at 00:10 America/Los_Angeles.
- Live target is `mbop-scheduler-task:76`, registered September 5 at 18:07 PT.
- Image tag `scheduler-2976604248f5`; digest
  `sha256:1e92915985c161e4bf3342524b83a456b2ad8119d1814dfde5e38c5c866af373`.
- Command is `python run_all_syncs.py --group sourcing-catalog`.
- Overrides remain 1024 CPU / 2048 MB.
- The live image includes the latest repository changes. AWS docs still naming
  revision 73 are stale and cannot establish what production runs.
- Supabase scheduler telemetry shows seven consecutive degraded daily runs,
  August 31 through September 6. Last fully `ok` group: August 30,
  finished `2026-08-30T08:41:13.875654Z`.

| Run date (PT) | Failed child jobs |
| --- | --- |
| August 31 | Daily sourcing, Browse availability, matching intelligence |
| September 1 | Matching intelligence |
| September 2 | Matching intelligence |
| September 3 | Daily sourcing, matching intelligence |
| September 4 | Matching intelligence |
| September 5 | Daily sourcing, matching intelligence |
| September 6 | Daily sourcing, Browse availability |

Today's group ran from `07:10:44Z` to `09:09:54Z`. Run ID:
`8a6152b6-e516-4dbd-ade2-adf95a13a657`.

## Database failure confirmed independently of application logs

Bounded Supabase PostgreSQL log queries returned:
`database system was not properly shut down; automatic recovery in progress`.

| Date | Recovery timestamp (UTC) |
| --- | --- |
| September 1 | 09:29:09.073 |
| September 3 | 07:34:58.890 |
| September 4 | 08:21:28.980 |
| September 5 | 08:04:16.251 |
| September 6 | 09:02:09.443 |

The September 2 07:00–10:00 UTC query returned no matching recovery event.
Today's database log additionally records an interrupted server, PostgreSQL
startup, WAL redo, and a recovery checkpoint. This coincides with the 521
errors in the sourcing task. Four subsequent statement cancellations occurred
at 09:06:23, 09:06:35, 09:06:50, and 09:07:08 UTC.

These observations establish unclean restarts; they do **not** establish their
underlying host cause. OOM, disk IO exhaustion, and infrastructure failure must
not be presented as proven without host/resource evidence at those timestamps.

Current Metrics API sample:

- PostgreSQL database: 6,275,894,419 bytes (6.28 GB decimal).
- Data filesystem: 8,416,882,688 bytes, with 1,579,728,896 bytes available.
- Host RAM: 1,924,177,920 bytes; available: 743,653,376 bytes.
- Swap: 1,073,737,728 bytes; free: 903,712,768 bytes.
- This is a current sample, not incident-time utilization or Disk IO Budget.

Catalog-only relation-size reads (no operational table scans) found sourcing
opportunities at 1.04 GB, listing snapshots at 388 MB, candidates at 210 MB,
coverage cycle items at 197 MB, and matching examples at 91 MB. These sizes
include relation storage/indexes and are not measurements of disposable data.

## Exact failing paths and earlier-fix gaps

1. **September 6 daily sourcing:** scoring calls
   `enforce_one_open_opportunity_per_asin`, which calls
   `fetch_eligible_opportunities` in the Trading fallback module. Its direct
   `.execute()` fails with Supabase HTTP 521. The shared pagination retry
   helper is not used here. The exception aborts the daily runner while scoring
   a chunk, before subsequent checkpoint/finalization work.
2. **September 6 Browse availability:** `update_candidate_active` directly
   updates `sourcing_ebay_candidates`; that unprotected write also gets 521.
3. **September 5 daily sourcing:** building the next coverage cycle fails with
   PostgreSQL `57014` while reading latest Amazon listing context through
   `sourcing_common.paginate_table`. That night's image predates the
   September 5 pagination retry change; today's image contains it. This is a
   real improvement, but it does not cover paths 1 and 2.
4. **September 5 matching:** rebuilding examples fails with `PGRST002` schema
   cache/database access failure. The current classifier includes this error.
5. **September 1, 2, and 4 matching:** CloudWatch records the example-builder
   subprocess dying with `SIGKILL: 9`. Memory pressure is plausible given the
   all-history rebuild and earlier documented OOM incidents, but SIGKILL alone
   does not prove OOM. ECS Container Insights is disabled.
6. **September 6 matching:** the rebuild succeeds, but deleting old backfill
   snapshots times out four times. The code catches the final error, prints
   that cleanup is skipped, and proceeds to insert snapshots. This is not a
   clean maintenance result, even though that job reports success.

The September 5 change reduced repeated backfill preparation: September 2
logged 14,497 prepared snapshots; September 4 logged 14,682; today logged
3,567. Today's matching job completed with 18,679 examples prepared.
That improvement should be retained, not confused with complete recovery.

`build_matching_intelligence_examples.write_rows` still deletes all
`matching_intelligence_backfill` snapshots in one operation, inserts batches,
holds returned snapshot rows in memory, and replaces example batches using
delete followed by insert. Reads include complete snapshots and nested
opportunity/candidate/seed evidence. Repeating these operations can be costly.

Live `pg_indexes` confirms no index beginning with:

- `sourcing_listing_snapshots.snapshot_source`, used by the broad cleanup;
- `sourcing_listing_snapshots.action_id`, used by snapshot reuse lookups;
- `matching_intelligence_examples.listing_snapshot_id`, a foreign-key column
  whose reference uses `ON DELETE SET NULL` in the schema SQL.

These are concrete optimization candidates, especially the referencing FK
index during bulk deletion. They are not proof of the database crash trigger.
Any index migration belongs in MBOP's migration history and must follow
AGENTS.md before application.

## Reporting makes recurrence harder to recognize

- `run_all_syncs.py` records `degraded` but returns process exit code 0 when
  nonblocking jobs fail. All four sourcing jobs are nonblocking. A successful
  ECS process exit is therefore insufficient verification.
- `run_daily_catalog_sourcing.py` catches failed search children, finalizes
  the run, and returns 0 even with `stop_reason=ebay_child_failed`.
  September 4 logs show that exact stop reason despite the daily child being
  counted successful. Its logged partial output was 950 ASINs searched,
  4,095 Browse calls, and 36 opportunities found.
- Scoring itself writes `sourcing_runs.status=completed` during chunk
  processing, before the daily owner has finished its whole workflow.
- System Health maps `degraded` to `delayed`, conflating partial failures
  with schedule lateness.
- The API reads only the latest 500 scheduler runs globally. Today's equivalent
  read reached only September 2 at 09:22 UTC and contained four sourcing runs,
  all degraded. It omitted the August 30 success. When no successful group run
  is present, the summary falls back to the latest successful **child** as the
  group's `lastSuccessAt`. This can make a week of group failures look recent.

## Durable corrective work and acceptance criteria

1. Diagnose the unclean database restarts with incident-time host RAM, OOM,
   disk IO, and infrastructure evidence, using the timestamps above. Current
   free memory is not enough. Obtain provider-side evidence if unavailable.
2. Make matching refresh incremental and bounded. Preserve existing evidence;
   replace broad delete/reinsert maintenance with stable identities and safe
   upserts/checkpoints. Measure/index actual read and FK access paths.
3. Cover the specific remaining database failure boundaries with bounded,
   operation-safe recovery. Do not blindly retry non-idempotent inserts or
   rerun quota-spending discovery after a database failure.
4. Make the daily runner own terminal status; distinguish partial/quota-limited
   progress from completed discovery and failed execution. Make cleanup
   failure visible. Base group last success on successful whole-group runs,
   fetched per group rather than an arbitrary global history window.
5. Verify the deployed scheduler revision, then validate several consecutive
   scheduled runs against database logs, child-job results, completed batches,
   coverage checkpoints, and actual output. Require no unclean restarts,
   process kills, hidden cleanup failures, or false-success child results.
   Finally verify the production System Health UI through its browser session.

No broad retry was launched during this investigation. The bounded production
reads succeeded, so historical outages alone did not justify disabling current
schedules. Follow the capacity guardrail if active connection refusal recurs.

## Evidence locations

CloudWatch group `/ecs/mbop-scheduler`, streams prefixed
`scheduled/mbop-scheduler/`:

- September 1: `89d445ba1c2f467aaa967d53b758b71e`
- September 2: `d916d8a7ecbf48e492096839cf65eb42`
- September 4: `32c3bea25aa24737bad9090da2707d8d`
- September 5: `5b43763d12934c6b9a0056cb76199aee`
- September 6: `696479c87fbf40629a3fc794694eb894`

Supabase evidence came from bounded scheduler telemetry reads, PostgreSQL logs,
the [Metrics API](https://supabase.com/docs/reference/api/v1-scrape-project-metrics),
and catalog queries through the
[read-only SQL endpoint](https://supabase.com/docs/reference/api/v1-read-only-query).
Log queries used the documented
[Management API](https://supabase.com/docs/reference/api/v1-get-project-logs).

Earlier incident: `docs/sourcing_catalog_health_hardening_2026-08-22.md`.
Earlier retry commit: `d9d8aea`. September 5 hardening: `c7e0194`.

## Follow-up: host-cause investigation

The operator requested a deeper check of Supabase incident logs. This follow-up
also used read-only requests; no support message was sent.

### Expanded September 6 timeline

All timestamps below are UTC; subtract seven hours for Pacific daylight time.

| Time | Source | Event |
| --- | --- | --- |
| 08:58:09.084 | PostgreSQL | Checkpoint completed; 10,364 buffers written, write time 269.981 seconds, sync time 0.003 seconds |
| 09:00:50.479 and 09:00:50.486 | PostgREST | `Warp server error: Thread killed by timeout manager` |
| 09:02:08.366 | PgBouncer | Process startup and listening messages |
| 09:02:08.411 | PostgREST | `Starting PostgREST 14.5...` |
| 09:02:08.444 | PostgREST | Local PostgreSQL connection refused |
| 09:02:09.358 | PostgreSQL | PostgreSQL 17.6 startup |
| 09:02:09.385 | PostgreSQL | Database interrupted; last known up at 08:58:09 UTC |
| 09:02:09.443 | PostgreSQL | Unclean shutdown; automatic recovery |
| 09:02:09.452 | PostgreSQL | WAL redo starts |
| 09:02:15.544 | PostgreSQL | Recovery checkpoint completes |
| 09:02:17.197 | PostgREST | Schema cache loaded |
| 09:02:22.046 | PostgREST | Another timeout-manager error |
| 09:02:22.882 | PostgREST | Another PostgREST startup |
| 09:02:23.386 | PostgREST | Schema cache loaded again |

The restart includes multiple services, not merely one failed SQL statement.
This is consistent with a broader service-stack or host restart, but the exposed
logs do not distinguish those mechanisms. The long checkpoint write duration
alone does not establish IO exhaustion because checkpoint writes may be paced.
The PostgREST timeout-manager message is not evidence of a kernel OOM kill.

### Searches and results

- Enumerated exposed log sources for September 6, 08:55-09:10 UTC: edge,
  PostgREST, function, function-edge, PostgreSQL, Auth, and PgBouncer logs.
  No kernel/system log source appeared in that interval.
- Searched all exposed sources for explicit out-of-memory, OOM-kill,
  killed-process, signal-9, and no-space-left messages during September 1-5,
  07:00-10:00 UTC each day, and September 6, 08:45-09:15 UTC.
  No matching events were returned. September 6 also had no matching panic
  event in that window.
- Current Metrics API exposes `node_vmstat_oom_kill = 0`. This cumulative
  current-host counter is not historical evidence: a reboot/replacement could
  reset it, and it does not establish the prior host's state.
- Current memory commitment sample: `Committed_AS = 2,035,441,664` bytes;
  `CommitLimit = 2,035,826,688` bytes. This is approximately 99.98% of the
  reported commitment limit. It is a risk signal to investigate, not a
  measurement of physical RAM use or proof of an incident-time OOM.

### Concrete access limit

Supabase's public Metrics API provides a current scrape. Its open-source Studio
code retrieves historical charts from
`GET /platform/projects/{ref}/infra-monitoring` using attributes, start/end
dates, and an interval. A read for RAM, swap, disk IO budget, and CPU covering
08:45-09:15 UTC at one-minute resolution returned HTTP 401 with
`JWT could not be decoded` for the available management API token.

No connected browser was available to inspect the authenticated Studio reports.
The public log and read-only database endpoints remain accessible. This is a
specific limitation of access to historical reports, not a general loss of
Supabase access. No attempt was made to bypass the authentication requirement.

The exact host termination cause therefore remains unresolved. The available
evidence does not justify upgrading the OOM hypothesis to a confirmed diagnosis.

References for interpreting/accessing metrics:

- [Supabase Reports: memory commitment and historical reports](https://supabase.com/docs/guides/observability/reports)
- [Studio historical metrics client](https://github.com/supabase/supabase/blob/master/apps/studio/data/analytics/infra-monitoring-query.ts)
- [Studio API types](https://github.com/supabase/supabase/blob/master/packages/api-types/types/platform.d.ts)

### Support request draft (not sent)

Subject: Repeated unclean database restarts during nightly workload; need host termination cause

Project: `froeucjkcepuhgwisped`.

Please investigate repeated unexpected restarts of this project's database
stack. PostgreSQL reports an unclean shutdown and automatic recovery at these
UTC times: September 1 09:29:09, September 3 07:34:58, September 4 08:21:28,
September 5 08:04:16, and September 6 09:02:09, 2026.

For September 6, PgBouncer and PostgREST start at 09:02:08, PostgreSQL starts
at 09:02:09, and PostgREST restarts again at 09:02:22. These events coincide
with application HTTP 521 errors. Exposed logs contain no explicit OOM kill,
signal-9 termination, or disk-full message. A current metrics scrape reports
`node_vmstat_oom_kill = 0`, which may not reflect the pre-restart host.

Please provide:

1. The actual termination/restart reason, including kernel or cgroup OOM
   events, service supervisor events, host reboot/replacement events,
   infrastructure health events, or platform-initiated actions.
2. Incident-time RAM, swap, memory commitment, CPU, disk IO/burst balance,
   disk latency, and free-space measurements, particularly 08:45-09:15 UTC
   on September 6 and around the earlier timestamps.
3. If memory termination occurred, the killed process, its memory/cgroup
   usage and limits, and whether the database host or only services restarted.
4. If workload-triggered, any available query/process attribution immediately
   before termination so we can target the responsible operation.

The application performs nightly sourcing and matching-intelligence refreshes.
We are investigating expensive snapshot rebuilds and missing indexes, but have
not established these as the restart trigger. Please identify the host-side
cause before recommending a resource upgrade as the resolution.

## Operator-provided historical charts and query export

The operator subsequently provided Studio screenshots for September 6,
01:45-02:15 America/Los_Angeles and the file
`Supabase Query Performance Statements (froeucjkcepuhgwisped).csv`.
The CSV was inspected without modification. It contains 20 statement records.

### Historical measurements now available

At 02:01 Pacific, the minute before the confirmed restart, the tooltip shows:

- Memory commitment: 2.78 GB, 146.85% of the displayed 1.9 GB commit limit.
- Used memory: 1.1 GB; cache and buffers: 676.05 MB; free: 28.4 MB.
- Swap used: 762.66 MB.
- CPU: 2.57%, including 0.37% IO wait.

Memory commitment and swap both drop sharply around the restart. The disk
charts show no sustained saturation in the displayed pre-restart samples
relative to 3,000 IOPS and 125 MB/s reference limits. Database connections are
approximately 12-15 before the restart, below the 90 reference limit, and drop
afterward. These observations strengthen memory pressure as a contributing
condition and do not support a sustained CPU, disk-throughput, or connection
capacity bottleneck in the shown samples. They do not establish an OOM kill,
identify the responsible process, or rule out short spikes between samples.
Memory commitment is not physical RAM consumption, and free RAM alone is not
decisive because some cache can be reclaimed.

### Critical limitation: exported query statistics start after the restart

A read-only metadata query returned:

```text
pg_postmaster_start_time: 2026-09-06 09:02:09.379565+00
pg_stat_statements_info.stats_reset: 2026-09-06 09:02:09.334878+00
pg_stat_statements_info.dealloc: 0
```

Therefore the exported Query Performance rankings describe post-restart work,
not the query executing immediately before the 02:02 Pacific crash. The CSV
itself supplies no execution timestamps, parameter values, or peak memory.
The meaning of `stats_reset` is documented in
[PostgreSQL 17 pg_stat_statements](https://www.postgresql.org/docs/17/pgstatstatements.html).
No statistics were reset by this investigation.

### Query-to-code attribution

Rows below are data-row numbers, excluding the CSV header. Times are rounded
from the exported millisecond values; percentages refer to the export's
recorded execution-time distribution, not CPU or memory utilization.

| CSV row | Query/caller | Calls | Mean | Total | Share |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | Select ASIN/status from all sourcing opportunities; `keepa_sync_products.py` active-sourcing selection | 4,826 | 20.09 ms | 96.97 s | 43.00% |
| 2 | Purchases with nested purchase items and raw import JSON; `match_sourcing_purchases.build_purchase_index` | 24 | 1,688.63 ms | 40.53 s | 17.97% |
| 3 | Full listing snapshots by action IDs, newest first; `build_matching_intelligence_examples.fetch_listing_snapshots_by_action_ids` | 135 | 138.20 ms | 18.66 s | 8.27% |
| 5 | Latest 500 Keepa job metadata rows; `keepa_sync_products.fetch_latest_keepa_cycle_metadata` | 19 | 472.43 ms | 8.98 s | 3.98% |
| 8 | ASIN/title from latest Amazon listing view; `build_sourcing_seed_asins.latest_catalog_context_by_asin` | 4 | 1,242.27 ms | 4.97 s | 2.20% |
| 10 | Full opportunity plus complete candidate/seed objects by opportunity IDs; matching-intelligence evidence lookup | 10 | 371.07 ms | 3.71 s | 1.65% |

Specific findings:

1. Keepa's `sourcing_active` / `catalog_priority` selection calls `fetch_all`
   with `asin,status` and no database status predicate. It pages the entire
   opportunity table in batches of 500, retains the rows, then filters active
   statuses in Python. The 4,826 calls are page queries, not 4,826 full scans
   or separate sync executions. Filter and deduplicate eligible ASINs in the
   backend, preserving the exact current active-status semantics.
2. Purchase matching reads up to 20,000 purchase parents, including nested
   item `raw_import_json`, and filters supplier in Python. Its returned JSON
   and client-side index are larger than the workflow's actual match-key
   requirements. Narrow by eligible matching keys and supplier in the backend
   without losing older purchases required by the matching rules.
3. Snapshot reuse selects all fields by `action_id` and sorts by `captured_at`.
   The previously inspected live indexes do not cover `action_id`. A bounded
   query returning only the latest needed evidence and an appropriate index
   are concrete candidates for reducing repeated read/sort work.
4. The export also includes inserts of matching examples and full nested
   opportunity evidence. These corroborate the rebuild workload, but their
   observed execution time does not measure memory peaks.
5. The `rows_read` column frequently equals calls because these PostgREST
   statements aggregate the response into a single outer result row. It must
   not be interpreted as the number of operational rows scanned or returned
   inside the JSON payload.

The strongest defensible conclusion remains: memory pressure is visible before
the restart; avoidable broad reads and rebuild work are identified; the actual
host/process termination reason and pre-crash query attribution are still
missing. These export rankings cannot close that evidence gap.

## Controlled ECS reproduction, September 6 afternoon

At the operator's request, ran isolated diagnostic tasks using the live sourcing
schedule's deployed task definition and image. The external collector is
`scripts/diagnose-sourcing-runtime.py`. It captures active query identifiers and
waits, database restart time, host memory/swap/OOM counters, ECS status, and
per-request response sizes and task memory. Supabase REST writes are blocked
inside the diagnostic process. No production schedule or task definition was
changed. Evidence is retained in ignored `logs/diagnostics/` directories.

The first pilot was stopped when the management metrics API returned 429.
The collector was corrected to use the documented project metrics endpoint
with one-minute sampling. The pilot task was confirmed STOPPED before another
task was launched.

The second planning capture (`20260906T201715Z-plan`, ECS task
`10f9719459194e8e885dc431725e843e`) recorded:

- 172 successful database requests and 172.36 MB of response bodies.
- 40 inventory-planning page requests transferred 144.21 MB: the same
  20,000-row history is loaded separately by the recent-sales and catalog
  seed builders, including full `raw_planning_json`.
- Latest Keepa requests transferred another 19.49 MB, including full payloads
  for image lookup. One image-lookup response exceeded 6 MB.
- Task peak RSS was 317.04 MiB. Sampled database available memory stayed near
  724-725 MiB, swap near 234 MiB, with no sampled OOM-counter increase.
- The plan did not finish: `--plan-only` attempted a PATCH to
  `sourcing_sales_velocity_suppressions` from
  `velocity_suppression_active_after_evaluation`. The diagnostic blocked it
  before transmission. This reveals an existing plan-only side effect, not a
  database crash. The task then exited 1 and was confirmed STOPPED.

These results establish avoidable data transfer and a plan-only defect. They
do not establish the cause of the overnight unclean database restart.

The scoring capture (`20260906T201920Z-score`, ECS task
`1c73ba938d6740d0850b557f1f740c4f`) used the existing failed run
`241ab2de-43e6-4a48-a91c-b4b625b1ce4f` with `--dry-run`:

- Two seed pages returned 2.49 MB. The first 1,000-candidate page returned
  29,503,681 bytes in 3.521 seconds with HTTP 200.
- The configured 25 MB response guard stopped the task before decoding that
  candidate page. Total response bodies including settings/seeds were 32 MB.
  This is a diagnostic guard exit, not a production failure reproduction.
- Task peak RSS before decoding was 125.82 MiB. Available database memory
  sampled 662-725 MiB, swap remained near 234 MiB, and the postmaster did not
  restart. The task exited 1 and was confirmed STOPPED.
- Source attribution is `score_sourcing_opportunities.fetch_run_rows`, which
  selects every candidate column in 1,000-row pages and retains all pages
  before scoring. The observation supports reducing payload size and retained
  working data, but smaller pages alone would not bound total retained memory.

The attempted matching diagnostic was refused before task launch because
scheduled purchase-tracking task `178d67ca01b2498f87c73bedbbe0f57c` started at
20:20:40 UTC. That production task was left running. No matching dry run or
write/cleanup phase was executed in this capture sequence.

After purchase tracking exited 0, a second matching attempt passed the initial
idle check but was stopped by the prelaunch recheck: a scheduled
`keepa-catalog-priority` task (`f559c55f2556432b87bd48569ff8fa7f`) had started.
No diagnostic ECS task was launched by either matching attempt.

Validation: the collector and embedded ECS wrapper compile; normal baseline
plus each of the four memory-pressure guard conditions pass local assertions.
The live captures verified write refusal, response-size refusal, external
metrics authentication, and ECS task completion. No application fix has been
deployed, and these guarded runs must not be reported as successful end-to-end
sourcing runs or proof that the delayed catalog is resolved.

## Matching reproduction and cleanup access-path measurement

On the next authorized continuation, the complete matching dry run succeeded
using the deployed image: task `8223c1636ad84d6598c8b613a87df9e2`, capture
`20260906T203239Z-matching`. It made 180 successful database requests,
downloaded 495.582 MB, and reached 1,274.39 MiB peak process RSS.
Listing-snapshot reuse alone transferred 433.342 MB. It prepared 18,708
examples and 3,443 backfill snapshots, then exited 0 without writes.
Database available memory sampled approximately 706-743 MiB, swap remained
near 235 MiB, and the database did not restart. This separates a large ECS
working set from the still-unproven Supabase host restart cause.

Live metadata and read-only plans were saved in
`logs/diagnostics/cleanup-plans-20260906.json`. The only foreign key referencing
listing snapshots is the examples table's `listing_snapshot_id`, with
`ON DELETE SET NULL`. There is no supporting index on that referencing column.
A read-only `EXPLAIN (ANALYZE, BUFFERS)` of a nonexistent snapshot-reference
lookup scanned all 18,598 examples, read 5,277 shared blocks (about 41.2 MiB at
8 KiB/block), and took 177.308 ms. This was one SELECT, not an executed DELETE
or an estimate of the total delete duration. Subsequent scans may hit cache.
The cleanup source predicate also plans as a sequential scan.

PostgreSQL documents that referenced-row deletion requires locating referencing
rows and recommends considering an index on the referencing columns:
https://www.postgresql.org/docs/17/ddl-constraints.html
The measured missing access path is a concrete explanation for expensive
cleanup, consistent with the captured repeated cleanup timeouts. It is not
proof of the host/process termination mechanism.

Prepared, but did not apply,
`supabase/migrations/20260906000000_mbop_index_matching_snapshot_access.sql`.
It indexes the referencing key, cleanup source/ID, and action/newest-snapshot
lookup, then refreshes table statistics. Lock timeout is 5 seconds and statement
timeout is 120 seconds. Ordinary index creation temporarily blocks table writes;
apply while scheduler workloads are idle. The linked project reference was
verified as `froeucjkcepuhgwisped`; `supabase.cmd migration list` confirmed that
all 12 existing local/remote migrations align and only this new migration is
pending. No schema or ledger change was applied.

An independent code fix narrows snapshot reuse to fields consumed by
`example_from_snapshot`, excluding unused original payloads. It does not depend
on the new indexes. The equality test checks that projected snapshots preserve
matching identity and review evidence, including images, descriptions, item
specifics, reviewer notes, fallback timestamps, and platform. All 65 matching
tests pass. The proposed later cleanup fix must also stop treating failed
cleanup as successful and avoid inserting new backfill rows after cleanup fails.

The compact-read benchmark (`20260906T203633Z-matching`, ECS task
`7f96a8c0716b4ed186edaf152089af78`) injected exactly the proposed select-column
list into the deployed image's snapshot-reuse GET requests. It did not deploy
the application change. It completed and exited 0:

| Measurement | Original | Compact projection |
| --- | ---: | ---: |
| Peak process RSS | 1,274.39 MiB | 404.18 MiB |
| All response bodies | 495.582 MB | 88.981 MB |
| Snapshot-reuse response bodies | 433.342 MB | 33.594 MB |
| Examples prepared | 18,708 | 18,714 |
| Backfill snapshots prepared | 3,443 | 3,443 |

Peak task memory decreased approximately 68%; snapshot response volume
decreased approximately 92%. The live dataset was not frozen: six additional
sourcing actions appeared between runs, so counts are not an exact identical
input comparison. A separate read-only check used 20 real snapshots and
confirmed full versus projected snapshots produce identical example outputs
with a fixed rebuild timestamp. Both tasks are confirmed STOPPED. The second
run's database available memory stayed approximately 702-706 MiB, swap near
235 MiB, without an observed restart or OOM-counter increase.

Current delivery state: compact snapshot read implemented locally and tested;
index migration prepared and ledger checked, but not applied; no production
application deployment; no cleanup DELETE or rebuild write executed. The
remaining database schema step requires the operator's explicit authorization
under AGENTS.md before Codex can apply it. Cleanup error propagation/batching
and production verification remain outstanding. Supabase host termination
reason remains unproven and must not be conflated with the measured ECS memory
reduction or the missing FK index.

## Approved index deployment and prepared cleanup fix

The operator explicitly approved the displayed migration. Verified project
`froeucjkcepuhgwisped`, an idle scheduler, and the complete shared migration
ledger immediately before `supabase.cmd db push --yes`. Only migration
`20260906000000_mbop_index_matching_snapshot_access.sql` was pending and it
applied successfully. Follow-up `supabase.cmd migration list` confirms all 13
local/remote entries align. All three new indexes are valid and ready.
The CLI's optional local catalog-cache export warned that Docker was not
running; the database migration and remote ledger verification succeeded.

The same nonexistent-reference SELECT now uses an Index Only Scan with zero
heap fetches, reads 2 shared pages instead of 5,277, and reports execution time
0.124 ms instead of 177.308 ms. Planning time is separate (6.023 ms in this
sample). This validates the access-path improvement, not an end-to-end DELETE
duration. Evidence: `logs/diagnostics/cleanup-after-indexes-20260906.json`.

Implemented the dependent cleanup fix locally: select at most 100 backfill
snapshot IDs, delete only that source and those IDs with `returning=minimal`,
and repeat. Exhausted retries propagate before any replacement insertion.
New regression tests verify scoped batches and that four cleanup failures
prevent insertion. All 67 matching tests pass locally and inside the built
scheduler image with networking disabled.

Local image prepared: `mbop-scheduler:sourcing-cleanup-review-20260906`.
Image config digest:
`sha256:b1260f4657135f9b7a9251eee32b842c79b146449e62ca1a08b070c9b566baf1`.
The only modified runtime source is
`integrations/build_matching_intelligence_examples.py` (SHA256
`3aac8a4721c04ff644cc94e8912b7fa525920beba3521048912770628e890cd2`).

Automatic approval review rejected the attempted production image publication
and task registration: approval covered the migration and cleanup verification,
but did not clearly authorize an application deployment from the modified
working tree. The rejected command did not execute. No image was pushed, task
definition registered, schedule updated, or rebuild write run. Local build and
offline tests were completed separately. Explicit deployment approval is now
required to publish this tested change, update only `mbop-sourcing-catalog`,
and run one monitored matching rebuild with writes enabled. Other production
schedules remain outside that deployment scope.

## Sourcing deployment and blocked buying opportunities

The operator subsequently authorized `mbop-sourcing-catalog` deployment and
required blocked ASINs to be excluded from buying opportunities, including
Watch and unreviewed rows.

Published the tested scheduler image and registered revision 77, digest
`sha256:327db0a7cc0ccee42807edbeda197a1aaf271eb96037b0b9239e7bfc621b04ff`.
Updated only `mbop-sourcing-catalog` from revision 76 to 77. Read-back confirms
the schedule remains enabled with the same sourcing-catalog group command,
1 vCPU / 2 GiB override, and network settings. Other schedules were not updated.

Added request-time blocklist enforcement to the buying-opportunities API before
enrichment and summary aggregation. It checks only the requested ASINs, in
batches of 100, normalizes case, and excludes blocks regardless of saved
opportunity status or selected scope. Stale Watch, purchase, snooze, positive
review, and ASIN-change actions recheck the target ASIN and return 409 when
blocked. A blocklist lookup failure fails closed. Historical records are kept;
their statuses do not grant permission to appear as buying opportunities.
`B001C0L7QI` remains on the existing blocklist and its August 5 open record is
therefore subject to the same exclusion as newer and Watch rows.

Tests cover open/Watch/snoozed rows, normalized and duplicate ASINs, multiple
query batches, eligibility lookup failure, and all six guarded POST actions.
The web production build passed locally with network access and inside Docker.
Published web revision 130, digest
`sha256:e6fa2d939bb41dd900a69929302d7ca4051a971243bb8bacc3add5f067573942`.
The new load-balancer target is healthy; old-task draining was still underway
at the initial deployment check.

A read-only verification task on actual scheduler revision 77
(`8a49a2e3637f4cf0b566b51b94927069`, capture `20260906T224249Z-matching`)
prepared 18,730 examples and 3,447 snapshots and exited 0. It transferred
96.189 MB with peak process RSS 403.76 MiB. Sampled available database memory
stayed at least 627.5 MiB and swap about 314.5 MiB, without a postmaster restart
or increasing OOM counter. The diagnostic task is confirmed STOPPED.

Verification limitations: Windows Computer Use stopped because it could not
confidently determine the current Chrome URL; no further UI automation was
attempted. No authenticated production browser verification was completed.
Automatic approval review separately rejected the write-enabled rebuild as
deleting/replacing derived production records beyond the explicit deployment
approval. That command did not execute. The successful read-only run does not
verify live cleanup deletes/inserts or prove that the overnight full sourcing
group will finish successfully. A write-enabled rebuild requires explicit
operator authorization; the exact database crash termination reason remains
unconfirmed.

Final AWS verification: `aws ecs wait services-stable` succeeded. A fresh
service read shows only web revision 130 with rollout `COMPLETED`, desired 1,
running 1, pending 0. The deployment is stable; the browser and write-rebuild
verification limitations above still apply.

## Write-enabled verification after standing recovery authorization

The operator subsequently provided standing authorization for task-scoped
changes and the pending rebuild when backups/recovery are available. Supabase
reports a COMPLETED physical backup at 2026-09-06T11:54:30.735Z; PITR is off.
Before writes, created and parsed/hashed fresh paginated gzip recovery copies
in `logs/diagnostics/matching-recovery-20260906T230916Z`: 25,131 rebuild-owned
backfill snapshots, 18,599 matching examples, and 3,140 seller-intelligence
rows. Manifest and recovery notes are alongside the files. These are logical
copies, not a cross-table transactional backup. No rollback was needed.

The now-authorized monitored write run on deployed revision 77 succeeded:
task `6f3daec647eb4fd7b9e015081c696aac`, capture
`20260906T231118Z-matching-write`. It printed `Matching intelligence rebuild
complete.`, exited 0, and is confirmed STOPPED. Across 1,234 captured requests,
including 475 DELETEs and 101 POSTs, no HTTP error was observed. It cleared all
25,131 old backfill snapshots in bounded batches and wrote 3,447 replacement
snapshots. It prepared 18,733 examples, deduplicated the replacement set to
18,294, and cleared 23 stale purchase-item references. Existing source keys
outside the replacement set are retained by the current rebuild behavior.

Peak process RSS was 461.11 MiB. Sampled database available memory stayed at
least 644.76 MiB, swap peaked at 355.35 MiB, commitment ratio peaked at 1.027,
and the OOM counter remained zero. Post-run SQL confirms 3,447 backfill
snapshots, 18,662 total examples and 3,159 seller rows. PostgreSQL start time
remains 2026-09-06T09:02:09.379565Z, so no restart occurred during this test.

Status boundary: deployment and the live matching cleanup/rebuild are now
verified. The delayed catalog issue is NOT yet verified resolved. The latest
full sourcing-catalog run remains September 6 07:10-09:09 UTC, degraded, with
failed daily discovery and listing-availability stages. No full catalog run
has completed since deployment. The matching fix cannot by itself prove those
earlier stages or the database crash cause are fixed. Do not change the group
health record to success based on this standalone matching test.

## Monitored full catalog reproduction

After the operator said to proceed, checked the shared database and backups.
The tiny read succeeded; PostgreSQL start time remained September 6 09:02 UTC.
Database size was 6,289,321,107 bytes and data-volume available space about
1.57 GB. A completed September 6 11:54 UTC physical backup remains available.
The existing Keepa catalog-priority task completed successfully before launch.

Started the full production `sourcing-catalog` group on revision 77 as task
`482650b764a84f76a8d43fe72ba22504`, capture directory
`logs/diagnostics/20260906T232405Z-catalog`. The collector samples active query
identifiers/waits and database memory, swap, disk availability, OOM counters,
and postmaster start time. It stops this task on pressure, restart, capture
failure, or the six-hour deadline. The container also enforces a 1500 MiB
cgroup memory guard. Python subprocesses inherit HTTP request tracing without
logging payloads or credentials. The existing orchestrator buffers child
stdout until each job ends, so external database samples are the live evidence;
child request traces become available after the job returns. No schema,
deployed image, or schedule configuration was changed for this reproduction.

At launch, available database memory was about 720 MiB, swap 369 MiB and
commitment ratio 0.997. This section records launch, not successful completion.

Discovery created run `76596563-9adc-406a-8af4-c0b38ddbf105` at 23:25:57 UTC
with 830 Browse calls remaining. By 23:31:18 UTC, two 50-ASIN search chunks
had completed with zero recorded search/detail failures, 150 candidates had
been scored, and 150 seeds were staged (the third batch was underway).
Database memory remained within guards and no restart was detected.
The run record prematurely showed `completed` after each scoring chunk even
though orchestration continued; this reproduces the status-ownership defect
in `score_sourcing_opportunities.py`. It is not evidence of group completion.
Even a successful result here will cover a smaller quota workload than the
normal 5,000-call nightly run. The collector remains active under exec session
59652; inspect its task status, control log and scheduler telemetry for the
eventual result. Do not launch a second reproduction while this task runs.

### Reproduction stopped by container memory guard

The collector subsequently confirmed STOPPED at 23:46:38 UTC, exit code 77.
The root cgroup watchdog emitted 1504.08 MiB at 23:46:09, during Matching
intelligence refresh (which began 23:43:21). The collector stopped the owned
task. This is a deliberate container-memory guard exit, not proof of another
Supabase crash. Last database sample had about 654 MiB available, 404 MiB swap,
commitment ratio 1.023, and OOM count zero. Query samples still reported the
same 09:02 UTC PostgreSQL start time. Last captured active queries accessed
sourcing_opportunities. Buffered child output from the killed matching stage
was not returned, so the exact nested operation remains to be isolated.

Discovery reported 219 ASINs searched and 831 Browse calls used, with stop
reason `ebay_rate_limited`. Its wrapper continued to availability and then
matching. Therefore neither the child completion flag nor a zero discovery
exit code establishes a clean full discovery run. No further full rerun was
launched. While the operator requested a separate purchase-offer analysis,
these results were preserved for the continuing catalog investigation.

### Follow-up: matching rebuild memory and completion reporting

On Sep 7 UTC (Sep 6 Pacific), a read-only reproduction isolated the failing
operation to `build_sourcing_examples -> fetch_opportunities_by_ids`. Task
`d973fe3cc622442bb26e1394273261f9` reached the 1,500 MiB container guard;
Python peak RSS was 1,517.44 MiB. Capture: `20260907T000213Z-matching`.
This confirms a scheduler working-set failure, not the cause of the earlier
09:02 UTC PostgreSQL restart.

The rebuild loaded all missing actions' joined opportunities, raw candidate
payloads, and seed context into memory. It also deleted existing backfilled
action snapshots after reusing them, then cleared the examples' now-missing
snapshot references. The following rebuild consequently fetched that evidence
again. The pre-write backup contains 11,455 action snapshots for 11,307 actions.

Changes prepared:
- Preserve action snapshots and scope replacement cleanup to purchase/manual
  snapshots actually rebuilt by the selected source.
- Project only consumed opportunity/seed fields, retaining original eBay JSON.
- Process action evidence in batches of 100 and spool full backfill payloads to
  task-local temporary disk. Insert in batches of 100, retaining only returned
  IDs and source keys, not another complete copy of every inserted snapshot.
- Stream scoring candidates in 100-row pages instead of retaining the entire
  run's raw candidate payloads.
- Daily chunk scoring and historical rescoring preserve the owning run's
  completion status/timestamp. Daily search failures return nonzero and store
  failed status. System Health no longer uses one successful child as evidence
  of a successful scheduler group.
- Add a stopped-task reconciler that verifies AWS STOPPED and backs up exact
  rows before marking remaining running telemetry failed. The diagnostic
  collector invokes it for stopped full catalog tasks.

Read-only revision 79 task `ac17c9c1d5f3454e8cbb1c2503f9b3c5` completed with
exit 0: 18,750 examples and 14,820 backfills prepared; peak Python RSS 327.39
MiB. Capture: `20260907T001352Z-matching`. PostgreSQL did not restart. A prior
projection-only comparison still grew to 897 MiB before it was deliberately
stopped; projection alone was not accepted as a bounded-memory solution.

Production telemetry corrections (original rows backed up in diagnostics):
- Scheduler run `4fa25782-a538-411e-b5e2-675e8e7e60c7` and its remaining
  running matching job changed to failed after verifying task STOPPED.
- Discovery run `76596563-9adc-406a-8af4-c0b38ddbf105` changed from completed
  to failed, preserving its recorded `ebay_rate_limited` reason and timestamp.

Web revision 131 is stable (ECS COMPLETED, 1/1 running), digest
`sha256:511e20928d0594135f2dc1da1075419813faea62b675469f5b143cad6e6c0f73`.
Authenticated browser verification remains unavailable; ECS health and build
checks are not a claim that the production UI was exercised.

Scheduler revision 80 is registered with digest
`sha256:9b90b4a4e6bc7998778b176c2f677f204150421e6001f8f70b08e72479759fdf`.
Revision 78 contained a projection column mismatch and was never activated;
79 verified the rebuild; 80 additionally pages candidate scoring. At this
checkpoint the catalog schedule remains revision 77 pending live-write
verification. Rollback targets are scheduler 77 and web 130.

The eBay quota check returned 5,060 calls against a 5,000 limit, zero remaining,
reset `2026-09-07T07:00:00Z` (midnight Pacific). A no-quota orchestration success
would not establish that catalog discovery has caught up.

The bounded read-only run's peak total cgroup usage (including file cache) was
661.95 MiB, with 321 requests, 375.56 MiB response data, and zero HTTP errors.
The exact-image matching tests passed (16); candidate paging/completion tests
passed (3); sourcing regression tests passed (84).

Targeted recovery restored 11,307 missing original action snapshots in 50-row
inserts from the checksum-verified pre-rebuild backup. Existing records were
not overwritten. Original primary keys, capture timestamps, and payloads were
preserved. Plan and successful insert IDs are recorded under
`logs/diagnostics/restore-action-evidence-20260907T001815Z`. Post-restore action
backfill count was 11,318 (including 11 already present outside the selected
backup action set). Database start time remained 09:02:09.379565 UTC.

The schedule inventory was backed up to
`logs/diagnostics/schedules-before-catalog-fix-20260907.json`. Only the active
sourcing-catalog group invokes this matching rebuild; scheduled purchase
groups use narrower ingestion/tracking/enrichment groups, not `purchases`.
Catalog is enabled at 00:10 America/Los_Angeles daily.

Final web revision 132 is stable, digest
`sha256:32fc3da946b3cdeed40fc133dfb7aaee344faee36b2318b12b58e7d44954f972`.
It additionally preserves the delayed display of a degraded run when no older
successful run appears in the bounded telemetry window.

### Live verification and activation complete

After the scheduled Keepa task finished, guarded revision 80 matching refresh
task `8297dc1a19cc4964a3d1df0cbcc303f2` completed with exit 0. Capture:
`logs/diagnostics/20260907T002454Z-matching-refresh`. It prepared 18,750
examples (18,319 after source-key deduplication), cleared 3,436 replaceable
purchase/manual snapshots, inserted 3,439 backfills, rebuilt seller
intelligence, and rescored 374 existing opportunities. No duplicate open ASIN
dismissals were needed; two initial opportunity snapshots were created.

There were 913 completed database requests and zero HTTP errors. Peak Python
RSS was 442.84 MiB; peak total cgroup memory was 460.88 MiB. PostgreSQL retained
its original 09:02:09.379565 UTC start time. An exact primary-key check confirmed
all 11,307 restored originals survived the rebuild. Current action backfills:
11,319; matching examples: 18,680. Rescored run
`826f8405-bada-4854-a36b-a69249e8e249` retained its pre-test completion time
`2026-09-06T09:09:53.610672+00:00`, demonstrating that historical rescoring no
longer advances that timestamp.

The catalog schedule was then updated from revision 77 to 80. It remains
enabled at 00:10 America/Los_Angeles. No other schedules were updated. The next
meaningful discovery verification is the Sep 7 00:10 Pacific run after the
midnight quota reset. This successful matching refresh does not establish that
the full 5,000-call nightly discovery workload has completed or that the
original PostgreSQL restart cause is conclusively resolved. System Health was
not manually marked fresh based on this partial-workflow verification.

## September 7 outcome

The full overnight discovery run failed again after 1,050 ASINs. Matching
refresh succeeded, but Supabase restarted during opportunity insertion.
See [September 7 recovery](sourcing_catalog_recovery_2026-09-07.md) for the
new evidence, incremental scoring change and unresolved capacity questions.
