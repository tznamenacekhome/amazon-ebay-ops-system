-- One-time InventoryLab active inventory historical backfill.
--
-- This table stores InventoryLab-derived cost basis and date context for
-- historical Amazon FBA inventory that predates MBOP as the operational source
-- of truth. It intentionally does not update purchase_items.

create table if not exists public.inventorylab_active_inventory_backfill (
  inventorylab_active_inventory_backfill_id uuid primary key default gen_random_uuid(),

  source_file text not null,
  source_row_number integer not null,
  imported_at timestamptz not null default now(),

  match_status text not null,
  match_method text,
  requires_review boolean not null default false,

  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  seller_sku text,
  asin text,
  fnsku text,
  title text,

  on_hand_quantity integer,
  total_in_stock_buy_cost numeric(14, 4),
  active_cost_per_unit numeric(12, 4),
  active_supplier text,
  active_date_purchased date,
  list_price numeric(12, 4),
  condition text,

  raw_inventorylab_json jsonb not null,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint inventorylab_backfill_match_status_check
    check (match_status in (
      'matched',
      'review_candidate',
      'ambiguous',
      'unmatched',
      'skipped'
    )),

  constraint inventorylab_backfill_match_method_check
    check (
      match_method is null
      or match_method in (
        'seller_sku',
        'asin_title_review'
      )
    ),

  unique (source_file, source_row_number)
);

comment on table public.inventorylab_active_inventory_backfill is
'Historical InventoryLab active inventory backfill data. Stores legacy cost/date context separately from MBOP purchase_items.';

create index if not exists inventorylab_backfill_seller_sku_idx
  on public.inventorylab_active_inventory_backfill (seller_sku);

create index if not exists inventorylab_backfill_asin_idx
  on public.inventorylab_active_inventory_backfill (asin);

create index if not exists inventorylab_backfill_match_status_idx
  on public.inventorylab_active_inventory_backfill (match_status, requires_review);

grant all on table public.inventorylab_active_inventory_backfill to service_role;
