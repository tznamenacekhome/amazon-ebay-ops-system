-- Read-only Amazon Finance balance snapshots.
--
-- MBOP uses Amazon Finance data to represent value that has moved from
-- inventory into Amazon-held cash or Amazon-to-bank in-transit cash. This data
-- must stay separate from purchases, purchase_items, inventory_positions, and
-- workflow tables.

create table if not exists public.amazon_finance_balance_snapshots (
  amazon_finance_balance_snapshot_id uuid primary key default gen_random_uuid(),

  captured_at timestamptz not null default now(),
  marketplace_id text not null,
  currency text,

  -- Operator-facing balances from Amazon Payments/Finances.
  total_amazon_cash numeric(14, 2),
  available_to_withdraw numeric(14, 2),
  in_transit_to_bank numeric(14, 2),
  deferred_or_reserved_cash numeric(14, 2),

  -- Diagnostics/source details. The first implementation should populate raw
  -- responses even when only some normalized values can be derived.
  financial_event_group_count integer,
  transaction_count integer,
  raw_financial_event_groups_json jsonb,
  raw_transactions_json jsonb,
  notes text,
  source text not null default 'amazon_spapi_finances',
  created_at timestamptz not null default now()
);

comment on table public.amazon_finance_balance_snapshots is
'Point-in-time read-only Amazon Finance balance snapshots for Amazon-held cash, available withdrawal cash, and Amazon-to-bank in-transit cash.';

create index if not exists amazon_finance_balance_snapshots_captured_idx
  on public.amazon_finance_balance_snapshots (captured_at desc);

create index if not exists amazon_finance_balance_snapshots_marketplace_idx
  on public.amazon_finance_balance_snapshots (marketplace_id, captured_at desc);

create or replace view public.vw_latest_amazon_finance_balance_snapshot as
select distinct on (marketplace_id)
  *
from public.amazon_finance_balance_snapshots
order by marketplace_id, captured_at desc, created_at desc;

grant all on table public.amazon_finance_balance_snapshots to service_role;
grant select on public.vw_latest_amazon_finance_balance_snapshot to service_role;
