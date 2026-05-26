-- One-time InventoryLab inventory valuation opening balance.
--
-- This table stores InventoryLab's current valuation export separately from
-- MBOP workflow tables. It is intended to seed legacy Amazon FBA cost basis
-- for inventory already at Amazon before MBOP became the operational source
-- of truth. Going forward, MBOP purchase/receiving/FBA workflows own cost.

create table if not exists public.inventorylab_inventory_valuation_snapshots (
  inventorylab_inventory_valuation_snapshot_id uuid primary key default gen_random_uuid(),

  source_file text not null,
  source_row_number integer not null,
  imported_at timestamptz not null default now(),

  title text,
  seller_sku text not null,
  fulfillment text,
  inbound_quantity integer,
  on_hand_quantity integer,
  unlisted_quantity integer,
  cost_per_unit numeric(12, 4),
  total_value numeric(14, 4),

  raw_inventorylab_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (source_file, source_row_number)
);

comment on table public.inventorylab_inventory_valuation_snapshots is
'InventoryLab valuation export snapshots used as a legacy opening-balance valuation layer for current Amazon FBA inventory. This table does not update purchase_items.';

create index if not exists inventorylab_inventory_valuation_sku_idx
  on public.inventorylab_inventory_valuation_snapshots (seller_sku, imported_at desc);

create index if not exists inventorylab_inventory_valuation_imported_idx
  on public.inventorylab_inventory_valuation_snapshots (imported_at desc);

create or replace view public.vw_latest_inventorylab_inventory_valuation as
select distinct on (seller_sku)
  *
from public.inventorylab_inventory_valuation_snapshots
order by seller_sku, imported_at desc, created_at desc;

grant all on table public.inventorylab_inventory_valuation_snapshots to service_role;
grant select on public.vw_latest_inventorylab_inventory_valuation to service_role;
