-- Supabase-backed telemetry for ECS/EventBridge scheduler runs.
-- Apply this before wiring run_all_syncs.py or System Health to these tables.

create table if not exists public.scheduler_job_definitions (
  job_key text primary key,
  job_name text not null,
  default_group_name text,
  command text not null,
  enabled boolean not null default true,
  blocking boolean not null default true,
  timeout_seconds integer,
  expected_cadence_minutes integer,
  stale_after_minutes integer,
  domain text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scheduler_runs (
  run_id uuid primary key default gen_random_uuid(),
  group_name text not null,
  status text not null check (status in ('running', 'ok', 'degraded', 'failed', 'blocked', 'cancelled')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  runtime_seconds numeric,
  trigger_source text,
  ecs_task_arn text,
  eventbridge_schedule_name text,
  container_cpu integer,
  container_memory integer,
  error_summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.scheduler_run_jobs (
  run_job_id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.scheduler_runs(run_id) on delete cascade,
  job_key text references public.scheduler_job_definitions(job_key),
  group_name text not null,
  job_name text not null,
  command text not null,
  status text not null check (status in ('running', 'ok', 'skipped', 'failed', 'blocked')),
  blocking boolean not null default true,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  runtime_seconds numeric,
  rows_read integer,
  rows_inserted integer,
  rows_updated integer,
  rows_deleted integer,
  rows_skipped integer,
  external_api_calls integer,
  retry_count integer,
  rate_limit_count integer,
  log_bytes integer,
  error_summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.scheduler_domain_freshness (
  domain text primary key,
  source_table text,
  latest_source_at timestamptz,
  last_success_run_id uuid references public.scheduler_runs(run_id) on delete set null,
  last_success_at timestamptz,
  stale_after_minutes integer,
  status text not null default 'unknown' check (status in ('fresh', 'stale', 'unknown', 'failed')),
  detail text,
  updated_at timestamptz not null default now()
);

create table if not exists public.scheduler_locks (
  lock_name text primary key,
  group_name text,
  run_id uuid references public.scheduler_runs(run_id) on delete set null,
  owner text,
  acquired_at timestamptz not null default now(),
  expires_at timestamptz not null,
  heartbeat_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists idx_scheduler_runs_group_started
  on public.scheduler_runs (group_name, started_at desc);

create index if not exists idx_scheduler_runs_status_started
  on public.scheduler_runs (status, started_at desc);

create index if not exists idx_scheduler_run_jobs_run
  on public.scheduler_run_jobs (run_id, started_at);

create index if not exists idx_scheduler_run_jobs_job_started
  on public.scheduler_run_jobs (job_name, started_at desc);

create index if not exists idx_scheduler_run_jobs_status_started
  on public.scheduler_run_jobs (status, started_at desc);

grant usage on schema public to service_role;

grant select, insert, update, delete on public.scheduler_job_definitions to service_role;
grant select, insert, update, delete on public.scheduler_runs to service_role;
grant select, insert, update, delete on public.scheduler_run_jobs to service_role;
grant select, insert, update, delete on public.scheduler_domain_freshness to service_role;
grant select, insert, update, delete on public.scheduler_locks to service_role;
