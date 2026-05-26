-- Read-only YNAB category balance snapshots.
--
-- MBOP uses the YNAB "Business" category available balance as the cash-on-hand
-- value for dashboard business valuation. YNAB data is cash/budget context only
-- and must not write to purchases, purchase_items, inventory_positions, Amazon
-- snapshots, or workflow tables.

create table if not exists public.ynab_category_balance_snapshots (
  ynab_category_balance_snapshot_id uuid primary key default gen_random_uuid(),

  captured_at timestamptz not null default now(),
  plan_id text not null,
  plan_name text,
  category_group_id text,
  category_group_name text,
  category_id text not null,
  category_name text not null,

  balance_milliunits integer,
  balance_currency numeric(14, 2),
  balance_formatted text,
  currency_code text,

  raw_category_json jsonb not null,
  source text not null default 'ynab_api',
  created_at timestamptz not null default now()
);

comment on table public.ynab_category_balance_snapshots is
'Point-in-time read-only YNAB category balance snapshots. MBOP uses the Business category available balance as cash on hand.';

create index if not exists ynab_category_balance_snapshots_captured_idx
  on public.ynab_category_balance_snapshots (captured_at desc);

create index if not exists ynab_category_balance_snapshots_category_idx
  on public.ynab_category_balance_snapshots (plan_id, category_id, captured_at desc);

create or replace view public.vw_latest_ynab_category_balance_snapshot as
select distinct on (plan_id, category_id)
  *
from public.ynab_category_balance_snapshots
order by plan_id, category_id, captured_at desc, created_at desc;

grant all on table public.ynab_category_balance_snapshots to service_role;
grant select on public.vw_latest_ynab_category_balance_snapshot to service_role;
