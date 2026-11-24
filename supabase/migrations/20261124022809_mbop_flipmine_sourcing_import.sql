-- Manual discovery adapter; matching/economics remain owned by the existing scorer.
alter table public.sourcing_ebay_candidates drop constraint sourcing_ebay_candidates_ebay_item_id_key;
alter table public.sourcing_ebay_candidates add constraint sourcing_ebay_candidates_pair_key unique(ebay_item_id,asin);
alter table public.sourcing_ebay_candidates add column source_tags text[] not null default '{}';
create index if not exists sourcing_opportunities_flipmine_pair_lookup on public.sourcing_opportunities(candidate_id,asin,created_at desc);
alter table public.sourcing_runs drop constraint sourcing_runs_run_type_check;
alter table public.sourcing_runs add constraint sourcing_runs_run_type_check
 check(run_type in ('recent_sales','full_listings','daily_catalog_sourcing','flipmine'));
alter table public.sourcing_seed_asins drop constraint sourcing_seed_asins_source_mode_check;
alter table public.sourcing_seed_asins add constraint sourcing_seed_asins_source_mode_check
 check(source_mode in ('recent_sales','full_listings','wholesale_catalog','1_recently_sold','2_purchased_not_sent','3_catalog_remaining','flipmine'));

create table public.sourcing_flipmine_runs (
 run_id uuid primary key, status text not null default 'running'
 check(status in ('running','evaluated','completed','partial','failed')),
 started_at timestamptz not null default now(), completed_at timestamptz,
 heartbeat_at timestamptz not null default now(), task_arn text, error_summary text,
 summary jsonb not null default '{}'
);
create unique index sourcing_flipmine_one_running on public.sourcing_flipmine_runs(status) where status='running';
create index sourcing_flipmine_run_started on public.sourcing_flipmine_runs(started_at desc);
create table public.sourcing_flipmine_tabs (
 tab_id uuid primary key default gen_random_uuid(), spreadsheet_id text not null,
 sheet_id bigint not null, tab_name text not null, run_id uuid not null references public.sourcing_flipmine_runs,
 sourcing_run_id uuid not null default gen_random_uuid(),
 status text not null default 'pending' check(status in ('pending','running','evaluated','completed','partial','failed')),
 started_at timestamptz not null default now(), completed_at timestamptz, source_hash text,
 rows_found integer not null default 0, summary jsonb not null default '{}', error_summary text,
 unique(spreadsheet_id,sheet_id)
);
create index sourcing_flipmine_tabs_run on public.sourcing_flipmine_tabs(run_id);
create table public.sourcing_flipmine_rows (
 tab_id uuid not null references public.sourcing_flipmine_tabs, row_number integer not null check(row_number>=2),
 asin text not null, ebay_legacy_item_id text not null, source_evidence jsonb not null default '{}',
 status text not null check(status in ('pending','invalid','evaluated','duplicate','excluded','failed')),
 candidate_id uuid references public.sourcing_ebay_candidates, opportunity_id uuid references public.sourcing_opportunities,
 error text, evaluation jsonb, updated_at timestamptz not null default now(),
 primary key(tab_id,row_number)
);
create index sourcing_flipmine_row_opportunity on public.sourcing_flipmine_rows(opportunity_id) where opportunity_id is not null;
create index sourcing_flipmine_row_candidate on public.sourcing_flipmine_rows(candidate_id) where candidate_id is not null;

create function public.flipmine_begin(p_run uuid) returns jsonb language plpgsql security invoker set search_path=public as $$
declare active uuid;
begin
 perform pg_advisory_xact_lock(hashtextextended('mbop:flipmine-import',0));
 select run_id into active from sourcing_flipmine_runs where status='running' and heartbeat_at>now()-interval '90 minutes';
 if found then return jsonb_build_object('run_id',active,'launch',false);end if;
 update sourcing_flipmine_tabs set status='partial',error_summary='Interrupted worker; retry retained source rows'
 where status='running' and run_id in(select run_id from sourcing_flipmine_runs where status='running');
 update sourcing_flipmine_runs set status='failed',completed_at=now(),error_summary='Worker lease expired; manual retry resumes source tabs' where status='running';
 insert into sourcing_flipmine_runs(run_id) values(p_run);
 return jsonb_build_object('run_id',p_run,'launch',true);
end $$;

