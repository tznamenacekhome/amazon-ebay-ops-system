-- Phase 3 wholesale opportunity evaluation, review lifecycle and draft intent.
-- Draft commitments are not supplier orders, purchases, inventory or accounting.

create table public.wholesale_opportunities (
  opportunity_id uuid primary key default gen_random_uuid(),
  supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
  marketplace_id text not null,
  current_candidate_id uuid references public.wholesale_amazon_candidates(candidate_id) on delete set null,
  current_observation_id uuid references public.wholesale_supplier_observations(observation_id) on delete set null,
  current_evaluation_id uuid,
  opportunity_status text not null default 'pending_matching' check (opportunity_status in (
    'ready_for_review','temporarily_passed','hard_passed','added_to_order',
    'pending_matching','pending_eligibility','not_financially_qualified','inactive','evaluation_incomplete'
  )),
  active_decision_scope text check (active_decision_scope is null or active_decision_scope in ('temporary','hard')),
  active_decision_reason text,
  evaluation_requested boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (supplier_product_id, marketplace_id)
);

create index wholesale_opportunities_queue_idx
  on public.wholesale_opportunities (opportunity_status, updated_at desc);

create or replace function public.wholesale_mark_evaluation_requested()
returns trigger language plpgsql set search_path=public as $$
begin
  update public.wholesale_opportunities set evaluation_requested=true,updated_at=now()
  where supplier_product_id=new.supplier_product_id;
  return new;
end $$;
create trigger wholesale_observation_requests_evaluation
after insert on public.wholesale_supplier_observations
for each row execute function public.wholesale_mark_evaluation_requested();

create or replace function public.wholesale_match_requests_evaluation()
returns trigger language plpgsql set search_path=public as $$
begin
  update public.wholesale_opportunities set evaluation_requested=true,updated_at=now()
  where supplier_product_id=new.supplier_product_id and marketplace_id=new.marketplace_id;
  return new;
end $$;
create trigger wholesale_match_requests_evaluation
after insert or update of selected_candidate_id,match_status on public.wholesale_match_states
for each row execute function public.wholesale_match_requests_evaluation();

create table public.wholesale_evaluations (
  evaluation_id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.wholesale_opportunities(opportunity_id) on delete cascade,
  supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
  candidate_id uuid references public.wholesale_amazon_candidates(candidate_id) on delete set null,
  observation_id uuid references public.wholesale_supplier_observations(observation_id) on delete set null,
  marketplace_id text not null,
  asin text,
  evaluator_version text not null,
  assumption_version text not null,
  input_fingerprint text not null,
  evaluated_at timestamptz not null default now(),
  evaluation_status text not null check (evaluation_status in ('complete','incomplete','pending_matching','pending_eligibility','restricted')),
  incomplete_reasons jsonb not null default '[]'::jsonb check (jsonb_typeof(incomplete_reasons) = 'array'),
  eligibility_status text,
  eligibility_checked_at timestamptz,
  supplier_unit_cost numeric(14,4),
  currency text not null default 'USD',
  current_buy_box_price numeric(14,4),
  keepa_avg30_price numeric(14,4),
  keepa_avg90_price numeric(14,4),
  keepa_captured_at timestamptz,
  current_total_amazon_fees numeric(14,4),
  current_referral_fee numeric(14,4),
  current_fba_fee numeric(14,4),
  avg90_total_amazon_fees numeric(14,4),
  avg90_referral_fee numeric(14,4),
  avg90_fba_fee numeric(14,4),
  fee_evidence_json jsonb not null default '{}'::jsonb check (jsonb_typeof(fee_evidence_json) = 'object'),
  inbound_allowance numeric(14,4),
  return_allowance numeric(14,4),
  storage_allowance numeric(14,4),
  allowance_status text not null check (allowance_status in ('complete','accessory_review_required')),
  current_true_profit numeric(14,4),
  current_true_roi numeric(14,8),
  avg90_true_profit numeric(14,4),
  avg90_true_roi numeric(14,8),
  qualification_basis text not null check (qualification_basis in ('current_only','avg90_only','both','neither','incomplete')),
  is_financially_qualified boolean not null default false,
  current_roi_floor_price numeric(14,4),
  avg90_roi_floor_price numeric(14,4),
  current_price_headroom numeric(14,8),
  keepa_sales_rank_drops90 integer,
  expected_monthly_sales numeric(14,4),
  fba_fulfillable_units integer not null default 0,
  inbound_units integer not null default 0,
  draft_commitment_units integer not null default 0,
  target_units numeric(14,4),
  purchase_capacity numeric(14,4),
  supplier_availability_raw text,
  supplier_availability_min integer,
  supplier_availability_is_exact boolean,
  previous_supplier_price numeric(14,4),
  supplier_price_30d numeric(14,4),
  supplier_price_90d numeric(14,4),
  supplier_historical_low numeric(14,4),
  supplier_price_change_30d numeric(14,8),
  supplier_price_change_90d numeric(14,8),
  amazon_price_change_30d numeric(14,8),
  amazon_price_change_90d numeric(14,8),
  offer_count_current integer,
  fba_seller_count integer,
  risk_signals_json jsonb not null default '{}'::jsonb check (jsonb_typeof(risk_signals_json) = 'object'),
  source_evidence_json jsonb not null default '{}'::jsonb check (jsonb_typeof(source_evidence_json) = 'object'),
  created_at timestamptz not null default now(),
  unique (opportunity_id, input_fingerprint)
);

