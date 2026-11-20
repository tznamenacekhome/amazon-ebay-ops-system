-- Recovery moves existing physical lots; it never receives or creates stock.
alter table public.amazon_listing_batches add column recovery_evidence jsonb;
alter table public.amazon_listing_batches drop constraint amazon_listing_batches_status_check;
alter table public.amazon_listing_batches add constraint amazon_listing_batches_status_check
 check(status in ('draft','exported','partially_listed','completed','partially_recovered','recovered'));
alter table public.amazon_listing_allocations
 add column transferred_quantity integer not null default 0 check(transferred_quantity>=0),
 add column recovery_batch_id uuid references public.amazon_listing_batches(id),
 add column recovery_source_allocation_id uuid unique references public.amazon_listing_allocations(id),
 add constraint listing_active_quantity check(listed_quantity+transferred_quantity<=quantity),
 add constraint listing_transfer_target check((transferred_quantity=0)=(recovery_batch_id is null));
create index listing_recovery_batch_idx on public.amazon_listing_allocations(recovery_batch_id) where recovery_batch_id is not null;
comment on column public.amazon_listing_allocations.transferred_quantity is
 'Units moved to a recovery batch. Original snapshot and export remain historical. Active quantity = quantity - transferred_quantity.';

create function public.mbop_recover_mf_listing(p_batch uuid,p_local timestamp,p_items jsonb,p_csv text,p_evidence jsonb)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare b public.amazon_listing_batches; a public.amazon_listing_allocations;
 l public.amazon_merchant_inventory_lots; x jsonb; new_id uuid; recovery_selection jsonb:='{}';
begin
 if p_local is null or coalesce(jsonb_array_length(p_items),0) not between 1 and 500
   or coalesce(p_csv,'')='' or coalesce(p_evidence->>'source_url','')='' then
   raise exception 'Recovery requires dated export, source evidence and allocations';
 end if;
 if (select count(*)<>count(distinct value->>'source_allocation_id') from jsonb_array_elements(p_items)) then
   raise exception 'Duplicate recovery allocation';
 end if;
 insert into public.amazon_listing_batches(id,fulfillment_method,external_reference,il_batch_local,status,selection,recovery_evidence)
 values(p_batch,'MF','MF '||to_char(p_local,'YYYY-MM-DD HH12:MI AM'),p_local,'draft','{}',p_evidence)
 on conflict(id) do nothing;
 select * into strict b from public.amazon_listing_batches where id=p_batch for update;
 if b.recovery_evidence is distinct from p_evidence or b.fulfillment_method<>'MF' then raise exception 'Recovery identity already used'; end if;
 if b.export_csv is not null then
   if b.export_csv is distinct from p_csv or b.recovery_evidence->'allocations' is distinct from p_items then raise exception 'Recovery retry changed'; end if;
   return to_jsonb(b);
 end if;
 if b.status<>'draft' or p_evidence->'allocations' is distinct from p_items then raise exception 'Recovery manifest mismatch'; end if;
 -- Stable locking serializes overlapping recoveries. Snapshot quantities are rechecked after locks.
 perform 1 from public.amazon_listing_batches where id in
  (select batch_id from public.amazon_listing_allocations where id in
   (select (value->>'source_allocation_id')::uuid from jsonb_array_elements(p_items))) order by id for update;
 perform 1 from public.amazon_listing_allocations where id in
  (select (value->>'source_allocation_id')::uuid from jsonb_array_elements(p_items)) order by id for update;
 for x in select value from jsonb_array_elements(p_items) order by value->>'source_allocation_id' loop
   select * into strict a from public.amazon_listing_allocations where id=(x->>'source_allocation_id')::uuid;
   if a.batch_id=p_batch or a.quantity is distinct from (x->>'quantity')::integer
    or a.listed_quantity<>a.quantity or a.transferred_quantity<>0 or a.recovery_source_allocation_id is not null
    or not exists(select 1 from public.amazon_listing_batches where id=a.batch_id and fulfillment_method='MF' and status in ('completed','partially_recovered')) then
     raise exception 'Source allocation is not fully listed and recoverable';
   end if;
   select * into strict l from public.amazon_merchant_inventory_lots where allocation_id=a.id for update;
   if l.seller_sku is not null or l.quantity<>a.quantity or l.unit_cost is distinct from (a.snapshot->>'unit_cost')::numeric
    or exists(select 1 from public.amazon_mf_lots where listing_lot_id=l.id)
    or not exists(select 1 from public.purchase_items where item_id=l.listed_item_id and current_status='listed' and quantity>=l.quantity) then
     raise exception 'Source inventory has changed or reconciled; recovery blocked';
   end if;
   if x->>'condition' is distinct from 'new' then raise exception 'This recovery requires source evidence of New condition'; end if;
   insert into public.amazon_listing_allocations(batch_id,source_key,source_item_id,purchase_id,snapshot,quantity,recovery_source_allocation_id)
   values(p_batch,'recovery:'||a.id,a.source_item_id,a.purchase_id,
    a.snapshot||jsonb_build_object('fulfillment_method','MF','seller_sku',nullif(x->>'seller_sku',''),'condition','new',
      'recovery_source_allocation_id',a.id,'recovery_source_batch_id',a.batch_id),a.quantity,a.id) returning id into new_id;
   -- Keep physical lot ID, cost, receipt pointers and original listed timestamp intact.
   update public.amazon_merchant_inventory_lots set allocation_id=new_id,condition='new' where id=l.id;
   update public.amazon_listing_allocations set listed_quantity=0,transferred_quantity=quantity,recovery_batch_id=p_batch where id=a.id;
   recovery_selection:=recovery_selection||jsonb_build_object('recovery:'||a.id,a.quantity::text);
 end loop;
 update public.amazon_listing_batches set
  status=case when exists(select 1 from public.amazon_listing_allocations active_alloc where active_alloc.batch_id=amazon_listing_batches.id and active_alloc.quantity>active_alloc.transferred_quantity)
   then 'partially_recovered' else 'recovered' end,updated_at=now()
 where id in(select moved_alloc.batch_id from public.amazon_listing_allocations moved_alloc where moved_alloc.recovery_batch_id=p_batch);
 update public.amazon_listing_batches set selection=recovery_selection,export_csv=p_csv,status='exported',exported_at=now(),updated_at=now()
 where id=p_batch returning * into b;
 return to_jsonb(b);