create function public.flipmine_claim_tab(p_run uuid,p_spreadsheet text,p_sheet bigint,p_name text)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare t sourcing_flipmine_tabs;
begin
 perform 1 from sourcing_flipmine_runs where run_id=p_run and status='running' for update;
 if not found then raise exception 'Flipmine run no longer owns its lease';end if;
 insert into sourcing_flipmine_tabs(spreadsheet_id,sheet_id,tab_name,run_id)
 values(p_spreadsheet,p_sheet,p_name,p_run) on conflict(spreadsheet_id,sheet_id) do nothing;
 select * into strict t from sourcing_flipmine_tabs where spreadsheet_id=p_spreadsheet and sheet_id=p_sheet for update;
 if t.status='completed' then return null;end if;
 update sourcing_flipmine_tabs set run_id=p_run,tab_name=p_name,status='running',error_summary=null where tab_id=t.tab_id returning * into t;
 insert into sourcing_runs(sourcing_run_id,run_type,status) values(t.sourcing_run_id,'flipmine','running')
 on conflict(sourcing_run_id) do update set status='running',completed_at=null;
 return to_jsonb(t);
end $$;

create function public.flipmine_snapshot_tab(p_run uuid,p_tab uuid,p_hash text,p_rows jsonb)
returns void language plpgsql security invoker set search_path=public as $$
declare t sourcing_flipmine_tabs;
begin
 select * into strict t from sourcing_flipmine_tabs where tab_id=p_tab and run_id=p_run and status='running' for update;
 if not exists(select 1 from sourcing_flipmine_runs where run_id=p_run and status='running') then raise exception 'Flipmine lease lost';end if;
 if t.source_hash is not null then return;end if;
 if jsonb_array_length(p_rows)>10000 then raise exception 'Flipmine tab row bound exceeded';end if;
 insert into sourcing_flipmine_rows(tab_id,row_number,asin,ebay_legacy_item_id,source_evidence,status,error)
 select p_tab,(j->>'row_number')::integer,j->>'asin',j->>'ebay_legacy_item_id',j->'source_evidence',j->>'status',j->>'error'
 from jsonb_array_elements(p_rows) j;
 update sourcing_flipmine_tabs set source_hash=p_hash,rows_found=jsonb_array_length(p_rows) where tab_id=p_tab;
end $$;

