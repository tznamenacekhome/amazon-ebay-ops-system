-- MBOP MF workflow: stock is never inferred from offer quantities.
create table public.amazon_mf_accounts (
 id uuid primary key default gen_random_uuid(), seller_id text not null, marketplace_id text not null,
 configured boolean not null default true, tracking_started_at timestamptz not null default now(),
 revision bigint not null default 0, revised_at timestamptz not null default now(),
 last_success_at timestamptz, orders_through timestamptz, offers_success_at timestamptz,
 last_attempt_at timestamptz,last_error text, unique(seller_id,marketplace_id)
);
create unique index amazon_mf_one_configured_account on public.amazon_mf_accounts(configured) where configured;
create table public.amazon_mf_sync_runs (
 id uuid primary key default gen_random_uuid(), account_id uuid references public.amazon_mf_accounts,
 started_at timestamptz not null default now(), finished_at timestamptz, status text not null default 'running',
 orders_through timestamptz, error text, stats jsonb not null default '{}'
);
create index on public.amazon_mf_sync_runs(account_id,started_at desc);
create table public.amazon_mf_offers (
 account_id uuid references public.amazon_mf_accounts, seller_sku text not null, asin text, title text,
 condition text not null, amazon_quantity integer, source_updated_at timestamptz, observed_at timestamptz not null,
 listing_status text[], brand text, sync_run_id uuid references public.amazon_mf_sync_runs,
 primary key(account_id,seller_sku)
);
create table public.amazon_mf_preferences (
 account_id uuid references public.amazon_mf_accounts, seller_sku text not null, keep_mf boolean not null,
 source text not null, updated_at timestamptz not null default now(), primary key(account_id,seller_sku)
);
create table public.amazon_mf_openings (
 id uuid primary key, account_id uuid not null references public.amazon_mf_accounts, seller_sku text not null,
 condition text not null, counted_on_hand integer not null check(counted_on_hand>=0),
 existing_on_hand integer not null, added_quantity integer not null check(added_quantity>=0),
 unit_cost numeric check(unit_cost>=0), notes text not null check(length(trim(notes))>0),
 observed_offer_quantity integer, confirmed_at timestamptz not null default now(),
 unique(account_id,seller_sku,condition)
);
create table public.amazon_mf_lots (
 id uuid primary key default gen_random_uuid(), account_id uuid not null references public.amazon_mf_accounts,
 listing_lot_id uuid unique references public.amazon_merchant_inventory_lots,
 opening_id uuid unique references public.amazon_mf_openings, seller_sku text not null, asin text,
 condition text not null, quantity integer not null check(quantity>0), unit_cost numeric check(unit_cost>=0),
 acquired_at timestamptz not null, stock_start_at timestamptz not null,
 inspection_held integer not null default 0 check(inspection_held>=0), transfer_allocated integer not null default 0 check(transfer_allocated>=0),
 check(num_nonnulls(listing_lot_id,opening_id)=1)
);
create index on public.amazon_mf_lots(account_id,seller_sku,condition,acquired_at,id);
create table public.amazon_mf_order_items (
 id uuid primary key default gen_random_uuid(), account_id uuid not null references public.amazon_mf_accounts,
 amazon_order_id text not null, amazon_order_item_id text not null, seller_sku text, asin text, title text,
 condition text not null, order_status text not null, ordered integer not null check(ordered>=0),
 shipped integer not null check(shipped>=0), baseline_shipped integer not null default 0,
 reservation_demand integer not null default 0 check(reservation_demand>=0),
 source_updated_at timestamptz not null, observed_at timestamptz not null default now(), purchased_at timestamptz not null,
 replacement_for jsonb not null default '[]', source_payload jsonb not null, anomaly text,
 unique(account_id,amazon_order_id,amazon_order_item_id)
);
create index on public.amazon_mf_order_items(account_id,seller_sku,condition,purchased_at);
create table public.amazon_mf_order_observations (
 account_id uuid not null references public.amazon_mf_accounts,amazon_order_id text not null,amazon_order_item_id text not null,
 source_updated_at timestamptz not null,observed_at timestamptz not null default now(),fingerprint text not null,outcome text not null,
 ordered integer not null,shipped integer not null,order_status text not null,
 primary key(account_id,amazon_order_id,amazon_order_item_id,source_updated_at,fingerprint)
);
create table public.amazon_mf_shipment_events (
 id uuid primary key default gen_random_uuid(), order_item_id uuid not null references public.amazon_mf_order_items,
 cumulative_shipped integer not null, quantity integer not null check(quantity>0),
 source_updated_at timestamptz not null, observed_at timestamptz not null default now(),
 unique(order_item_id,cumulative_shipped)
);
create table public.amazon_mf_lot_allocations (
 order_item_id uuid not null references public.amazon_mf_order_items, lot_id uuid not null references public.amazon_mf_lots,
 reserved integer not null default 0 check(reserved>=0), primary key(order_item_id,lot_id)
);
create index on public.amazon_mf_lot_allocations(lot_id);
create table public.amazon_mf_shipment_allocations (
 event_id uuid not null references public.amazon_mf_shipment_events,lot_id uuid not null references public.amazon_mf_lots,
 quantity integer not null check(quantity>0), primary key(event_id,lot_id)
);
create index on public.amazon_mf_shipment_allocations(lot_id);

