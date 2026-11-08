-- MBOP ordinary merchant-fulfilled customer returns. No Amazon writes.
create table public.amazon_mf_return_sync_runs (
 id uuid primary key default gen_random_uuid(),account_id uuid references public.amazon_mf_accounts,
 started_at timestamptz not null default now(),finished_at timestamptz,status text not null default 'running',
 error text,stats jsonb not null default '{}'
);
create index on public.amazon_mf_return_sync_runs(account_id,started_at desc);
create function public.mbop_mf_return_sync_begin(p_account uuid) returns uuid language plpgsql security invoker set search_path=public as $$
declare rid uuid;begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 if exists(select 1 from amazon_mf_return_sync_runs where account_id=p_account and status='running' and started_at>now()-interval '90 minutes') then return null;end if;
 update amazon_mf_return_sync_runs set status='failed',finished_at=now(),error='Worker lease expired; refresh resumes report IDs' where account_id=p_account and status='running';
 insert into amazon_mf_return_sync_runs(account_id)values(p_account)returning id into rid;return rid;
end $$;
create function public.mbop_mf_return_sync_finish(p_run uuid,p_error text,p_stats jsonb) returns void language plpgsql security invoker set search_path=public as $$
begin update amazon_mf_return_sync_runs set finished_at=now(),status=case when p_error is null then 'completed' else 'failed' end,error=p_error,stats=p_stats where id=p_run and status='running';end $$;
create table public.amazon_mf_return_reports (
 id uuid primary key default gen_random_uuid(),account_id uuid not null references public.amazon_mf_accounts,
 report_id text,window_start timestamptz not null,window_end timestamptz not null,
 requested_at timestamptz not null default now(),source_created_at timestamptz,status text not null default 'requesting',
 document_id text,imported_at timestamptz,error text,unique(account_id,report_id)
);
create index on public.amazon_mf_return_reports(account_id,window_start,window_end);
create table public.amazon_mf_returns (
 id uuid primary key default gen_random_uuid(),account_id uuid not null references public.amazon_mf_accounts,
 source_key text not null,amazon_order_id text not null,amazon_order_item_id text,order_item_id uuid references public.amazon_mf_order_items,
 rma text,merchant_rma text,seller_sku text,asin text,title text,expected_quantity integer not null check(expected_quantity>=0),
 order_at timestamptz,requested_at timestamptz,source_status text,reason text,resolution text,
 reported_refund_amount numeric,currency text,amazon_claim jsonb not null default '{}',source_dates jsonb not null default '{}',
 report_id uuid references public.amazon_mf_return_reports,source_observed_at timestamptz not null,
 identity_warning text,manual_returnless boolean not null default false,
 unique(account_id,source_key)
);
create index on public.amazon_mf_returns(account_id,amazon_order_id,amazon_order_item_id);
create index on public.amazon_mf_returns(account_id,rma);
create table public.amazon_mf_return_observations (
 return_id uuid not null references public.amazon_mf_returns,report_id uuid not null references public.amazon_mf_return_reports,
 fingerprint text not null,payload jsonb not null,observed_at timestamptz not null,
 primary key(return_id,report_id,fingerprint)
);
create table public.amazon_mf_return_packages (
 id uuid primary key default gen_random_uuid(),account_id uuid not null references public.amazon_mf_accounts,
 tracking_number text not null,carrier text,quoted_label_cost numeric,currency text,label_type text,
 amazon_delivery_at timestamptz,amazon_delivery_raw text,amazon_observed_at timestamptz,
 first_scan_at timestamptz,carrier_delivery_at timestamptz,carrier_observed_at timestamptz,
 easypost_tracker_id text,carrier_status text,carrier_error text,
 received_at timestamptz,receipt_request uuid unique,raw_scan text,receipt_notes text,unmatched boolean not null default false,
 unique(account_id,tracking_number)
);
create index on public.amazon_mf_return_packages(account_id,received_at);
create table public.amazon_mf_return_package_items (
 package_id uuid not null references public.amazon_mf_return_packages,return_id uuid not null references public.amazon_mf_returns,
 primary key(package_id,return_id)
);
create index on public.amazon_mf_return_package_items(return_id);
create table public.amazon_mf_return_finances (
 account_id uuid not null references public.amazon_mf_accounts,transaction_id text not null,
 amazon_order_id text not null,kind text not null,status text,posted_at timestamptz not null,
 amount numeric,currency text,description text,items jsonb not null default '[]',components jsonb not null default '[]',
 observed_at timestamptz not null,release_transaction_id text,deferred_transaction_id text,primary key(account_id,transaction_id)
);
create index on public.amazon_mf_return_finances(account_id,amazon_order_id,posted_at);
create table public.amazon_mf_return_finance_notes (
 id uuid primary key,account_id uuid not null,transaction_id text not null,return_id uuid not null references public.amazon_mf_returns,
 kind text not null check(kind in ('return_label','reimbursement','item_refund')),
 component_amount numeric not null,currency text not null,notes text not null,source_reference text not null,
 recorded_at timestamptz not null default now(),foreign key(account_id,transaction_id) references public.amazon_mf_return_finances,
 unique(account_id,transaction_id,return_id,kind)
);
create view public.vw_mf_return_finances with(security_invoker=true) as
 select f.* from amazon_mf_return_finances f where not exists(select 1 from amazon_mf_return_finances newer
 where newer.account_id=f.account_id and newer.status='RELEASED'
 and (newer.transaction_id=f.release_transaction_id or newer.deferred_transaction_id=f.transaction_id));
