-- MBOP sourcing catalog identity and velocity suppression.
-- Additive, read-only marketplace boundary: these tables/cache rows are MBOP
-- operational state only and do not write to Amazon or eBay.

create table if not exists public.amazon_catalog_item_identity_snapshots (
  asin text primary key,
  marketplace_id text,
  product_type text,
  normalized_platform text,
  normalized_edition text,
  normalized_release_date date,
  normalized_release_year integer,
  normalized_region text,
  normalized_format text,
  package_quantity integer,
  variation_parent_asins jsonb not null default '[]'::jsonb,
  variation_child_asins jsonb not null default '[]'::jsonb,
  variation_theme jsonb,
  relevant_attributes_json jsonb not null default '{}'::jsonb,
  raw_catalog_json jsonb not null default '{}'::jsonb,
  source_version text not null default 'spapi_catalog_items_2022_04_01',
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.amazon_catalog_item_identity_snapshots is
'Cached read-only Amazon Catalog Items identity evidence for sourcing diagnostics. Exact-ASIN structured evidence is preferred over title inference.';

create index if not exists amazon_catalog_item_identity_snapshots_product_type_idx
  on public.amazon_catalog_item_identity_snapshots (product_type);

create table if not exists public.sourcing_sales_velocity_suppressions (
  suppression_id uuid primary key default gen_random_uuid(),
  asin text not null,
  source_action_id uuid references public.sourcing_actions(action_id) on delete set null,
  dismissed_at timestamptz not null default now(),
  velocity_at_dismissal numeric(12, 4),
  metric_window_days integer not null,
  required_velocity numeric(12, 4) not null,
  current_velocity numeric(12, 4),
  status text not null default 'active'
    check (status in ('active', 'released')),
  last_evaluated_at timestamptz,
  reactivated_at timestamptz,
  reason_code text not null default 'sales_velocity_too_low',
  raw_context_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.sourcing_sales_velocity_suppressions is
'Dynamic ASIN-level suppression for valid products dismissed because sales velocity is too low. Suppression releases only when the current sourcing velocity threshold is met.';

create unique index if not exists sourcing_sales_velocity_suppressions_active_asin_uidx
  on public.sourcing_sales_velocity_suppressions (asin)
  where status = 'active';

create index if not exists sourcing_sales_velocity_suppressions_status_idx
  on public.sourcing_sales_velocity_suppressions (status, last_evaluated_at desc);

grant all on table public.amazon_catalog_item_identity_snapshots to service_role;
grant all on table public.sourcing_sales_velocity_suppressions to service_role;
