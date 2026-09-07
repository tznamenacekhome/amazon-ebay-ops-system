-- MBOP-owned ZFI Buying contract. Additive; no historical cost backfill.
begin;

alter table public.purchases add column if not exists zfi_source_updated_at timestamptz not null default now();
alter table public.purchase_items add column if not exists zfi_source_updated_at timestamptz not null default now();

create function public.mbop_zfi_touch_purchase() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  new.zfi_source_updated_at := clock_timestamp();
  return new;
end $$;
create trigger mbop_zfi_purchase_changed before update on public.purchases
for each row execute function public.mbop_zfi_touch_purchase();
create trigger mbop_zfi_item_changed before update on public.purchase_items
for each row execute function public.mbop_zfi_touch_purchase();

create function public.mbop_zfi_touch_item_parent() returns trigger
language plpgsql security definer set search_path = pg_catalog, public as $$
begin
  if tg_op = 'DELETE' then
    update public.purchases set zfi_source_updated_at = clock_timestamp() where purchase_id = old.purchase_id;
  elsif tg_op = 'INSERT' then
    update public.purchases set zfi_source_updated_at = clock_timestamp() where purchase_id = new.purchase_id;
  else
    update public.purchases set zfi_source_updated_at = clock_timestamp() where purchase_id in (old.purchase_id,new.purchase_id);
  end if;
  return null;
end $$;
create trigger mbop_zfi_item_parent_changed after insert or update or delete on public.purchase_items
for each row execute function public.mbop_zfi_touch_item_parent();

create view public.zfi_ebay_purchase_facts with (security_barrier = true) as
with lines as (
  select p.purchase_id,
    coalesce(nullif(btrim(p.supplier_order_id), ''), 'missing:' || p.purchase_id::text) as order_key,
    nullif(btrim(p.supplier_order_id), '') as ebay_order_id,
    p.order_date, p.zfi_source_updated_at as purchase_updated_at,
    i.item_id, i.quantity, i.unit_cost, i.manual_split_child,
    i.zfi_source_updated_at as item_updated_at,
    case when lower(p.order_status) in ('cancelled','canceled') then 'cancelled'
      else coalesce(nullif(lower(i.current_status), ''), 'unknown') end as item_status,
    i.item_id is not null and not coalesce(i.exclude_from_purchase_reporting, false)
      and coalesce(lower(i.current_status), '') not in ('cancelled', 'return_opened')
      and coalesce(lower(p.order_status), '') not in ('cancelled','canceled') as reportable
  from public.purchases p left join public.purchase_items i using (purchase_id)
  where lower(btrim(p.supplier)) = 'ebay'
)
select '2026-09-07'::text as contract_version,
  md5('mbop:ebay:' || order_key)::uuid as source_purchase_id,
  max(ebay_order_id) as ebay_order_id,
  min(order_date) as purchase_date,
  count(distinct order_date) > 1 or bool_or(order_date is null) as date_needs_review,
  'USD'::text as cost_currency,
  coalesce(sum(quantity) filter (where reportable), 0)::bigint as unit_count,
  coalesce(sum(quantity), 0)::bigint as recorded_unit_count,
  coalesce(sum(quantity) filter (where not reportable), 0)::bigint as excluded_unit_count,
  case when bool_or(reportable and (unit_cost is null or quantity is null or quantity <= 0))
    then null else coalesce(sum(quantity * unit_cost) filter (where reportable), 0) end as acquisition_cost_total,
  case when bool_or(item_id is not null and (unit_cost is null or quantity is null or quantity <= 0))
    then null else coalesce(sum(quantity * unit_cost), 0) end as recorded_acquisition_cost_total,
  coalesce(bool_or(reportable and (unit_cost is null or quantity is null or quantity <= 0)), false) as cost_needs_review,
  case when count(item_id) = 0 then 'no_items'
    when count(*) filter (where reportable) = 0 then 'excluded'
    when count(*) filter (where reportable) = count(item_id) then 'included'
    else 'partially_excluded' end as exclusion_status,
  case when count(distinct item_status) = 1 then min(item_status) else 'mixed' end as purchase_status,
  count(distinct purchase_id)::integer as source_purchase_count,
  count(item_id)::integer as source_item_count,
  count(*) filter (where manual_split_child)::integer as manual_split_item_count,
  'mbop_item_cost_after_recorded_adjustments'::text as cost_basis,
  null::numeric as refund_amount,
  'not_separately_normalized'::text as refund_status,
  greatest(max(purchase_updated_at), max(item_updated_at)) as source_updated_at
