-- MBOP listing identity is marketplace + fulfillment method + seller SKU.
-- Preserve provider registration IDs and all immutable batch/export history.
create or replace function public.mbop_listing_fulfillment_method(p_channel text)
returns text language sql immutable parallel safe set search_path=public as $$
  select case upper(trim(p_channel))
    when 'AMAZON' then 'FBA' when 'AMAZON_NA' then 'FBA' when 'AFN' then 'FBA' when 'FBA' then 'FBA'
    when 'DEFAULT' then 'MF' when 'MFN' then 'MF' when 'MF' then 'MF' when 'FBM' then 'MF'
    when 'MERCHANT' then 'MF' when 'MERCHANT_NA' then 'MF'
    else null end
$$;

alter table public.amazon_skus add column fulfillment_method text
  generated always as (public.mbop_listing_fulfillment_method(fulfillment_channel)) stored;
create index amazon_skus_fulfillment_identity_idx
  on public.amazon_skus(marketplace_id,fulfillment_method,asin,seller_sku);
comment on column public.amazon_skus.fulfillment_method is
  'Canonical current listing method. MSKU resolution must include marketplace and this method. ASIN alone never identifies an MSKU.';
comment on column public.amazon_listing_snapshots.fulfillment_channel is
  'Observed fulfillment context for this historical seller SKU snapshot. DEFAULT is MF, AMAZON_NA is FBA. Never resolve an MSKU across methods.';
comment on column public.amazon_listing_allocations.snapshot is
  'Immutable export allocation. New snapshots include fulfillment_method and the method-specific seller_sku. Legacy snapshots inherit method from their batch.';

-- Repair only current catalog rows whose retained report explicitly says DEFAULT.
update public.amazon_skus
set fulfillment_channel='DEFAULT',fnsku=null,updated_at=now()
where raw_listing_json->>'source' like 'amazon_report_%'
  and upper(raw_listing_json->'row'->>'fulfillment-channel')='DEFAULT'
  and (fulfillment_channel is distinct from 'DEFAULT' or fnsku is not null);

alter table public.amazon_merchant_inventory_lots
  add column fulfillment_method text not null default 'MF' check(fulfillment_method='MF');
alter table public.fba_shipment_items
  add column fulfillment_method text not null default 'FBA' check(fulfillment_method='FBA');
alter table public.fba_shipment_source_items
  add column fulfillment_method text not null default 'FBA' check(fulfillment_method='FBA');

create or replace function public.mbop_validate_listing_msku()
returns trigger language plpgsql security invoker set search_path=public as $$
declare market text;
begin
  -- Existing historical allocations retain their observed fulfillment context.
  if tg_op='UPDATE' then
    if new.seller_sku is not distinct from old.seller_sku and new.asin is not distinct from old.asin then return new;end if;
  end if;
  new.seller_sku:=nullif(trim(new.seller_sku),'');
  if new.seller_sku is null then return new;end if;
  select marketplace_id into market from public.amazon_mf_accounts where configured;
  market:=coalesce(market,'ATVPDKIKX0DER');
  if exists(select 1 from public.amazon_skus s where s.marketplace_id=market and s.seller_sku=new.seller_sku
    and s.fulfillment_method is not null and s.fulfillment_method<>new.fulfillment_method) then
    raise exception 'MSKU belongs to a different fulfillment method';
  end if;
  if exists(select 1 from public.amazon_skus s where s.marketplace_id=market and s.seller_sku=new.seller_sku
    and s.fulfillment_method=new.fulfillment_method and s.asin is distinct from new.asin) then
    raise exception 'MSKU is mapped to a different ASIN for this fulfillment method';
  end if;
  if new.fulfillment_method='MF' and not (
    exists(select 1 from public.amazon_skus s where s.marketplace_id=market and s.fulfillment_method='MF'
      and s.seller_sku=new.seller_sku and s.asin=new.asin)
    or exists(select 1 from public.amazon_mf_offers o join public.amazon_mf_accounts a on a.id=o.account_id
      where a.configured and a.marketplace_id=market and o.seller_sku=new.seller_sku and o.asin=new.asin
      and o.listing_state in ('in_stock','out_of_stock','unknown'))
  ) then
    raise exception 'MF MSKU is unverified; leave it pending Amazon reconciliation';
  end if;
  return new;
end $$;

create trigger merchant_listing_msku_method before insert or update of seller_sku,asin
  on public.amazon_merchant_inventory_lots for each row execute function public.mbop_validate_listing_msku();
create trigger fba_listing_msku_method before insert or update of seller_sku,asin
  on public.fba_shipment_items for each row execute function public.mbop_validate_listing_msku();
create trigger fba_source_msku_method before insert or update of seller_sku,asin
  on public.fba_shipment_source_items for each row execute function public.mbop_validate_listing_msku();

revoke all on function public.mbop_listing_fulfillment_method(text) from public,anon,authenticated;
revoke all on function public.mbop_validate_listing_msku() from public,anon,authenticated;
grant execute on function public.mbop_listing_fulfillment_method(text) to service_role;
grant execute on function public.mbop_validate_listing_msku() to service_role;

create function public.mbop_validate_allocation_fulfillment()
returns trigger language plpgsql security invoker set search_path=public as $$
declare method text; market text;
begin
  select fulfillment_method into strict method from public.amazon_listing_batches where id=new.batch_id;
  if new.snapshot ? 'fulfillment_method' and new.snapshot->>'fulfillment_method' is distinct from method then
    raise exception 'Allocation fulfillment method differs from batch';
  end if;
  new.snapshot:=new.snapshot || jsonb_build_object('fulfillment_method',method);
  select marketplace_id into market from public.amazon_mf_accounts where configured;
  market:=coalesce(market,'ATVPDKIKX0DER');
  if exists(select 1 from public.amazon_skus s where s.marketplace_id=market and s.seller_sku=new.snapshot->>'seller_sku'
    and (s.fulfillment_method is distinct from method or s.asin is distinct from new.snapshot->>'asin')) then
    raise exception 'Allocation MSKU differs from the batch fulfillment method or ASIN';
  end if;
  return new;
end $$;
create trigger listing_allocation_fulfillment before insert on public.amazon_listing_allocations
  for each row execute function public.mbop_validate_allocation_fulfillment();

create function public.mbop_preserve_batch_fulfillment()
returns trigger language plpgsql security invoker set search_path=public as $$
begin
  if old.fulfillment_method is distinct from new.fulfillment_method then
    raise exception 'Batch fulfillment method is immutable; start a new batch';
  end if;
  return new;
end $$;
create trigger listing_batch_fulfillment before update of fulfillment_method on public.amazon_listing_batches
  for each row execute function public.mbop_preserve_batch_fulfillment();
revoke all on function public.mbop_validate_allocation_fulfillment() from public,anon,authenticated;
revoke all on function public.mbop_preserve_batch_fulfillment() from public,anon,authenticated;
grant execute on function public.mbop_validate_allocation_fulfillment() to service_role;
grant execute on function public.mbop_preserve_batch_fulfillment() to service_role;

-- Replace the old unscoped SKU/ASIN validation with the fulfillment-scoped lot guard.
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
    status=case when exists(select 1 from public.amazon_listing_allocations where batch_id=p_batch and listed_quantity<quantity) then 'partially_listed' else 'completed' end
    where id=p_batch returning * into b;
  return to_jsonb(b);
end $$;
