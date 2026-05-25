create table if not exists public.amazon_skus (
  amazon_sku_id uuid primary key default gen_random_uuid(),
  seller_sku text not null,
  marketplace_id text not null,
  asin text,
  fnsku text,
  product_name text,
  condition text,
  fulfillment_channel text,
  listing_status text,
  item_status text,
  currency text,
  listing_price numeric(12, 2),
  landed_price numeric(12, 2),
  last_listing_sync_at timestamptz,
  last_pricing_sync_at timestamptz,
  raw_listing_json jsonb,
  raw_pricing_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (seller_sku, marketplace_id)
);

create index if not exists amazon_skus_asin_idx
  on public.amazon_skus (asin);

create index if not exists amazon_skus_marketplace_status_idx
  on public.amazon_skus (marketplace_id, listing_status);

create table if not exists public.amazon_fba_inventory_snapshots (
  amazon_fba_inventory_snapshot_id uuid primary key default gen_random_uuid(),
  captured_at timestamptz not null default now(),
  marketplace_id text not null,
  seller_sku text not null,
  asin text,
  fnsku text,
  product_name text,
  condition text,
  total_quantity integer,
  fulfillable_quantity integer,
  inbound_working_quantity integer,
  inbound_shipped_quantity integer,
  inbound_receiving_quantity integer,
  reserved_quantity integer,
  researching_quantity integer,
  unfulfillable_quantity integer,
  raw_inventory_json jsonb,
  source text not null default 'amazon_spapi',
  created_at timestamptz not null default now()
);

create index if not exists amazon_fba_inventory_snapshots_captured_at_idx
  on public.amazon_fba_inventory_snapshots (captured_at desc);

create index if not exists amazon_fba_inventory_snapshots_sku_idx
  on public.amazon_fba_inventory_snapshots (seller_sku, marketplace_id, captured_at desc);

create index if not exists amazon_fba_inventory_snapshots_asin_idx
  on public.amazon_fba_inventory_snapshots (asin);

grant all on table public.amazon_skus to service_role;
grant all on table public.amazon_fba_inventory_snapshots to service_role;
