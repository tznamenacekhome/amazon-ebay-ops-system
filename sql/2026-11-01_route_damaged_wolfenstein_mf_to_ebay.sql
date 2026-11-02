-- Operator-directed intake of one identifiable existing MF copy.
-- No exact purchase-to-SKU linkage is known; preserve unknown basis rather
-- than changing an unrelated same-ASIN purchase or Amazon listing snapshot.
BEGIN;
DO $$
DECLARE inventory_purchase_id uuid;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('mf-to-ebay:R2-DOAI-V6CM'));
  IF EXISTS (SELECT 1 FROM public.purchase_items
    WHERE raw_import_json->>'inventory_transfer_key'='mf-to-ebay:R2-DOAI-V6CM') THEN RETURN; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.amazon_skus
    WHERE seller_sku='R2-DOAI-V6CM' AND asin='B074B5F8LD') THEN
    RAISE EXCEPTION 'Expected MF SKU/ASIN missing'; END IF;
  INSERT INTO public.purchases
    (supplier,supplier_order_id,order_date,total_order_cost,order_status,notes,raw_import_json)
  VALUES ('Existing inventory - source unknown','MF-TO-EBAY-R2-DOAI-V6CM',NULL,NULL,'received',
    'Existing damaged MF inventory, not a new purchase. Original source/date/cost unconfirmed. Operator routing to eBay on 2026-11-01.',
    '{"source":"manual_existing_inventory_intake","source_seller_sku":"R2-DOAI-V6CM","purchase_date_unknown":true}')
  RETURNING purchase_id INTO inventory_purchase_id;
  INSERT INTO public.purchase_items
    (purchase_id,supplier_sku,title,amazon_title,system,asin,quantity,unit_cost,
     current_status,condition,marketplace,received_date,verified_date,
     manual_unit_cost_override,notes,raw_import_json)
  VALUES (inventory_purchase_id,'R2-DOAI-V6CM',
    'Wolfenstein: The Two-Pack - Xbox One [video game]',
    'Wolfenstein: The Two-Pack - Xbox One [video game]','Xbox One','B074B5F8LD',1,NULL,
    'received','damaged','eBay','2026-11-01','2026-11-01',true,
    'Operator routing damaged MF copy to eBay because it is not selling in non-new condition. Amazon listing note: sealed game, torn wrapper, cracked case corner. Operator removing Amazon offer. Original purchase linkage/cost unknown.',
    '{"source":"manual_existing_inventory_intake","inventory_transfer_key":"mf-to-ebay:R2-DOAI-V6CM","source_seller_sku":"R2-DOAI-V6CM","purchase_date_unknown":true,"purchase_cost_unknown":true,"damage":"Torn wrapper and cracked case corner"}');
END $$;
COMMIT;
