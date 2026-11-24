-- Shared production Browse quota reservations; no credentials or buyer PII stored.
create table public.ebay_api_resource_limits (
 app_key text not null,resource text not null,quota_limit bigint not null default 0,
 calls_used bigint not null default 0,remaining bigint not null default 0,
 observed_count bigint,observed_remaining bigint,
 reset_at timestamptz,window_seconds integer,observed_at timestamptz,
 blocked_until timestamptz,reason text,refresh_until timestamptz,
 last_http_status integer,last_error_json jsonb,last_retry_after text,last_response_at timestamptz,
 primary key(app_key,resource)
);
create table public.ebay_api_usage (
 app_key text not null,resource text not null,job_name text not null,day date not null,
 attempts bigint not null default 0,primary key(app_key,resource,job_name,day)
);
create table public.ebay_listing_detail_cache (
 app_key text not null,marketplace text not null,item_id text not null,buyer_context text not null,
 payload jsonb not null,fetched_at timestamptz not null,expires_at timestamptz not null,
 primary key(app_key,marketplace,item_id,buyer_context),
 check(expires_at<=fetched_at+interval '6 hours')
);
create index ebay_listing_cache_expiry on public.ebay_listing_detail_cache(expires_at);

alter table public.sourcing_flipmine_runs drop constraint sourcing_flipmine_runs_status_check;
alter table public.sourcing_flipmine_runs add constraint sourcing_flipmine_runs_status_check check(status in('running','paused','evaluated','completed','partial','failed'));
alter table public.sourcing_flipmine_tabs drop constraint sourcing_flipmine_tabs_status_check;
alter table public.sourcing_flipmine_tabs add constraint sourcing_flipmine_tabs_status_check check(status in('pending','running','paused','evaluated','completed','partial','failed'));
alter table public.sourcing_flipmine_runs add column next_retry_at timestamptz,add column paused_resource text;
create index sourcing_flipmine_retry on public.sourcing_flipmine_runs(next_retry_at) where status='paused';
create index sourcing_flipmine_outstanding_listings on public.sourcing_flipmine_rows(tab_id,ebay_legacy_item_id) where status in('pending','failed');

create function public.ebay_pending_flipmine_calls() returns bigint language sql stable security invoker set search_path=public as $$
 select count(distinct r.ebay_legacy_item_id) from sourcing_flipmine_runs i
 join sourcing_flipmine_tabs t using(run_id) join sourcing_flipmine_rows r using(tab_id)
 where (i.status='running' or (i.status='paused' and i.next_retry_at<=now())) and r.status in('pending','failed')
$$;

create function public.ebay_quota_reserve(p_app text,p_resource text,p_job text,p_peek boolean default false) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare q ebay_api_resource_limits;reserved bigint;
begin
 insert into ebay_api_resource_limits(app_key,resource) values(p_app,p_resource) on conflict do nothing;
 select * into q from ebay_api_resource_limits where app_key=p_app and resource=p_resource for update;
 if q.blocked_until>now() then return jsonb_build_object('allowed',false,'retry_at',q.blocked_until,'reason',q.reason);end if;
 if q.refresh_until>now() then return jsonb_build_object('allowed',false,'retry_at',q.refresh_until,'reason','quota_refresh_in_progress');end if;
 if q.observed_at is null or q.reset_at<=now() or q.observed_at<now()-interval '5 minutes' then
  update ebay_api_resource_limits set refresh_until=now()+interval '45 seconds' where app_key=p_app and resource=p_resource;
  return jsonb_build_object('refresh',true);
 end if;
 if q.remaining<=0 then return jsonb_build_object('allowed',false,'retry_at',q.reset_at,'reason','daily_quota_exhausted');end if;
 if p_job<>'import_flipmine.py' and p_resource='buy.browse' then
  reserved:=ebay_pending_flipmine_calls();
  if q.remaining<=reserved then return jsonb_build_object('allowed',false,'retry_at',now()+interval '30 minutes','reason','capacity_reserved_for_saved_import');end if;
 end if;
 if p_peek then return jsonb_build_object('allowed',true,'remaining',q.remaining,'reset',q.reset_at);end if;
 update ebay_api_resource_limits set remaining=remaining-1,calls_used=calls_used+1 where app_key=p_app and resource=p_resource;
 -- Bound transient payload storage without a broad historical cleanup job.
 delete from ebay_listing_detail_cache where ctid in(select ctid from ebay_listing_detail_cache where app_key=p_app and expires_at<now() order by expires_at limit 10);
 insert into ebay_api_usage(app_key,resource,job_name,day,attempts) values(p_app,p_resource,left(p_job,150),(now() at time zone 'America/Los_Angeles')::date,1)
 on conflict(app_key,resource,job_name,day) do update set attempts=ebay_api_usage.attempts+1;
 return jsonb_build_object('allowed',true,'remaining',q.remaining-1,'reset',q.reset_at);
end $$;