create table public.amazon_mf_return_inspections (
 id uuid primary key,account_id uuid not null references public.amazon_mf_accounts,
 return_id uuid not null references public.amazon_mf_returns,package_id uuid not null references public.amazon_mf_return_packages,
 quantity integer not null check(quantity>0),product_scan text not null,condition text not null,
 disposition text not null check(disposition in ('saleable','inspection_hold','damaged','wrong_item','missing')),
 missing_parts text,notes text not null,inspected_at timestamptz not null,recorded_at timestamptz not null default now(),
 lineage_warning text,request_payload jsonb not null,superseded_by uuid references public.amazon_mf_return_inspections
);
create index on public.amazon_mf_return_inspections(return_id,package_id);
create table public.amazon_mf_return_restock_allocations (
 inspection_id uuid not null references public.amazon_mf_return_inspections,
 original_lot_id uuid not null references public.amazon_mf_lots,quantity integer not null check(quantity>0),
 primary key(inspection_id,original_lot_id)
);
create table public.amazon_mf_return_claims (
 id uuid primary key,account_id uuid not null references public.amazon_mf_accounts,
 return_id uuid not null references public.amazon_mf_returns,claim_type text not null,case_id text,
 submitted_at timestamptz,claimed_amount numeric check(claimed_amount>=0),currency text not null,
 status text not null check(status in ('review','submitted','pending','appeal','resolved','denied','closed')),
 next_follow_up timestamptz,resolved_at timestamptz,resolution text,reimbursed_amount numeric check(reimbursed_amount>=0),
 deadline_at timestamptz,deadline_source text,notes text not null,updated_at timestamptz not null default now(),
 check(deadline_at is null or length(trim(deadline_source))>0)
);
create index on public.amazon_mf_return_claims(return_id,status,next_follow_up);
create table public.amazon_mf_return_evidence (
 id uuid primary key,account_id uuid not null references public.amazon_mf_accounts,
 return_id uuid not null references public.amazon_mf_returns,package_id uuid references public.amazon_mf_return_packages,
 inspection_id uuid references public.amazon_mf_return_inspections,claim_id uuid references public.amazon_mf_return_claims,
 url text not null check(url like 'https://%'),caption text not null,created_at timestamptz not null default now()
);
create index on public.amazon_mf_return_evidence(return_id);
-- Recorded merchant dates never replace Amazon/carrier source dates.
create table public.amazon_mf_return_dates (
 id uuid primary key,return_id uuid not null references public.amazon_mf_returns,
 kind text not null check(kind in ('authorization','first_scan','carrier_delivery','refund_posting')),
 occurred_at timestamptz not null,notes text not null,recorded_at timestamptz not null default now()
);

alter table public.amazon_mf_lots add column return_inspection_id uuid references public.amazon_mf_return_inspections;
alter table public.amazon_mf_lots add column parent_lot_id uuid references public.amazon_mf_lots;
-- Replace only this MBOP source-exclusivity check; no rows or external objects removed.
do $$ declare c record;begin
 for c in select conname from pg_constraint where conrelid='public.amazon_mf_lots'::regclass and contype='c'
 and pg_get_constraintdef(oid) like '%num_nonnulls%' loop
 execute format('alter table public.amazon_mf_lots drop constraint %I',c.conname);end loop;
