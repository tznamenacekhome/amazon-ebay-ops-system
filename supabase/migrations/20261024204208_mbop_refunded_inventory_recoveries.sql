-- MBOP: full refund plus a usable retained item or replacement, on the same unit.
create table public.purchase_item_refund_recoveries (
  recovery_id uuid primary key default gen_random_uuid(),
  item_id uuid not null unique references public.purchase_items(item_id),
  problem_case_id uuid not null unique references public.order_problem_cases(problem_case_id),
  resolution text not null check (resolution in ('refunded_replacement_received', 'refunded_item_retained')),
  quantity integer not null check (quantity > 0),
  original_unit_cost numeric not null check (original_unit_cost >= 0),
  refund_amount numeric(12,2) not null check (refund_amount > 0),
  currency text not null,
  reported_received_at timestamptz not null,
  recorded_at timestamptz not null default now(),
  notes text not null check (length(trim(notes)) > 0),
  check (refund_amount = round(original_unit_cost * quantity, 2))
);
comment on table public.purchase_item_refund_recoveries is
  'MBOP full-refund inventory recoveries. Original outlay is retained here; operational unit_cost is zero. reported_received_at is operator confirmation, not warehouse received_date.';
alter table public.purchase_item_refund_recoveries enable row level security;
revoke all on public.purchase_item_refund_recoveries from public, anon, authenticated;
grant select, insert on public.purchase_item_refund_recoveries to service_role;

create function public.mbop_protect_refunded_inventory()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare recovery public.purchase_item_refund_recoveries%rowtype;
begin
  select * into recovery from public.purchase_item_refund_recoveries where item_id = new.item_id;
  if not found then return new; end if;
  new.unit_cost := 0;
  new.manual_unit_cost_override := true;
  -- Old shipment/return normalization cannot remove a physically recovered unit.
  -- A newly opened problem episode and explicit Return Pending still work.
  if new.current_status in ('cancelled','return_opened','no_tracking','shipped_no_tracking',
      'awaiting_carrier_scan','in_transit','partially_delivered','out_for_delivery',
      'available_for_pickup','exception') and not exists (
    select 1 from public.order_problem_cases c where c.purchase_item_id = new.item_id
      and c.problem_case_id <> recovery.problem_case_id and c.is_open
  ) then
    new.current_status := case when old.current_status in ('received','listed','return_pending')
      then old.current_status else 'delivered' end;
  end if;
  return new;
end;
$$;
revoke all on function public.mbop_protect_refunded_inventory() from public, anon, authenticated;
grant execute on function public.mbop_protect_refunded_inventory() to service_role;
create trigger mbop_protect_refunded_inventory before update on public.purchase_items
for each row execute function public.mbop_protect_refunded_inventory();

create function public.mbop_record_refunded_inventory_recovery(
  p_item_id uuid, p_problem_case_id uuid, p_refund_amount numeric,
  p_resolution text, p_notes text, p_reported_received_at timestamptz default now()
) returns uuid language plpgsql security invoker set search_path = '' as $$
declare
  item public.purchase_items%rowtype;
  problem public.order_problem_cases%rowtype;
  existing public.purchase_item_refund_recoveries%rowtype;
  recovery_id uuid;
begin
  select * into item from public.purchase_items where item_id = p_item_id for update;
  if not found then raise exception 'Purchase item not found'; end if;
  select * into existing from public.purchase_item_refund_recoveries where item_id = p_item_id;
  if found then
    if existing.problem_case_id is distinct from p_problem_case_id or existing.refund_amount is distinct from p_refund_amount
      or existing.resolution is distinct from p_resolution then raise exception 'Conflicting recovery already recorded'; end if;
    return existing.recovery_id; -- Retrying must not reset Received/Listed or duplicate events.
  end if;
  select * into problem from public.order_problem_cases where problem_case_id = p_problem_case_id for update;
  if not found or problem.purchase_item_id is distinct from p_item_id or problem.purchase_id is distinct from item.purchase_id then
    raise exception 'Refund case does not belong to this purchase item';
  end if;
  if p_resolution is null or p_resolution not in ('refunded_replacement_received','refunded_item_retained')
    or nullif(trim(p_notes),'') is null or p_reported_received_at is null
    or p_reported_received_at > now() + interval '5 minutes' then
    raise exception 'Resolution, operator notes, and a non-future receipt report are required';
  end if;
  if problem.workflow_state <> 'resolved_refunded' or problem.is_open
    or problem.refund_received_at is null then raise exception 'Confirm and resolve the refund first'; end if;
  if item.current_status is null or item.current_status not in ('return_pending','return_opened','cancelled','delivered') then
    raise exception 'Item must be awaiting recovery, not already Received or Listed';
  end if;
  if exists (select 1 from public.order_problem_cases c where c.purchase_item_id=p_item_id
      and c.problem_case_id<>p_problem_case_id and c.is_open) then
    raise exception 'Resolve the other open problem episode first';
  end if;
  if item.unit_cost is null or item.quantity is null or item.quantity <= 0
    or p_refund_amount is null or p_refund_amount <= 0
    or p_refund_amount <> round(item.unit_cost * item.quantity,2) then
    raise exception 'This workflow requires a full refund of the complete item quantity';
  end if;
  if problem.actual_refund_amount is not null and problem.actual_refund_amount <> p_refund_amount then
    raise exception 'Refund amount differs from the confirmed case amount';
  end if;
  insert into public.purchase_item_refund_recoveries
    (item_id,problem_case_id,resolution,quantity,original_unit_cost,refund_amount,currency,reported_received_at,notes)
  values (p_item_id,p_problem_case_id,p_resolution,item.quantity,item.unit_cost,p_refund_amount,
    coalesce(problem.refund_currency,'USD'),p_reported_received_at,trim(p_notes))
  returning purchase_item_refund_recoveries.recovery_id into recovery_id;
  update public.order_problem_cases set actual_refund_amount=p_refund_amount,
    replacement_received_at=case when p_resolution='refunded_replacement_received'
      then p_reported_received_at else replacement_received_at end,
    notes=concat_ws(E'\n',nullif(notes,''),trim(p_notes)), updated_at=now()
  where problem_case_id=p_problem_case_id;
  update public.purchase_items set unit_cost=0, manual_unit_cost_override=true,
    current_status='delivered', exclude_from_purchase_reporting=false, exclusion_reason=null,
    notes=concat_ws(E'\n',nullif(notes,''),'Full refund; usable inventory recovered. ' || trim(p_notes))
  where item_id=p_item_id;
  -- Clear wrong-item receipt quantities and reopen for correct-item verification.
  update public.inbound_shipment_items set resolution_status='open', resolved_at=null,
    resolution_reason=null, resolved_by=null, received_verified=false,
    quantity_received_from_package=0
  where item_id=p_item_id and resolution_status in ('return_pending','open');
  insert into public.order_problem_events
    (problem_case_id,event_type,event_source,event_at,message,amount,currency,raw_json)
  values (p_problem_case_id,'refunded_inventory_recovered','operator',now(),trim(p_notes),p_refund_amount,
    coalesce(problem.refund_currency,'USD'),jsonb_build_object('recovery_id',recovery_id,
      'resolution',p_resolution,'quantity',item.quantity,'original_unit_cost',item.unit_cost,'net_unit_cost',0));
  return recovery_id;
end;
$$;
revoke all on function public.mbop_record_refunded_inventory_recovery(uuid,uuid,numeric,text,text,timestamptz) from public, anon, authenticated;
grant execute on function public.mbop_record_refunded_inventory_recovery(uuid,uuid,numeric,text,text,timestamptz) to service_role;
