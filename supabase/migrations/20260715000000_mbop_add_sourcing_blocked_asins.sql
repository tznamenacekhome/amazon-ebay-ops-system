create table if not exists public.sourcing_blocked_asins (
  asin text primary key,
  reason text,
  notes text,
  source_opportunity_id uuid references public.sourcing_opportunities(opportunity_id) on delete set null,
  source_action_id uuid references public.sourcing_actions(action_id) on delete set null,
  blocked_by text,
  blocked_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_sourcing_blocked_asins_blocked_at
  on public.sourcing_blocked_asins (blocked_at desc);

grant select, insert, update, delete on public.sourcing_blocked_asins to service_role;
