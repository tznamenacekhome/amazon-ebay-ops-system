-- Amazon Sales Orders foundation.
--
-- This is an additive seller-sales subsystem. It intentionally stays separate
-- from purchases, purchase_items, receiving, FBA shipment prep, repricing, and
-- inventory reconciliation workflow tables.

create table if not exists public.amazon_sales_orders (
  amazon_sales_order_id uuid primary key default gen_random_uuid(),
  amazon_order_id text not null unique,

  purchase_date timestamptz,
  last_update_date timestamptz,
  order_status text,
  fulfillment_channel text,
  sales_channel text,
  marketplace_id text,
  buyer_requested_cancel boolean,
  is_replacement_order boolean,
  is_business_order boolean,
  is_prime boolean,
  number_of_items_shipped integer,
  number_of_items_unshipped integer,
  order_total_amount numeric(14, 2),
  order_total_currency text,
  payment_method text,
  shipment_service_level_category text,
  earliest_ship_date timestamptz,
  latest_ship_date timestamptz,
  earliest_delivery_date timestamptz,
  latest_delivery_date timestamptz,

  raw_order_json jsonb,
  import_batch_id uuid,
  source text not null default 'amazon_spapi_orders',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.amazon_sales_orders is
'Amazon seller order headers imported from SP-API Orders. This table must not store buyer name, address, email, or phone.';

create index if not exists amazon_sales_orders_purchase_date_idx
  on public.amazon_sales_orders (purchase_date desc);

create index if not exists amazon_sales_orders_last_update_idx
  on public.amazon_sales_orders (last_update_date desc);

create index if not exists amazon_sales_orders_status_idx
  on public.amazon_sales_orders (order_status);

create index if not exists amazon_sales_orders_fulfillment_idx
  on public.amazon_sales_orders (fulfillment_channel);

create table if not exists public.amazon_sales_order_items (
  amazon_sales_order_item_id uuid primary key default gen_random_uuid(),
  amazon_order_item_id text not null unique,
  amazon_order_id text not null references public.amazon_sales_orders(amazon_order_id) on delete cascade,

  asin text,
  seller_sku text,
  title text,
  quantity_ordered integer,
  quantity_shipped integer,
  item_price_amount numeric(14, 2),
  item_price_currency text,
  item_tax_amount numeric(14, 2),
  shipping_price_amount numeric(14, 2),
  shipping_tax_amount numeric(14, 2),
  gift_wrap_price_amount numeric(14, 2),
  gift_wrap_tax_amount numeric(14, 2),
  item_promotion_discount_amount numeric(14, 2),
  ship_promotion_discount_amount numeric(14, 2),
  condition_id text,
  condition_subtype_id text,

  raw_order_item_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists amazon_sales_order_items_order_idx
  on public.amazon_sales_order_items (amazon_order_id);

create index if not exists amazon_sales_order_items_asin_idx
  on public.amazon_sales_order_items (asin);

create index if not exists amazon_sales_order_items_sku_idx
  on public.amazon_sales_order_items (seller_sku);

create table if not exists public.amazon_sales_financial_events (
  amazon_sales_financial_event_id uuid primary key default gen_random_uuid(),
  financial_event_id text,
  amazon_order_id text references public.amazon_sales_orders(amazon_order_id) on delete cascade,
  amazon_order_item_id text,

  event_type text not null,
  posted_date timestamptz,
  amount numeric(14, 2),
  currency text,
  fee_type text,
  charge_type text,
  promotion_type text,
  source text not null default 'amazon_spapi_finances',
  raw_financial_event_json jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists amazon_sales_financial_events_external_id_uidx
  on public.amazon_sales_financial_events (financial_event_id)
  where financial_event_id is not null;

create index if not exists amazon_sales_financial_events_order_idx
  on public.amazon_sales_financial_events (amazon_order_id, posted_date desc);

create index if not exists amazon_sales_financial_events_item_idx
  on public.amazon_sales_financial_events (amazon_order_item_id);

create index if not exists amazon_sales_financial_events_type_idx
  on public.amazon_sales_financial_events (event_type, fee_type, charge_type);

create table if not exists public.amazon_sales_profitability (
  amazon_sales_profitability_id uuid primary key default gen_random_uuid(),
  amazon_order_id text not null references public.amazon_sales_orders(amazon_order_id) on delete cascade,
  amazon_order_item_id text not null,

  asin text,
  seller_sku text,
  title text,
  quantity integer not null default 0,
  sale_price numeric(14, 2),
  amazon_fees_excluding_fulfillment numeric(14, 2),
  fulfillment_cost numeric(14, 2),
  fulfillment_cost_source text not null default 'missing',
  cogs numeric(14, 2),
  cogs_source text not null default 'missing',
  net_profit numeric(14, 2),
  roi numeric(14, 4),
  data_status text not null default 'missing_cogs',
  calculated_at timestamptz not null default now(),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (amazon_order_id, amazon_order_item_id),

  constraint amazon_sales_profitability_fulfillment_source_check
    check (fulfillment_cost_source in (
      'amazon_fba_fee',
      'veeqo_label',
      'manual',
      'missing'
    )),

  constraint amazon_sales_profitability_cogs_source_check
    check (cogs_source in (
      'mbop_fifo',
      'inventorylab_legacy',
      'manual',
      'missing'
    )),

  constraint amazon_sales_profitability_data_status_check
    check (data_status in (
      'complete',
      'missing_fees',
      'missing_fulfillment_cost',
      'missing_cogs',
      'refunded',
      'cancelled'
    ))
);

create index if not exists amazon_sales_profitability_order_idx
  on public.amazon_sales_profitability (amazon_order_id);

create index if not exists amazon_sales_profitability_asin_idx
  on public.amazon_sales_profitability (asin);

create index if not exists amazon_sales_profitability_status_idx
  on public.amazon_sales_profitability (data_status);

create index if not exists amazon_sales_profitability_roi_idx
  on public.amazon_sales_profitability (roi);

create table if not exists public.amazon_sales_cogs_consumption (
  consumption_id uuid primary key default gen_random_uuid(),
  amazon_order_id text not null references public.amazon_sales_orders(amazon_order_id) on delete cascade,
  amazon_order_item_id text not null,

  asin text,
  seller_sku text,
  quantity_consumed integer not null check (quantity_consumed > 0),
  unit_cogs numeric(14, 4) not null,
  total_cogs numeric(14, 4) not null,
  cost_source text not null,
  source_reference_type text not null,
  source_reference_id text,
  consumed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),

  constraint amazon_sales_cogs_consumption_cost_source_check
    check (cost_source in (
      'mbop_fifo',
      'inventorylab_legacy',
      'manual'
    )),

  constraint amazon_sales_cogs_consumption_reference_type_check
    check (source_reference_type in (
      'purchase_item',
      'inventorylab_legacy_valuation',
      'manual_adjustment'
    ))
);

create index if not exists amazon_sales_cogs_consumption_order_item_idx
  on public.amazon_sales_cogs_consumption (amazon_order_id, amazon_order_item_id);

create index if not exists amazon_sales_cogs_consumption_asin_idx
  on public.amazon_sales_cogs_consumption (asin);

create table if not exists public.veeqo_sales_orders (
  veeqo_sales_order_row_id uuid primary key default gen_random_uuid(),
  veeqo_order_id text not null unique,
  amazon_order_id text references public.amazon_sales_orders(amazon_order_id) on delete set null,

  status text,
  channel text,
  raw_veeqo_order_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists veeqo_sales_orders_amazon_order_idx
  on public.veeqo_sales_orders (amazon_order_id);

create table if not exists public.veeqo_sales_shipments (
  veeqo_sales_shipment_row_id uuid primary key default gen_random_uuid(),
  veeqo_shipment_id text not null unique,
  veeqo_order_id text references public.veeqo_sales_orders(veeqo_order_id) on delete cascade,
  amazon_order_id text references public.amazon_sales_orders(amazon_order_id) on delete set null,

  carrier text,
  service text,
  tracking_number text,
  label_cost_amount numeric(14, 2),
  label_cost_currency text,
  label_cost_source_field text,
  raw_veeqo_shipment_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists veeqo_sales_shipments_order_idx
  on public.veeqo_sales_shipments (amazon_order_id);

create index if not exists veeqo_sales_shipments_veeqo_order_idx
  on public.veeqo_sales_shipments (veeqo_order_id);

create or replace view public.vw_amazon_sales_orders_recent as
select
  orders.purchase_date,
  orders.amazon_order_id,
  profitability.amazon_order_item_id,
  profitability.asin,
  profitability.seller_sku,
  profitability.title,
  profitability.quantity,
  profitability.sale_price,
  orders.fulfillment_channel,
  profitability.amazon_fees_excluding_fulfillment,
  profitability.fulfillment_cost,
  profitability.fulfillment_cost_source,
  profitability.cogs,
  profitability.cogs_source,
  profitability.net_profit,
  profitability.roi,
  profitability.data_status
from public.amazon_sales_profitability profitability
join public.amazon_sales_orders orders
  on orders.amazon_order_id = profitability.amazon_order_id
where coalesce(lower(orders.order_status), '') <> 'canceled'
  and profitability.data_status not in ('cancelled', 'refunded');

create or replace view public.vw_amazon_sales_summary as
select
  count(distinct orders.amazon_order_id) as order_count,
  coalesce(sum(profitability.quantity), 0) as unit_count,
  coalesce(sum(profitability.sale_price), 0)::numeric(14, 2) as total_revenue,
  coalesce(sum(profitability.amazon_fees_excluding_fulfillment), 0)::numeric(14, 2) as amazon_fees_excluding_fulfillment,
  coalesce(sum(profitability.fulfillment_cost), 0)::numeric(14, 2) as fulfillment_cost,
  coalesce(sum(profitability.cogs), 0)::numeric(14, 2) as cogs,
  coalesce(sum(profitability.net_profit), 0)::numeric(14, 2) as net_profit,
  avg(profitability.roi)::numeric(14, 4) as average_roi,
  count(*) filter (where profitability.data_status = 'missing_fees') as missing_fee_count,
  count(*) filter (where profitability.data_status = 'missing_cogs') as missing_cogs_count,
  count(*) filter (where profitability.data_status = 'missing_fulfillment_cost') as missing_fulfillment_cost_count,
  count(distinct orders.amazon_order_id) filter (
    where orders.fulfillment_channel in ('MFN', 'Merchant', 'MerchantFulfilled')
  ) as mf_order_count,
  count(distinct orders.amazon_order_id) filter (
    where orders.fulfillment_channel in ('AFN', 'Amazon', 'AmazonFulfilled')
  ) as fba_order_count
from public.amazon_sales_profitability profitability
join public.amazon_sales_orders orders
  on orders.amazon_order_id = profitability.amazon_order_id
where coalesce(lower(orders.order_status), '') <> 'canceled'
  and profitability.data_status not in ('cancelled', 'refunded');

grant all on table public.amazon_sales_orders to service_role;
grant all on table public.amazon_sales_order_items to service_role;
grant all on table public.amazon_sales_financial_events to service_role;
grant all on table public.amazon_sales_profitability to service_role;
grant all on table public.amazon_sales_cogs_consumption to service_role;
grant all on table public.veeqo_sales_orders to service_role;
grant all on table public.veeqo_sales_shipments to service_role;
grant select on public.vw_amazon_sales_orders_recent to service_role;
grant select on public.vw_amazon_sales_summary to service_role;
