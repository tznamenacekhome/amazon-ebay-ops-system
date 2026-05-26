-- Refresh latest Amazon FBA inventory view to expose normalized inventory
-- detail quantities added in 2026-05-26_add_amazon_fba_inventory_detail_quantities.sql.

create or replace view public.vw_latest_amazon_fba_inventory_snapshot as
select distinct on (seller_sku, marketplace_id)
  *
from public.amazon_fba_inventory_snapshots
order by seller_sku, marketplace_id, captured_at desc;

grant select on public.vw_latest_amazon_fba_inventory_snapshot to service_role;
