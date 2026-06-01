-- Durable fulfillment-cost overrides and Amazon-purchased shipping label source.
--
-- Merchant Fulfilled labels may be bought outside Veeqo, either in Seller
-- Central or in another shipping platform. Profitability is recalculated, so
-- one-off fixes need a source table rather than direct edits to
-- amazon_sales_profitability.

create table if not exists public.amazon_sales_fulfillment_cost_overrides (
  amazon_sales_fulfillment_cost_override_id uuid primary key default gen_random_uuid(),
  amazon_order_id text not null references public.amazon_sales_orders(amazon_order_id) on delete cascade,
  amazon_order_item_id text,

  fulfillment_cost numeric(14, 2) not null check (fulfillment_cost >= 0),
  currency text not null default 'USD',
  fulfillment_cost_source text not null default 'manual',
  active boolean not null default true,
  notes text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint amazon_sales_fulfillment_cost_overrides_source_check
    check (fulfillment_cost_source in (
      'manual',
      'amazon_shipping_label'
    ))
);

create unique index if not exists amazon_sales_fulfillment_cost_overrides_active_idx
  on public.amazon_sales_fulfillment_cost_overrides (
    amazon_order_id,
    coalesce(amazon_order_item_id, '')
  )
  where active = true;

create index if not exists amazon_sales_fulfillment_cost_overrides_order_idx
  on public.amazon_sales_fulfillment_cost_overrides (amazon_order_id)
  where active = true;

alter table public.amazon_sales_profitability
  drop constraint if exists amazon_sales_profitability_fulfillment_source_check;

alter table public.amazon_sales_profitability
  add constraint amazon_sales_profitability_fulfillment_source_check
    check (fulfillment_cost_source in (
      'amazon_fba_fee',
      'amazon_shipping_label',
      'veeqo_label',
      'manual',
      'missing'
    ));

grant all on table public.amazon_sales_fulfillment_cost_overrides to service_role;

update public.amazon_sales_fulfillment_cost_overrides
set active = false,
    updated_at = now()
where amazon_order_id = '114-6021948-3727407'
  and amazon_order_item_id is null
  and active = true;

insert into public.amazon_sales_fulfillment_cost_overrides (
  amazon_order_id,
  fulfillment_cost,
  currency,
  fulfillment_cost_source,
  notes
) values (
  '114-6021948-3727407',
  4.14,
  'USD',
  'manual',
  'External shipping platform label cost provided by operator on 2026-05-31.'
);