end $$;
revoke all on function public.mbop_recover_mf_listing(uuid,timestamp,jsonb,text,jsonb) from public,anon,authenticated;
grant execute on function public.mbop_recover_mf_listing(uuid,timestamp,jsonb,text,jsonb) to service_role;

-- Recovery confirmation reuses its existing physical lot; normal listing behavior is unchanged.
create or replace function public.mbop_complete_mf_listing(p_batch uuid,p_request uuid,p_items jsonb,p_local timestamp)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare b public.amazon_listing_batches; a public.amazon_listing_allocations; s public.purchase_items;
  x jsonb; q integer; listed_id uuid; c public.amazon_listing_completions; total integer:=0; ref text; lot public.amazon_merchant_inventory_lots;
begin
  select * into strict b from public.amazon_listing_batches where id=p_batch for update;
  select * into c from public.amazon_listing_completions where request_id=p_request;
  if found then
    if c.batch_id <> p_batch or c.payload is distinct from p_items then raise exception 'Completion request already used with different allocations'; end if;
    return to_jsonb(b);
  end if;
  if b.fulfillment_method <> 'MF' or b.status not in ('exported','partially_listed') then raise exception 'Only pending exported MF batches can be marked listed'; end if;
  if p_local is null or jsonb_array_length(p_items)=0 then raise exception 'Batch date/time and listed allocations are required'; end if;
  if (select count(*) <> count(distinct value->>'allocation_id') from jsonb_array_elements(p_items)) then raise exception 'Duplicate allocation'; end if;
  ref := 'MF ' || to_char(p_local,'YYYY-MM-DD HH12:MI AM');
  insert into public.amazon_listing_completions(request_id,batch_id,payload,external_reference) values(p_request,p_batch,p_items,ref);
  perform 1 from public.purchase_items where item_id in
    (select source_item_id from public.amazon_listing_allocations where batch_id=p_batch and id in
      (select (value->>'allocation_id')::uuid from jsonb_array_elements(p_items))) order by item_id for update;
  for x in select value from jsonb_array_elements(p_items) order by value->>'allocation_id' loop
    q := (x->>'quantity')::integer;
    select * into strict a from public.amazon_listing_allocations where id=(x->>'allocation_id')::uuid and batch_id=p_batch for update;
    if q is null or q<1 or q>a.quantity-a.listed_quantity-a.transferred_quantity then raise exception 'Valid pending quantity required'; end if;
    if a.recovery_source_allocation_id is not null then
      if q<>a.quantity or a.listed_quantity<>0 then raise exception 'Confirm the full recovery allocation or exclude it'; end if;
      select * into strict lot from public.amazon_merchant_inventory_lots where allocation_id=a.id for update;
      if lot.quantity<>q or lot.unit_cost is distinct from (a.snapshot->>'unit_cost')::numeric then raise exception 'Recovery lot changed'; end if;
      if nullif(trim(x->>'seller_sku'),'') is not null and lot.seller_sku is not null and lot.seller_sku<>trim(x->>'seller_sku') then raise exception 'Recovery SKU already reconciled'; end if;
      update public.amazon_merchant_inventory_lots set completion_request_id=p_request,
        seller_sku=coalesce(lot.seller_sku,nullif(trim(x->>'seller_sku'),'')) where id=lot.id;
      update public.amazon_listing_allocations set listed_quantity=listed_quantity+q where id=a.id;
      total:=total+q;
      continue;
    end if;
    -- Source locks are acquired above in a stable UUID order across batches.
    -- A source remains Received for its unlisted balance; a listed child preserves acquisition fields.
    select * into strict s from public.purchase_items where item_id=a.source_item_id for update;
    if s.current_status <> 'received' or s.marketplace='eBay' or s.exclude_from_purchase_reporting or s.asin is distinct from a.snapshot->>'asin' or s.quantity<q or s.condition is distinct from a.snapshot->>'condition' or s.unit_cost is distinct from (a.snapshot->>'unit_cost')::numeric then
      raise exception 'Source allocation is no longer available; reconcile the pending batch';
    end if;
    -- The merchant lot trigger validates the marketplace, method, and ASIN together.
    if q=s.quantity then
      listed_id:=s.item_id;
      update public.purchase_items set current_status='listed',raw_import_json=coalesce(raw_import_json,'{}') || '{"listing_fulfillment_method":"MF"}'::jsonb where item_id=s.item_id;
    else
      listed_id:=gen_random_uuid();
      -- Clone all original receipt/acquisition fields, including future added fields.
      insert into public.purchase_items select (jsonb_populate_record(null::public.purchase_items,
        to_jsonb(s) || jsonb_build_object('item_id',listed_id,'quantity',q,'current_status','listed','manual_split_child',true,
        'manual_split_parent_item_id',s.item_id,'raw_import_json',coalesce(s.raw_import_json,'{}') || '{"listing_fulfillment_method":"MF"}'::jsonb))).*;
      update public.purchase_items set quantity=quantity-q where item_id=s.item_id;
    end if;
    insert into public.amazon_merchant_inventory_lots(allocation_id,completion_request_id,source_item_id,listed_item_id,purchase_id,asin,seller_sku,condition,quantity,unit_cost)
      values(a.id,p_request,s.item_id,listed_id,a.purchase_id,a.snapshot->>'asin',nullif(trim(x->>'seller_sku'),''),a.snapshot->>'condition',q,(a.snapshot->>'unit_cost')::numeric);
    update public.amazon_listing_allocations set listed_quantity=listed_quantity+q where id=a.id;
    total:=total+q;
  end loop;
  if total=0 then raise exception 'Select at least one listed unit'; end if;
  update public.amazon_listing_batches set il_batch_local=p_local,external_reference=ref,completed_at=now(),updated_at=now(),
    status=case when exists(select 1 from public.amazon_listing_allocations where batch_id=p_batch and listed_quantity+transferred_quantity<quantity) then 'partially_listed' else 'completed' end
    where id=p_batch returning * into b;
  return to_jsonb(b);
end $$;
