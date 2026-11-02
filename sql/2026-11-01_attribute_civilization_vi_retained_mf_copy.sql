-- Operator accepts refunded MF sale as explanation for retained physical copy.
-- Select the $23.24 unallocated December 7 purchase as its operational basis.
-- This is an operator attribution, not a proven historical sale/return linkage.
BEGIN;
DO $$
DECLARE original public.purchase_items%rowtype;
DECLARE temporary public.purchase_items%rowtype;
BEGIN
  SELECT * INTO original FROM public.purchase_items
    WHERE item_id='f3ca6e83-7afa-42ce-a1a1-eba8ba6a7ec2' FOR UPDATE;
  SELECT * INTO temporary FROM public.purchase_items
    WHERE item_id='6f432b0a-01f9-4942-a634-d0bac0d50e6c' FOR UPDATE;
  IF original.raw_import_json->>'mbop_retained_mf_attribution'='2026-11-01' THEN RETURN; END IF;
  IF original.quantity IS DISTINCT FROM 1 OR original.unit_cost IS DISTINCT FROM 23.24
    OR original.current_status IS DISTINCT FROM 'listed'
    OR temporary.current_status IS DISTINCT FROM 'received' OR temporary.quantity IS DISTINCT FROM 1
    OR NOT EXISTS (SELECT 1 FROM public.purchases WHERE purchase_id=original.purchase_id
      AND supplier_order_id='25-13920-71530' AND order_date='2025-12-07') THEN
    RAISE EXCEPTION 'Inventory attribution preconditions changed';
  END IF;
  IF EXISTS (SELECT 1 FROM public.fba_shipment_items f JOIN public.fba_shipments s USING(fba_shipment_id)
      WHERE f.item_id IN (original.item_id,temporary.item_id)
      AND s.shipment_code IS DISTINCT FROM 'legacy_listed_no_shipment_id')
    OR EXISTS (SELECT 1 FROM public.amazon_sales_cogs_consumption
      WHERE source_reference_type='purchase_item' AND source_reference_id=original.item_id::text) THEN
    RAISE EXCEPTION 'Item already assigned to shipment or sale';
  END IF;
  UPDATE public.purchase_items SET
    asin='B07HH8ZSMM',amazon_title=temporary.amazon_title,
    current_status='received',marketplace='Amazon',received_date=temporary.received_date,
    verified_date=temporary.verified_date,target_price=temporary.target_price,
    notes=concat_ws(E'\n',nullif(original.notes,''),
      'Operator attribution 2026-11-01: retained MF copy SKU 1070795694 assigned to this unallocated eBay purchase ($23.24, 2025-12-07). Operator accepts refunded MF sale as explanation for possession; exact physical sale/return linkage unproven. Alternate listing ASIN B07HCXXRLL changed to B07HH8ZSMM for FBA.'),
    raw_import_json=coalesce(original.raw_import_json,'{}'::jsonb)||jsonb_build_object(
      'mbop_retained_mf_attribution','2026-11-01','source_seller_sku','1070795694',
      'original_asin','B07HCXXRLL','superseded_intake_item_id',temporary.item_id,
      'attribution_basis','operator_accepted_refunded_mf_sale_retained_inventory',
      'superseded_legacy_shipment_rows',(SELECT jsonb_agg(to_jsonb(f)) FROM public.fba_shipment_items f
        JOIN public.fba_shipments s USING(fba_shipment_id) WHERE f.item_id=original.item_id
        AND s.shipment_code='legacy_listed_no_shipment_id'))
    WHERE item_id=original.item_id;
  -- Retire only the synthetic legacy Listed placeholder, preserved above for audit.
  DELETE FROM public.fba_shipment_items f USING public.fba_shipments s
    WHERE f.fba_shipment_id=s.fba_shipment_id AND f.item_id=original.item_id
    AND s.shipment_code='legacy_listed_no_shipment_id';
  UPDATE public.purchase_items SET current_status='cancelled',exclude_from_purchase_reporting=true,
    exclusion_reason='Superseded existing-inventory intake; original purchase identified by operator attribution',
    notes=concat_ws(E'\n',nullif(notes,''),'Superseded 2026-11-01 by original eBay purchase item '||original.item_id::text||'; no additional physical unit. Original purchase now supplies FBA queue.'),
    raw_import_json=coalesce(raw_import_json,'{}'::jsonb)||jsonb_build_object('superseded_by_item_id',original.item_id)
    WHERE item_id=temporary.item_id;
END $$;
COMMIT;