alter table public.wholesale_opportunities
  add constraint wholesale_opportunities_current_evaluation_fk
  foreign key (current_evaluation_id) references public.wholesale_evaluations(evaluation_id) on delete set null;

create index wholesale_evaluations_opportunity_idx
  on public.wholesale_evaluations (opportunity_id, evaluated_at desc);

create table public.wholesale_decisions (
  decision_id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.wholesale_opportunities(opportunity_id) on delete cascade,
  evaluation_id uuid references public.wholesale_evaluations(evaluation_id) on delete set null,
  candidate_id uuid references public.wholesale_amazon_candidates(candidate_id) on delete set null,
  decision_action text not null check (decision_action in (
    'temporary_pass','hard_pass','reverse_pass','add_to_order','update_draft','remove_draft','automatic_resurface'
  )),
  decision_scope text check (decision_scope is null or decision_scope in ('temporary','hard','draft','system')),
  reason_code text,
  notes text,
  actor text,
  reverses_decision_id uuid references public.wholesale_decisions(decision_id),
  decision_context jsonb not null default '{}'::jsonb check (jsonb_typeof(decision_context) = 'object'),
  created_at timestamptz not null default now()
);

create index wholesale_decisions_opportunity_idx
  on public.wholesale_decisions (opportunity_id, created_at desc);

create table public.wholesale_order_candidates (
  order_candidate_id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.wholesale_opportunities(opportunity_id) on delete cascade,
  supplier_id uuid not null references public.wholesale_suppliers(supplier_id),
  supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id),
  candidate_id uuid not null references public.wholesale_amazon_candidates(candidate_id),
  evaluation_id uuid not null references public.wholesale_evaluations(evaluation_id),
  observation_id uuid not null references public.wholesale_supplier_observations(observation_id),
  marketplace_id text not null,
  asin text not null,
  quantity integer not null check (quantity > 0),
  supplier_unit_price numeric(14,4) not null check (supplier_unit_price >= 0),
  extended_supplier_cost numeric(16,4) generated always as (quantity * supplier_unit_price) stored,
  currency text not null,
  commitment_status text not null default 'draft' check (commitment_status in ('draft','released','consumed')),
  idempotency_key text not null unique,
  revision integer not null default 1 check (revision > 0),
  actor text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  released_at timestamptz
);

create unique index wholesale_order_candidates_one_active_product_uidx
  on public.wholesale_order_candidates (supplier_product_id, marketplace_id)
  where commitment_status = 'draft';
create index wholesale_order_candidates_opportunity_idx
  on public.wholesale_order_candidates (opportunity_id, commitment_status);

create table public.wholesale_order_candidate_requests (
  idempotency_key text primary key,
  order_candidate_id uuid not null references public.wholesale_order_candidates(order_candidate_id) on delete cascade,
  requested_quantity integer not null,
  resulting_revision integer not null,
  created_at timestamptz not null default now()
);

create or replace function public.wholesale_draft_requests_evaluation()
returns trigger language plpgsql set search_path=public as $$
begin
  update public.wholesale_opportunities set evaluation_requested=true,updated_at=now()
  where opportunity_id=new.opportunity_id;
  return new;
end $$;
create trigger wholesale_draft_requests_evaluation
after insert or update of quantity,commitment_status on public.wholesale_order_candidates
for each row execute function public.wholesale_draft_requests_evaluation();

create or replace function public.wholesale_apply_decision(
  p_opportunity_id uuid, p_evaluation_id uuid, p_action text,
  p_reason_code text default null, p_notes text default null, p_actor text default null
) returns public.wholesale_opportunities
language plpgsql security definer set search_path = public as $$
declare
  v_opportunity public.wholesale_opportunities;
  v_decision_id uuid;
  v_scope text;
  v_status text;
  v_reverses uuid;
  v_match_status text;