end $$;
alter table public.amazon_mf_lots add constraint mf_lot_one_source check(num_nonnulls(listing_lot_id,opening_id,return_inspection_id)=1);
create unique index on public.amazon_mf_lots(return_inspection_id,parent_lot_id) nulls not distinct where return_inspection_id is not null;

create function public.mbop_mf_return_match(p_account uuid,p_return uuid,p_item uuid,p_quantity integer,p_notes text) returns void
language plpgsql security invoker set search_path=public as $$
declare r amazon_mf_returns;o amazon_mf_order_items;begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 select * into strict r from amazon_mf_returns where id=p_return and account_id=p_account;
 select * into strict o from amazon_mf_order_items where id=p_item and account_id=p_account and amazon_order_id=r.amazon_order_id;
 if nullif(trim(p_notes),'') is null or (r.seller_sku is not null and r.seller_sku<>o.seller_sku) or (r.asin is not null and r.asin<>o.asin) then raise exception 'Exact order/product identity and reconciliation notes required';end if;
 if exists(select 1 from amazon_mf_return_inspections where return_id=r.id) then raise exception 'Cannot change identity after inspection';end if;
 if p_quantity<1 or p_quantity>o.shipped then raise exception 'Explicit return quantity must be within Amazon shipped quantity';end if;
 update amazon_mf_returns set order_item_id=o.id,amazon_order_item_id=o.amazon_order_item_id,seller_sku=o.seller_sku,asin=o.asin,title=o.title,
 expected_quantity=case when source_key like 'finance-order:%' then p_quantity else expected_quantity end,
 identity_warning='Merchant reconciled identity: '||p_notes where id=r.id;
end $$;

create function public.mbop_mf_return_import(p_account uuid,p_report uuid,p_line jsonb) returns uuid
language plpgsql security invoker set search_path=public as $$
declare rid uuid;pid uuid;oi uuid;matches integer;observed timestamptz;pkg jsonb;old amazon_mf_returns;warn text;
begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 select coalesce(source_created_at,requested_at) into strict observed from amazon_mf_return_reports where id=p_report and account_id=p_account;
 select * into old from amazon_mf_returns where account_id=p_account and source_key=p_line->>'source_key';
 if old.source_observed_at>observed then return old.id;end if;
 select count(*),(array_agg(id))[1] into matches,oi from amazon_mf_order_items where account_id=p_account
 and amazon_order_id=p_line->>'amazon_order_id' and seller_sku=p_line->>'seller_sku'
 and (nullif(p_line->>'asin','') is null or asin=p_line->>'asin')
 and (nullif(p_line->>'amazon_order_item_id','') is null or amazon_order_item_id=p_line->>'amazon_order_item_id');
 warn:=p_line->>'identity_warning';
 if matches<>1 then oi:=null;warn:=concat_ws('; ',warn,'Order-item match missing or ambiguous; do not infer lineage');end if;
 insert into amazon_mf_returns(account_id,source_key,amazon_order_id,amazon_order_item_id,order_item_id,rma,merchant_rma,seller_sku,asin,title,expected_quantity,
 order_at,requested_at,source_status,reason,resolution,reported_refund_amount,currency,amazon_claim,source_dates,report_id,source_observed_at,identity_warning)
 values(p_account,p_line->>'source_key',p_line->>'amazon_order_id',p_line->>'amazon_order_item_id',oi,p_line->>'rma',p_line->>'merchant_rma',p_line->>'seller_sku',p_line->>'asin',p_line->>'title',(p_line->>'quantity')::integer,
 (p_line->>'order_at')::timestamptz,(p_line->>'requested_at')::timestamptz,p_line->>'status',p_line->>'reason',p_line->>'resolution',(p_line->>'reported_refund_amount')::numeric,p_line->>'currency',coalesce(p_line->'amazon_claim','{}'),coalesce(p_line->'source_dates','{}'),p_report,observed,warn)
 on conflict(account_id,source_key) do update set order_item_id=coalesce(excluded.order_item_id,amazon_mf_returns.order_item_id),
 expected_quantity=excluded.expected_quantity,source_status=excluded.source_status,reason=excluded.reason,resolution=excluded.resolution,
 reported_refund_amount=excluded.reported_refund_amount,currency=excluded.currency,amazon_claim=excluded.amazon_claim,
 source_dates=excluded.source_dates,source_observed_at=excluded.source_observed_at,report_id=excluded.report_id,identity_warning=excluded.identity_warning
 returning id into rid;
 insert into amazon_mf_return_observations values(rid,p_report,md5(p_line::text),p_line,observed) on conflict do nothing;
 for pkg in select * from jsonb_array_elements(coalesce(p_line->'packages','[]')) loop
 if nullif(pkg->>'tracking_number','') is null then continue;end if;
 insert into amazon_mf_return_packages(account_id,tracking_number,carrier,quoted_label_cost,currency,label_type,amazon_delivery_at,amazon_delivery_raw,amazon_observed_at)
 values(p_account,pkg->>'tracking_number',pkg->>'carrier',(pkg->>'quoted_label_cost')::numeric,pkg->>'currency',pkg->>'label_type',(pkg->>'delivery_at')::timestamptz,pkg->>'delivery_raw',observed)
 on conflict(account_id,tracking_number) do update set carrier=coalesce(excluded.carrier,amazon_mf_return_packages.carrier),
 amazon_delivery_at=coalesce(excluded.amazon_delivery_at,amazon_mf_return_packages.amazon_delivery_at),amazon_delivery_raw=coalesce(excluded.amazon_delivery_raw,amazon_mf_return_packages.amazon_delivery_raw),
 amazon_observed_at=excluded.amazon_observed_at,quoted_label_cost=excluded.quoted_label_cost
 where excluded.amazon_observed_at>=coalesce(amazon_mf_return_packages.amazon_observed_at,'-infinity') returning id into pid;
 if pid is null then select id into pid from amazon_mf_return_packages where account_id=p_account and tracking_number=pkg->>'tracking_number';end if;
 insert into amazon_mf_return_package_items values(pid,rid) on conflict do nothing;
 end loop;
 return rid;
