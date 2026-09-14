-- MBOP closeout candidate. Apply only after the accepted strict and write-guard tests pass.
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

-- Exact numbers and native timestamp columns have one transport representation.
-- Embedded JSON strings remain exact; array order remains significant.
create function public.sourcing_guard_canonical(p_value jsonb, p_path text[] default '{}')
returns jsonb language plpgsql stable security invoker set search_path = ''
set timezone = 'UTC' set datestyle = 'ISO, YMD' as $$
declare result jsonb;
begin
  case jsonb_typeof(p_value)
    when 'number' then return to_jsonb(trim_scale((p_value #>> '{}')::numeric));
    when 'object' then
      select coalesce(jsonb_object_agg(k,public.sourcing_guard_canonical(v,p_path||k) order by k),'{}'::jsonb)
      into result from jsonb_each(p_value) e(k,v);
      return result;
    when 'array' then
      select coalesce(jsonb_agg(public.sourcing_guard_canonical(v,p_path||array['*']) order by n),'[]'::jsonb)
      into result from jsonb_array_elements(p_value) with ordinality e(v,n);
      return result;
    when 'string' then
      if array_to_string(p_path,'.') = any(array['actions.*.created_at',
        'blockedAsin.blocked_at',
        'blockedAsin.updated_at',
        'declinedOffers.*.first_seen_at',
        'declinedOffers.*.last_seen_at',
        'candidate.auction_end_time',
        'candidate.first_seen_at',
        'candidate.last_seen_at',
        'opportunity.created_at',
        'opportunity.updated_at',
        'velocityHolds.*.dismissed_at',
        'velocityHolds.*.last_evaluated_at',
        'velocityHolds.*.reactivated_at',
        'velocityHolds.*.created_at',
        'velocityHolds.*.updated_at',
        'seed.last_sold_at',
        'seed.created_at',
        'settings.*.created_at',
        'settings.*.updated_at',
        'pairHistory.*.updated_at']) then
        return to_jsonb(to_char((p_value #>> '{}')::timestamptz at time zone 'UTC',
          'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'));
      end if;
      return p_value;
    else return p_value;
  end case;
end;
$$;
revoke all on function public.sourcing_guard_canonical(jsonb,text[]) from public, anon, authenticated;
grant execute on function public.sourcing_guard_canonical(jsonb,text[]) to service_role;

create function public.sourcing_guard_hash(p_value jsonb)
returns text language sql stable security invoker set search_path = '' as $$
  select encode(sha256(convert_to(public.sourcing_guard_canonical(p_value)::text,'UTF8')),'hex');
$$;
revoke all on function public.sourcing_guard_hash(jsonb) from public, anon, authenticated;
grant execute on function public.sourcing_guard_hash(jsonb) to service_role;

-- Semantic action normalization is shared by all guard hold decisions.
-- Match the existing action API semantics; known automation is not human review.
create function public.sourcing_guard_automated_action(a jsonb)
returns boolean language sql immutable security invoker set search_path='' as $$
 select coalesce(a->'raw_action_context'->>'cleanup_source'='cleanup_sourcing_duplicate_asin_opportunities'
   or (a->>'action_type'='dismissed' and a->>'dismiss_reason'='no_longer_available'
     and a->>'notes' like 'Daily availability refresh:%'),false);
$$;
create function public.sourcing_guard_identity_review(a jsonb)
returns boolean language sql immutable security invoker set search_path='' as $$
 select not public.sourcing_guard_automated_action(a) and coalesce(
   a->>'action_type' in ('confirmed_valid_match','confirmed_exclusion','mark_valid_match','confirm_exclusion','asin_updated')
   or a->'raw_action_context'->'matchingFeedback'->>'pairVerdict' in ('correct','incorrect','unsure')
   or (a->>'action_type'='matching_feedback' and
       (a->'raw_action_context'->'matchingFeedback'->>'evidenceProvenance'='explicit'
         or a->'raw_action_context'->>'source'='identity_adjudication_queue')),false);
$$;
revoke all on function public.sourcing_guard_automated_action(jsonb), public.sourcing_guard_identity_review(jsonb) from public,anon,authenticated;
grant execute on function public.sourcing_guard_automated_action(jsonb), public.sourcing_guard_identity_review(jsonb) to service_role;

create function public.sourcing_guard_hold_type(p_action jsonb)
returns text language sql immutable security invoker set search_path = '' as $$
  select case
    when p_action->>'action_type' in ('inventory_snoozed','inventory_snooze')
      or (p_action->>'action_type' in ('roi_snoozed','roi_snooze','snooze_roi')
          and p_action->'raw_action_context'->>'actionType'='inventory_snooze') then 'inventory_snooze'
    when p_action->>'action_type' in ('roi_snoozed','roi_snooze','snooze_roi') then 'roi_snooze'
    else 'other' end;
$$;
revoke all on function public.sourcing_guard_hold_type(jsonb) from public, anon, authenticated;
grant execute on function public.sourcing_guard_hold_type(jsonb) to service_role;

-- Same owned-unit inputs and exclusions as fetch_owned_units_by_asin.
-- The state reader and transaction locks cover all pipeline inputs.
create function public.sourcing_guard_owned_units(p_state jsonb)
returns numeric language sql immutable security invoker set search_path = '' as $$
  select greatest(0,trunc(coalesce((p_state->'seed'->>'current_inventory_units')::numeric,0))) +
    coalesce((select sum(case
      when lower(btrim(p->>'current_status')) in
        ('ordered','no_tracking','shipped_no_tracking','awaiting_carrier_scan','in_transit','delivered','received')
        then greatest(1,trunc(coalesce((p->>'quantity')::numeric,1)))
      when lower(btrim(p->>'current_status'))='listed' then
        coalesce((select sum(greatest(0,trunc(coalesce((f->>'outbound_remaining_quantity')::numeric,
          greatest(0,coalesce((f->>'quantity')::numeric,0)) -
          greatest(0,coalesce((f->>'received_quantity')::numeric,0)) -
          greatest(0,coalesce((f->>'available_quantity')::numeric,0))))))
          from jsonb_array_elements(p_state->'pipelineShipments') f
          where f->>'item_id'=p->>'item_id' and f->>'included' is distinct from 'false'
            and nullif(btrim(f->>'shipment_code'),'') is not null
            and lower(btrim(f->>'shipment_code')) <> 'legacy_listed_no_shipment_id'
            and coalesce(lower(btrim(f->>'workflow_status')),'') not in ('cancelled','canceled','closed','deleted','voided','abandoned')
            and coalesce(lower(btrim(f->>'amazon_status_normalized')),'') not in ('cancelled','canceled','closed','deleted','voided','abandoned')),0)
      else 0 end)
      from jsonb_array_elements(p_state->'pipelinePurchases') p
      where p->>'exclude_from_purchase_reporting' is distinct from 'true'
        and coalesce(lower(btrim(p->>'marketplace')),'') <> 'ebay'
        and coalesce(lower(btrim(p->>'current_status')),'') not in ('cancelled','return_opened','return_pending')),0);
$$;
revoke all on function public.sourcing_guard_owned_units(jsonb) from public, anon, authenticated;
grant execute on function public.sourcing_guard_owned_units(jsonb) to service_role;

create function public.sourcing_guard_active_hold(p_state jsonb, p_proposed_status text)
returns jsonb language plpgsql immutable security invoker set search_path = '' as $$
declare a jsonb; h jsonb; threshold numeric; baseline numeric; op jsonb := p_state->'opportunity';
  cost numeric; old_cost numeric; old_cap numeric; cap numeric;
begin
  -- Later inventory snoozes replace the ASIN's earlier threshold, as in the scorer.
  select value into a from jsonb_array_elements(p_state->'actions')
    where value->>'asin'=op->>'asin' and public.sourcing_guard_hold_type(value)='inventory_snooze'
    order by value->>'created_at' desc,value->>'action_id' desc limit 1;
  if a is not null then
    h := a->'raw_action_context'->'inventorySnooze';
    threshold := nullif(h->>'representAtUnits','')::numeric;
    baseline := nullif(h->>'baselineUnits','')::numeric;
    if threshold < 0 then threshold := null; end if;
    if threshold is null and baseline >= 0 then
      threshold := greatest(0,trunc(baseline)-greatest(1,ceil(trunc(baseline)*0.1)));
    end if;
    if p_proposed_status is distinct from 'open' or threshold is null
      or public.sourcing_guard_owned_units(p_state) > trunc(threshold) then
      return jsonb_build_object('type','inventory_snooze','scope','asin','actionId',a->>'action_id');
    end if;
  end if;
  -- ROI/price holds remain exact pair scoped. Latest pair lifecycle action wins.
  select value into a from jsonb_array_elements(p_state->'actions')
    where value->>'asin'=op->>'asin' and value->>'ebay_item_id'=op->>'ebay_item_id'
      and (public.sourcing_guard_hold_type(value)='roi_snooze'
        or value->>'action_type' in ('watching','watch','dismissed','purchased','inventory_snoozed'))
    order by value->>'created_at' desc,value->>'action_id' desc limit 1;
  if a is not null and (public.sourcing_guard_hold_type(a)='roi_snooze' or a->>'action_type' in ('watching','watch')) then
    old_cost := nullif(a->>'expected_purchase_cost','')::numeric;
    old_cap := nullif(a->>'required_max_landed_cost','')::numeric;
    cap := nullif(op->>'max_profitable_landed_cost','')::numeric;
    cost := case when op->>'opportunity_type'='best_offer' and op->>'max_offer_price' is not null
      then (op->>'max_offer_price')::numeric else coalesce((op->>'landed_cost')::numeric,
        case when nullif(p_state->'candidate'->>'price','')::numeric > 0
          then (p_state->'candidate'->>'price')::numeric end) end;
    if p_proposed_status is distinct from 'open' or not coalesce(
      (old_cost>0 and cost is not null and cost<old_cost-0.009)
      or (old_cap>0 and cap>old_cap+0.009),false) then
      return jsonb_build_object('type','roi_snooze','scope','pair','actionId',a->>'action_id');
    end if;
  end if;
  return null;
end;
$$;
revoke all on function public.sourcing_guard_active_hold(jsonb,text) from public, anon, authenticated;
grant execute on function public.sourcing_guard_active_hold(jsonb,text) to service_role;

create function public.sourcing_decision_guard_state(p_opportunity_id uuid)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object(
    'opportunity', (to_jsonb(o)-'matching_diagnostics_json') || jsonb_build_object(
      'diagnosticsHash',public.sourcing_guard_hash(o.matching_diagnostics_json),
      'previousIdentity',coalesce(o.matching_diagnostics_json->'canonicalDecision'->>'productIdentityVerdict',
        o.matching_diagnostics_json->'static_rules'->'identity_comparison'->'evidenceDecision'->>'productIdentityVerdict'),
      'previousRecommendation',o.matching_diagnostics_json->>'recommendation',
      'previousEligible',o.matching_diagnostics_json->'presentationDecision'->'eligible'),
    'pipelinePurchases', coalesce((select jsonb_agg(jsonb_build_object(
      'item_id',p.item_id,'asin',p.asin,'quantity',p.quantity,'current_status',p.current_status,
      'marketplace',p.marketplace,'exclude_from_purchase_reporting',p.exclude_from_purchase_reporting) order by p.item_id)
      from public.purchase_items p where p.asin=o.asin),'[]'::jsonb),
    'pipelineShipments', coalesce((select jsonb_agg(jsonb_build_object(
      'id',f.fba_shipment_item_id,'item_id',f.item_id,'quantity',f.quantity,'included',f.included,
      'outbound_remaining_quantity',f.outbound_remaining_quantity,'received_quantity',f.received_quantity,
      'available_quantity',f.available_quantity,'shipment_code',h.shipment_code,
      'workflow_status',h.workflow_status,'amazon_status_normalized',h.amazon_status_normalized) order by f.fba_shipment_item_id)
      from public.fba_shipment_items f join public.purchase_items p on p.item_id=f.item_id
      join public.fba_shipments h on h.fba_shipment_id=f.fba_shipment_id where p.asin=o.asin),'[]'::jsonb),
    'candidate', (select (to_jsonb(c)-'raw_ebay_json')||jsonb_build_object('rawHash',public.sourcing_guard_hash(c.raw_ebay_json)) from public.sourcing_ebay_candidates c where c.candidate_id=o.candidate_id),
    'seed', (select (to_jsonb(s)-'raw_context_json')||jsonb_build_object('rawHash',public.sourcing_guard_hash(s.raw_context_json)) from public.sourcing_seed_asins s where s.seed_id=o.seed_id),
    'actions', coalesce((select jsonb_agg((to_jsonb(a)-'raw_action_context')||jsonb_build_object(
        'contextHash',public.sourcing_guard_hash(a.raw_action_context),
        'raw_action_context',jsonb_build_object('actionType',a.raw_action_context->'actionType',
          'source',a.raw_action_context->'source','cleanup_source',a.raw_action_context->'cleanup_source',
          'inventorySnooze',a.raw_action_context->'inventorySnooze','matchingFeedback',
            jsonb_build_object('pairVerdict',a.raw_action_context->'matchingFeedback'->'pairVerdict',
              'evidenceProvenance',a.raw_action_context->'matchingFeedback'->'evidenceProvenance')))
        order by a.created_at,a.action_id)
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
  expected_state jsonb;
  canonical_state jsonb;
  fingerprint text;
  saved public.sourcing_decision_refresh_log%rowtype;
  changed jsonb;
  outcome jsonb;
  op jsonb;
  verdict text;
  active_hold jsonb;
begin
  if p_request_id is null or p_opportunity_id is null or p_allowed_ids is null
    or cardinality(p_allowed_ids) not between 1 and 2000
    or not p_opportunity_id=any(p_allowed_ids) then
    raise exception 'Explicit bounded opportunity IDs required' using errcode='22023';
  end if;
  if jsonb_typeof(p_patch) is distinct from 'object' or p_patch='{}'::jsonb
    or exists(select 1 from jsonb_object_keys(p_patch) k where k not in ('status','matching_diagnostics_json','score','score_reason','ai_flags','opportunity_type','target_sale_price','target_sale_price_source','landed_cost','profit','roi_percent','total_profit_opportunity','max_profitable_landed_cost','max_offer_price','required_offer_percent_of_ask','max_bid','inventory_need_level','months_of_supply','monthly_velocity','warning_flags','seller_trust_status','seller_trust_score'))
    or p_patch->>'status' not in ('open','rejected')
    or jsonb_typeof(p_patch->'matching_diagnostics_json') is distinct from 'object' then
    raise exception 'Only decision fields and mutable statuses may be refreshed' using errcode='22023';
  end if;
  expected_state := public.sourcing_guard_canonical(p_before_state);
  fingerprint := public.sourcing_guard_hash(jsonb_build_object('id',p_opportunity_id,'ids',p_allowed_ids,
    'before',expected_state,'hash',p_before_hash,'patch',p_patch));
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
      public.sourcing_settings, public.sourcing_declined_ebay_offers,
      public.purchase_items, public.fba_shipment_items, public.fba_shipments in share row exclusive mode nowait;
    current_state := public.sourcing_decision_guard_state(p_opportunity_id);
    if p_before_state is null or p_before_hash is distinct from
      public.sourcing_guard_hash(p_before_state) then
      return jsonb_build_object('result','stale_state_skip','changed',jsonb_build_array('before_hash'));
    end if;
    if exists(select 1 from jsonb_array_elements(current_state->'actions') a
      where a->>'asin'=current_state->'opportunity'->>'asin'
        and a->>'ebay_item_id'=current_state->'opportunity'->>'ebay_item_id'
        and public.sourcing_guard_identity_review(a)) then
      return jsonb_build_object('result','protected_skip','reason','operator_identity_review');
    end if;
    active_hold := public.sourcing_guard_active_hold(current_state,p_patch->>'status');
    if active_hold is not null then
      return jsonb_build_object('result','protected_skip','reason','active_hold','hold',active_hold);
    end if;
    canonical_state := public.sourcing_guard_canonical(current_state);
    -- Full database JSONB equality is authoritative, never hash equality alone.
    if canonical_state is distinct from expected_state then
      select jsonb_agg(k order by k) into changed from
        (select jsonb_object_keys(coalesce(current_state,'{}'::jsonb)||p_before_state) k) keys
        where canonical_state->k is distinct from expected_state->k;
      return jsonb_build_object('result','stale_state_skip','changed',coalesce(changed,'["missing_row"]'::jsonb));
    end if;
    op := current_state->'opportunity';
    if (op->>'status' not in ('open','rejected') and not (op->>'status'='dismissed' and exists(
      select 1 from jsonb_array_elements(current_state->'actions') a
      where a->>'opportunity_id'=op->>'opportunity_id' and public.sourcing_guard_automated_action(a)))) or exists(
      select 1 from jsonb_array_elements(current_state->'pairHistory') h
      where h->>'status' not in ('open','rejected') and not (h->>'status'='dismissed' and exists(
        select 1 from jsonb_array_elements(current_state->'actions') a
        where a->>'opportunity_id'=h->>'id' and public.sourcing_guard_automated_action(a)))) or exists(
      select 1 from jsonb_array_elements(current_state->'actions') a
      where a->>'asin'=op->>'asin' and not public.sourcing_guard_automated_action(a) and
        (a->>'ebay_item_id'=op->>'ebay_item_id' and (a->>'action_type' in ('dismissed','purchased',
          'confirmed_valid_match','confirmed_exclusion') or
          a->'raw_action_context'->'matchingFeedback'->>'pairVerdict' in ('correct','incorrect')))) then
      return jsonb_build_object('result','protected_skip','reason','Lifecycle or exact-pair operator history protected');
    end if;
    verdict := p_patch->'matching_diagnostics_json'->'static_rules'->'identity_comparison'->'evidenceDecision'->>'productIdentityVerdict';
    if p_patch->>'status'='open' and (verdict is distinct from 'match'
      or current_state->'blockedAsin' <> 'null'::jsonb or current_state->'velocityHolds' <> '[]'::jsonb
      or (coalesce(p_patch->>'opportunity_type',op->>'opportunity_type')='best_offer' and exists(
        select 1 from jsonb_array_elements(current_state->'declinedOffers') d
        where nullif(coalesce(p_patch->>'max_offer_price',op->>'max_offer_price'),'') is null or
          (coalesce(p_patch->>'max_offer_price',op->>'max_offer_price'))::numeric <= (d->>'declined_offer_amount')::numeric))
      or p_patch->'matching_diagnostics_json'->'presentationDecision'->>'eligible' is distinct from 'true') then
      raise exception 'Identity or business exclusion cannot be bypassed' using errcode='22023';
    end if;
    update public.sourcing_opportunities set status=p_patch->>'status',
      matching_diagnostics_json=p_patch->'matching_diagnostics_json',
      score=case when p_patch ? 'score' then (p_patch->>'score')::numeric else score end,
      score_reason=case when p_patch ? 'score_reason' then p_patch->>'score_reason' else score_reason end,
      ai_flags=case when p_patch ? 'ai_flags' then array(select jsonb_array_elements_text(p_patch->'ai_flags')) else ai_flags end,
      opportunity_type=case when p_patch ? 'opportunity_type' then p_patch->>'opportunity_type' else opportunity_type end,
      target_sale_price=case when p_patch ? 'target_sale_price' then (p_patch->>'target_sale_price')::numeric else target_sale_price end,
      target_sale_price_source=case when p_patch ? 'target_sale_price_source' then p_patch->>'target_sale_price_source' else target_sale_price_source end,
      landed_cost=case when p_patch ? 'landed_cost' then (p_patch->>'landed_cost')::numeric else landed_cost end,
      profit=case when p_patch ? 'profit' then (p_patch->>'profit')::numeric else profit end,
      roi_percent=case when p_patch ? 'roi_percent' then (p_patch->>'roi_percent')::numeric else roi_percent end,
      total_profit_opportunity=case when p_patch ? 'total_profit_opportunity' then (p_patch->>'total_profit_opportunity')::numeric else total_profit_opportunity end,
      max_profitable_landed_cost=case when p_patch ? 'max_profitable_landed_cost' then (p_patch->>'max_profitable_landed_cost')::numeric else max_profitable_landed_cost end,
      max_offer_price=case when p_patch ? 'max_offer_price' then (p_patch->>'max_offer_price')::numeric else max_offer_price end,
      required_offer_percent_of_ask=case when p_patch ? 'required_offer_percent_of_ask' then (p_patch->>'required_offer_percent_of_ask')::numeric else required_offer_percent_of_ask end,
      max_bid=case when p_patch ? 'max_bid' then (p_patch->>'max_bid')::numeric else max_bid end,
      inventory_need_level=case when p_patch ? 'inventory_need_level' then p_patch->>'inventory_need_level' else inventory_need_level end,
      months_of_supply=case when p_patch ? 'months_of_supply' then (p_patch->>'months_of_supply')::numeric else months_of_supply end,
      monthly_velocity=case when p_patch ? 'monthly_velocity' then (p_patch->>'monthly_velocity')::numeric else monthly_velocity end,
      warning_flags=case when p_patch ? 'warning_flags' then array(select jsonb_array_elements_text(p_patch->'warning_flags')) else warning_flags end,
      seller_trust_status=case when p_patch ? 'seller_trust_status' then p_patch->>'seller_trust_status' else seller_trust_status end,
      seller_trust_score=case when p_patch ? 'seller_trust_score' then (p_patch->>'seller_trust_score')::numeric else seller_trust_score end,
      updated_at=clock_timestamp() where opportunity_id=p_opportunity_id
      and asin is not distinct from op->>'asin'
      and ebay_item_id is not distinct from op->>'ebay_item_id'
      and candidate_id is not distinct from (op->>'candidate_id')::uuid
      and seed_id is not distinct from (op->>'seed_id')::uuid
      and status is not distinct from op->>'status'
      and updated_at is not distinct from (op->>'updated_at')::timestamptz
      and max_offer_price is not distinct from (op->>'max_offer_price')::numeric;
    if not found then
      return jsonb_build_object('result','stale_state_skip','changed',jsonb_build_array('typed_opportunity_state'));
    end if;
    after_state := public.sourcing_decision_guard_state(p_opportunity_id);
    outcome := jsonb_build_object('result','written','opportunityId',p_opportunity_id,'requestId',p_request_id,
      'beforeStatus',op->>'status','afterStatus',p_patch->>'status');
    insert into public.sourcing_decision_refresh_log(request_id,opportunity_id,request_hash,before_state,after_state,result)
      values(p_request_id,p_opportunity_id,fingerprint,jsonb_build_object('opportunity',current_state->'opportunity','guardHash',public.sourcing_guard_hash(current_state)),
        jsonb_build_object('opportunity',after_state->'opportunity','guardHash',public.sourcing_guard_hash(after_state)),outcome);
    return outcome;
  exception when lock_not_available then
    return jsonb_build_object('result','stale_state_skip','changed',jsonb_build_array('concurrent_operator_or_source_activity'));
  end;
end;
$$;
revoke all on function public.sourcing_refresh_decision_guarded(uuid,uuid,uuid[],jsonb,text,jsonb) from public, anon, authenticated;
grant execute on function public.sourcing_refresh_decision_guarded(uuid,uuid,uuid[],jsonb,text,jsonb) to service_role;

create function public.sourcing_closeout_cohort(p_start timestamptz,p_end timestamptz,p_after uuid default null)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
begin
  if p_end<p_start or p_end-p_start>interval '31 days' then raise exception 'Bounded calendar window required'; end if;
  return (select coalesce(jsonb_agg(to_jsonb(r) order by opportunity_id),'[]'::jsonb) from (
    select o.opportunity_id,o.asin,o.ebay_item_id,o.candidate_id,o.seed_id,o.status,o.created_at,
      case when exists(select 1 from public.sourcing_actions a where a.asin=o.asin and a.ebay_item_id=o.ebay_item_id
        and public.sourcing_guard_identity_review(to_jsonb(a))) then 'operator_reviewed'
      when o.status not in ('open','rejected','dismissed') or exists(
        select 1 from public.sourcing_actions a where a.asin=o.asin and a.ebay_item_id=o.ebay_item_id
          and a.action_type in ('dismissed','purchased') and not public.sourcing_guard_automated_action(to_jsonb(a)))
        or (o.status='dismissed' and not exists(select 1 from public.sourcing_actions a
          where a.opportunity_id=o.opportunity_id and public.sourcing_guard_automated_action(to_jsonb(a)))) then 'protected_lifecycle'
      when o.candidate_id is null or o.seed_id is null then 'insufficient_evidence'
      else null end exclusion
    from public.sourcing_opportunities o
    where o.created_at>=p_start and o.created_at<=p_end and (p_after is null or o.opportunity_id>p_after)
    order by o.opportunity_id limit 1000
  ) r);
end;
$$;

create function public.sourcing_closeout_capture(p_ids uuid[],p_sources boolean default true)
returns jsonb language plpgsql stable security invoker set search_path='' as $$
declare id uuid; s jsonb; result jsonb := '[]'; item jsonb; protected text;
begin
  if cardinality(p_ids) not between 1 and 25 then raise exception '1-25 explicit IDs required'; end if;
  foreach id in array p_ids loop
    s:=public.sourcing_decision_guard_state(id);
    protected:=null;
    if s is null then protected:='missing_row';
    elsif exists(select 1 from jsonb_array_elements(s->'actions') a
      where a->>'asin'=s->'opportunity'->>'asin' and a->>'ebay_item_id'=s->'opportunity'->>'ebay_item_id'
        and public.sourcing_guard_identity_review(a)) then protected:='operator_reviewed';
    elsif public.sourcing_guard_active_hold(s,'open') is not null then protected:='active_hold';
    elsif s->'blockedAsin'<>'null'::jsonb or s->'velocityHolds'<>'[]'::jsonb then protected:='asin_business_hold';
    elsif s->'opportunity'->>'status' not in ('open','rejected','dismissed') then protected:='protected_lifecycle';
    end if;
    item:=jsonb_build_object('opportunityId',id,'state',s,'hash',public.sourcing_guard_hash(s),
      'protected',protected,'ownedUnits',public.sourcing_guard_owned_units(s),'capturedAt',statement_timestamp());
    if p_sources and protected is null then
      item:=item||jsonb_build_object(
        'candidate',(select to_jsonb(c) from public.sourcing_ebay_candidates c where c.candidate_id=(s->'opportunity'->>'candidate_id')::uuid),
        'seed',(select to_jsonb(r) from public.sourcing_seed_asins r where r.seed_id=(s->'opportunity'->>'seed_id')::uuid),
        'reviews',coalesce((select jsonb_agg(to_jsonb(a)||jsonb_build_object('snapshot',to_jsonb(snap)) order by a.created_at,a.action_id)
          from public.sourcing_actions a join public.sourcing_listing_snapshots snap on snap.listing_snapshot_id=a.listing_snapshot_id
          where a.asin=s->'opportunity'->>'asin' and a.raw_action_context->'matchingFeedback'->>'version'='matching_feedback_v3'),'[]'::jsonb));
    end if;
    result:=result||jsonb_build_array(item);
  end loop;
  return result;
end;
$$;

create function public.sourcing_closeout_write_batch(p_rows jsonb,p_allowed_ids uuid[])
returns jsonb language plpgsql security invoker set search_path='' as $$
declare r jsonb; result jsonb:='[]';
begin
  if jsonb_array_length(p_rows) not between 1 and 25 then raise exception '1-25 explicit writes required'; end if;
  for r in select value from jsonb_array_elements(p_rows) loop
    result:=result||jsonb_build_array(public.sourcing_refresh_decision_guarded(
      (r->>'requestId')::uuid,(r->>'opportunityId')::uuid,p_allowed_ids,r->'state',r->>'hash',r->'patch'));
  end loop;
  return result;
end;
$$;
revoke all on function public.sourcing_closeout_cohort(timestamptz,timestamptz,uuid),
  public.sourcing_closeout_capture(uuid[],boolean),public.sourcing_closeout_write_batch(jsonb,uuid[]) from public,anon,authenticated;
grant execute on function public.sourcing_closeout_cohort(timestamptz,timestamptz,uuid),
  public.sourcing_closeout_capture(uuid[],boolean),public.sourcing_closeout_write_batch(jsonb,uuid[]) to service_role;
