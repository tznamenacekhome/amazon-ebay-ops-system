update purchases
set order_date = to_date(raw_import_json ->> 'Purchased Date', 'MM/DD/YYYY')
where order_date is null
  and raw_import_json ->> 'Purchased Date' ~ '^\d{1,2}/\d{1,2}/\d{4}$';

update purchase_items pi
set system = 'Wii U'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '15-14586-73097'
  and pi.asin = 'B01IW7Z746'
  and pi.system is null;