create function public.ebay_quota_observe(p_app text,p_resource text,p_rate jsonb) returns void
language plpgsql security invoker set search_path=public as $$
begin
 insert into ebay_api_resource_limits(app_key,resource) values(p_app,p_resource) on conflict do nothing;
 update ebay_api_resource_limits set
 remaining=case when reset_at=(p_rate->>'reset')::timestamptz then least(remaining,(p_rate->>'remaining')::bigint) else (p_rate->>'remaining')::bigint end,
 calls_used=case when reset_at=(p_rate->>'reset')::timestamptz then greatest(calls_used,(p_rate->>'count')::bigint) else (p_rate->>'count')::bigint end,
 observed_count=(p_rate->>'count')::bigint,observed_remaining=(p_rate->>'remaining')::bigint,
 quota_limit=(p_rate->>'limit')::bigint,reset_at=(p_rate->>'reset')::timestamptz,
 window_seconds=(p_rate->>'timeWindow')::integer,observed_at=now(),refresh_until=null,
 blocked_until=case when (p_rate->>'remaining')::bigint<=0 then greatest(blocked_until,(p_rate->>'reset')::timestamptz)
  when reset_at is not distinct from (p_rate->>'reset')::timestamptz and reason='temporary_throttle' and blocked_until>now() then blocked_until else null end,
 reason=case when (p_rate->>'remaining')::bigint<=0 then 'daily_quota_exhausted'
  when reset_at is not distinct from (p_rate->>'reset')::timestamptz and reason='temporary_throttle' and blocked_until>now() then reason else null end
 where app_key=p_app and resource=p_resource;
end $$;

create function public.flipmine_pause(p_run uuid,p_until timestamptz,p_resource text,p_reason text) returns void
language plpgsql security invoker set search_path=public as $$
begin
 perform 1 from sourcing_flipmine_runs where run_id=p_run and status='running' for update;
 if not found then raise exception 'Flipmine lease lost';end if;
 update sourcing_flipmine_tabs set status='paused',error_summary=p_reason where run_id=p_run and status='running';
 update sourcing_runs s set status='failed',completed_at=now() from sourcing_flipmine_tabs t where t.run_id=p_run and s.sourcing_run_id=t.sourcing_run_id and s.status='running';
 update sourcing_flipmine_runs set status='paused',next_retry_at=greatest(p_until,now()+interval '5 seconds'),paused_resource=p_resource,
  completed_at=null,error_summary=p_reason,summary=summary||jsonb_build_object('phase','paused') where run_id=p_run;
end $$;

create function public.flipmine_claim_resume(p_run uuid default null,p_due_only boolean default true) returns uuid
language plpgsql security invoker set search_path=public as $$
declare rid uuid;
begin
 perform pg_advisory_xact_lock(hashtextextended('mbop:flipmine-import',0));
 -- A killed recovery worker must not strand the original checkpoint.
 update sourcing_flipmine_tabs set status='paused' where status='running' and run_id in(select run_id from sourcing_flipmine_runs where status='running' and heartbeat_at<now()-interval '90 minutes');
 update sourcing_flipmine_runs set status='paused',next_retry_at=now(),paused_resource='checkpoint',error_summary='Interrupted worker; checkpoint retained'
 where status='running' and heartbeat_at<now()-interval '90 minutes';
 if exists(select 1 from sourcing_flipmine_runs where status='running') then return null;end if;
 select run_id into rid from sourcing_flipmine_runs
 where (p_run is null or run_id=p_run) and
  ((status='paused' and next_retry_at<=now()) or (not p_due_only and status in('partial','failed','paused')))
 order by started_at for update skip locked limit 1;
 if rid is null then return null;end if;
 if not exists(select 1 from sourcing_flipmine_tabs where run_id=rid and source_hash is not null and status<>'completed') then return null;end if;
 update sourcing_flipmine_runs set status='running',heartbeat_at=now(),completed_at=null,error_summary=null,next_retry_at=null,paused_resource=null,
  summary=summary||jsonb_build_object('phase','resuming') where run_id=rid;
 -- Retry prior quota failures without erasing their last error or source evidence.
 update sourcing_flipmine_rows r set status='pending' from sourcing_flipmine_tabs t
 where t.run_id=rid and r.tab_id=t.tab_id and r.status='failed' and r.error like 'EbayRateLimitedError:%';
 return rid;
end $$;

-- Manual clicks cannot create a second job while a checkpoint is paused.
create or replace function public.flipmine_begin(p_run uuid) returns jsonb language plpgsql security invoker set search_path=public as $$
declare active uuid;active_status text;
begin
 perform pg_advisory_xact_lock(hashtextextended('mbop:flipmine-import',0));
 update sourcing_flipmine_tabs set status='partial',error_summary='Interrupted worker; checkpoint retained'
 where status='running' and run_id in(select run_id from sourcing_flipmine_runs where status='running' and heartbeat_at<now()-interval '90 minutes');
 update sourcing_flipmine_runs set status='failed',completed_at=now(),error_summary='Worker lease expired; checkpoint retained'
 where status='running' and heartbeat_at<now()-interval '90 minutes';
 select run_id,status into active,active_status from sourcing_flipmine_runs where status in('running','paused') order by started_at limit 1;
 if found then return jsonb_build_object('run_id',active,'launch',false,'status',active_status);end if;
 insert into sourcing_flipmine_runs(run_id) values(p_run);
 return jsonb_build_object('run_id',p_run,'launch',true);
end $$;

do $$declare t text;f record;begin
 foreach t in array array['ebay_api_resource_limits','ebay_api_usage','ebay_listing_detail_cache'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant all on public.%I to service_role',t);
 end loop;
 for f in select oid::regprocedure sig from pg_proc where pronamespace='public'::regnamespace and (proname like 'ebay_quota_%' or proname in ('ebay_pending_flipmine_calls','flipmine_pause','flipmine_claim_resume')) loop
  execute format('revoke all on function %s from public,anon,authenticated',f.sig);
  execute format('grant execute on function %s to service_role',f.sig);
 end loop;
end $$;