begin
  select * into v_opportunity from public.wholesale_opportunities where opportunity_id = p_opportunity_id for update;
  if not found then raise exception 'opportunity_not_found'; end if;
  if p_evaluation_id is distinct from v_opportunity.current_evaluation_id then raise exception 'stale_evaluation'; end if;

  if p_action = 'temporary_pass' then
    if p_reason_code not in ('low_profitability','price_risk','too_much_inventory','competition','other') then
      raise exception 'invalid_temporary_pass_reason';
    end if;
    v_scope := 'temporary'; v_status := 'temporarily_passed';
  elsif p_action = 'hard_pass' then
    if p_reason_code not in ('listing_asin_issue','restricted_cant_sell') then raise exception 'invalid_hard_pass_reason'; end if;
    if p_reason_code = 'restricted_cant_sell' then
      select match_status into v_match_status from public.wholesale_match_states
      where supplier_product_id = v_opportunity.supplier_product_id and marketplace_id = v_opportunity.marketplace_id;
      if v_match_status is distinct from 'restricted_no_eligible' then raise exception 'eligibility_not_confirmed_restricted'; end if;
    end if;
    v_scope := 'hard'; v_status := 'hard_passed';
  elsif p_action = 'reverse_pass' then
    select decision_id into v_reverses from public.wholesale_decisions
    where opportunity_id = p_opportunity_id and decision_scope in ('temporary','hard')
    order by created_at desc limit 1;
    v_scope := null;
    select case
      when e.evaluation_status = 'pending_matching' then 'pending_matching'
      when e.evaluation_status in ('pending_eligibility','restricted') then 'pending_eligibility'
      when e.evaluation_status = 'incomplete' then 'evaluation_incomplete'
      when e.is_financially_qualified then 'ready_for_review'
      else 'not_financially_qualified'
    end into v_status from public.wholesale_evaluations e where e.evaluation_id = p_evaluation_id;
  else raise exception 'invalid_decision_action';
  end if;

  insert into public.wholesale_decisions (
    opportunity_id,evaluation_id,candidate_id,decision_action,decision_scope,reason_code,notes,actor,reverses_decision_id
  ) values (
    p_opportunity_id,p_evaluation_id,v_opportunity.current_candidate_id,p_action,
    case when p_action='reverse_pass' then 'system' else v_scope end,p_reason_code,p_notes,p_actor,v_reverses
  ) returning decision_id into v_decision_id;

  update public.wholesale_opportunities set opportunity_status=v_status,
    active_decision_scope=v_scope,
    active_decision_reason=case when p_action='reverse_pass' then null else p_reason_code end,
    updated_at=now() where opportunity_id=p_opportunity_id returning * into v_opportunity;
  return v_opportunity;
end $$;

create or replace function public.wholesale_upsert_draft_commitment(
  p_opportunity_id uuid, p_evaluation_id uuid, p_quantity integer,
  p_idempotency_key text, p_actor text default null
) returns public.wholesale_order_candidates
language plpgsql security definer set search_path = public as $$
declare
  v_opportunity public.wholesale_opportunities;
  v_evaluation public.wholesale_evaluations;
  v_product public.wholesale_supplier_products;
  v_existing public.wholesale_order_candidates;
  v_result public.wholesale_order_candidates;
  v_action text;
begin
  if p_quantity <= 0 then raise exception 'quantity_must_be_positive'; end if;
  if nullif(btrim(p_idempotency_key),'') is null then raise exception 'idempotency_key_required'; end if;
  select * into v_opportunity from public.wholesale_opportunities where opportunity_id=p_opportunity_id for update;
  if not found then raise exception 'opportunity_not_found'; end if;
  if v_opportunity.current_evaluation_id is distinct from p_evaluation_id then raise exception 'stale_evaluation'; end if;
  select * into v_evaluation from public.wholesale_evaluations where evaluation_id=p_evaluation_id;
  if not found or v_evaluation.evaluation_status <> 'complete' or not v_evaluation.is_financially_qualified
     or v_evaluation.eligibility_status <> 'eligible' then raise exception 'opportunity_not_actionable'; end if;
  if v_evaluation.supplier_availability_is_exact and p_quantity > v_evaluation.supplier_availability_min then
    raise exception 'quantity_exceeds_exact_supplier_availability';
  end if;
  select oc.* into v_existing from public.wholesale_order_candidate_requests r
    join public.wholesale_order_candidates oc on oc.order_candidate_id=r.order_candidate_id
    where r.idempotency_key=p_idempotency_key;
  if found then return v_existing; end if;
  select * into v_product from public.wholesale_supplier_products where supplier_product_id=v_opportunity.supplier_product_id;
  select * into v_existing from public.wholesale_order_candidates
    where supplier_product_id=v_opportunity.supplier_product_id and marketplace_id=v_opportunity.marketplace_id
      and commitment_status='draft' for update;
  if found then
    update public.wholesale_order_candidates set quantity=p_quantity,evaluation_id=p_evaluation_id,
      candidate_id=v_opportunity.current_candidate_id,observation_id=v_evaluation.observation_id,
      asin=v_evaluation.asin,supplier_unit_price=v_evaluation.supplier_unit_cost,
      revision=revision+1,actor=p_actor,updated_at=now()
    where order_candidate_id=v_existing.order_candidate_id returning * into v_result;
    v_action := 'update_draft';
  else
    insert into public.wholesale_order_candidates (
      opportunity_id,supplier_id,supplier_product_id,candidate_id,evaluation_id,observation_id,
      marketplace_id,asin,quantity,supplier_unit_price,currency,idempotency_key,actor
    ) values (
      p_opportunity_id,v_product.supplier_id,v_product.supplier_product_id,v_opportunity.current_candidate_id,
      p_evaluation_id,v_evaluation.observation_id,v_opportunity.marketplace_id,v_evaluation.asin,
      p_quantity,v_evaluation.supplier_unit_cost,v_evaluation.currency,p_idempotency_key,p_actor
    ) returning * into v_result;
    v_action := 'add_to_order';
  end if;
  insert into public.wholesale_order_candidate_requests(idempotency_key,order_candidate_id,requested_quantity,resulting_revision)
    values(p_idempotency_key,v_result.order_candidate_id,p_quantity,v_result.revision);
  insert into public.wholesale_decisions (
    opportunity_id,evaluation_id,candidate_id,decision_action,decision_scope,reason_code,actor,decision_context
  ) values (
    p_opportunity_id,p_evaluation_id,v_opportunity.current_candidate_id,v_action,'draft',null,p_actor,
    jsonb_build_object('order_candidate_id',v_result.order_candidate_id,'quantity',p_quantity,'revision',v_result.revision)
  );
  update public.wholesale_opportunities set opportunity_status='added_to_order',updated_at=now()
    where opportunity_id=p_opportunity_id;
  return v_result;
