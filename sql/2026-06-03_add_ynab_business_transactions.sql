-- Read-only YNAB Business category transactions.
--
-- MBOP uses these rows as a local history of YNAB transactions categorized to
-- Business. This is source data for future P&L, Schedule C, and cash
-- reconciliation features. It must stay separate from purchases,
-- purchase_items, Amazon finance snapshots, eBay financial data, and workflow
-- tables.

create table if not exists public.ynab_business_transactions (
  ynab_business_transaction_id uuid primary key default gen_random_uuid(),

  synced_at timestamptz not null default now(),
  plan_id text not null,
  plan_name text,
  ynab_transaction_id text not null,

  transaction_date date not null,
  account_id text,
  account_name text,
  payee_id text,
  payee_name text,
  import_payee_name text,
  import_payee_name_original text,
  category_id text,
  category_name text,

  amount_milliunits integer not null,
  amount_currency numeric(14, 2) not null,
  amount_formatted text,
  memo text,
  cleared text,
  approved boolean,
  deleted boolean not null default false,
  flag_color text,
  flag_name text,
  import_id text,
  matched_transaction_id text,
  transfer_account_id text,
  transfer_transaction_id text,
  debt_transaction_type text,

  raw_transaction_json jsonb not null,
  source text not null default 'ynab_api',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (plan_id, ynab_transaction_id)
);

comment on table public.ynab_business_transactions is
'Read-only local copy of YNAB transactions categorized as Business for future P&L, Schedule C, and cash reconciliation reporting.';

create index if not exists ynab_business_transactions_date_idx
  on public.ynab_business_transactions (transaction_date desc);

create index if not exists ynab_business_transactions_account_idx
  on public.ynab_business_transactions (account_id, transaction_date desc);

create index if not exists ynab_business_transactions_category_idx
  on public.ynab_business_transactions (category_id, transaction_date desc);

create index if not exists ynab_business_transactions_payee_idx
  on public.ynab_business_transactions (payee_name);

create index if not exists ynab_business_transactions_import_id_idx
  on public.ynab_business_transactions (import_id)
  where import_id is not null;

grant all on table public.ynab_business_transactions to service_role;
