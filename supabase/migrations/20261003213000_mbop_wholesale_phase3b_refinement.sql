-- Wholesale Phase 3B refinement: auditable discovery evidence, conditional
-- pass resurfacing inputs, and persistent product classifications.

alter table public.wholesale_catalog_searches
  add column if not exists query_context jsonb not null default '{}'::jsonb
  check (jsonb_typeof(query_context) = 'object');

create table if not exists public.wholesale_product_classifications (
  classification_id uuid primary key default gen_random_uuid(),
  supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
  classification_code text not null check (classification_code in ('non_na_version')),
  classification_status text not null default 'active' check (classification_status in ('active','reversed')),
  evidence_json jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence_json) = 'object'),
  actor text,
  created_at timestamptz not null default now(),
  reversed_at timestamptz,
  reversed_by text
);

create unique index if not exists wholesale_product_classifications_active_uidx
  on public.wholesale_product_classifications(supplier_product_id, classification_code)
  where classification_status = 'active';
create index if not exists wholesale_product_classifications_product_idx
  on public.wholesale_product_classifications(supplier_product_id, created_at desc);

create or replace function public.wholesale_set_product_classification(
  p_supplier_product_id uuid, p_classification_code text, p_active boolean,
  p_evidence_json jsonb default '{}'::jsonb, p_actor text default null
) returns public.wholesale_product_classifications
language plpgsql security definer set search_path=public as $$
declare v_row public.wholesale_product_classifications;
begin
  if p_classification_code <> 'non_na_version' then raise exception 'invalid_product_classification'; end if;
  if p_active then
    select * into v_row from public.wholesale_product_classifications
    where supplier_product_id=p_supplier_product_id and classification_code=p_classification_code
      and classification_status='active' for update;
    if found then return v_row; end if;
    insert into public.wholesale_product_classifications(
      supplier_product_id,classification_code,evidence_json,actor
    ) values (p_supplier_product_id,p_classification_code,coalesce(p_evidence_json,'{}'::jsonb),p_actor)
    returning * into v_row;
  else
    update public.wholesale_product_classifications set classification_status='reversed',
      reversed_at=now(),reversed_by=p_actor
    where supplier_product_id=p_supplier_product_id and classification_code=p_classification_code
      and classification_status='active' returning * into v_row;
    if not found then raise exception 'active_product_classification_not_found'; end if;
  end if;
  return v_row;
end $$;

create or replace function public.wholesale_apply_decision(
  p_opportunity_id uuid, p_evaluation_id uuid, p_action text,
  p_reason_code text default null, p_notes text default null, p_actor text default null
) returns public.wholesale_opportunities
language plpgsql security definer set search_path=public as $$
declare
  v_opportunity public.wholesale_opportunities;
  v_evaluation public.wholesale_evaluations;
  v_decision_id uuid;
  v_scope text;
  v_status text;
  v_reverses uuid;
  v_context jsonb := '{}'::jsonb;
begin
  select * into v_opportunity from public.wholesale_opportunities where opportunity_id=p_opportunity_id for update;
  if not found then raise exception 'opportunity_not_found'; end if;
  if p_evaluation_id is distinct from v_opportunity.current_evaluation_id then raise exception 'stale_evaluation'; end if;
  select * into v_evaluation from public.wholesale_evaluations where evaluation_id=p_evaluation_id;

  if p_action='temporary_pass' then
    if p_reason_code not in ('price_risk','too_much_inventory','competition','other') then
      raise exception 'invalid_temporary_pass_reason';
    end if;
    v_scope := 'temporary'; v_status := 'temporarily_passed';
  elsif p_action='hard_pass' then
    if p_reason_code <> 'listing_asin_issue' then raise exception 'invalid_hard_pass_reason'; end if;
    v_scope := 'hard'; v_status := 'hard_passed';
  elsif p_action='reverse_pass' then
    select decision_id into v_reverses from public.wholesale_decisions
      where opportunity_id=p_opportunity_id and decision_scope in ('temporary','hard')
      order by created_at desc limit 1;
    v_scope := null;
    v_status := case
      when v_evaluation.evaluation_status='pending_matching' then 'pending_matching'
      when v_evaluation.evaluation_status in ('pending_eligibility','restricted') then 'pending_eligibility'
      when v_evaluation.evaluation_status='incomplete' then 'evaluation_incomplete'
      when v_evaluation.is_financially_qualified then 'ready_for_review'
      else 'not_financially_qualified' end;
  else raise exception 'invalid_decision_action';
  end if;

  if p_action in ('temporary_pass','hard_pass') then
    select jsonb_build_object(
      'passed_at',now(),
      'selected_asin',v_evaluation.asin,
      'list_context',jsonb_build_object(
        'import_id',o.import_id,'effective_date',i.effective_date,
        'imported_at',i.imported_at,'supplier_id',i.supplier_id),
      'condition_snapshot',jsonb_build_object(
        'fba_units',v_evaluation.fba_fulfillable_units,
        'inbound_units',v_evaluation.inbound_units,
        'draft_units',v_evaluation.draft_commitment_units,
        'total_exposure',v_evaluation.fba_fulfillable_units+v_evaluation.inbound_units+v_evaluation.draft_commitment_units,
        'velocity90',v_evaluation.keepa_sales_rank_drops90,
        'target_units',v_evaluation.target_units,
        'purchase_capacity',v_evaluation.purchase_capacity,
        'supplier_price',v_evaluation.supplier_unit_cost,
        'current_buy_box',v_evaluation.current_buy_box_price,
        'avg30',v_evaluation.keepa_avg30_price,
        'avg90',v_evaluation.keepa_avg90_price,
        'previous_supplier_price',v_evaluation.previous_supplier_price,
        'supplier_price_30d',v_evaluation.supplier_price_30d,
        'supplier_price_90d',v_evaluation.supplier_price_90d,
        'offer_count',v_evaluation.offer_count_current,
        'fba_seller_count',v_evaluation.fba_seller_count,
        'risk_signals',v_evaluation.risk_signals_json,
        'input_fingerprint',v_evaluation.input_fingerprint
      )
    ) into v_context
    from public.wholesale_supplier_observations o
    join public.wholesale_imports i on i.import_id=o.import_id
    where o.observation_id=v_evaluation.observation_id;
  end if;

  insert into public.wholesale_decisions(
    opportunity_id,evaluation_id,candidate_id,decision_action,decision_scope,
    reason_code,notes,actor,reverses_decision_id,decision_context
  ) values (
    p_opportunity_id,p_evaluation_id,v_opportunity.current_candidate_id,p_action,
    case when p_action='reverse_pass' then 'system' else v_scope end,
    p_reason_code,p_notes,p_actor,v_reverses,coalesce(v_context,'{}'::jsonb)
  ) returning decision_id into v_decision_id;

  update public.wholesale_opportunities set opportunity_status=v_status,
    active_decision_scope=v_scope,
    active_decision_reason=case when p_action='reverse_pass' then null else p_reason_code end,
    updated_at=now() where opportunity_id=p_opportunity_id returning * into v_opportunity;
  return v_opportunity;
end $$;

alter table public.wholesale_product_classifications enable row level security;
revoke all on table public.wholesale_product_classifications from anon,authenticated;
revoke all on function public.wholesale_set_product_classification(uuid,text,boolean,jsonb,text) from public,anon,authenticated;
grant select,insert,update on table public.wholesale_product_classifications to service_role;
grant execute on function public.wholesale_set_product_classification(uuid,text,boolean,jsonb,text) to service_role;

