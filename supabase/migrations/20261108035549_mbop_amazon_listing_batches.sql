-- MBOP-owned listing workflow. No Amazon API writes or availability claims.
create table public.amazon_listing_batches (
  id uuid primary key default gen_random_uuid(),
  fulfillment_method text not null check (fulfillment_method in ('FBA','MF')),
  external_reference text not null,
  il_batch_local timestamp without time zone not null,
  business_timezone text not null default 'America/Los_Angeles' check (business_timezone = 'America/Los_Angeles'),
  status text not null default 'draft' check (status in ('draft','exported','partially_listed','completed')),
  selection jsonb not null default '{}',
  export_csv text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  exported_at timestamptz,
  completed_at timestamptz,
  fba_shipment_code text
);
create table public.amazon_listing_allocations (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.amazon_listing_batches(id),
  source_key text not null,
  source_item_id uuid references public.purchase_items(item_id),
  purchase_id uuid references public.purchases(purchase_id),
  snapshot jsonb not null,
  quantity integer not null check (quantity > 0),
  listed_quantity integer not null default 0 check (listed_quantity >= 0 and listed_quantity <= quantity),
  unique(batch_id,source_key)
);
create table public.amazon_listing_completions (
  request_id uuid primary key,
  batch_id uuid not null references public.amazon_listing_batches(id),
  payload jsonb not null,
  external_reference text not null,
  completed_at timestamptz not null default now()
);
create table public.amazon_merchant_inventory_lots (
  id uuid primary key default gen_random_uuid(),
  allocation_id uuid not null references public.amazon_listing_allocations(id),
  completion_request_id uuid not null references public.amazon_listing_completions(request_id),
  source_item_id uuid not null references public.purchase_items(item_id),
  listed_item_id uuid not null references public.purchase_items(item_id),
  purchase_id uuid not null references public.purchases(purchase_id),
  asin text not null,
  seller_sku text not null check (length(trim(seller_sku)) > 0),
  condition text,
  quantity integer not null check (quantity > 0),
  unit_cost numeric not null check (unit_cost >= 0),
  physical_location text not null default 'merchant' check (physical_location='merchant'),
  confirmation_source text not null default 'manual' check (confirmation_source='manual'),
  amazon_verified_at timestamptz,
  listed_at timestamptz not null default now(),
  unique(completion_request_id,allocation_id),
  check (amazon_verified_at is null)
);
create index on public.amazon_listing_batches(created_at desc);
create index on public.amazon_listing_allocations(source_item_id);
create index on public.amazon_merchant_inventory_lots(source_item_id);
create index on public.amazon_merchant_inventory_lots(listed_at desc);
create index on public.amazon_merchant_inventory_lots(allocation_id);
create index on public.amazon_listing_completions(batch_id);
alter table public.amazon_listing_batches enable row level security;
alter table public.amazon_listing_allocations enable row level security;
alter table public.amazon_listing_completions enable row level security;
alter table public.amazon_merchant_inventory_lots enable row level security;
revoke all on public.amazon_listing_batches, public.amazon_listing_allocations, public.amazon_listing_completions, public.amazon_merchant_inventory_lots from anon, authenticated;
grant all on public.amazon_listing_batches, public.amazon_listing_allocations, public.amazon_listing_completions, public.amazon_merchant_inventory_lots to service_role;

-- Lock the batch for every mutation, including export-vs-draft races.
create function public.mbop_save_listing_batch(p_id uuid, p_method text, p_local timestamp, p_reference text, p_selection jsonb, p_csv text default null, p_allocations jsonb default null)
returns jsonb language plpgsql security invoker set search_path = public as $$
declare b public.amazon_listing_batches; a jsonb; s public.purchase_items;
begin
  if p_method not in ('FBA','MF') or p_method is null or p_local is null or nullif(trim(p_reference),'') is null then
    raise exception 'Method, InventoryLab date/time and reference are required';
  end if;
  insert into public.amazon_listing_batches(id,fulfillment_method,il_batch_local,external_reference,selection)
    values(p_id,p_method,p_local,p_reference,p_selection) on conflict(id) do nothing;
  select * into strict b from public.amazon_listing_batches where id=p_id for update;
  if b.status <> 'draft' then
    if p_csv is not null then return to_jsonb(b); end if;
    raise exception 'Exported batches are immutable; start a new selection';
  end if;
  if p_csv is not null then
    if jsonb_array_length(p_allocations)=0 or p_allocations is null then raise exception 'No allocations selected'; end if;
    for a in select value from jsonb_array_elements(p_allocations) order by value->>'item_id' loop
      if p_method='MF' and a->>'source_type' <> 'purchase_item' then raise exception 'MF supports received purchase allocations only'; end if;
      if a->>'source_type'='purchase_item' then
        select * into strict s from public.purchase_items where item_id=(a->>'item_id')::uuid for update;
        if s.current_status <> 'received' or s.marketplace='eBay' or s.exclude_from_purchase_reporting or s.asin is distinct from a->>'asin'
          or (a->>'quantity')::integer < 1 or (a->>'quantity')::integer > s.quantity then
          raise exception 'Allocation changed; refresh and review the selection';
        end if;
      end if;
      insert into public.amazon_listing_allocations(batch_id,source_key,source_item_id,purchase_id,snapshot,quantity)
        values(p_id,a->>'item_id',case when a->>'source_type'='purchase_item' then (a->>'item_id')::uuid end,
          (a->>'purchase_id')::uuid,case when a->>'source_type'='purchase_item' then a || jsonb_build_object('purchase_item_snapshot',to_jsonb(s)) else a end,(a->>'quantity')::integer);
    end loop;
  end if;
  update public.amazon_listing_batches set fulfillment_method=p_method,il_batch_local=p_local,external_reference=p_reference,
    selection=p_selection,export_csv=p_csv,exported_at=case when p_csv is not null then now() end,
    status=case when p_csv is not null then 'exported' else 'draft' end,updated_at=now() where id=p_id returning * into b;
  return to_jsonb(b);
