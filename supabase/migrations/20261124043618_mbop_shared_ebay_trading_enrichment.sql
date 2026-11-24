-- One admission lock per application/resource, including ALL Trading methods.
create table public.ebay_api_quota_policy (
 resource text primary key,
 essential_percent integer not null check(essential_percent between 0 and 50),
 discovery_percent integer not null check(discovery_percent between 0 and 50),
 sourcing_share_percent integer not null check(sourcing_share_percent between 1 and 100)
);
-- Tunable operational defaults, not claims about eBay's configured quota.
insert into public.ebay_api_quota_policy values ('trading',10,0,50),('buy.browse',10,20,50);
create table public.ebay_api_events (
 app_key text not null,resource text not null,job_name text not null,day date not null,
 event text not null,total bigint not null default 0,
 primary key(app_key,resource,job_name,day,event)
);
create function public.ebay_api_event(p_app text,p_resource text,p_job text,p_event text)
returns void language sql security invoker set search_path=public as $$
 insert into ebay_api_events values(p_app,p_resource,left(p_job,150),(now() at time zone 'America/Los_Angeles')::date,left(p_event,100),1)
 on conflict(app_key,resource,job_name,day,event) do update set total=ebay_api_events.total+1
$$;

create function public.ebay_quota_block(p_app text,p_resource text,p_until timestamptz,p_reason text,p_status integer)
returns void language sql security invoker set search_path=public as $$
 update ebay_api_resource_limits set blocked_until=greatest(blocked_until,p_until),reason=p_reason,
 last_http_status=p_status,last_response_at=now() where app_key=p_app and resource=p_resource
$$;

create function public.ebay_quota_admit(p_app text,p_resource text,p_job text,p_operation text,p_priority text,p_peek boolean default false)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare q ebay_api_resource_limits; policy ebay_api_quota_policy; floor_calls bigint:=0; class_used bigint; class_cap bigint;
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
 select * into policy from ebay_api_quota_policy where resource=p_resource;
 if found and p_priority<>'essential' then
  -- Preserve essential headroom and Browse discovery independently of enrichment.
  floor_calls:=ceil(q.quota_limit*policy.essential_percent/100.0);
  if p_resource='buy.browse' and p_operation<>'search' then floor_calls:=floor_calls+ceil(q.quota_limit*policy.discovery_percent/100.0);end if;
  if q.remaining<=floor_calls then return jsonb_build_object('allowed',false,'retry_at',q.reset_at,'reason','protected_operational_capacity');end if;
  -- When an import is outstanding, neither sourcing class can consume the other's
  -- share. Unused allocations are released when the saved import finishes.
  if p_priority in ('manual','catalog','background') and exists(
   select 1 from sourcing_flipmine_runs where status in ('running','paused')) then
   select coalesce(sum(attempts),0) into class_used from ebay_api_usage
   where app_key=p_app and resource=p_resource and day=(now() at time zone 'America/Los_Angeles')::date
    and (case when p_priority='manual' then job_name='import_flipmine.py' else job_name<>'import_flipmine.py' and job_name not like 'essential:%' end);
   class_cap:=floor(q.quota_limit*(100-policy.essential_percent)/100.0 *
     (case when p_priority='manual' then policy.sourcing_share_percent else 100-policy.sourcing_share_percent end)/100.0);
   if class_used>=class_cap then return jsonb_build_object('allowed',false,'retry_at',q.reset_at,'reason','sourcing_fair_share_reached');end if;
  end if;
 end if;
 if p_peek then return jsonb_build_object('allowed',true,'remaining',q.remaining,'reset',q.reset_at,'protected',floor_calls);end if;
 update ebay_api_resource_limits set remaining=remaining-1,calls_used=calls_used+1 where app_key=p_app and resource=p_resource;
 insert into ebay_api_usage values(p_app,p_resource,left(p_job,150),(now() at time zone 'America/Los_Angeles')::date,1)
 on conflict(app_key,resource,job_name,day) do update set attempts=ebay_api_usage.attempts+1;
 perform ebay_api_event(p_app,p_resource,p_job,p_operation);
 delete from ebay_listing_detail_cache where ctid in(select ctid from ebay_listing_detail_cache where app_key=p_app and expires_at<now() order by expires_at limit 10);
 return jsonb_build_object('allowed',true,'remaining',q.remaining-1,'reset',q.reset_at,'protected',floor_calls);
end $$;

-- Keep older deployed workers on the same lock and fairness policy during rollout.
create or replace function public.ebay_quota_reserve(p_app text,p_resource text,p_job text,p_peek boolean default false)
returns jsonb language sql security invoker set search_path=public as $$
 select ebay_quota_admit(p_app,p_resource,p_job,'detail',case when p_job='import_flipmine.py' then 'manual' else 'catalog' end,p_peek)
$$;

do $$declare t text;f record;begin
 foreach t in array array['ebay_api_quota_policy','ebay_api_events'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant all on public.%I to service_role',t);
 end loop;
 for f in select oid::regprocedure sig from pg_proc where pronamespace='public'::regnamespace and proname in('ebay_api_event','ebay_quota_admit','ebay_quota_block') loop
  execute format('revoke all on function %s from public,anon,authenticated',f.sig);
  execute format('grant execute on function %s to service_role',f.sig);
 end loop;
end $$;
