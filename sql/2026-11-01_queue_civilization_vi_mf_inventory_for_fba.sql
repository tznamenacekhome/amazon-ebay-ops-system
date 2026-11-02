-- Operator requested one existing MF copy be queued for FBA.
-- This is an inventory intake, not a newly incurred purchase. Historical
-- source, purchase date, and cost are unknown; never substitute listing date
-- or the unrelated June eBay order. No Amazon listing write is performed.
BEGIN;
DO $$
DECLARE
  inventory_purchase_id uuid;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('mf-to-fba:1070795694'));
  IF EXISTS (SELECT 1 FROM public.purchase_items
             WHERE raw_import_json->>'inventory_transfer_key' = 'mf-to-fba:1070795694') THEN
    RETURN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.amazon_skus
                 WHERE seller_sku = '1070795694' AND asin = 'B07HH8ZSMM') THEN
    RAISE EXCEPTION 'Expected source SKU/ASIN not found';
  END IF;
  INSERT INTO public.purchases
    (supplier, supplier_order_id, order_date, total_order_cost, order_status, notes, raw_import_json)
  VALUES
    ('Existing inventory - source unknown', 'MF-TO-FBA-1070795694', NULL, NULL, 'received',
     'Existing MF inventory intake, not a new purchase. Original source, purchase date and cost unknown. Recorded 2026-11-01 at operator request.',
     '{"source":"manual_existing_inventory_intake","source_seller_sku":"1070795694","purchase_date_unknown":true}')
  RETURNING purchase_id INTO inventory_purchase_id;
  INSERT INTO public.purchase_items
    (purchase_id, supplier_sku, title, amazon_title, system, asin, quantity,
     unit_cost, target_price, current_status, condition, marketplace,
     received_date, verified_date, manual_unit_cost_override, notes, raw_import_json)
  VALUES
    (inventory_purchase_id, '1070795694',
     'Sid Meier''s Civilization VI - Nintendo Switch [video game]',
     'Sid Meier''s Civilization VI - Nintendo Switch [video game]',
     'Switch', 'B07HH8ZSMM', 1, NULL, 35.99, 'received', 'new', 'Amazon',
     '2026-11-01', '2026-11-01', true,
     'One existing MF copy queued for FBA at operator request. Source SKU 1070795694. Original purchase source/date/cost unknown. Operator will remove MF offer; MBOP has not modified Amazon listing.',
     '{"source":"manual_existing_inventory_intake","inventory_transfer_key":"mf-to-fba:1070795694","source_seller_sku":"1070795694","purchase_date_unknown":true,"purchase_cost_unknown":true,"operator_request":"Move one existing MF copy to ready to send to FBA"}');
END $$;
COMMIT;
