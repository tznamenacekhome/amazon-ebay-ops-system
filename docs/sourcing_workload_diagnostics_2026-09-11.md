# Sourcing workload correlation

The catalog parent now runs a read-only workload collector in AWS alongside
the existing memory sampler. It uses the already-configured Supabase management
credential and the documented `/database/query/read-only` endpoint. No schema,
database configuration, statistics resets, or new credential grants are needed.

- Every approximately 15 seconds: active query IDs, query/transaction age,
  backend types, waits, session counts, database temporary-file counters,
  PostgreSQL start time, and up to 32 running MBOP scheduler jobs started in
  the last 24 hours.
- Every approximately 60 seconds: at most 2,000 `pg_stat_statements` entries,
  returning numeric counters and identities only. Logs retain the 15 largest
  elapsed-time deltas and five largest temporary-write deltas. Truncation is
  explicit. First-seen entries, evictions, and resets establish a new baseline;
  historical totals are never represented as work during the current interval.
- Every failed capacity gate now records the measured memory/swap/disk values
  alongside its reason, including the final exhausted attempt.

CloudWatch events `database_workload`, `database_statement_deltas`, and the
existing `database_pressure`/`database_guard_wait` share timestamps and the
catalog scheduler run ID. Job IDs/group names identify MBOP overlap. Query IDs
can be looked up later in PostgreSQL for a targeted query-plan investigation.
The collector does not export SQL text, parameter values, client addresses,
headers, or credentials. It does not read College Planner application rows.

The collector runs only in the catalog parent; children do not multiply its
polling. Requests use an eight-second timeout, a 2 MB response cap, and a
60-second backoff after errors. Collection failures do not block sourcing and
do not replace the existing fail-closed capacity gate. Output survives in
`/ecs/mbop-scheduler` under its existing retention policy.

This is sampled correlation, not a measurement of memory per query or proof of
which process caused a memory spike. Short queries may fall between samples;
completed-query timing/spill deltas supplement the active samples. Background
jobs outside MBOP have query IDs/backend activity but no MBOP scheduler label.
The collector starts and stops with the catalog task. Metrics do not establish
remaining Supabase Disk IO Budget; free disk space is a separate measurement.

Counter semantics follow PostgreSQL 17 documentation:
[statement statistics](https://www.postgresql.org/docs/17/pgstatstatements.html)
and [activity/statistics views](https://www.postgresql.org/docs/17/monitoring-stats.html).

## Deployment and first live evidence

Source commit `ed6f2e11ae21`; scheduler revision 89 pins image
`sha256:273a7adf0e1ec27f5a326e9cb528a0f70cf25da6fcb9cf7a0c1204f6dfb8bf00`.
The task was cloned from the catalog's revision 86, retaining its runtime
configuration. All 20 MBOP schedules were compared before/after: only
`mbop-sourcing-catalog` changed from revision 86 to 89. Its cadence is unchanged.
Rollback target is revision 86. The dirty build suffix reflects the unrelated
untracked wholesale-discovery document; deployed integration changes are committed.

All 20 targeted tests passed both locally and in the Linux image. AWS read-only
smoke task `20a426ac14014256b5023bb50a74ab8d` exited zero and emitted workload,
statement baseline, and memory records plus successful child/grandchild logging
and a tiny database read. No schema was applied.

The authorized full sourcing run launched as task
`0830d53b18b149b4be21f85108d337f9`, scheduler run
`a2971730-be17-4feb-8f59-b25b5d1ac161`, starting September 11 at 18:57 Pacific.
No other active scheduler telemetry was present at launch. The initial metrics
passed existing guards; disk remained tight at approximately 1.38 GiB free.
This records a launch and early observations, not a completed run or a durable fix.

The first 61.6-second statement interval identified query
`-4429572817857345153`: 40 calls, 8.90 seconds cumulative execution time and
480,408 temporary blocks written (approximately 3.66 GiB with 8 KiB blocks).
Its normalized shape reads `amazon_inventory_planning_snapshots`, including
`raw_planning_json`, ordered by `captured_at DESC`, with limit/offset pagination.
It maps to `latest_inventory_planning_by_asin` in `build_sourcing_seed_asins.py`,
which reads up to 20,000 rows and is used in both seed-building paths.
A read-only EXPLAIN (without ANALYZE) confirms a parallel sequential scan,
sort, and gather merge for a late page. This is measured startup amplification,
not proof of the query's memory footprint or the cause of prior guard failures.
No query optimization or guard change is bundled into this instrumentation release.

Evidence and rollback metadata are retained under the ignored
`logs/diagnostics/workload-deploy-20260911/` directory; the live CloudWatch stream
is `scheduled/mbop-scheduler/0830d53b18b149b4be21f85108d337f9`.
