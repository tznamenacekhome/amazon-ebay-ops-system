-- Optional MSKU at manual completion; no placeholder SKU or duplicate physical stock.
alter table public.amazon_merchant_inventory_lots alter column seller_sku drop not null;
alter table public.amazon_merchant_inventory_lots add column msku_reconciled_at timestamptz;
create index merchant_inventory_pending_msku on public.amazon_merchant_inventory_lots(asin) where seller_sku is null;
create or replace function public.mbop_complete_mf_listing(p_batch uuid,p_request uuid,p_items jsonb,p_local timestamp)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare b public.amazon_listing_batches; a public.amazon_listing_allocations; s public.purchase_items;
  x jsonb; q integer; listed_id uuid; c public.amazon_listing_completions; total integer:=0; ref text;
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
    if q is null or q<1 or q>a.quantity-a.listed_quantity then raise exception 'Valid pending quantity required'; end if;
    -- Source locks are acquired above in a stable UUID order across batches.
    -- A source remains Received for its unlisted balance; a listed child preserves acquisition fields.
    select * into strict s from public.purchase_items where item_id=a.source_item_id for update;
    if s.current_status <> 'received' or s.marketplace='eBay' or s.exclude_from_purchase_reporting or s.asin is distinct from a.snapshot->>'asin' or s.quantity<q or s.condition is distinct from a.snapshot->>'condition' or s.unit_cost is distinct from (a.snapshot->>'unit_cost')::numeric then
      raise exception 'Source allocation is no longer available; reconcile the pending batch';
    end if;
    if exists(select 1 from public.amazon_skus where seller_sku=trim(x->>'seller_sku') and asin is distinct from s.asin) then
      raise exception 'MSKU is mapped to a different ASIN';
    end if;
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
    status=case when exists(select 1 from public.amazon_listing_allocations where batch_id=p_batch and listed_quantity<quantity) then 'partially_listed' else 'completed' end
    where id=p_batch returning * into b;
  return to_jsonb(b);
end $$;
create or replace function public.mbop_mf_register_lots() returns void language plpgsql security invoker set search_path=public as $$
declare aid uuid;
begin
 select id into aid from public.amazon_mf_accounts where configured for update;
 if aid is null then return; end if;
 -- Only a complete, newer Amazon offer snapshot can resolve an unknown MSKU.
 update public.amazon_merchant_inventory_lots m set seller_sku=c.sku,msku_reconciled_at=now()
 from (
   select m2.id,min(o.seller_sku) sku
   from public.amazon_merchant_inventory_lots m2
   join public.amazon_mf_accounts account on account.id=aid
   join public.amazon_mf_offers o on o.account_id=aid and o.asin=m2.asin
     and o.condition=public.mbop_mf_condition(m2.condition)
     and o.observed_at>=account.offers_success_at and o.observed_at>=m2.listed_at
     and o.listing_state in ('in_stock','out_of_stock','unknown')
   where m2.seller_sku is null and account.offers_success_at is not null
   group by m2.id having count(distinct o.seller_sku)=1
 ) c where m.id=c.id and m.seller_sku is null;
 insert into public.amazon_mf_lots(account_id,listing_lot_id,seller_sku,asin,condition,quantity,unit_cost,acquired_at,stock_start_at)
 select aid,m.id,m.seller_sku,m.asin,public.mbop_mf_condition(m.condition),m.quantity,m.unit_cost,
 coalesce((a.snapshot->>'order_date')::timestamptz,m.listed_at),least(m.listed_at,b.il_batch_local at time zone b.business_timezone)
 from public.amazon_merchant_inventory_lots m join public.amazon_listing_allocations a on a.id=m.allocation_id join public.amazon_listing_batches b on b.id=a.batch_id
 where m.seller_sku is not null
 on conflict(listing_lot_id) do nothing;
 perform public.mbop_mf_allocate(aid);
end $$;
create or replace function public.mbop_mf_sync_finish(p_run uuid,p_through timestamptz,p_error text,p_stats jsonb) returns void language plpgsql security invoker set search_path=public as $$
declare r public.amazon_mf_sync_runs;
begin
 select * into strict r from public.amazon_mf_sync_runs where id=p_run for update;
 update public.amazon_mf_sync_runs set finished_at=now(),status=case when p_error is null then 'completed' else 'failed' end,error=p_error,stats=p_stats,orders_through=p_through where id=p_run;
 update public.amazon_mf_accounts set
 last_success_at=case when p_error is null then greatest(last_success_at,now()) else last_success_at end,
 offers_success_at=case when p_error is null then greatest(offers_success_at,(p_stats->>'offers_observed_at')::timestamptz) else offers_success_at end,
 orders_through=case when p_error is null then greatest(orders_through,p_through) else orders_through end,
 last_error=case when r.started_at>=coalesce(last_attempt_at,'-infinity') then p_error else last_error end
 where id=r.account_id;
 if p_error is null then perform public.mbop_mf_register_lots();end if;
