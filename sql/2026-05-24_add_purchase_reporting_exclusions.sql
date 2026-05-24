alter table purchase_items
  add column if not exists exclude_from_purchase_reporting boolean not null default false,
  add column if not exists exclusion_reason text;

comment on column purchase_items.exclude_from_purchase_reporting is
'Excludes non-resale or otherwise out-of-scope purchase items from dashboard/reporting totals.';

comment on column purchase_items.exclusion_reason is
'Operator-entered reason for excluding a purchase item from purchase reporting, such as Personal purchase or Business supply.';

create index if not exists idx_purchase_items_reporting_exclusion
  on purchase_items(exclude_from_purchase_reporting);

update purchase_items pi
set
  exclude_from_purchase_reporting = true,
  exclusion_reason = 'Personal purchase'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '19-14476-44107'
  and pi.title ilike '%Tommy Bahama%';

update purchase_items pi
set
  exclude_from_purchase_reporting = true,
  exclusion_reason = 'Business supply / non-resale'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '11-14441-71152'
  and pi.title ilike '%Kraft Waffle Padded Mailers%';

update purchase_items pi
set
  current_status = 'received',
  marketplace = 'eBay'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '16-14113-30387'
  and pi.title = 'NBA 2K22'
  and pi.unit_cost is null;
