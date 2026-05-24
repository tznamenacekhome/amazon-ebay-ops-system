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

update purchase_items pi
set
  exclude_from_purchase_reporting = true,
  exclusion_reason = 'Missing from reference spreadsheet after 2026-05-15 reconciliation'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id in (
    '08-14658-30729',
    '10-14655-54530',
    '18-14643-18650',
    '21-14639-11943',
    '27-14629-25991',
    '27-14629-25992',
    '26-14640-17463',
    '26-14640-17464',
    '26-14640-17467',
    '26-14640-17468',
    '26-14640-17469',
    '26-14640-17470'
  );

update purchase_items pi
set current_status = 'return_opened'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id in (
    '18-14253-77448',
    '03-14281-67958',
    '25-14280-29209',
    '04-14325-38181',
    '03-14338-18129',
    '06-14354-87435',
    '13-14344-99646',
    '12-14374-42899',
    '04-14393-93479',
    '04-14393-93481',
    '08-14403-57148',
    '14-14401-47898',
    '08-14431-22367',
    '21-14414-47361',
    '25-14430-16063',
    '20-14438-92004',
    '07-14463-53104',
    '12-14459-90721',
    '22-14472-59023',
    '23-14481-86906',
    '04-14517-30156',
    '13-14512-43085',
    '17-14512-21380',
    '20-14507-83649',
    '21-14540-08626',
    '27-14616-40271'
  );

update purchase_items pi
set current_status = 'cancelled'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id in (
    '16-14289-40143',
    '15-14314-47668',
    '25-14380-13939',
    '25-14408-53703',
    '24-14450-59862',
    '25-14431-70876',
    '25-14431-70881',
    '08-14481-22851',
    '04-14546-24806',
    '08-14556-83162',
    '15-14576-82325',
    '18-14572-43609',
    '07-14604-33646'
  );
