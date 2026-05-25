grant all on table public.fba_shipments to service_role;
grant all on table public.fba_shipment_items to service_role;

update purchase_items target
set amazon_title = source.amazon_title
from (
  select asin, max(amazon_title) as amazon_title
  from purchase_items
  where asin is not null
    and amazon_title is not null
  group by asin
) source
where target.asin = source.asin
  and target.amazon_title is null;

delete from inbound_shipment_items
where item_id in (
  select pi.item_id
  from purchase_items pi
  join purchases p on p.purchase_id = pi.purchase_id
  where p.supplier_order_id = '08-14527-65268'
    and pi.exclude_from_purchase_reporting = true
);

delete from fba_shipment_items
where item_id in (
  select pi.item_id
  from purchase_items pi
  join purchases p on p.purchase_id = pi.purchase_id
  where p.supplier_order_id = '08-14527-65268'
    and pi.exclude_from_purchase_reporting = true
);

delete from purchase_items
where item_id in (
  select pi.item_id
  from purchase_items pi
  join purchases p on p.purchase_id = pi.purchase_id
  where p.supplier_order_id = '08-14527-65268'
    and pi.exclude_from_purchase_reporting = true
);