create function public.mbop_mf_condition(v text) returns text language sql immutable as $$
 select case lower(coalesce(v,'')) when 'new_new' then 'new' when 'newitem' then 'new'
 when '' then 'unknown' when 'used_like_new' then 'used_mint' when 'used_very_good' then 'used_verygood' when 'collectible_like_new' then 'collectible_mint' when 'collectible_very_good' then 'collectible_verygood' else lower(v) end
$$;

create view public.vw_mf_lot_balances with(security_invoker=true) as
 select l.*,l.quantity-coalesce(s.shipped,0) as on_hand,coalesce(s.shipped,0) as shipped,
 coalesce(r.reserved,0) as order_reserved,
 l.quantity-coalesce(s.shipped,0)-coalesce(r.reserved,0)-l.inspection_held-l.transfer_allocated as available
 from public.amazon_mf_lots l
 left join (select lot_id,sum(quantity)::integer shipped from public.amazon_mf_shipment_allocations group by lot_id) s on s.lot_id=l.id
 left join (select lot_id,sum(reserved)::integer reserved from public.amazon_mf_lot_allocations group by lot_id) r on r.lot_id=l.id;

-- FIFO is exact account + MSKU + condition, never an ASIN-only substitution.
-- Allocated shipments are immutable. Reservations are rebuilt from current demand.
create function public.mbop_mf_allocate(p_account uuid) returns void language plpgsql security invoker set search_path=public as $$
declare e record; l record; o record; needed integer; take integer;
begin
 perform 1 from public.amazon_mf_accounts where id=p_account for update;
 update public.amazon_mf_lot_allocations set reserved=0 where order_item_id in(select id from public.amazon_mf_order_items where account_id=p_account);
 for e in select ev.*,i.seller_sku,i.condition,i.asin from public.amazon_mf_shipment_events ev join public.amazon_mf_order_items i on i.id=ev.order_item_id
   where i.account_id=p_account order by ev.source_updated_at,ev.id loop
   select e.quantity-coalesce(sum(quantity),0) into needed from public.amazon_mf_shipment_allocations where event_id=e.id;
   if needed<=0 then continue; end if;
   for l in select * from public.vw_mf_lot_balances where account_id=p_account and seller_sku=e.seller_sku and condition=e.condition
    and asin=e.asin and stock_start_at<=e.source_updated_at and on_hand>0 order by acquired_at,id loop
     take:=least(needed,l.on_hand);
     insert into public.amazon_mf_shipment_allocations values(e.id,l.id,take)
      on conflict(event_id,lot_id) do update set quantity=amazon_mf_shipment_allocations.quantity+excluded.quantity;
     needed:=needed-take; exit when needed=0;
   end loop;
 end loop;
 for o in select * from public.amazon_mf_order_items where account_id=p_account and reservation_demand>0 order by purchased_at,amazon_order_id,amazon_order_item_id loop
   needed:=o.reservation_demand;
   for l in select * from public.vw_mf_lot_balances where account_id=p_account and seller_sku=o.seller_sku and condition=o.condition and asin=o.asin and available>0 order by acquired_at,id loop
     take:=least(needed,l.available);
     insert into public.amazon_mf_lot_allocations values(o.id,l.id,take) on conflict(order_item_id,lot_id) do update set reserved=excluded.reserved;
     needed:=needed-take; exit when needed=0;
   end loop;
 end loop;
 update public.amazon_mf_accounts set revision=revision+1,revised_at=now() where id=p_account;
end $$;