end $$;

create function public.mbop_mf_return_finance(p_account uuid,p_transaction jsonb,p_observed timestamptz) returns void
language plpgsql security invoker set search_path=public as $$
declare oid text:=p_transaction->>'amazon_order_id';i record;
begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 if not exists(select 1 from amazon_mf_order_items where account_id=p_account and amazon_order_id=oid) then raise exception 'Financial order is not verified merchant fulfilled';end if;
 if nullif(p_transaction->>'marketplace_id','') is not null and p_transaction->>'marketplace_id'<>(select marketplace_id from amazon_mf_accounts where id=p_account) then raise exception 'Financial marketplace mismatch';end if;
 insert into amazon_mf_return_finances(account_id,transaction_id,amazon_order_id,kind,status,posted_at,amount,currency,description,items,components,observed_at,release_transaction_id,deferred_transaction_id)
 values(p_account,p_transaction->>'transaction_id',oid,p_transaction->>'kind',p_transaction->>'status',(p_transaction->>'posted_at')::timestamptz,(p_transaction->>'amount')::numeric,p_transaction->>'currency',p_transaction->>'description',p_transaction->'items',p_transaction->'components',p_observed,p_transaction->>'release_transaction_id',p_transaction->>'deferred_transaction_id')
 on conflict(account_id,transaction_id) do update set status=excluded.status,amount=excluded.amount,items=excluded.items,components=excluded.components,observed_at=excluded.observed_at,
 release_transaction_id=coalesce(excluded.release_transaction_id,amazon_mf_return_finances.release_transaction_id),deferred_transaction_id=coalesce(excluded.deferred_transaction_id,amazon_mf_return_finances.deferred_transaction_id)
 where excluded.observed_at>amazon_mf_return_finances.observed_at and not(amazon_mf_return_finances.status in ('RELEASED','DEFERRED_RELEASED') and excluded.status='DEFERRED');
 -- A refund-only placeholder keeps refunds/returnless refunds visible without inventing a physical return.
 if lower(p_transaction->>'kind')='refund' then
 insert into amazon_mf_returns(account_id,source_key,amazon_order_id,expected_quantity,source_observed_at,identity_warning)
 values(p_account,'finance-order:'||oid,oid,0,p_observed,'Refund without matched return; returnless status needs review') on conflict do nothing;
 end if;
