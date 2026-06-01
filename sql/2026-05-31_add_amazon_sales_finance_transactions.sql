-- Store order-level rows from the newer Amazon Finances Transactions API.
--
-- The legacy listFinancialEventsByOrderId endpoint can return empty financial
-- events while Seller Central and /finances/2024-06-19/transactions show a
-- DEFERRED order transaction with a full fee breakdown. This table preserves
-- the transaction-level status and raw breakdown for Sales Orders profitability.

create table if not exists public.amazon_sales_finance_transactions (
  amazon_sales_finance_transaction_id uuid primary key default gen_random_uuid(),

  transaction_id text not null unique,
  amazon_order_id text references public.amazon_sales_orders(amazon_order_id) on delete cascade,
  transaction_type text,
  transaction_status text,
  posted_date timestamptz,

  marketplace_id text,
  marketplace_name text,
  financial_event_group_id text,
  shipment_id text,
  settlement_id text,

  total_amount numeric(14, 2),
  currency text,
  description text,
  source text not null default 'amazon_spapi_transactions',
  raw_transaction_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists amazon_sales_finance_transactions_order_idx
  on public.amazon_sales_finance_transactions (amazon_order_id, posted_date desc);

create index if not exists amazon_sales_finance_transactions_status_idx
  on public.amazon_sales_finance_transactions (transaction_status);

create index if not exists amazon_sales_finance_transactions_group_idx
  on public.amazon_sales_finance_transactions (financial_event_group_id)
  where financial_event_group_id is not null;

grant all on table public.amazon_sales_finance_transactions to service_role;
