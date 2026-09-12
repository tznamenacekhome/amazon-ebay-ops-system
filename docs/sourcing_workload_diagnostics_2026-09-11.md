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