end $$;

create or replace function public.mbop_mf_opening(p_account uuid,p_request uuid,p_sku text,p_condition text,p_count integer,p_cost numeric,p_notes text,p_revision bigint) returns jsonb language plpgsql security invoker set search_path=public as $$
declare a public.amazon_mf_accounts;o public.amazon_mf_offers;existing integer;delta integer;prior public.amazon_mf_openings;
begin
 select * into strict a from public.amazon_mf_accounts where id=p_account for update;
 select * into prior from public.amazon_mf_openings where id=p_request;
 if found then
  if prior.account_id<>p_account or prior.seller_sku<>p_sku or prior.counted_on_hand<>p_count or prior.unit_cost is distinct from p_cost then raise exception 'Opening request already used for a different count';end if;
  return to_jsonb(prior);
 end if;
 if a.revision<>p_revision then raise exception 'Stock or orders changed since preview; refresh the count preview';end if;
 select * into strict o from public.amazon_mf_offers where account_id=p_account and seller_sku=p_sku and condition=p_condition;
 if exists(select 1 from public.amazon_merchant_inventory_lots m where m.seller_sku is null and m.asin=o.asin) then raise exception 'Listed stock for this ASIN awaits Amazon MSKU reconciliation; resolve it before adding an opening balance';end if;
 if o.observed_at<now()-interval '2 hours' then raise exception 'Refresh Amazon offers before an opening balance';end if;
 select coalesce(sum(on_hand),0) into existing from public.vw_mf_lot_balances where account_id=p_account and seller_sku=p_sku and condition=p_condition;
 existing:=existing+coalesce((select sum(quantity) from public.vw_mf_return_holds where account_id=p_account and seller_sku=p_sku and condition=p_condition),0);
 delta:=p_count-existing;
 if delta<0 then raise exception 'Count is below existing MBOP stock; investigate discrepancy instead of adding an opening balance';end if;
 insert into public.amazon_mf_openings(id,account_id,seller_sku,condition,counted_on_hand,existing_on_hand,added_quantity,unit_cost,notes,observed_offer_quantity)
 values(p_request,p_account,p_sku,p_condition,p_count,existing,delta,p_cost,p_notes,o.amazon_quantity) returning * into prior;
 if delta>0 then
 insert into public.amazon_mf_lots(account_id,opening_id,seller_sku,asin,condition,quantity,unit_cost,acquired_at,stock_start_at)
 values(p_account,p_request,p_sku,o.asin,p_condition,delta,p_cost,now(),now());end if;
 perform public.mbop_mf_allocate(p_account);
 return to_jsonb(prior);
end $$;



create view public.vw_mf_pending_msku with(security_invoker=true) as
 select m.*,account.id account_id,b.external_reference,a.snapshot->>'title' title
 from public.amazon_merchant_inventory_lots m
 join public.amazon_listing_allocations a on a.id=m.allocation_id
 join public.amazon_listing_batches b on b.id=a.batch_id
 join public.amazon_mf_accounts account on account.configured
 where m.seller_sku is null;
revoke all on public.vw_mf_pending_msku from public,anon,authenticated;
grant select on public.vw_mf_pending_msku to service_role;
create or replace function public.mbop_mf_purchase_balances(p_items uuid[]) returns table(listed_item_id uuid,on_hand bigint)
 language sql security invoker set search_path=public as $$
 with recursive lineage as (
 select l.id,l.listing_lot_id from amazon_mf_lots l where l.listing_lot_id is not null
 union all select l.id,p.listing_lot_id from amazon_mf_lots l join lineage p on p.id=l.parent_lot_id
 ), balances as (
 select m.listed_item_id,b.on_hand::bigint from vw_mf_lot_balances b join lineage x on x.id=b.id
 join amazon_merchant_inventory_lots m on m.id=x.listing_lot_id where m.listed_item_id=any(p_items)
 union all select m.listed_item_id,m.quantity::bigint from amazon_merchant_inventory_lots m where m.seller_sku is null and m.listed_item_id=any(p_items)
 ) select balances.listed_item_id,sum(balances.on_hand)::bigint from balances group by balances.listed_item_id;
$$;