create function public.mbop_mf_register_lots() returns void language plpgsql security invoker set search_path=public as $$
declare aid uuid;
begin
 select id into aid from public.amazon_mf_accounts where configured for update;
 if aid is null then return; end if;
 insert into public.amazon_mf_lots(account_id,listing_lot_id,seller_sku,asin,condition,quantity,unit_cost,acquired_at,stock_start_at)
 select aid,m.id,m.seller_sku,m.asin,public.mbop_mf_condition(m.condition),m.quantity,m.unit_cost,
 coalesce((a.snapshot->>'order_date')::timestamptz,m.listed_at),least(m.listed_at,b.il_batch_local at time zone b.business_timezone)
 from public.amazon_merchant_inventory_lots m join public.amazon_listing_allocations a on a.id=m.allocation_id join public.amazon_listing_batches b on b.id=a.batch_id
 on conflict(listing_lot_id) do nothing;
 perform public.mbop_mf_allocate(aid);
end $$;
create function public.mbop_mf_listing_lot_trigger() returns trigger language plpgsql security invoker set search_path=public as $$
begin perform public.mbop_mf_register_lots();return new;end $$;
create trigger mf_register_completed_listing after insert on public.amazon_merchant_inventory_lots for each statement execute function public.mbop_mf_listing_lot_trigger();

create function public.mbop_mf_apply_order(p_account uuid,p_item jsonb) returns void language plpgsql security invoker set search_path=public as $$
declare old public.amazon_mf_order_items; rowid uuid; q integer; shippedq integer; base integer:=0; demand integer; source_at timestamptz; start_at timestamptz;
begin
 select tracking_started_at into strict start_at from public.amazon_mf_accounts where id=p_account for update;
 if p_item->>'marketplace_id' is distinct from (select marketplace_id from public.amazon_mf_accounts where id=p_account)
 or p_item->>'fulfillment_channel'<>'MFN' then raise exception 'MF account/marketplace/channel mismatch';end if;
 source_at:=(p_item->>'source_updated_at')::timestamptz;
 if source_at is null then raise exception 'Source timestamp required';end if;
 q:=(p_item->>'ordered')::integer;shippedq:=(p_item->>'shipped')::integer;
 if q is null or shippedq is null or q<0 or shippedq<0 then raise exception 'Valid order quantities required';end if;
 select * into old from public.amazon_mf_order_items where account_id=p_account and amazon_order_id=p_item->>'amazon_order_id' and amazon_order_item_id=p_item->>'amazon_order_item_id';
 insert into public.amazon_mf_order_observations(account_id,amazon_order_id,amazon_order_item_id,source_updated_at,fingerprint,outcome,ordered,shipped,order_status)
 values(p_account,p_item->>'amazon_order_id',p_item->>'amazon_order_item_id',source_at,md5(p_item::text),
 case when source_at<old.source_updated_at then 'stale_ignored' when source_at=old.source_updated_at and old.source_payload is distinct from p_item then 'timestamp_conflict' else 'observed' end,q,shippedq,p_item->>'status') on conflict do nothing;
 if old.id is not null then
  if source_at<old.source_updated_at then return;end if;
  if source_at=old.source_updated_at then
    if old.source_payload is distinct from p_item then update public.amazon_mf_order_items set anomaly='Conflicting observations at identical source timestamp' where id=old.id;end if;
    return;
  end if;
  if old.seller_sku is distinct from p_item->>'seller_sku' or old.condition<>public.mbop_mf_condition(p_item->>'condition') or old.asin is distinct from p_item->>'asin' then
   update public.amazon_mf_order_items set anomaly='Order product identity changed; reconciliation required' where id=old.id;return;
  end if;
  base:=old.baseline_shipped;
  if source_at<start_at then base:=greatest(base,shippedq);end if;
 elsif source_at<start_at then base:=shippedq;
 end if;
 demand:=case when p_item->>'status' in ('Canceled','Shipped','Unfulfillable') then 0 else (p_item->>'unfulfilled')::integer end;
 if demand is null or demand<0 then raise exception 'Unfulfilled quantity required';end if;
 insert into public.amazon_mf_order_items(account_id,amazon_order_id,amazon_order_item_id,seller_sku,asin,title,condition,order_status,ordered,shipped,baseline_shipped,reservation_demand,source_updated_at,purchased_at,replacement_for,source_payload,anomaly)
 values(p_account,p_item->>'amazon_order_id',p_item->>'amazon_order_item_id',p_item->>'seller_sku',p_item->>'asin',p_item->>'title',public.mbop_mf_condition(p_item->>'condition'),p_item->>'status',q,greatest(shippedq,coalesce(old.shipped,0)),base,demand,source_at,(p_item->>'purchased_at')::timestamptz,coalesce(p_item->'replacement_for','[]'),p_item,
 case when shippedq<old.shipped then 'Amazon shipped quantity decreased; physical stock was not restored' when shippedq+ demand>q then 'Fulfilled plus unfulfilled exceeds ordered quantity' end)
 on conflict(account_id,amazon_order_id,amazon_order_item_id) do update set order_status=excluded.order_status,ordered=excluded.ordered,shipped=excluded.shipped,baseline_shipped=excluded.baseline_shipped,reservation_demand=excluded.reservation_demand,
 source_updated_at=excluded.source_updated_at,observed_at=now(),source_payload=excluded.source_payload,anomaly=excluded.anomaly returning id into rowid;
 if shippedq>greatest(coalesce(old.shipped,base),base) then
  insert into public.amazon_mf_shipment_events(order_item_id,cumulative_shipped,quantity,source_updated_at) values(rowid,shippedq,shippedq-greatest(coalesce(old.shipped,base),base),source_at) on conflict do nothing;
 end if;
 perform public.mbop_mf_allocate(p_account);