from lines group by order_key;

revoke all on public.zfi_ebay_purchase_facts from public, anon, authenticated;
grant select on public.zfi_ebay_purchase_facts to service_role;

create table public.mbop_purchase_ingestion_requests (
  run_id uuid primary key,
  status text not null check (status in ('queued', 'running', 'succeeded', 'failed')),
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  task_arn text,
  source text not null,
  error_code text
);
create unique index mbop_one_active_purchase_ingestion
  on public.mbop_purchase_ingestion_requests ((true)) where status in ('queued','running');
alter table public.mbop_purchase_ingestion_requests enable row level security;
revoke all on public.mbop_purchase_ingestion_requests from public, anon, authenticated;
grant select, insert, update on public.mbop_purchase_ingestion_requests to service_role;

-- Shared by the API reservation and purchase-ingestion worker startup.
-- No time-based lock stealing: reconcile terminal ECS tasks before retrying.
create function public.mbop_claim_purchase_ingestion(p_run_id uuid, p_start boolean default false, p_task_arn text default null)
returns jsonb language plpgsql security definer set search_path = pg_catalog, public as $$
declare active public.mbop_purchase_ingestion_requests; legacy public.scheduler_runs;
begin
  perform pg_advisory_xact_lock(170907, 1);
  select * into active from public.mbop_purchase_ingestion_requests where status in ('queued','running') for update;
  if active.run_id is null then
    -- Honor a scheduled run that predates adoption of this shared lock.
    select * into legacy from public.scheduler_runs
      where group_name in ('purchase-ingestion','purchases','dashboard','core','all')
        and status='running' and run_id <> p_run_id
      order by started_at desc limit 1;
    if legacy.run_id is not null then
      insert into public.mbop_purchase_ingestion_requests(run_id,status,requested_at,started_at,task_arn,source)
        values(legacy.run_id,'running',legacy.started_at,legacy.started_at,legacy.ecs_task_arn,'scheduled')
        on conflict(run_id) do update set status='running', completed_at=null
        returning * into active;
    end if;
  end if;
  if active.run_id is not null and active.run_id <> p_run_id then
    return to_jsonb(active) || jsonb_build_object('acquired',false);
  end if;
  if active.run_id is null then
    insert into public.mbop_purchase_ingestion_requests(run_id,status,source)
      values(p_run_id,'queued',case when p_start then 'scheduled' else 'zfi' end)
      returning * into active;
  end if;
  if p_start then
    if active.status = 'running' and active.task_arn is distinct from p_task_arn then
      return to_jsonb(active) || jsonb_build_object('acquired',false);
    end if;
    update public.mbop_purchase_ingestion_requests set status='running',
      started_at=coalesce(started_at,clock_timestamp()), task_arn=coalesce(p_task_arn,task_arn)
      where run_id=p_run_id returning * into active;
  end if;
  return to_jsonb(active) || jsonb_build_object('acquired',true);
end $$;
revoke all on function public.mbop_claim_purchase_ingestion(uuid,boolean,text) from public, anon, authenticated;
grant execute on function public.mbop_claim_purchase_ingestion(uuid,boolean,text) to service_role;
revoke all on function public.mbop_zfi_touch_purchase(), public.mbop_zfi_touch_item_parent() from public, anon, authenticated;
comment on view public.zfi_ebay_purchase_facts is 'ZFI Buying v1: one logical eBay order; item quantities and net stored item costs, never repeated header totals. No raw vendor/customer/payment data.';
commit;
