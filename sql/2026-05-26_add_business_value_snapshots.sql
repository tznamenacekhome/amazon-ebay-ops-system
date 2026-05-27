-- Daily MBOP business value snapshots.
--
-- This table stores the backend-computed total business value once per day so
-- MBOP can show change over time. It is a reporting snapshot only and must not
-- write back to purchases, purchase_items, inventory_positions, Amazon finance
-- snapshots, YNAB snapshots, or workflow tables.

create table if not exists public.business_value_snapshots (
  business_value_snapshot_id uuid primary key default gen_random_uuid(),

  snapshot_date date not null,
  captured_at timestamptz not null default now(),

  amazon_inventory_value numeric(14, 2) not null default 0,
  pre_amazon_inventory_value numeric(14, 2) not null default 0,
  amazon_cash_balance numeric(14, 2) not null default 0,
  amazon_cash_in_transit numeric(14, 2) not null default 0,
  cash_on_hand numeric(14, 2) not null default 0,
  total_business_value numeric(14, 2) not null default 0,

  source text not null default 'mbop_dashboard_rollup',
  raw_rollup_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (snapshot_date)
);

comment on table public.business_value_snapshots is
'Daily backend-computed MBOP business value snapshots for trend reporting. Values are derived from existing inventory, Amazon Finance, and YNAB snapshot sources.';

create index if not exists business_value_snapshots_date_idx
  on public.business_value_snapshots (snapshot_date desc);

grant all on table public.business_value_snapshots to service_role;
