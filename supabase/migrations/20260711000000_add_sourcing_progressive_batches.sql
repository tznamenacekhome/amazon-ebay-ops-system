-- Progressive sourcing batches for resumable "find 100 more" opportunity runs.
-- Mirrored from sql/2026-07-11_add_sourcing_progressive_batches.sql for Supabase CLI migration pushes.

create table if not exists public.sourcing_opportunity_batches (
  batch_id uuid primary key default gen_random_uuid(),
  sourcing_run_id uuid not null references public.sourcing_runs(sourcing_run_id) on delete cascade,
  batch_sequence integer not null,
  status text not null default 'running',
  requested_opportunity_count integer not null default 100,
  qualifying_opportunity_count integer not null default 0,
  cumulative_qualifying_count integer not null default 0,
  seeds_searched integer not null default 0,
  cumulative_seeds_searched integer not null default 0,
  seeds_remaining integer,
  candidates_found integer not null default 0,
  hard_blocked_count integer not null default 0,
  profitability_reject_count integer not null default 0,
  duplicate_count integer not null default 0,
  api_call_count integer not null default 0,
  stop_reason text,
  funnel_json jsonb not null default '{}'::jsonb,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint sourcing_opportunity_batches_sequence_unique
    unique (sourcing_run_id, batch_sequence),
  constraint sourcing_opportunity_batches_status_check
    check (status in ('running', 'completed', 'failed'))
);

create table if not exists public.sourcing_opportunity_batch_items (
  batch_item_id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.sourcing_opportunity_batches(batch_id) on delete cascade,
  sourcing_run_id uuid not null references public.sourcing_runs(sourcing_run_id) on delete cascade,
  opportunity_id uuid not null references public.sourcing_opportunities(opportunity_id) on delete cascade,
  asin text not null,
  ebay_item_id text,
  score numeric,
  opportunity_type text,
  presented_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  constraint sourcing_opportunity_batch_items_unique_run_opportunity
    unique (sourcing_run_id, opportunity_id)
);

create index if not exists sourcing_opportunity_batches_run_sequence_idx
  on public.sourcing_opportunity_batches (sourcing_run_id, batch_sequence desc);

create index if not exists sourcing_opportunity_batches_status_idx
  on public.sourcing_opportunity_batches (status, started_at desc);

create index if not exists sourcing_opportunity_batch_items_batch_idx
  on public.sourcing_opportunity_batch_items (batch_id);

create index if not exists sourcing_opportunity_batch_items_run_idx
  on public.sourcing_opportunity_batch_items (sourcing_run_id, presented_at desc);

grant all on table public.sourcing_opportunity_batches to service_role;
grant all on table public.sourcing_opportunity_batch_items to service_role;

comment on table public.sourcing_opportunity_batches is
'Durable sourcing opportunity batches used by the progressive Find 100 More workflow.';

comment on table public.sourcing_opportunity_batch_items is
'Stable membership of scored sourcing opportunities presented in each progressive batch.';