end $$;

create view public.vw_mf_orders with(security_invoker=true) as
 select i.*,coalesce(r.reserved,0)::integer as reserved,coalesce(s.allocated,0)::integer as stock_removed,
 i.reservation_demand-coalesce(r.reserved,0)::integer as reservation_shortage,
 i.shipped-i.baseline_shipped-coalesce(s.allocated,0)::integer as shipment_shortage
 from public.amazon_mf_order_items i
 left join(select order_item_id,sum(reserved) reserved from public.amazon_mf_lot_allocations group by order_item_id) r on r.order_item_id=i.id
 left join(select e.order_item_id,sum(a.quantity) allocated from public.amazon_mf_shipment_events e join public.amazon_mf_shipment_allocations a on a.event_id=e.id group by e.order_item_id) s on s.order_item_id=i.id;

create view public.vw_mf_inventory with(security_invoker=true) as
 with keys as(select account_id,seller_sku,condition from public.amazon_mf_lots union select account_id,seller_sku,condition from public.amazon_mf_offers union select account_id,seller_sku,condition from public.amazon_mf_order_items),
 stock as(select account_id,seller_sku,condition,max(asin) asin,sum(on_hand)::integer on_hand,sum(order_reserved)::integer reserved,sum(inspection_held)::integer inspection_held,sum(transfer_allocated)::integer transfer_allocated,sum(available)::integer available,count(*) lot_count from public.vw_mf_lot_balances group by 1,2,3),
 demand as(select account_id,seller_sku,condition,sum(reservation_demand)::integer demand,sum(reservation_shortage+shipment_shortage)::integer shortage from public.vw_mf_orders group by 1,2,3)
 select k.*,coalesce(o.asin,s.asin) asin,o.title,coalesce(s.on_hand,0) on_hand,coalesce(s.reserved,0) order_reserved,
 coalesce(s.inspection_held,0) inspection_held,coalesce(s.transfer_allocated,0) fba_transfer_allocation,
 coalesce(s.on_hand,0)-coalesce(d.demand,0)-coalesce(s.inspection_held,0)-coalesce(s.transfer_allocated,0) available,
 o.amazon_quantity as amazon_listed_quantity,o.observed_at as offer_observed_at,o.source_updated_at as offer_source_updated_at,
 coalesce(d.shortage,0) shortage,coalesce(s.lot_count,0) lot_count,
 coalesce(s.on_hand,0)-coalesce(d.demand,0)-coalesce(s.inspection_held,0)-coalesce(s.transfer_allocated,0)-o.amazon_quantity as quantity_difference,
 exists(select 1 from public.amazon_mf_openings x where x.account_id=k.account_id and x.seller_sku=k.seller_sku and x.condition=k.condition) opening_reconciled,
 coalesce(p.keep_mf,false) keep_mf,p.source as preference_source,a.last_success_at,a.last_attempt_at,a.last_error,
 case when o.observed_at is null then 'Manual / unmatched offer' when o.condition<>k.condition or o.asin is distinct from s.asin and s.asin is not null then 'Offer identity mismatch' else 'Amazon offer observed; physical count independent' end verification_state,
 (o.account_id is null) as unmatched_sku,(a.last_success_at is null or a.last_success_at<now()-interval '2 hours' or o.observed_at<now()-interval '2 hours' or o.observed_at<a.offers_success_at) stale_sync
 from keys k join public.amazon_mf_accounts a on a.id=k.account_id
 left join stock s on s.account_id=k.account_id and s.seller_sku=k.seller_sku and s.condition=k.condition
 left join public.amazon_mf_offers o on o.account_id=k.account_id and o.seller_sku=k.seller_sku and o.condition=k.condition
 left join demand d on d.account_id=k.account_id and d.seller_sku is not distinct from k.seller_sku and d.condition=k.condition
 left join public.amazon_mf_preferences p on p.account_id=k.account_id and p.seller_sku=k.seller_sku;

