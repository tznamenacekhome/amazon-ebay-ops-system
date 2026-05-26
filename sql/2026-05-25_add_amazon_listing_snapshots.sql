-- Read-only Amazon Listings Items status snapshots.
--
-- This table stores point-in-time listing status details from Amazon SP-API.
-- It is Amazon-specific and must not be written into purchases/purchase_items.

create table if not exists public.amazon_listing_snapshots (
  amazon_listing_snapshot_id uuid primary key default gen_random_uuid(),
  captured_at timestamptz not null default now(),

  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  marketplace_id text not null,
  seller_sku text not null,
  asin text,
  product_name text,
  condition text,

  listing_status text,
  item_status text,
  fulfillment_channel text,
  fulfillment_availability jsonb,

  issue_count integer not null default 0,
  issue_severity text,
  issues_json jsonb,
  raw_listing_json jsonb not null,
  source text not null default 'amazon_spapi_listings_items',
  created_at timestamptz not null default now()
);

comment on table public.amazon_listing_snapshots is
'Point-in-time read-only Amazon Listings Items snapshots for listing status, issues, and fulfillment availability.';

create index if not exists amazon_listing_snapshots_captured_at_idx
  on public.amazon_listing_snapshots (captured_at desc);

create index if not exists amazon_listing_snapshots_sku_idx
  on public.amazon_listing_snapshots (seller_sku, marketplace_id, captured_at desc);

create index if not exists amazon_listing_snapshots_asin_idx
  on public.amazon_listing_snapshots (asin);

create index if not exists amazon_listing_snapshots_issue_idx
  on public.amazon_listing_snapshots (issue_count, issue_severity);

create or replace view public.vw_latest_amazon_listing_snapshot as
select distinct on (seller_sku, marketplace_id)
  *
from public.amazon_listing_snapshots
order by seller_sku, marketplace_id, captured_at desc;

grant all on table public.amazon_listing_snapshots to service_role;
grant select on public.vw_latest_amazon_listing_snapshot to service_role;
