-- Speed up latest Amazon FBA inventory lookups used by scheduler jobs.
-- The latest-view pattern is:
--   distinct on (seller_sku, marketplace_id) ... order by captured_at desc

create index concurrently if not exists idx_amazon_fba_inventory_snapshots_latest
  on public.amazon_fba_inventory_snapshots (
    seller_sku,
    marketplace_id,
    captured_at desc
  );