end $$;

create function public.mbop_mf_return_receive(p_account uuid,p_request uuid,p_package uuid,p_tracking text,p_raw text,p_received timestamptz,p_notes text,p_return uuid default null) returns uuid
language plpgsql security invoker set search_path=public as $$
declare pid uuid;old amazon_mf_return_packages;
begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 if p_received is null or p_received>now()+interval '5 minutes' or nullif(trim(p_raw),'') is null then raise exception 'Actual package receipt date and raw scan required';end if;
 select * into old from amazon_mf_return_packages where receipt_request=p_request;
 if old.id is not null then
 if old.account_id<>p_account or old.raw_scan<>p_raw or old.received_at<>p_received then raise exception 'Receipt request reused with changed contents';end if;return old.id;end if;
 if p_package is not null then select * into strict old from amazon_mf_return_packages where id=p_package and account_id=p_account for update;pid:=old.id;
 else
 if nullif(trim(p_tracking),'') is null or nullif(trim(p_notes),'') is null then raise exception 'Unmatched package requires tracking and exception notes';end if;
 insert into amazon_mf_return_packages(account_id,tracking_number,unmatched) values(p_account,upper(p_tracking),true)
 on conflict(account_id,tracking_number) do nothing;
 select * into strict old from amazon_mf_return_packages where account_id=p_account and tracking_number=upper(p_tracking) for update;pid:=old.id;
 end if;
 if p_return is not null then
 perform 1 from amazon_mf_returns where id=p_return and account_id=p_account;if not found then raise exception 'Return scope mismatch';end if;
 insert into amazon_mf_return_package_items values(pid,p_return) on conflict do nothing;
 update amazon_mf_return_packages set unmatched=false where id=pid;
 end if;
 if old.received_at is not null then return old.id;end if;
 update amazon_mf_return_packages set received_at=p_received,receipt_request=p_request,raw_scan=p_raw,receipt_notes=p_notes where id=pid;
 return pid;
end $$;

create function public.mbop_mf_return_inspect(p_account uuid,p_request uuid,p_data jsonb) returns uuid
language plpgsql security invoker set search_path=public as $$
declare r amazon_mf_returns;pkg amazon_mf_return_packages;prior amazon_mf_return_inspections;
 q integer:=(p_data->>'quantity')::integer;disposition text:=p_data->>'disposition';cond text:=mbop_mf_condition(p_data->>'condition');
 oi amazon_mf_order_items;l record;needed integer;take integer;remaining integer;inspected timestamptz:=(p_data->>'inspected_at')::timestamptz;