-- Hold the candidate table while checking/creating a pair. Normal sourcing INSERTs
-- serialize with this short transaction; completed/operator-owned opportunities
-- are linked for provenance, never overwritten or blindly rescored.
create function public.flipmine_bind_candidate(p_run uuid,p_tab uuid,p_row integer,p_candidate jsonb)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare r sourcing_flipmine_rows;c sourcing_ebay_candidates;o sourcing_opportunities; fresh boolean:=false;
begin
 perform 1 from sourcing_flipmine_tabs t join sourcing_flipmine_runs i on i.run_id=t.run_id
 where t.tab_id=p_tab and t.run_id=p_run and t.status='running' and i.status='running' for update of t;
 if not found then raise exception 'Flipmine lease lost';end if;
 select * into strict r from sourcing_flipmine_rows where tab_id=p_tab and row_number=p_row for update;
 if r.asin<>p_candidate->>'asin' or p_candidate->>'ebay_legacy_item_id'<>r.ebay_legacy_item_id then raise exception 'Flipmine pair identity changed';end if;
 lock table sourcing_ebay_candidates in share row exclusive mode;
 select * into c from sourcing_ebay_candidates where asin=r.asin and ebay_item_id=p_candidate->>'ebay_item_id' for update;
 if not found then
  insert into sourcing_ebay_candidates(candidate_id,sourcing_run_id,seed_id,asin,ebay_item_id,ebay_legacy_item_id,
   ebay_item_web_url,ebay_title,ebay_image_url,seller_username,item_location_country,condition_id,condition,buying_options,
   price,shipping_cost,landed_cost,shipping_is_separate,available_quantity,is_multi_quantity,auction_end_time,bid_count,
   current_bid,best_offer_enabled,raw_ebay_json,first_seen_at,last_seen_at,listing_status,source_tags)
  select coalesce(x.candidate_id,gen_random_uuid()),x.sourcing_run_id,x.seed_id,x.asin,x.ebay_item_id,x.ebay_legacy_item_id,
   x.ebay_item_web_url,x.ebay_title,x.ebay_image_url,x.seller_username,x.item_location_country,x.condition_id,x.condition,
   coalesce(x.buying_options,'{}'),x.price,x.shipping_cost,x.landed_cost,coalesce(x.shipping_is_separate,false),x.available_quantity,
   coalesce(x.is_multi_quantity,false),x.auction_end_time,x.bid_count,x.current_bid,coalesce(x.best_offer_enabled,false),
   coalesce(x.raw_ebay_json,'{}'),coalesce(x.first_seen_at,now()),coalesce(x.last_seen_at,now()),coalesce(x.listing_status,'unknown'),array['flipmine']
  from jsonb_populate_record(null::sourcing_ebay_candidates,p_candidate) x returning * into c;
  fresh:=true;
 else
  update sourcing_ebay_candidates set source_tags=array(select distinct unnest(source_tags||array['flipmine']))
  where candidate_id=c.candidate_id returning * into c;
 end if;
 select * into o from sourcing_opportunities where candidate_id=c.candidate_id and asin=r.asin order by created_at desc limit 1;
 if found and (o.matching_diagnostics_json is null or o.matching_diagnostics_json='{}'::jsonb) then raise exception 'Existing opportunity has no completed evaluation; review/retry required';end if;
 if o.opportunity_id is null and not fresh then
  update sourcing_ebay_candidates set sourcing_run_id=x.sourcing_run_id,seed_id=x.seed_id,
   ebay_title=x.ebay_title,ebay_image_url=x.ebay_image_url,ebay_item_web_url=x.ebay_item_web_url,
   seller_username=x.seller_username,item_location_country=x.item_location_country,
   condition=x.condition,condition_id=x.condition_id,buying_options=x.buying_options,
   price=x.price,shipping_cost=x.shipping_cost,landed_cost=x.landed_cost,shipping_is_separate=x.shipping_is_separate,
   available_quantity=x.available_quantity,is_multi_quantity=x.is_multi_quantity,auction_end_time=x.auction_end_time,
   current_bid=x.current_bid,bid_count=x.bid_count,best_offer_enabled=x.best_offer_enabled,
   raw_ebay_json=x.raw_ebay_json,last_seen_at=now(),listing_status=x.listing_status
  from jsonb_populate_record(null::sourcing_ebay_candidates,p_candidate) x
  where sourcing_ebay_candidates.candidate_id=c.candidate_id returning sourcing_ebay_candidates.* into c;
 end if;
 update sourcing_flipmine_rows set candidate_id=c.candidate_id,opportunity_id=o.opportunity_id,
 status=case when o.opportunity_id is null then 'pending' else 'duplicate' end,error=null,updated_at=now()
 where tab_id=p_tab and row_number=p_row;
 return jsonb_build_object('candidate',to_jsonb(c),'opportunity_id',o.opportunity_id,'duplicate',o.opportunity_id is not null,'new_candidate',fresh);
end $$;

create function public.flipmine_update_row(p_run uuid,p_tab uuid,p_row integer,p_values jsonb)
returns void language plpgsql security invoker set search_path=public as $$
begin
 perform 1 from sourcing_flipmine_tabs t join sourcing_flipmine_runs i on i.run_id=t.run_id
 where t.tab_id=p_tab and t.run_id=p_run and t.status='running' and i.status='running' for update of t;
 if not found then raise exception 'Flipmine lease lost';end if;
 update sourcing_flipmine_rows set status=p_values->>'status',error=p_values->>'error',
 evaluation=p_values->'evaluation',updated_at=now() where tab_id=p_tab and row_number=p_row;
end $$;

