-- Fill the remaining ready return purchase bases from exact-SKU InventoryLab
-- records, cross-checked against the original sale's consumed legacy cost.
-- Keep original source dates/costs; never create replacement purchases.
BEGIN;
DO $$
DECLARE r record; matched integer := 0;
BEGIN
  FOR r IN
    SELECT c.amazon_return_recovery_case_id,b.*
    FROM public.amazon_return_recovery_cases c
    JOIN public.inventorylab_active_inventory_backfill b ON b.seller_sku=c.seller_sku AND b.asin=c.asin
    WHERE c.amazon_return_recovery_case_id IN ('0a4f0ed9-0873-4fbc-a284-49af654d03b5','1ad3ca6d-db09-4ad1-877a-fa8972dc599d')
      AND b.active_date_purchased IS NOT NULL AND b.active_supplier IS NOT NULL
      AND EXISTS (SELECT 1 FROM public.amazon_sales_cogs_consumption s
        JOIN public.amazon_sales_orders o USING(amazon_order_id)
        WHERE s.amazon_order_id=c.amazon_order_id AND s.seller_sku=c.seller_sku AND s.asin=c.asin
          AND s.cost_source='inventorylab_legacy' AND s.unit_cogs=b.active_cost_per_unit
          AND o.purchase_date::date >= b.active_date_purchased)
  LOOP
    UPDATE public.amazon_return_recovery_cases SET raw_evidence_json=raw_evidence_json||
      jsonb_build_object('purchase_basis',jsonb_build_object(
        'verified',true,'asin',r.asin,'seller_sku',r.seller_sku,'unit_cost',r.active_cost_per_unit,
        'purchase_date',r.active_date_purchased,'supplier',r.active_supplier,
        'source','inventorylab_exact_sku_and_consumed_legacy_cost',
        'inventorylab_backfill_id',r.inventorylab_active_inventory_backfill_id,
        'source_file',r.source_file,'source_row',r.source_row_number,'verified_on','2026-11-02')),
      updated_at=now() WHERE amazon_return_recovery_case_id=r.amazon_return_recovery_case_id;
    matched := matched+1;
  END LOOP;
  IF matched<>2 THEN RAISE EXCEPTION 'Expected exactly two verified legacy return source records, found %',matched; END IF;
END $$;
COMMIT;