end $$;

create function public.mbop_complete_mf_listing(p_batch uuid,p_request uuid,p_items jsonb,p_local timestamp)
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
    if q is null or q<1 or q>a.quantity-a.listed_quantity or nullif(trim(x->>'seller_sku'),'') is null then raise exception 'Valid pending quantity and actual Amazon MSKU required'; end if;
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
      values(a.id,p_request,s.item_id,listed_id,a.purchase_id,a.snapshot->>'asin',trim(x->>'seller_sku'),a.snapshot->>'condition',q,(a.snapshot->>'unit_cost')::numeric);
    update public.amazon_listing_allocations set listed_quantity=listed_quantity+q where id=a.id;
    total:=total+q;
  end loop;
  if total=0 then raise exception 'Select at least one listed unit'; end if;
  update public.amazon_listing_batches set il_batch_local=p_local,external_reference=ref,completed_at=now(),updated_at=now(),
    status=case when exists(select 1 from public.amazon_listing_allocations where batch_id=p_batch and listed_quantity<quantity) then 'partially_listed' else 'completed' end
    where id=p_batch returning * into b;
  return to_jsonb(b);
end $$;
revoke all on function public.mbop_save_listing_batch(uuid,text,timestamp,text,jsonb,text,jsonb) from public,anon,authenticated;
revoke all on function public.mbop_complete_mf_listing(uuid,uuid,jsonb,timestamp) from public,anon,authenticated;
grant execute on function public.mbop_save_listing_batch(uuid,text,timestamp,text,jsonb,text,jsonb) to service_role;
grant execute on function public.mbop_complete_mf_listing(uuid,uuid,jsonb,timestamp) to service_role;

-- Existing FBA mutations stay in their established API; this records their batch history.
create function public.mbop_finish_fba_listing_batch(p_batch uuid,p_code text)
returns void language plpgsql security invoker set search_path=public as $$
declare b public.amazon_listing_batches; x record;
begin
  select * into strict b from public.amazon_listing_batches where id=p_batch for update;
  if b.fulfillment_method<>'FBA' then raise exception 'FBA batch required'; end if;
  for x in select key,value from jsonb_each_text(b.selection) where value::integer>0 loop
    if x.key not like 'amazon-return:%' and not exists(
      select 1 from public.fba_shipment_items i join public.fba_shipments s on i.fba_shipment_id=s.fba_shipment_id
      where s.shipment_code=p_code and i.item_id=x.key::uuid and i.quantity=x.value::integer and i.included
    ) then raise exception 'FBA allocation not saved; retry shipment save'; end if;
    if x.key like 'amazon-return:%' and not exists(
      select 1 from public.fba_shipment_source_items i join public.fba_shipments s on i.fba_shipment_id=s.fba_shipment_id
      where s.shipment_code=p_code and i.source_row_id=substring(x.key from 15)::uuid and i.quantity=x.value::integer and i.included
    ) then raise exception 'Return recovery allocation not saved; retry shipment save'; end if;
  end loop;
  update public.amazon_listing_allocations set listed_quantity=quantity where batch_id=p_batch;
  update public.amazon_listing_batches set status='completed',external_reference=p_code,fba_shipment_code=p_code,completed_at=coalesce(completed_at,now()),updated_at=now() where id=p_batch;
end $$;
revoke all on function public.mbop_finish_fba_listing_batch(uuid,text) from public,anon,authenticated;
grant execute on function public.mbop_finish_fba_listing_batch(uuid,text) to service_role;