begin
 perform 1 from amazon_mf_accounts where id=p_account for update;
 select * into prior from amazon_mf_return_inspections where id=p_request;
 if prior.id is not null then if prior.account_id<>p_account or prior.request_payload<>p_data then raise exception 'Inspection retry payload changed';end if;return prior.id;end if;
 select * into strict r from amazon_mf_returns where id=(p_data->>'return_id')::uuid and account_id=p_account;
 select * into strict pkg from amazon_mf_return_packages where id=(p_data->>'package_id')::uuid and account_id=p_account;
 if pkg.received_at is null or not exists(select 1 from amazon_mf_return_package_items where package_id=pkg.id and return_id=r.id) then raise exception 'Receive and explicitly associate this package before inspection';end if;
 if q is null or q<=0 or inspected is null or inspected<pkg.received_at or inspected>now()+interval '5 minutes' or nullif(trim(p_data->>'product_scan'),'') is null or nullif(trim(p_data->>'notes'),'') is null or cond='unknown' then raise exception 'Explicit count, product scan, condition, inspection date and notes required';end if;
 if disposition='saleable' and not coalesce((p_data->>'identity_confirmed')::boolean,false) then raise exception 'Verify actual product identity before saleable restock';end if;
 select r.expected_quantity-coalesce(sum(quantity),0) into remaining from amazon_mf_return_inspections where return_id=r.id and superseded_by is null;
 if p_data->>'release_inspection' is not null then
 select x.* into strict prior from amazon_mf_return_inspections x where x.id=(p_data->>'release_inspection')::uuid and x.return_id=r.id and x.package_id=pkg.id and x.disposition='inspection_hold' and x.superseded_by is null for update;
 if q<>prior.quantity then raise exception 'Resolve the complete held inspection quantity';end if;
 remaining:=remaining+prior.quantity;
 end if;
 if q>remaining then raise exception 'Inspection exceeds remaining expected quantity; reconcile return identity/quantity first';end if;
 select * into oi from amazon_mf_order_items where id=r.order_item_id;
 insert into amazon_mf_return_inspections(id,account_id,return_id,package_id,quantity,product_scan,condition,disposition,missing_parts,notes,inspected_at,lineage_warning,request_payload)
 values(p_request,p_account,r.id,pkg.id,q,p_data->>'product_scan',cond,disposition,p_data->>'missing_parts',p_data->>'notes',inspected,
 case when oi.id is null then 'Uncertain original purchase lineage' end,p_data);
 if p_data->>'release_inspection' is not null then update amazon_mf_return_inspections set superseded_by=p_request where id=prior.id;end if;
 if disposition='saleable' then
 if oi.seller_sku is null or oi.asin is null then raise exception 'Reconcile the Amazon order-item/MSKU identity before saleable restock';end if;
 if cond not in ('new','used_mint','used_verygood','used_good','used_acceptable','collectible_mint','collectible_verygood','collectible_good','collectible_acceptable','refurbished') then raise exception 'Saleable stock requires a supported sellable condition';end if;
 if q+coalesce((select sum(x.quantity) from amazon_mf_return_inspections x join amazon_mf_returns rr on rr.id=x.return_id where rr.order_item_id=oi.id and x.disposition='saleable' and x.id<>p_request and x.superseded_by is null),0)>oi.shipped then raise exception 'Saleable returns exceed Amazon shipped quantity across all return records';end if;
 needed:=q;
 -- Follow the actually shipped FIFO lots; never restore more to a lineage than was shipped.
 for l in select lot.*,s.shipped-coalesce(ret.returned,0) restorable from amazon_mf_lots lot
 join (select a.lot_id,sum(a.quantity)::integer shipped from amazon_mf_shipment_allocations a join amazon_mf_shipment_events e on e.id=a.event_id where e.order_item_id=oi.id group by a.lot_id)s on s.lot_id=lot.id
 left join (select a.original_lot_id,sum(a.quantity)::integer returned from amazon_mf_return_restock_allocations a join amazon_mf_return_inspections x on x.id=a.inspection_id join amazon_mf_returns rr on rr.id=x.return_id where rr.order_item_id=oi.id group by a.original_lot_id)ret on ret.original_lot_id=lot.id
 where s.shipped>coalesce(ret.returned,0) order by lot.acquired_at,lot.id loop
 take:=least(needed,l.restorable);
 insert into amazon_mf_return_restock_allocations values(p_request,l.id,take);
 insert into amazon_mf_lots(account_id,return_inspection_id,parent_lot_id,seller_sku,asin,condition,quantity,unit_cost,acquired_at,stock_start_at)
 values(p_account,p_request,l.id,oi.seller_sku,oi.asin,cond,take,l.unit_cost,l.acquired_at,inspected);
 needed:=needed-take;exit when needed=0;end loop;
 if needed>0 then
 -- Historical shipments can lack purchase allocations. Unknown cost is explicit, never fabricated.
 if not coalesce((p_data->>'uncertain_lineage_acknowledged')::boolean,false) then raise exception 'Original shipped cost lineage incomplete; explicitly acknowledge unknown cost';end if;
 if q+coalesce((select sum(x.quantity) from amazon_mf_return_inspections x join amazon_mf_returns rr on rr.id=x.return_id where rr.order_item_id=oi.id and x.disposition='saleable' and x.id<>p_request),0)>oi.shipped then raise exception 'Saleable returns exceed Amazon shipped quantity';end if;
 insert into amazon_mf_lots(account_id,return_inspection_id,seller_sku,asin,condition,quantity,acquired_at,stock_start_at)
 values(p_account,p_request,oi.seller_sku,oi.asin,cond,needed,inspected,inspected);
 update amazon_mf_return_inspections set lineage_warning='Original shipment lot unavailable; acquisition cost unknown' where id=p_request;
 end if;
 perform mbop_mf_allocate(p_account);
 end if;
 return p_request;
end $$;

