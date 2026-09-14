-- UNAPPROVED CANDIDATE: numeric fingerprint acceptance failed; do not apply remotely.
-- See docs/sourcing_phase3_final_deployment_2026-09-13.md before continuing.
-- MBOP: bounded decision refresh only. No provider, review or lifecycle writes.
-- This migration is not an activation flag. Legacy scoring remains unchanged.
create table public.sourcing_decision_refresh_log (
  request_id uuid primary key,
  opportunity_id uuid not null,
  request_hash text not null,
  before_state jsonb not null,
  after_state jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default clock_timestamp()
);
alter table public.sourcing_decision_refresh_log enable row level security;
revoke all on public.sourcing_decision_refresh_log from public, anon, authenticated;
grant select, insert on public.sourcing_decision_refresh_log to service_role;

create function public.sourcing_decision_guard_state(p_opportunity_id uuid)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object(
    'opportunity', to_jsonb(o),
    'candidate', (select to_jsonb(c) from public.sourcing_ebay_candidates c where c.candidate_id=o.candidate_id),
    'seed', (select to_jsonb(s) from public.sourcing_seed_asins s where s.seed_id=o.seed_id),
    'actions', coalesce((select jsonb_agg(to_jsonb(a) order by a.created_at,a.action_id)
      from public.sourcing_actions a where a.asin=o.asin or a.ebay_item_id=o.ebay_item_id),'[]'::jsonb),
    'pairHistory', coalesce((select jsonb_agg(jsonb_build_object('id',h.opportunity_id,'status',h.status,'updated_at',h.updated_at)
      order by h.opportunity_id) from public.sourcing_opportunities h
      where h.asin=o.asin and h.ebay_item_id=o.ebay_item_id),'[]'::jsonb),
    'blockedAsin', (select to_jsonb(b) from public.sourcing_blocked_asins b where b.asin=o.asin),
    'declinedOffers', coalesce((select jsonb_agg(to_jsonb(d) order by d.ebay_legacy_item_id)
      from public.sourcing_declined_ebay_offers d where d.ebay_legacy_item_id =
        case when o.ebay_item_id like 'v1|%|%' then split_part(o.ebay_item_id,'|',2) else o.ebay_item_id end),'[]'::jsonb),
    'velocityHolds', coalesce((select jsonb_agg(to_jsonb(v) order by v.suppression_id)
      from public.sourcing_sales_velocity_suppressions v where v.asin=o.asin and v.status='active'),'[]'::jsonb),
    'settings', coalesce((select jsonb_agg(to_jsonb(s) order by s.setting_id) from public.sourcing_settings s),'[]'::jsonb)
  ) from public.sourcing_opportunities o where o.opportunity_id=p_opportunity_id;
$$;
revoke all on function public.sourcing_decision_guard_state(uuid) from public, anon, authenticated;
grant execute on function public.sourcing_decision_guard_state(uuid) to service_role;

