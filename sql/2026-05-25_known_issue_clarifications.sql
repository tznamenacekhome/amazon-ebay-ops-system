update purchase_items pi
set current_status = 'listed'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '01-13574-33587'
  and pi.title = 'Lego Marvel Super Heroes';

update purchase_items pi
set
  exclude_from_purchase_reporting = true,
  exclusion_reason = 'Non-resale personal/business item'
from purchases p
where p.purchase_id = pi.purchase_id
  and p.supplier_order_id = '03-13734-80549'
  and pi.title = 'Philips Norelco HQ8 Replacement Men''s Electric Shaver Heads';
