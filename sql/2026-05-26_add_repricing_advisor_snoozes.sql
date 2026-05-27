-- Aged Amazon Inventory Repricing Advisor snoozes.
--
-- Snoozes are operator workflow state for the advisory page only. They do not
-- modify Amazon, Informed, Keepa, purchases, purchase_items, inventory
-- snapshots, or FBA workflow tables.

create table if not exists public.amazon_repricing_advisor_snoozes (
  amazon_repricing_advisor_snooze_id uuid primary key default gen_random_uuid(),

  asin text,
  seller_sku text not null,
  marketplace_id text,

  snoozed_at timestamptz not null default now(),
  snoozed_until timestamptz not null,
  snooze_days integer not null default 30,
  reason text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint amazon_repricing_snooze_days_check
    check (snooze_days > 0 and snooze_days <= 365),

  unique (seller_sku)
);

comment on table public.amazon_repricing_advisor_snoozes is
'Operator snooze state for Aged Amazon Inventory recommendations. A snoozed SKU remains hidden from the default advisor list until snoozed_until.';

create index if not exists amazon_repricing_snoozes_until_idx
  on public.amazon_repricing_advisor_snoozes (snoozed_until desc);

create index if not exists amazon_repricing_snoozes_asin_idx
  on public.amazon_repricing_advisor_snoozes (asin);

grant all on table public.amazon_repricing_advisor_snoozes to service_role;