-- Recreate view with identical original column order, then new source columns.
create or replace view public.vw_mf_lot_balances with(security_invoker=true) as
 select l.id,l.account_id,l.listing_lot_id,l.opening_id,l.seller_sku,l.asin,l.condition,l.quantity,l.unit_cost,l.acquired_at,l.stock_start_at,l.inspection_held,l.transfer_allocated,
 l.quantity-coalesce(s.shipped,0) as on_hand,coalesce(s.shipped,0) as shipped,coalesce(r.reserved,0) as order_reserved,
 l.quantity-coalesce(s.shipped,0)-coalesce(r.reserved,0)-l.inspection_held-l.transfer_allocated as available,
 l.return_inspection_id,l.parent_lot_id
 from public.amazon_mf_lots l
 left join (select lot_id,sum(quantity)::integer shipped from public.amazon_mf_shipment_allocations group by lot_id)s on s.lot_id=l.id
 left join (select lot_id,sum(reserved)::integer reserved from public.amazon_mf_lot_allocations group by lot_id)r on r.lot_id=l.id;

create view public.vw_mf_return_holds with(security_invoker=true) as
 select x.account_id,o.seller_sku,o.asin,x.condition,sum(x.quantity)::integer quantity
 from amazon_mf_return_inspections x join amazon_mf_returns r on r.id=x.return_id join amazon_mf_order_items o on o.id=r.order_item_id
 where x.disposition='inspection_hold' and x.superseded_by is null group by 1,2,3,4;
create or replace view public.vw_mf_inventory with(security_invoker=true) as
 with keys as(select account_id,seller_sku,condition from public.amazon_mf_lots union select account_id,seller_sku,condition from public.amazon_mf_offers union select account_id,seller_sku,condition from public.amazon_mf_order_items union select account_id,seller_sku,condition from public.vw_mf_return_holds),
 stock as(select account_id,seller_sku,condition,max(asin) asin,sum(on_hand)::integer on_hand,sum(order_reserved)::integer reserved,sum(inspection_held)::integer inspection_held,sum(transfer_allocated)::integer transfer_allocated,sum(available)::integer available,count(*) lot_count from (select account_id,seller_sku,condition,asin,on_hand,order_reserved,inspection_held,transfer_allocated,available from public.vw_mf_lot_balances union all select account_id,seller_sku,condition,asin,quantity,0,quantity,0,0 from public.vw_mf_return_holds) balances group by 1,2,3),
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

create or replace function public.mbop_mf_purchase_balances(p_items uuid[]) returns table(listed_item_id uuid,on_hand bigint)
 language sql security invoker set search_path=public as $$
 with recursive lineage as (
 select l.id,l.listing_lot_id from amazon_mf_lots l where l.listing_lot_id is not null
 union all select l.id,p.listing_lot_id from amazon_mf_lots l join lineage p on p.id=l.parent_lot_id
 ) select m.listed_item_id,sum(b.on_hand) from vw_mf_lot_balances b join lineage x on x.id=b.id
 join amazon_merchant_inventory_lots m on m.id=x.listing_lot_id where m.listed_item_id=any(p_items) group by m.listed_item_id
$$;
revoke all on public.vw_mf_return_holds from public,anon,authenticated;
grant select on public.vw_mf_return_holds to service_role;

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