create function public.mbop_mf_opening(p_account uuid,p_request uuid,p_sku text,p_condition text,p_count integer,p_cost numeric,p_notes text,p_revision bigint) returns jsonb language plpgsql security invoker set search_path=public as $$
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
 if o.observed_at<now()-interval '2 hours' then raise exception 'Refresh Amazon offers before an opening balance';end if;
 select coalesce(sum(on_hand),0) into existing from public.vw_mf_lot_balances where account_id=p_account and seller_sku=p_sku and condition=p_condition;
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


create function public.mbop_mf_apply_offer(p_account uuid,p_offer jsonb) returns void language plpgsql security invoker set search_path=public as $$
begin
 perform 1 from public.amazon_mf_accounts where id=p_account for update;
 insert into public.amazon_mf_offers(account_id,seller_sku,asin,title,condition,amazon_quantity,source_updated_at,observed_at,listing_status,brand,sync_run_id)
 values(p_account,p_offer->>'seller_sku',p_offer->>'asin',p_offer->>'title',public.mbop_mf_condition(p_offer->>'condition'),(p_offer->>'quantity')::integer,(p_offer->>'source_updated_at')::timestamptz,(p_offer->>'observed_at')::timestamptz,
 array(select jsonb_array_elements_text(coalesce(p_offer->'status','[]'))),p_offer->>'brand',(p_offer->>'run_id')::uuid)
 on conflict(account_id,seller_sku) do update set asin=excluded.asin,title=excluded.title,condition=excluded.condition,amazon_quantity=excluded.amazon_quantity,
 source_updated_at=excluded.source_updated_at,observed_at=excluded.observed_at,listing_status=excluded.listing_status,brand=excluded.brand,sync_run_id=excluded.sync_run_id
 where excluded.observed_at>amazon_mf_offers.observed_at and coalesce(excluded.source_updated_at,'-infinity')>=coalesce(amazon_mf_offers.source_updated_at,'-infinity');
 -- Exact structured brand or explicitly reviewed ASIN from the prior Tilly audit.
 -- DO NOTHING preserves every later operator choice, including Keep MF=false.
 if lower(trim(p_offer->>'brand')) in ('tilly tackers','tilly tacker') or p_offer->>'asin'='B092FLB415' then
 insert into public.amazon_mf_preferences values(p_account,p_offer->>'seller_sku',true,'identified_tilly_default',now()) on conflict do nothing;
 end if;
 update public.amazon_mf_accounts set revision=revision+1,revised_at=now() where id=p_account;
end $$;
create function public.mbop_mf_sync_finish(p_run uuid,p_through timestamptz,p_error text,p_stats jsonb) returns void language plpgsql security invoker set search_path=public as $$
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
end $$;

create function public.mbop_mf_purchase_balances(p_items uuid[]) returns table(listed_item_id uuid,on_hand bigint)
 language sql security invoker set search_path=public as $$
 select m.listed_item_id,sum(b.on_hand) from public.vw_mf_lot_balances b join public.amazon_merchant_inventory_lots m on m.id=b.listing_lot_id
 where m.listed_item_id=any(p_items) group by m.listed_item_id
$$;

-- All MF data and privileged functions remain server-only, matching MBOP architecture.
do $$ declare t text;f record;begin
 foreach t in array array['amazon_mf_accounts','amazon_mf_sync_runs','amazon_mf_offers','amazon_mf_preferences','amazon_mf_openings','amazon_mf_lots','amazon_mf_order_items','amazon_mf_order_observations','amazon_mf_shipment_events','amazon_mf_lot_allocations','amazon_mf_shipment_allocations'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('revoke all on public.%I from anon,authenticated',t);
 execute format('grant all on public.%I to service_role',t);
 end loop;
 for f in select oid::regprocedure sig from pg_proc where pronamespace='public'::regnamespace and proname like 'mbop_mf_%' loop
 execute format('revoke all on function %s from public,anon,authenticated',f.sig);
 execute format('grant execute on function %s to service_role',f.sig);
 end loop;
end $$;
revoke all on public.vw_mf_lot_balances,public.vw_mf_orders,public.vw_mf_inventory from anon,authenticated;
grant select on public.vw_mf_lot_balances,public.vw_mf_orders,public.vw_mf_inventory to service_role;
