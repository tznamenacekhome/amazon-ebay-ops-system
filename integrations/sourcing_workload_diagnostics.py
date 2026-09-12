"""Bounded read-only workload correlation; never export SQL text or parameters.

Runs in the catalog parent only. Failures back off and never block sourcing.
These are query timing/IO observations, not per-query memory measurements.
"""
from __future__ import annotations

import os
import time

import requests

from .scheduler_diagnostics import emit

PROJECT_URL = "https://froeucjkcepuhgwisped.supabase.co"
QUERY_URL = "https://api.supabase.com/v1/projects/froeucjkcepuhgwisped/database/query/read-only"

# pg_stat_activity is an in-memory activity view. Include idle-in-transaction
# sessions and background workers, but never return query text or client details.
ACTIVITY_SQL = """/* mbop_workload_diagnostics */
with activity as materialized (
 select pid, query_id::text, backend_type, state, wait_event_type, wait_event,
        extract(epoch from (clock_timestamp()-query_start)) as query_seconds,
        extract(epoch from (clock_timestamp()-xact_start)) as transaction_seconds
 from pg_catalog.pg_stat_activity
 where datname=current_database() and pid<>pg_backend_pid()
), active as (
 select * from activity where state is distinct from 'idle'
 order by query_seconds desc nulls last limit 24
), sessions as (
 select backend_type, state, wait_event_type, wait_event, count(*) as sessions
 from activity group by 1,2,3,4 order by count(*) desc limit 32
), jobs as (
 select run_id, job_key, group_name, status, started_at
 from public.scheduler_run_jobs where status='running'
 and started_at > now()-interval '24 hours' order by started_at desc limit 32
)
select clock_timestamp() as sampled_at, pg_postmaster_start_time() as postmaster_started_at,
 (select jsonb_build_object('temp_bytes', temp_bytes, 'temp_files', temp_files,
   'deadlocks', deadlocks, 'stats_reset', stats_reset)
  from pg_catalog.pg_stat_database where datname=current_database()) as database_counters,
 (select count(*) from activity) as session_count,
 coalesce((select jsonb_agg(a) from active a),'[]'::jsonb) as active,
 coalesce((select jsonb_agg(s) from sessions s),'[]'::jsonb) as sessions,
 coalesce((select jsonb_agg(j) from jobs j),'[]'::jsonb) as scheduler_jobs
"""

# Fetch up to 2,000 shared-memory statistics entries, not application rows.
# 2,001st entry detects truncation; no SQL text leaves PostgreSQL. stats_since
# and stats_reset prevent counter resets/evictions from becoming false deltas.
STATEMENTS_SQL = """/* mbop_workload_diagnostics */
select userid::text, dbid::text, toplevel, queryid::text as query_id,
 stats_since, calls, total_exec_time, rows, shared_blks_read,
 shared_blks_hit, temp_blks_read, temp_blks_written,
 (select stats_reset from extensions.pg_stat_statements_info) as stats_reset,
 position('mbop_workload_diagnostics' in query)>0 as collector
from extensions.pg_stat_statements
where dbid=(select oid from pg_catalog.pg_database where datname=current_database())
order by total_exec_time desc, userid, queryid, toplevel limit 2001
"""

COUNTERS = ("calls", "total_exec_time", "rows", "shared_blks_read",
            "shared_blks_hit", "temp_blks_read", "temp_blks_written")
IDENTITY = ("userid", "dbid", "toplevel", "query_id", "stats_since", "stats_reset")


def statement_deltas(previous, current):
    old = {tuple(row.get(k) for k in IDENTITY): row for row in previous}
    changes = []
    baselines = 0
    for row in current:
        if row.get("collector"):
            continue
        prior = old.get(tuple(row.get(k) for k in IDENTITY))
        if prior is None:
            baselines += 1
            continue
        values = {k: row[k] - prior[k] for k in COUNTERS}
        if any(v < 0 for v in values.values()):
            baselines += 1
            continue
        if any(values.values()):
            changes.append({**{k: row.get(k) for k in IDENTITY}, **values})
    # Preserve both highest elapsed-time and highest spill entries.
    top = sorted(changes, key=lambda r: r["total_exec_time"], reverse=True)[:15]
    spill = sorted(changes, key=lambda r: r["temp_blks_written"], reverse=True)[:5]
    for row in spill:
        if row not in top:
            top.append(row)
    return {"changed_statements": len(changes), "new_baselines": baselines, "top_deltas": top}


class WorkloadSampler:
    def __init__(self, session):
        self.session = session
        self.previous = []
        self.previous_at = None

    def query(self, sql):
        # Stream with a hard response cap. Never print errors containing query
        # payloads or HTTP headers, even on management API failures.
        with self.session.post(QUERY_URL, json={"query": sql}, timeout=8, stream=True) as response:
            response.raise_for_status()
            body = bytearray()
            for part in response.iter_content(65536):
                body.extend(part)
                if len(body) > 2_000_000:
                    raise ValueError("Diagnostic response exceeds cap")
            import json
            result = json.loads(body)
            if not isinstance(result, list):
                raise ValueError("Unexpected diagnostic response")
            return result

    def sample(self, *, statements=False):
        activity = self.query(ACTIVITY_SQL)
        if len(activity) != 1:
            raise ValueError("Unexpected activity response")
        emit("database_workload", **activity[0])
        if statements:
            rows = self.query(STATEMENTS_SQL)
            sampled_at = time.monotonic()
            truncated = len(rows) > 2000
            rows = rows[:2000]
            emit("database_statement_deltas", **statement_deltas(self.previous, rows),
                 interval_seconds=None if self.previous_at is None else round(sampled_at-self.previous_at, 3),
                 sampled_statements=len(rows), truncated=truncated)
            self.previous, self.previous_at = rows, sampled_at


def workload_loop():
    token = os.getenv("SUPABASE_ACCESS_TOKEN") or os.getenv("SUPABASE_MANAGEMENT_ACCESS_TOKEN")
    if os.getenv("SUPABASE_URL", "").rstrip("/") != PROJECT_URL or not token:
        emit("database_workload_unavailable", reason="missing_or_unexpected_configuration")
        return
    with requests.Session() as session:
        session.headers.update({"Authorization": "Bearer " + token,
                                "User-Agent": "MBOP-readonly-workload-diagnostics/1.0"})
        sampler = WorkloadSampler(session)
        next_statements = 0
        while True:
            try:
                statements = time.monotonic() >= next_statements
                sampler.sample(statements=statements)
                if statements:
                    next_statements = time.monotonic() + 60
            except Exception as error:
                emit("database_workload_error", error_type=type(error).__name__)
                time.sleep(60)
                continue
            time.sleep(15)