create function public.sourcing_refresh_decision_guarded(
  p_request_id uuid, p_opportunity_id uuid, p_allowed_ids uuid[],
  p_before_state jsonb, p_before_hash text, p_patch jsonb
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  current_state jsonb;
  after_state jsonb;
  fingerprint text;
  saved public.sourcing_decision_refresh_log%rowtype;
  changed jsonb;
  outcome jsonb;
  op jsonb;
  verdict text;
begin
  if p_request_id is null or p_opportunity_id is null or p_allowed_ids is null
    or cardinality(p_allowed_ids) not between 1 and 2000
    or not p_opportunity_id=any(p_allowed_ids) then
    raise exception 'Explicit bounded opportunity IDs required' using errcode='22023';
  end if;
  if jsonb_typeof(p_patch) is distinct from 'object' or p_patch='{}'::jsonb
    or exists(select 1 from jsonb_object_keys(p_patch) k where k not in ('status','matching_diagnostics_json','score','score_reason','ai_flags'))
    or p_patch->>'status' not in ('open','rejected')
    or jsonb_typeof(p_patch->'matching_diagnostics_json') is distinct from 'object' then
    raise exception 'Only decision fields and mutable statuses may be refreshed' using errcode='22023';
  end if;
  fingerprint := encode(sha256(convert_to(jsonb_build_object('id',p_opportunity_id,'ids',p_allowed_ids,
    'before',p_before_state,'hash',p_before_hash,'patch',p_patch)::text,'UTF8')),'hex');
  perform pg_advisory_xact_lock(hashtextextended('decision-refresh|'||p_request_id::text,0));
  select * into saved from public.sourcing_decision_refresh_log where request_id=p_request_id;
  if found then
    if saved.request_hash is distinct from fingerprint then
      raise exception 'Refresh request ID reused with different input' using errcode='22023';
    end if;
    return saved.result || jsonb_build_object('replayed',true);
  end if;
  -- Existing operator writers do not all share an advisory lock. Brief table
  -- locks also exclude those writers and prevent phantom action/hold inserts.
  -- NOWAIT releases all acquired locks on contention and skips, never stalls
  -- an operator transaction or continues from an application-only precheck.
  begin
    lock table public.sourcing_opportunities in exclusive mode nowait;
    lock table public.sourcing_actions, public.sourcing_ebay_candidates, public.sourcing_seed_asins,
      public.sourcing_blocked_asins, public.sourcing_sales_velocity_suppressions,
      public.sourcing_settings, public.sourcing_declined_ebay_offers in share row exclusive mode nowait;
    current_state := public.sourcing_decision_guard_state(p_opportunity_id);
    if p_before_state is null or p_before_hash is distinct from
      encode(sha256(convert_to(p_before_state::text,'UTF8')),'hex') then
      return jsonb_build_object('result','stale_state_skip','changed',jsonb_build_array('before_hash'));
    end if;
    if current_state is distinct from p_before_state then
      select jsonb_agg(k order by k) into changed from
        (select jsonb_object_keys(coalesce(current_state,'{}'::jsonb)||p_before_state) k) keys
        where current_state->k is distinct from p_before_state->k;
      return jsonb_build_object('result','stale_state_skip','changed',coalesce(changed,'["missing_row"]'::jsonb));
    end if;
    op := current_state->'opportunity';
    if op->>'status' not in ('open','rejected') or exists(
      select 1 from jsonb_array_elements(current_state->'pairHistory') h
      where h->>'status' not in ('open','rejected')) or exists(
      select 1 from jsonb_array_elements(current_state->'actions') a
      where a->>'asin'=op->>'asin' and (a->>'action_type'='inventory_snoozed' or
        (a->>'ebay_item_id'=op->>'ebay_item_id' and (a->>'action_type' in ('dismissed','purchased','watching','roi_snoozed','inventory_snoozed',
          'confirmed_valid_match','confirmed_exclusion') or
          a->'raw_action_context'->'matchingFeedback'->>'pairVerdict' in ('correct','incorrect'))))) then
      return jsonb_build_object('result','protected_skip','reason','Lifecycle or exact-pair operator history protected');
    end if;
    verdict := p_patch->'matching_diagnostics_json'->'static_rules'->'identity_comparison'->'evidenceDecision'->>'productIdentityVerdict';
    if p_patch->>'status'='open' and (verdict is distinct from 'match'
      or current_state->'blockedAsin' <> 'null'::jsonb or current_state->'velocityHolds' <> '[]'::jsonb
      or (op->>'opportunity_type'='best_offer' and exists(
        select 1 from jsonb_array_elements(current_state->'declinedOffers') d
        where nullif(op->>'max_offer_price','') is null or
          (op->>'max_offer_price')::numeric <= (d->>'declined_offer_amount')::numeric))
      or p_patch->'matching_diagnostics_json'->'presentationDecision'->>'eligible' is distinct from 'true') then
      raise exception 'Identity or business exclusion cannot be bypassed' using errcode='22023';
    end if;
    update public.sourcing_opportunities set status=p_patch->>'status',
      matching_diagnostics_json=p_patch->'matching_diagnostics_json',
      score=case when p_patch ? 'score' then (p_patch->>'score')::numeric else score end,
      score_reason=case when p_patch ? 'score_reason' then p_patch->>'score_reason' else score_reason end,
      ai_flags=case when p_patch ? 'ai_flags' then array(select jsonb_array_elements_text(p_patch->'ai_flags')) else ai_flags end,
      updated_at=clock_timestamp() where opportunity_id=p_opportunity_id;
    after_state := public.sourcing_decision_guard_state(p_opportunity_id);
    outcome := jsonb_build_object('result','written','opportunityId',p_opportunity_id,'requestId',p_request_id,
      'beforeStatus',op->>'status','afterStatus',p_patch->>'status');
    insert into public.sourcing_decision_refresh_log(request_id,opportunity_id,request_hash,before_state,after_state,result)
      values(p_request_id,p_opportunity_id,fingerprint,current_state,after_state,outcome);
    return outcome;
  exception when lock_not_available then
    return jsonb_build_object('result','stale_state_skip','changed',jsonb_build_array('concurrent_operator_or_source_activity'));
  end;
end;
$$;
revoke all on function public.sourcing_refresh_decision_guarded(uuid,uuid,uuid[],jsonb,text,jsonb) from public, anon, authenticated;
grant execute on function public.sourcing_refresh_decision_guarded(uuid,uuid,uuid[],jsonb,text,jsonb) to service_role;
