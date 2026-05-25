update purchase_items pi
set
  exclude_from_purchase_reporting = true,
  exclusion_reason = 'Non-resale personal/business item'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id in ('25-13638-84763', '01-13685-25998');