end $$;

create or replace function public.wholesale_release_draft_commitment(
  p_order_candidate_id uuid, p_actor text default null
) returns public.wholesale_order_candidates
language plpgsql security definer set search_path = public as $$
declare v_result public.wholesale_order_candidates; v_eval public.wholesale_evaluations; v_status text;
begin
  update public.wholesale_order_candidates set commitment_status='released',released_at=now(),updated_at=now(),
    revision=revision+1,actor=p_actor where order_candidate_id=p_order_candidate_id and commitment_status='draft'
    returning * into v_result;
  if not found then raise exception 'active_draft_not_found'; end if;
  select * into v_eval from public.wholesale_evaluations where evaluation_id=v_result.evaluation_id;
  v_status := case when v_eval.is_financially_qualified then 'ready_for_review' else 'not_financially_qualified' end;
  insert into public.wholesale_decisions(opportunity_id,evaluation_id,candidate_id,decision_action,decision_scope,actor,decision_context)
    values(v_result.opportunity_id,v_result.evaluation_id,v_result.candidate_id,'remove_draft','draft',p_actor,
      jsonb_build_object('order_candidate_id',v_result.order_candidate_id,'quantity',v_result.quantity));
  update public.wholesale_opportunities set opportunity_status=v_status,updated_at=now()
    where opportunity_id=v_result.opportunity_id and active_decision_scope is null;
  return v_result;
end $$;

alter table public.wholesale_opportunities enable row level security;
alter table public.wholesale_evaluations enable row level security;
alter table public.wholesale_decisions enable row level security;
alter table public.wholesale_order_candidates enable row level security;
alter table public.wholesale_order_candidate_requests enable row level security;

revoke all on table public.wholesale_opportunities,public.wholesale_evaluations,public.wholesale_decisions,public.wholesale_order_candidates from anon,authenticated;
revoke all on table public.wholesale_order_candidate_requests from anon,authenticated;
revoke all on function public.wholesale_mark_evaluation_requested() from public,anon,authenticated;
revoke all on function public.wholesale_match_requests_evaluation() from public,anon,authenticated;
revoke all on function public.wholesale_draft_requests_evaluation() from public,anon,authenticated;
revoke all on function public.wholesale_apply_decision(uuid,uuid,text,text,text,text) from public,anon,authenticated;
revoke all on function public.wholesale_upsert_draft_commitment(uuid,uuid,integer,text,text) from public,anon,authenticated;
revoke all on function public.wholesale_release_draft_commitment(uuid,text) from public,anon,authenticated;
grant select,insert,update on table public.wholesale_opportunities,public.wholesale_evaluations to service_role;
grant select,insert on table public.wholesale_decisions to service_role;
grant select,insert,update on table public.wholesale_order_candidates to service_role;
grant select,insert on table public.wholesale_order_candidate_requests to service_role;
grant execute on function public.wholesale_apply_decision(uuid,uuid,text,text,text,text) to service_role;
grant execute on function public.wholesale_upsert_draft_commitment(uuid,uuid,integer,text,text) to service_role;
grant execute on function public.wholesale_release_draft_commitment(uuid,text) to service_role;
