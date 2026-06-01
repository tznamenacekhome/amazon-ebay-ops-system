-- Non-eBay purchase source COGS layers for Amazon sales and current inventory.
--
-- This extends the Amazon sales COGS subsystem so FIFO allocations can point to
-- non_ebay_purchase_cogs_sources rows. It also adds a separate inventory-layer
-- table for current/inbound Amazon inventory cost basis. This does not write to
-- purchases or purchase_items.

alter table public.amazon_sales_cogs_consumption
  drop constraint if exists amazon_sales_cogs_consumption_reference_type_check;

alter table public.amazon_sales_cogs_consumption
  add constraint amazon_sales_cogs_consumption_reference_type_check
    check (source_reference_type in (
      'purchase_item',
      'inventorylab_legacy_valuation',
      'non_ebay_purchase_cogs_source',
      'manual_adjustment'
    ));

create table if not exists public.amazon_inventory_cogs_layers (
  amazon_inventory_cogs_layer_id uuid primary key default gen_random_uuid(),
  allocation_run_id uuid not null,

  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  marketplace_id text,
  seller_sku text not null,
  asin text not null,
  fnsku text,
  title text,

  inventory_state text not null,
  fba_shipment_id text,
  snapshot_captured_at timestamptz,

  quantity_assigned integer not null check (quantity_assigned > 0),
  unit_cogs numeric(14, 4) not null check (unit_cogs >= 0),
  total_cogs numeric(14, 4) not null check (total_cogs >= 0),

  cost_source text not null default 'mbop_fifo',
  source_reference_type text not null default 'non_ebay_purchase_cogs_source',
  source_reference_id uuid references public.non_ebay_purchase_cogs_sources(non_ebay_purchase_cogs_source_id) on delete restrict,
  source_order_date date,
  allocation_method text not null default 'fifo_asin',

  active boolean not null default true,
  notes text,
  raw_allocation_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint amazon_inventory_cogs_layers_inventory_state_check
    check (inventory_state in (
      'fulfillable',
      'reserved',
      'inbound_working',
      'inbound_shipped',
      'inbound_receiving',
      'unfulfillable',
      'other'
    )),

  constraint amazon_inventory_cogs_layers_cost_source_check
    check (cost_source in (
      'mbop_fifo',
      'inventorylab_legacy',
      'manual'
    )),

  constraint amazon_inventory_cogs_layers_reference_type_check
    check (source_reference_type in (
      'non_ebay_purchase_cogs_source',
      'purchase_item',
      'inventorylab_legacy_valuation',
      'manual_adjustment'
    ))
);

create index if not exists amazon_inventory_cogs_layers_active_sku_idx
  on public.amazon_inventory_cogs_layers (active, seller_sku, marketplace_id);

create index if not exists amazon_inventory_cogs_layers_asin_idx
  on public.amazon_inventory_cogs_layers (active, asin);

create index if not exists amazon_inventory_cogs_layers_source_idx
  on public.amazon_inventory_cogs_layers (source_reference_type, source_reference_id);

create index if not exists amazon_inventory_cogs_layers_shipment_idx
  on public.amazon_inventory_cogs_layers (fba_shipment_id)
  where fba_shipment_id is not null;

create or replace view public.vw_current_amazon_inventory_cogs as
select
  seller_sku,
  marketplace_id,
  asin,
  max(fnsku) as fnsku,
  max(title) as title,
  sum(quantity_assigned) as quantity_assigned,
  sum(total_cogs)::numeric(14, 4) as total_cogs,
  case
    when sum(quantity_assigned) > 0
      then (sum(total_cogs) / sum(quantity_assigned))::numeric(14, 4)
    else null
  end as weighted_unit_cogs,
  min(source_order_date) as oldest_source_order_date,
  max(source_order_date) as newest_source_order_date,
  array_remove(array_agg(distinct fba_shipment_id), null) as fba_shipment_ids
from public.amazon_inventory_cogs_layers
where active = true
group by seller_sku, marketplace_id, asin;

grant all on table public.amazon_inventory_cogs_layers to service_role;
grant select on public.vw_current_amazon_inventory_cogs to service_role;