create view public.vw_mf_open_returns with(security_invoker=true) as
 select r.*,coalesce(x.verified,0) inspected_quantity,coalesce(x.received_contents,0) received_quantity,
 coalesce(x.saleable,0) saleable_quantity,coalesce(x.held,0) inspection_held_quantity,
 p.package_received_at,p.carrier_delivery_at,p.first_scan_at,p.carrier_error,
 coalesce(x.exceptions,0)>0 contents_exception,
 case when coalesce(x.held,0)>0 then 'received_awaiting_inspection'
 when coalesce(x.verified,0)=0 and p.package_received_at is null then 'awaiting_return'
 when coalesce(x.verified,0)=0 then 'received_awaiting_inspection'
 when coalesce(x.verified,0)<r.expected_quantity then 'partially_received' else 'inspected' end physical_status,
 f.refund_posted_at,f.posted_refund_net,f.currency as financial_currency,
 case when f.refund_posted_at is null then 'no_posted_refund' when f.item_matched then 'posted_refund' else 'order_refund_needs_item_review' end financial_status,
 (f.refund_posted_at is not null and (coalesce(x.received_contents,0)<r.expected_quantity or r.source_key like 'finance-order:%') and not r.manual_returnless) refunded_unreceived,
 coalesce(p.delivered_unreceived,false) delivered_unreceived,
 (coalesce(c.unresolved,0)>0 or (nullif(r.amazon_claim->>'SafeT claim id','') is not null and lower(coalesce(r.amazon_claim->>'SafeT claim state','unknown')) not in ('closed','resolved','denied','approved'))) unresolved_claim,
 c.next_follow_up,c.deadline_at,c.deadline_source,
 extract(epoch from now()-r.requested_at)/86400 return_age_days,
 extract(epoch from now()-f.refund_posted_at)/86400 refund_age_days,
 extract(epoch from now()-p.carrier_delivery_at)/86400 delivery_age_days
 from amazon_mf_returns r
 left join lateral(select sum(quantity)::integer verified,sum(quantity)filter(where disposition<>'missing')::integer received_contents,
 sum(quantity)filter(where disposition='saleable')::integer saleable,sum(quantity)filter(where disposition='inspection_hold')::integer held,
 sum(quantity)filter(where disposition in ('wrong_item','damaged','missing'))::integer exceptions from amazon_mf_return_inspections where return_id=r.id and superseded_by is null)x on true
 left join lateral(select min(pkg.received_at) package_received_at,min(coalesce(pkg.carrier_delivery_at,pkg.amazon_delivery_at)) carrier_delivery_at,min(pkg.first_scan_at) first_scan_at,
 string_agg(pkg.carrier_error,'; ')carrier_error,bool_or(coalesce(pkg.carrier_delivery_at,pkg.amazon_delivery_at) is not null and pkg.received_at is null) delivered_unreceived
 from amazon_mf_return_packages pkg join amazon_mf_return_package_items pi on pi.package_id=pkg.id where pi.return_id=r.id)p on true
 -- Net amount is explicitly ORDER-scoped; never aggregate these repeated order totals across return rows.
 left join lateral(select min(posted_at) refund_posted_at,case when count(distinct currency)=1 then sum(amount) end posted_refund_net,min(currency) currency,
 bool_or(exists(select 1 from jsonb_array_elements(items) j where j->>'amazon_order_item_id'=coalesce(r.amazon_order_item_id,(select amazon_order_item_id from amazon_mf_order_items where id=r.order_item_id)))) item_matched
 from vw_mf_return_finances where account_id=r.account_id and amazon_order_id=r.amazon_order_id and lower(kind)='refund' and status in ('RELEASED','DEFERRED_RELEASED'))f on true
 left join lateral(select count(*)filter(where status not in ('resolved','closed','denied')) unresolved,min(next_follow_up)filter(where status not in ('resolved','closed','denied')) next_follow_up,
 min(deadline_at) deadline_at,min(deadline_source) deadline_source from amazon_mf_return_claims where return_id=r.id)c on true
 where r.source_key not like 'finance-order:%' or not exists(select 1 from amazon_mf_returns other where other.account_id=r.account_id and other.amazon_order_id=r.amazon_order_id and other.source_key not like 'finance-order:%');

do $$declare t text;f record;begin
 foreach t in array array['amazon_mf_return_sync_runs','amazon_mf_return_reports','amazon_mf_returns','amazon_mf_return_observations','amazon_mf_return_packages','amazon_mf_return_package_items','amazon_mf_return_finances','amazon_mf_return_finance_notes','amazon_mf_return_inspections','amazon_mf_return_restock_allocations','amazon_mf_return_claims','amazon_mf_return_evidence','amazon_mf_return_dates'] loop
 execute format('alter table public.%I enable row level security',t);execute format('revoke all on public.%I from public,anon,authenticated',t);execute format('grant all on public.%I to service_role',t);end loop;
 for f in select oid::regprocedure sig from pg_proc where pronamespace='public'::regnamespace and proname like 'mbop_mf_return_%' loop
 execute format('revoke all on function %s from public,anon,authenticated',f.sig);execute format('grant execute on function %s to service_role',f.sig);end loop;
end $$;
revoke all on public.vw_mf_open_returns from public,anon,authenticated;
grant select on public.vw_mf_open_returns to service_role;
revoke all on public.vw_mf_return_finances from public,anon,authenticated;
grant select on public.vw_mf_return_finances to service_role;
