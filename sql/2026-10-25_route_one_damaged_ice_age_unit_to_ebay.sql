-- MBOP production: operator-directed, one-unit destination correction.
-- Preserve all 13 received units and $130 cost. Never create a return.
begin;
do $$
declare
  source public.purchase_items%rowtype;
  child_id uuid;
  package public.inbound_shipment_items%rowtype;
begin
  select * into source from public.purchase_items
    where item_id='9c6b9c2d-e626-415d-a2c4-5561ff53e4ab' for update;
  if not found or source.purchase_id <> '7ee38a47-1a17-4bb5-a40f-cd811278a0fe'::uuid then
    raise exception 'Expected order/item not found';
  end if;
  if exists(select 1 from public.purchase_items where manual_split_parent_item_id=source.item_id
      and raw_import_json->>'mbop_destination_adjustment'='2026-10-25_one_damaged_ice_age_unit') then
    return; -- A replay cannot move another unit.
  end if;
  if source.quantity<>13 or source.marketplace<>'Amazon' or source.current_status<>'received'
      or source.unit_cost<>10 then raise exception 'Source changed; review before splitting'; end if;
  if exists(select 1 from public.fba_shipment_items where item_id=source.item_id) then
    raise exception 'Source already belongs to an FBA shipment';
  end if;
  select * into package from public.inbound_shipment_items where item_id=source.item_id for update;
  if not found or package.quantity_expected_in_package<>13 or package.quantity_received_from_package<>13
      or not package.received_verified or package.resolution_status<>'received' then
    raise exception 'Unexpected package receipt state';
  end if;
  if (select count(*) from public.inbound_shipment_items where item_id=source.item_id)<>1 then
    raise exception 'Multiple packages require explicit allocation';
  end if;
  insert into public.purchase_items (
    purchase_id,title,amazon_title,asin,system,quantity,unit_cost,target_price,
    current_status,condition,tracking_number,received_date,verified_date,
    supplier_listing_url,supplier_sku,import_batch_id,current_location_id,
    raw_import_json,manual_title_override,manual_unit_cost_override,
    manual_split_child,manual_split_parent_item_id,marketplace,notes
  ) values (
    source.purchase_id,source.title,source.amazon_title,source.asin,source.system,1,source.unit_cost,source.target_price,
    'received','damaged',source.tracking_number,source.received_date,source.verified_date,
    source.supplier_listing_url,source.supplier_sku,source.import_batch_id,source.current_location_id,
    coalesce(source.raw_import_json,'{}'::jsonb)||jsonb_build_object('mbop_destination_adjustment','2026-10-25_one_damaged_ice_age_unit'),
    source.manual_title_override,source.manual_unit_cost_override,true,source.item_id,'eBay',
    'Operator: one damaged copy of order 19-15303-56046 retained for eBay sale instead of return; removed from Send to Amazon allocation on 2026-10-25.'
  ) returning item_id into child_id;
  update public.purchase_items set quantity=12,
    notes=concat_ws(E'\n',nullif(notes,''),'One damaged received copy split to eBay; 12 copies remain Amazon-bound. Adjustment 2026-10-25.')
    where item_id=source.item_id;
  update public.inbound_shipment_items set quantity_expected_in_package=12,quantity_received_from_package=12
    where inbound_shipment_item_id=package.inbound_shipment_item_id;
  insert into public.inbound_shipment_items (
    inbound_shipment_id,item_id,quantity_expected_in_package,quantity_received_from_package,
    received_verified,resolution_status,resolved_at,resolution_reason,resolved_by,notes
  ) values (
    package.inbound_shipment_id,child_id,1,1,true,'received',package.resolved_at,
    'Damaged unit retained for eBay sale',package.resolved_by,
    'One received copy split from '||source.item_id::text||'; destination eBay. Original package total remains 13.'
  );
end $$;
commit;
