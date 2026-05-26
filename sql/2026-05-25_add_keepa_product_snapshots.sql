-- Read-only Keepa product research snapshots.
--
-- Keepa is used for catalog intelligence such as price history, sales-rank
-- history, sales-rank drop frequency, Buy Box context, and offer signals.
-- Keepa data is product/catalog intelligence only and must not be written into
-- purchases, purchase_items, or Amazon seller workflow tables.

create table if not exists public.keepa_product_snapshots (
  keepa_product_snapshot_id uuid primary key default gen_random_uuid(),
  captured_at timestamptz not null default now(),

  -- Keepa domain 1 is Amazon.com / US. Store the integer because Keepa APIs
  -- address marketplaces by domain id.
  domain_id integer not null default 1,
  asin text not null,

  title text,
  brand text,
  manufacturer text,
  product_group text,
  root_category bigint,
  category_tree_json jsonb,

  -- Current and averaged price/rank summaries are derived from Keepa stats.
  -- Price values are stored in cents when Keepa returns cent-based values.
  buy_box_price_current_cents integer,
  buy_box_price_avg30_cents integer,
  buy_box_price_avg90_cents integer,
  amazon_price_current_cents integer,
  new_price_current_cents integer,
  new_fba_price_current_cents integer,
  new_fbm_price_current_cents integer,
  used_price_current_cents integer,

  sales_rank_current integer,
  sales_rank_avg30 integer,
  sales_rank_avg90 integer,
  sales_rank_avg180 integer,
  sales_rank_drops30 integer,
  sales_rank_drops90 integer,
  sales_rank_drops180 integer,

  offer_count_current integer,
  review_count_current integer,
  rating_current numeric(6, 2),

  raw_keepa_json jsonb not null,
  token_cost integer,
  tokens_left integer,
  source text not null default 'keepa_product',
  created_at timestamptz not null default now()
);

comment on table public.keepa_product_snapshots is
'Point-in-time read-only Keepa product snapshots for catalog intelligence, price history, sales-rank history, and sales-frequency signals.';

create index if not exists keepa_product_snapshots_asin_idx
  on public.keepa_product_snapshots (asin, domain_id, captured_at desc);

create index if not exists keepa_product_snapshots_captured_at_idx
  on public.keepa_product_snapshots (captured_at desc);

create index if not exists keepa_product_snapshots_sales_rank_idx
  on public.keepa_product_snapshots (sales_rank_current, sales_rank_avg90);

create index if not exists keepa_product_snapshots_drops_idx
  on public.keepa_product_snapshots (sales_rank_drops30, sales_rank_drops90);

create table if not exists public.keepa_product_history_points (
  keepa_product_history_point_id uuid primary key default gen_random_uuid(),
  keepa_product_snapshot_id uuid not null
    references public.keepa_product_snapshots(keepa_product_snapshot_id)
    on delete cascade,

  domain_id integer not null default 1,
  asin text not null,
  metric_name text not null,
  observed_at timestamptz not null,
  metric_value integer,
  created_at timestamptz not null default now(),

  constraint keepa_product_history_points_metric_check
    check (metric_name in (
      'amazon_price',
      'new_price',
      'used_price',
      'sales_rank',
      'buy_box_price',
      'new_fba_price',
      'new_fbm_price',
      'offer_count',
      'review_count',
      'rating'
    ))
);

comment on table public.keepa_product_history_points is
'Optional normalized Keepa time-series points extracted from Keepa CSV history arrays. The raw Keepa payload remains stored on keepa_product_snapshots.';

create index if not exists keepa_history_points_asin_metric_idx
  on public.keepa_product_history_points (asin, domain_id, metric_name, observed_at desc);

create or replace view public.vw_latest_keepa_product_snapshot as
select distinct on (asin, domain_id)
  *
from public.keepa_product_snapshots
order by asin, domain_id, captured_at desc;

grant all on table public.keepa_product_snapshots to service_role;
grant all on table public.keepa_product_history_points to service_role;
grant select on public.vw_latest_keepa_product_snapshot to service_role;
