-- MBOP receipt review: allocated order charges, ASIN and sell price.
create or replace function public.mbop_purchase_intake_costs(p_data jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare
 v_shipping numeric; v_fees numeric:=0; v_tax numeric; v_discount numeric; v_total numeric; v_subtotal numeric:=0;
 v_line jsonb; v_lines jsonb:='[]'; v_allocations jsonb:='[]'; v_qty int; v_amount numeric;
 v_target bigint; v_floor_sum bigint; v_remaining int; v_alloc record; v_base bigint; v_extra int;
 v_date date;
 v_total_only boolean:=coalesce(p_data->>'cost_basis','itemized')='total_only';
begin
 if jsonb_typeof(p_data)<>'object' or nullif(btrim(p_data->>'supplier'),'') is null
    or length(p_data->>'supplier')>200 or lower(btrim(p_data->>'supplier'))='ebay' then
   raise exception 'Enter a non-eBay supplier.';
 end if;
 if coalesce(p_data->>'currency','')<>'USD' then raise exception 'Only USD receipts are supported. Convert and review outside this intake.'; end if;
 if coalesce(p_data->>'order_date','') !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'Purchase date is required.'; end if;
 v_date:=(p_data->>'order_date')::date;
 if coalesce(length(p_data->>'order_id'),0)>200 or coalesce(length(p_data->>'notes'),0)>4000 then raise exception 'Order reference or notes are too long.'; end if;
 if coalesce(p_data->>'cost_basis','itemized') not in ('itemized','total_only') then raise exception 'Invalid receipt cost basis.'; end if;
 foreach v_line in array case when v_total_only then array[p_data->'order_total'] else array[p_data->'shipping',p_data->'tax',p_data->'discount',p_data->'order_total',coalesce(p_data->'other_charges','0'::jsonb)] end loop
   if v_line is null or v_line='null'::jsonb or v_line#>>'{}' !~ '^\d+(\.\d{1,2})?$' then
     raise exception 'Enter shipping, tax, discount and order total in dollars (zero where confirmed).';
   end if;
 end loop;
 v_total:=(p_data->>'order_total')::numeric;
 if not v_total_only then
   v_shipping:=(p_data->>'shipping')::numeric; v_tax:=(p_data->>'tax')::numeric; v_discount:=(p_data->>'discount')::numeric; v_fees:=coalesce(p_data->>'other_charges','0')::numeric;
 end if;
 if greatest(v_shipping,v_tax,v_discount,v_total,v_fees)>9999999 then raise exception 'Receipt amount is too large.'; end if;
 if jsonb_typeof(p_data->'items') is distinct from 'array' or jsonb_array_length(p_data->'items') not between 1 and 100 then raise exception 'Review between 1 and 100 receipt items.'; end if;
 if v_total_only and jsonb_array_length(p_data->'items')<>1 then raise exception 'Grand-total-only costing requires exactly one product line.'; end if;
 for v_line in select value from jsonb_array_elements(p_data->'items') loop
   if nullif(btrim(v_line->>'title'),'') is null or length(v_line->>'title')>1000 then raise exception 'Each item needs a title (up to 1000 characters).'; end if;
   if coalesce(v_line->>'quantity','') !~ '^\d+$' or (not v_total_only and coalesce(v_line->>'line_total','') !~ '^\d+(\.\d{1,2})?$') then raise exception 'Each item needs a whole quantity and merchandise line total.'; end if;
   v_qty:=(v_line->>'quantity')::int;
   v_amount:=case when v_total_only then 0 else (v_line->>'line_total')::numeric end;
   if v_qty not between 1 and 10000 or v_amount>9999999 then raise exception 'Invalid quantity or line total.'; end if;
   if nullif(v_line->>'asin','') is not null and v_line->>'asin' !~ '^[A-Z0-9]{10}$' then raise exception 'Enter a valid 10-character ASIN or leave it blank.'; end if;
   if nullif(v_line->>'sell_price','') is not null and (v_line->>'sell_price' !~ '^\d+(\.\d{1,2})?$' or (v_line->>'sell_price')::numeric>9999999) then raise exception 'Enter a valid sell price or leave it blank.'; end if;
   if coalesce(v_line->>'condition','') not in ('new','used') then raise exception 'Choose New or Used for each item.'; end if;
   if coalesce(v_line->>'system','') not in ('','Switch 2','Switch','3DS','DS','Wii U','Wii','Gamecube','Nintendo 64','Super Nintendo','NES','PS 5','PS 4','PS 3','PS 2','PS','PSP','PS Vita','Xbox Series X','Xbox Series S','Xbox One','Xbox 360','Xbox','PC') then raise exception 'Choose a canonical platform or leave it blank.'; end if;
   if jsonb_typeof(v_line->'exclude_from_purchase_reporting') is distinct from 'boolean' then raise exception 'Review whether each item is resale inventory.'; end if;
   v_subtotal:=v_subtotal+v_amount;
   v_lines:=v_lines||jsonb_build_array(v_line||jsonb_build_object('quantity',v_qty,'line_total',case when v_total_only then null else v_amount end));
 end loop;
 if v_discount>v_subtotal then raise exception 'Discount exceeds merchandise subtotal.'; end if;
 if not v_total_only and v_total<>v_subtotal-v_discount+v_shipping+v_tax+v_fees then raise exception 'Receipt total differs by $%. Include packing/handling in Other charges, or correct the item totals, shipping, tax or discount.', to_char(v_total-(v_subtotal-v_discount+v_shipping+v_tax+v_fees),'FM999999990.00'); end if;
 v_target:=(v_total*100)::bigint;
 -- Largest remainder allocation by merchandise value; all-free orders use units.
 with weights as (
   select ordinality n, value item,
     case when v_subtotal>0 then (value->>'line_total')::numeric/v_subtotal
          else (value->>'quantity')::numeric/(select sum((value->>'quantity')::numeric) from jsonb_array_elements(v_lines)) end w
   from jsonb_array_elements(v_lines) with ordinality
 ) select coalesce(sum(floor(v_target*w)),0)::bigint into v_floor_sum from weights;
 v_remaining:=(v_target-v_floor_sum)::int;
 for v_alloc in
   with weights as (
     select ordinality n,value item,
       case when v_subtotal>0 then (value->>'line_total')::numeric/v_subtotal
            else (value->>'quantity')::numeric/(select sum((value->>'quantity')::numeric) from jsonb_array_elements(v_lines)) end w
     from jsonb_array_elements(v_lines) with ordinality
   ), ranked as (
     select *,floor(v_target*w)::bigint cents,row_number() over(order by (v_target*w-floor(v_target*w)) desc,n) rank from weights
   ) select *,cents+case when rank<=v_remaining then 1 else 0 end landed_cents from ranked order by n
 loop
   v_qty:=(v_alloc.item->>'quantity')::int;
   v_base:=v_alloc.landed_cents/v_qty; v_extra:=(v_alloc.landed_cents%v_qty)::int;
   v_allocations:=v_allocations||jsonb_build_array(v_alloc.item||jsonb_build_object(
     'line_number',v_alloc.n,'landed_total',v_alloc.landed_cents/100.0,
     'average_unit_cost',v_alloc.landed_cents/100.0/v_qty,
     'base_unit_cost',v_base/100.0,'base_quantity',v_qty-v_extra,
     'extra_unit_cost',(v_base+1)/100.0,'extra_quantity',v_extra));
 end loop;
 return jsonb_build_object('cost_basis',case when v_total_only then 'total_only' else 'itemized' end,'subtotal',case when v_total_only then null else v_subtotal end,'shipping',v_shipping,'other_charges',case when v_total_only then null else v_fees end,'tax',v_tax,'discount',v_discount,'order_total',v_total,'items',v_allocations,'policy','Merchandise-value proportional allocation; largest remainder cents, then exact per-unit cent allocations. Free merchandise uses unit weights; one-product total-only receipts retain unknown charge breakdowns.');
end $$;

create or replace function public.mbop_save_purchase_intake(p_id uuid,p_data jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare v_draft purchase_intake_drafts; v_cost jsonb; v_purchase uuid; v_line jsonb; v_part record; v_ids jsonb:='[]'; v_item uuid;
begin
 select * into v_draft from purchase_intake_drafts where id=p_id for update;
 if not found then raise exception 'Receipt draft not found.'; end if;
 if v_draft.status='saved' then return jsonb_build_object('purchase_id',v_draft.purchase_id,'already_saved',true); end if;
 if v_draft.status not in ('review','failed') then raise exception 'Wait for extraction to finish before saving.'; end if;
 v_cost:=mbop_purchase_intake_costs(p_data);
 -- Serialize same supplier/invoice saves, including distinct scans of the same invoice.
 if nullif(btrim(p_data->>'order_id'),'') is not null then
   perform pg_advisory_xact_lock(hashtextextended(lower(btrim(p_data->>'supplier'))||':'||lower(btrim(p_data->>'order_id')),0));
   if exists(select 1 from purchases where lower(btrim(supplier))=lower(btrim(p_data->>'supplier')) and lower(btrim(supplier_order_id))=lower(btrim(p_data->>'order_id'))) then
     raise exception 'This supplier order reference already exists. Review the existing purchase instead.';
   end if;
 end if;
 insert into purchases(supplier,supplier_order_id,order_date,total_order_cost,shipping_cost,tax_amount,order_status,raw_import_json,notes)
 values(btrim(p_data->>'supplier'),nullif(btrim(p_data->>'order_id'),''),(p_data->>'order_date')::date,(v_cost->>'order_total')::numeric,
 (v_cost->>'shipping')::numeric,(v_cost->>'tax')::numeric,'ordered',
 jsonb_build_object('source','non_ebay_receipt','intake_draft_id',p_id,'document_sha256',v_draft.document_sha256,'reviewed_receipt',p_data,'cost_snapshot',v_cost),nullif(p_data->>'notes','')) returning purchase_id into v_purchase;
 for v_line in select value from jsonb_array_elements(v_cost->'items') loop
   for v_part in select (v_line->>'base_quantity')::int qty,(v_line->>'base_unit_cost')::numeric cost
     union all select (v_line->>'extra_quantity')::int,(v_line->>'extra_unit_cost')::numeric loop
     if v_part.qty=0 then continue; end if;
     insert into purchase_items(purchase_id,title,supplier_sku,system,quantity,unit_cost,asin,amazon_title,target_price,current_status,condition,manual_unit_cost_override,exclude_from_purchase_reporting,exclusion_reason,raw_import_json)
     values(v_purchase,btrim(v_line->>'title'),nullif(v_line->>'supplier_sku',''),nullif(v_line->>'system',''),v_part.qty,v_part.cost,nullif(v_line->>'asin',''),nullif(v_line->>'amazon_title',''),nullif(v_line->>'sell_price','')::numeric,'ordered',v_line->>'condition',true,
       (v_line->>'exclude_from_purchase_reporting')::boolean,case when (v_line->>'exclude_from_purchase_reporting')::boolean then 'Non-resale receipt item' else null end,
       jsonb_build_object('source','non_ebay_receipt','intake_draft_id',p_id,'receipt_line',v_line)) returning item_id into v_item;
     v_ids:=v_ids||to_jsonb(v_item);
   end loop;
 end loop;
 update purchase_intake_drafts set status='saved',purchase_id=v_purchase,reviewed_data=p_data,cost_snapshot=v_cost,saved_at=now(),updated_at=now() where id=p_id;
 return jsonb_build_object('purchase_id',v_purchase,'item_ids',v_ids,'already_saved',false);
end $$;
revoke all on function public.mbop_purchase_intake_costs(jsonb) from public,anon,authenticated;
revoke all on function public.mbop_save_purchase_intake(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.mbop_purchase_intake_costs(jsonb) to service_role;
grant execute on function public.mbop_save_purchase_intake(uuid,jsonb) to service_role;