create function public.flipmine_write_opportunity(p_run uuid,p_tab uuid,p_row integer,p_scored jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare r sourcing_flipmine_rows;oid uuid;
begin
 perform 1 from sourcing_flipmine_tabs t join sourcing_flipmine_runs i on i.run_id=t.run_id
 where t.tab_id=p_tab and t.run_id=p_run and t.status='running' and i.status='running' for update of t;
 if not found then raise exception 'Flipmine lease lost';end if;
 select * into strict r from sourcing_flipmine_rows where tab_id=p_tab and row_number=p_row for update;
 perform 1 from sourcing_ebay_candidates where candidate_id=r.candidate_id for update;
 if (p_scored->>'candidate_id')::uuid<>r.candidate_id or p_scored->>'asin'<>r.asin then raise exception 'Scored pair identity mismatch';end if;
 select opportunity_id into oid from sourcing_opportunities where candidate_id=r.candidate_id and asin=r.asin order by created_at desc limit 1;
 if oid is null then
  insert into sourcing_opportunities(opportunity_id,sourcing_run_id,seed_id,candidate_id,asin,ebay_item_id,opportunity_type,status,
   target_sale_price,target_sale_price_source,landed_cost,profit,roi_percent,max_profitable_landed_cost,max_offer_price,
   required_offer_percent_of_ask,max_bid,total_profit_opportunity,inventory_need_level,months_of_supply,monthly_velocity,
   score,score_reason,warning_flags,ai_flags,seller_trust_status,seller_trust_score,matching_diagnostics_json,created_at,updated_at)
  select gen_random_uuid(),x.sourcing_run_id,x.seed_id,x.candidate_id,x.asin,x.ebay_item_id,x.opportunity_type,x.status,
   x.target_sale_price,x.target_sale_price_source,x.landed_cost,x.profit,x.roi_percent,x.max_profitable_landed_cost,x.max_offer_price,
   x.required_offer_percent_of_ask,x.max_bid,x.total_profit_opportunity,x.inventory_need_level,x.months_of_supply,x.monthly_velocity,
   x.score,x.score_reason,coalesce(x.warning_flags,'{}'),coalesce(x.ai_flags,'{}'),x.seller_trust_status,x.seller_trust_score,
   x.matching_diagnostics_json,coalesce(x.created_at,now()),coalesce(x.updated_at,now())
  from jsonb_populate_record(null::sourcing_opportunities,p_scored) x returning opportunity_id into oid;
 end if;
 update sourcing_flipmine_rows set status='evaluated',opportunity_id=oid,evaluation=p_scored->'matching_diagnostics_json',error=null,updated_at=now()
 where tab_id=p_tab and row_number=p_row;
 return oid;
end $$;

create function public.flipmine_tab_evaluated(p_run uuid,p_tab uuid) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare s jsonb;bad integer;t sourcing_flipmine_tabs;
begin
 select * into strict t from sourcing_flipmine_tabs where tab_id=p_tab and run_id=p_run for update;
 if not exists(select 1 from sourcing_flipmine_runs where run_id=p_run and status='running') then raise exception 'Flipmine lease lost';end if;
 select count(*) filter(where status in ('pending','failed')),
 jsonb_build_object('rows',count(*),'valid',count(*) filter(where status<>'invalid'),
  'evaluated',count(*) filter(where status='evaluated' or evaluation is not null),'duplicates',count(*) filter(where status='duplicate'),
  'invalid',count(*) filter(where status='invalid'),'excluded',count(*) filter(where status='excluded'),
  'failed',count(*) filter(where status in ('pending','failed')))
 into bad,s from sourcing_flipmine_rows where tab_id=p_tab;
 update sourcing_flipmine_tabs set status=case when bad>0 then 'partial' else 'evaluated' end,summary=s where tab_id=p_tab;
 update sourcing_runs set status=case when bad>0 then 'failed' else 'completed' end,completed_at=now()
 where sourcing_run_id=t.sourcing_run_id;
 return s;
end $$;

create function public.flipmine_complete_tab(p_tab uuid,p_summary jsonb) returns boolean
language plpgsql security invoker set search_path=public as $$
begin
 perform 1 from sourcing_flipmine_tabs where tab_id=p_tab and status='evaluated' for update;
 if not found then return false;end if;
 if exists(select 1 from sourcing_flipmine_rows where tab_id=p_tab and status in ('pending','failed')) then raise exception 'Flipmine evaluation is incomplete';end if;
 update sourcing_flipmine_tabs set status='completed',completed_at=now(),summary=summary||p_summary where tab_id=p_tab;
 return true;
end $$;

do $$declare t text;f record;begin
 foreach t in array array['sourcing_flipmine_runs','sourcing_flipmine_tabs','sourcing_flipmine_rows'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant all on public.%I to service_role',t);
 end loop;
 for f in select oid::regprocedure sig from pg_proc where pronamespace='public'::regnamespace and proname like 'flipmine_%' loop
  execute format('revoke all on function %s from public,anon,authenticated',f.sig);
  execute format('grant execute on function %s to service_role',f.sig);
 end loop;
end $$;
