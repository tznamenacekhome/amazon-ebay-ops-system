-- Exact SKU evidence: data/imports/inventorylab_fba_active_inventory_2026-0.csv,
-- line 354: SKU 1070891208 / ASIN B07FYN3JDL / eBay / 12/21/2025 / $35.
-- The purchase row independently matches the date and cost. Do not create a
-- new purchase or change sale profitability/COGS allocation for a returned unit.
BEGIN;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.purchase_items pi JOIN public.purchases p USING(purchase_id)
    WHERE pi.item_id='befea0e0-be4e-4b4b-8587-e9be138352e5' AND pi.asin='B07FYN3JDL'
    AND pi.unit_cost=35 AND p.order_date='2025-12-21' AND p.supplier_order_id='25-13983-50117') THEN
    RAISE EXCEPTION 'Verified source purchase changed';
  END IF;
  UPDATE public.amazon_return_recovery_cases SET
    raw_evidence_json=raw_evidence_json||jsonb_build_object('purchase_basis',jsonb_build_object(
      'verified',true,'asin','B07FYN3JDL','seller_sku','1070891208','unit_cost',35.00,
      'purchase_date','2025-12-21','supplier','eBay','supplier_order_id','25-13983-50117',
      'purchase_item_id','befea0e0-be4e-4b4b-8587-e9be138352e5',
      'source','inventorylab_exact_sku_and_mbop_purchase',
      'source_file','data/imports/inventorylab_fba_active_inventory_2026-0.csv','source_line',354,
      'verified_on','2026-11-02')), updated_at=now()
  WHERE amazon_return_recovery_case_id='e07aeb39-998c-4605-b215-b848af83a567'
    AND amazon_order_id='111-7134497-9675438' AND asin='B07FYN3JDL' AND seller_sku='1070891208';
  IF NOT FOUND THEN RAISE EXCEPTION 'Expected return case missing'; END IF;
END $$;
COMMIT;
