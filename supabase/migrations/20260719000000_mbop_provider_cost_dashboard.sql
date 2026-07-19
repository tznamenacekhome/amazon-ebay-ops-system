-- Provider-native cost and usage storage for the MBOP provider-cost dashboard.
-- Monetary values must come from supported provider APIs/reports or from
-- reproducible calculations over automatically collected records.

create table if not exists public.provider_cost_sync_runs (
  sync_run_id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('aws', 'supabase', 'easypost')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null check (status in ('running', 'ok', 'partial', 'failed')),
  requested_period_start date,
  requested_period_end date,
  source_type text not null check (source_type in ('api', 'report', 'calculated')),
  records_read integer not null default 0,
  records_written integer not null default 0,
  error_summary text,
  retry_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.provider_billing_periods (
  provider_billing_period_id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('aws', 'supabase', 'easypost')),
  external_account_id text not null default 'default',
  period_start date not null,
  period_end date not null,
  billing_cycle_type text not null,
  period_status text not null check (period_status in ('current', 'completed', 'finalized', 'partial', 'unavailable')),
  currency text,
  source text not null check (source in ('api', 'report', 'calculated')),
  coverage_status text not null check (coverage_status in ('complete', 'partial', 'unavailable')),
  provider_reported_total numeric(12, 4),
  calculated_total numeric(12, 4),
  forecast_total numeric(12, 4),
  finalized_total numeric(12, 4),
  last_synchronized_at timestamptz,
  raw_source_reference text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint provider_billing_periods_period_order check (period_end > period_start),
  constraint provider_billing_periods_unique_period unique (
    provider,
    external_account_id,
    period_start,
    period_end,
    billing_cycle_type
  )
);

create table if not exists public.provider_cost_line_items (
  provider_cost_line_item_id uuid primary key default gen_random_uuid(),
  provider_billing_period_id uuid not null references public.provider_billing_periods(provider_billing_period_id) on delete cascade,
  provider text not null check (provider in ('aws', 'supabase', 'easypost')),
  category text not null,
  subcategory text,
  service text,
  project_or_resource_id text,
  usage_type text,
  quantity numeric(18, 6),
  unit text,
  unit_price numeric(18, 8),
  cost numeric(12, 4),
  credits_or_adjustments numeric(12, 4),
  source text not null check (source in ('api', 'report', 'calculated')),
  provider_record_id text not null,
  usage_start timestamptz,
  usage_end timestamptz,
  raw_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint provider_cost_line_items_unique_record unique (
    provider_billing_period_id,
    provider,
    provider_record_id
  )
);

create table if not exists public.provider_usage_snapshots (
  provider_usage_snapshot_id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('aws', 'supabase', 'easypost')),
  external_account_id text not null default 'default',
  project_or_resource_id text,
  metric_name text not null,
  metric_value numeric(18, 6),
  metric_unit text,
  source text not null check (source in ('api', 'report', 'calculated')),
  period_start timestamptz,
  period_end timestamptz,
  captured_at timestamptz not null default now(),
  raw_metadata jsonb not null default '{}'::jsonb,
  provider_record_id text,
  created_at timestamptz not null default now()
);

create table if not exists public.provider_raw_payloads (
  provider_raw_payload_id uuid primary key default gen_random_uuid(),
  provider text not null check (provider in ('aws', 'supabase', 'easypost')),
  source_type text not null check (source_type in ('api', 'report', 'calculated')),
  external_account_id text not null default 'default',
  provider_record_id text,
  captured_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  redaction_notes text,
  created_at timestamptz not null default now()
);

create index if not exists idx_provider_billing_periods_provider_period
  on public.provider_billing_periods (provider, period_start desc);

create index if not exists idx_provider_cost_line_items_period
  on public.provider_cost_line_items (provider_billing_period_id, category, service);

create index if not exists idx_provider_usage_snapshots_provider_metric
  on public.provider_usage_snapshots (provider, metric_name, captured_at desc);

create unique index if not exists provider_usage_snapshots_unique_record
  on public.provider_usage_snapshots (
    provider,
    external_account_id,
    metric_name,
    captured_at,
    coalesce(provider_record_id, '')
  );

create index if not exists idx_provider_cost_sync_runs_provider_started
  on public.provider_cost_sync_runs (provider, started_at desc);

grant usage on schema public to service_role;
grant select, insert, update, delete on public.provider_cost_sync_runs to service_role;
grant select, insert, update, delete on public.provider_billing_periods to service_role;
grant select, insert, update, delete on public.provider_cost_line_items to service_role;
grant select, insert, update, delete on public.provider_usage_snapshots to service_role;
grant select, insert, update, delete on public.provider_raw_payloads to service_role;
