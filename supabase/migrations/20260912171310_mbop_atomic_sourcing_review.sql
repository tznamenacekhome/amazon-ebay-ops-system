-- MBOP only. Append-only review evidence; no historical relabel or backfill.
-- Existing validated snapshot values are a subset of this expanded constraint.
-- NOT VALID avoids a full historical snapshot scan; all new writes are checked.
alter table public.sourcing_listing_snapshots drop constraint sourcing_listing_snapshots_event_check;
alter table public.sourcing_listing_snapshots add constraint sourcing_listing_snapshots_event_check
check (snapshot_event in ('opportunity_created','dismissed','watching','purchased','offer_made','roi_snoozed',
  'availability_refresh','backfill','confirmed_valid_match','confirmed_exclusion','matching_feedback')) not valid;

create index sourcing_actions_review_pair_idx on public.sourcing_actions
  (asin, ebay_item_id, created_at desc, action_id desc)
  where raw_action_context->'matchingFeedback'->>'version' = 'matching_feedback_v3';

create function public.sourcing_save_review(
  p_opportunity_id uuid, p_request_id uuid, p_asin text, p_candidate_id uuid,
  p_action_type text, p_reason text, p_notes text, p_actor text,
  p_request_hash text, p_context jsonb, p_snapshot jsonb, p_label jsonb
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  op public.sourcing_opportunities%rowtype;
  prior public.sourcing_actions%rowtype;
  snap public.sourcing_listing_snapshots%rowtype;
  snapshot_id uuid := gen_random_uuid();
  recorded_at timestamptz := clock_timestamp();
  stored_type text;
  context jsonb;
  lookback integer;
  velocity numeric;
  required_velocity numeric;
begin
  if p_request_id is null or nullif(p_actor,'') is null or nullif(p_request_hash,'') is null then
    raise exception 'Review requires request ID, actor and fingerprint' using errcode='22023';
  end if;
  if p_action_type not in ('dismiss','block_asin','mark_valid_match','confirm_exclusion','save_match_feedback') then
    raise exception 'Unsupported review action' using errcode='22023';
  end if;
  if p_action_type in ('dismiss','confirm_exclusion') and nullif(p_reason,'') is null then
    raise exception 'A concrete exclusion reason is required' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_request_id::text, 0));
  select * into prior from public.sourcing_actions where action_id=p_request_id;
  if found then
    if prior.opportunity_id is distinct from p_opportunity_id or prior.raw_action_context->>'actor' is distinct from p_actor
      or prior.raw_action_context->>'requestHash' is distinct from p_request_hash then
      raise exception 'Request ID already used for different feedback' using errcode='22023';
    end if;
    return jsonb_build_object('actionId',prior.action_id,'snapshotId',prior.listing_snapshot_id,'replayed',true);
  end if;
  select * into op from public.sourcing_opportunities where opportunity_id=p_opportunity_id for update;
  if not found then raise exception 'Opportunity not found' using errcode='P0002'; end if;
  if op.asin is distinct from p_asin or op.candidate_id is distinct from p_candidate_id
    or op.ebay_item_id is distinct from p_context->'pair'->>'ebayItemId'
    or op.matching_diagnostics_json->'canonicalDecision'->>'evaluationId' is distinct from p_context->'evaluation'->>'id' then
    raise exception 'Opportunity identity changed; reload before saving' using errcode='40001';
  end if;
  stored_type := case p_action_type when 'dismiss' then 'dismissed' when 'block_asin' then 'dismissed'
    when 'mark_valid_match' then 'confirmed_valid_match' when 'confirm_exclusion' then 'confirmed_exclusion' else 'matching_feedback' end;
  context := coalesce(p_context,'{}') || jsonb_build_object('actor',p_actor,'requestHash',p_request_hash,
    'requestId',p_request_id,'recordedAt',recorded_at,'snapshotId',snapshot_id,'previousStatus',op.status,
    'newStatus',case when p_action_type in ('dismiss','block_asin') and op.status in ('open','rejected','watching','roi_snoozed','inventory_snoozed') then 'dismissed' else op.status end);
  insert into public.sourcing_actions(action_id,opportunity_id,candidate_id,asin,ebay_item_id,action_type,dismiss_reason,notes,raw_action_context,created_at)
    values(p_request_id,op.opportunity_id,op.candidate_id,op.asin,op.ebay_item_id,stored_type,p_reason,p_notes,context,recorded_at);
  snap := jsonb_populate_record(null::public.sourcing_listing_snapshots, coalesce(p_snapshot,'{}') || jsonb_build_object(
    'listing_snapshot_id',snapshot_id,'opportunity_id',op.opportunity_id,'candidate_id',op.candidate_id,
    'action_id',p_request_id,'asin',op.asin,'ebay_item_id',op.ebay_item_id,'snapshot_event',stored_type,
    'snapshot_source','sourcing_review_api','raw_context_json',context,'captured_at',recorded_at,'created_at',recorded_at));
  insert into public.sourcing_listing_snapshots select snap.*;
  update public.sourcing_actions set listing_snapshot_id=snapshot_id where action_id=p_request_id;
  insert into public.matching_intelligence_examples(source_table,source_id,source_detail,source_weight,listing_snapshot_id,
    opportunity_id,candidate_id,action_id,asin,amazon_title,amazon_image_url,amazon_system,ebay_item_id,ebay_legacy_item_id,
    ebay_title,ebay_primary_image_url,ebay_item_specifics_json,ebay_condition,ebay_category,ebay_seller_username,operator_action,
    dismiss_reason,dismissal_note,match_label,label_type,confidence,evidence_strength,raw_context_json,reviewed_at)
  values('sourcing_actions',p_request_id::text,stored_type,case when p_label->>'label_type'='unknown' then 0 else 7 end,snapshot_id,
    op.opportunity_id,op.candidate_id,p_request_id,op.asin,snap.amazon_title,snap.amazon_image_url,snap.amazon_system,op.ebay_item_id,snap.ebay_legacy_item_id,
    snap.ebay_title,snap.ebay_primary_image_url,snap.ebay_item_specifics_json,snap.ebay_condition,snap.ebay_category,snap.seller_username,stored_type,
    p_reason,p_notes,p_label->>'match_label',p_label->>'label_type',1,'high',context,recorded_at);
  if p_action_type='block_asin' then
    insert into public.sourcing_blocked_asins(asin,reason,notes,source_opportunity_id,source_action_id,blocked_by,updated_at)
      values(op.asin,'asin_blocked',p_notes,op.opportunity_id,p_request_id,p_actor,recorded_at)
      on conflict(asin) do update set reason=excluded.reason,notes=excluded.notes,source_opportunity_id=excluded.source_opportunity_id,
        source_action_id=excluded.source_action_id,blocked_by=excluded.blocked_by,updated_at=excluded.updated_at;
  end if;
  if p_action_type='dismiss' and p_reason='sales_velocity_too_low' then
    select greatest(1,coalesce(sales_lookback_days,90)) into lookback from public.sourcing_settings order by created_at desc limit 1;
    lookback:=coalesce(lookback,90);
    select monthly_velocity into velocity from public.sourcing_seed_asins where seed_id=op.seed_id;
    required_velocity:=round(1 / greatest(lookback::numeric/30,1),4);
    insert into public.sourcing_sales_velocity_suppressions(asin,source_action_id,dismissed_at,velocity_at_dismissal,
      metric_window_days,required_velocity,current_velocity,status,last_evaluated_at,raw_context_json,updated_at)
    values(op.asin,p_request_id,recorded_at,velocity,lookback,required_velocity,velocity,'active',recorded_at,
      jsonb_build_object('opportunityId',op.opportunity_id,'sourcingRunId',op.sourcing_run_id,'seedId',op.seed_id),recorded_at)
    on conflict(asin) where status='active' do nothing; -- Existing hold/release conditions are immutable to feedback.
  end if;
  if p_action_type in ('dismiss','block_asin') then
    update public.sourcing_opportunities set status='dismissed',updated_at=recorded_at,latest_listing_snapshot_id=snapshot_id
      where asin=op.asin and (p_action_type='block_asin' or ebay_item_id=op.ebay_item_id)
        and status in ('open','rejected','watching','roi_snoozed','inventory_snoozed');
  end if;
  return jsonb_build_object('actionId',p_request_id,'snapshotId',snapshot_id,'replayed',false);
end $$;
revoke all on function public.sourcing_save_review(uuid,uuid,text,uuid,text,text,text,text,text,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.sourcing_save_review(uuid,uuid,text,uuid,text,text,text,text,text,jsonb,jsonb,jsonb) to service_role;

create function public.sourcing_latest_reviews(p_pairs jsonb) returns jsonb
language sql stable security invoker set search_path='' as $$
  select coalesce(jsonb_agg(jsonb_build_object('asin',p.asin,'ebayItemId',p.ebay_item_id,
    'feedback',a.raw_action_context->'matchingFeedback','actionId',a.action_id,'createdAt',a.created_at,
    'pairVerdict',v.raw_action_context->'matchingFeedback'->>'pairVerdict','verdictActionId',v.action_id,
    'corrections',coalesce(c.corrections,'[]'::jsonb))), '[]'::jsonb)
  from (select * from jsonb_to_recordset(p_pairs) as x(asin text,ebay_item_id text) limit 100) p
  left join lateral (select action_id,raw_action_context,created_at from public.sourcing_actions
    where asin=p.asin and ebay_item_id=p.ebay_item_id
      and raw_action_context->'matchingFeedback'->>'version'='matching_feedback_v3'
    order by created_at desc,action_id desc limit 1) a on true
  left join lateral (select action_id,raw_action_context from public.sourcing_actions
    where asin=p.asin and ebay_item_id=p.ebay_item_id
      and raw_action_context->'matchingFeedback'->>'version'='matching_feedback_v3'
      and raw_action_context->'matchingFeedback'->>'pairVerdict' in ('correct','incorrect','unsure')
    order by created_at desc,action_id desc limit 1) v on true
  left join lateral (
    select jsonb_agg(correction) corrections from (
      select distinct on (correction->>'side',correction->>'field',correction->>'scope')
        correction || jsonb_build_object('actionId',r.action_id,'recordedAt',r.created_at) correction
      from public.sourcing_actions r
      cross join lateral jsonb_array_elements(coalesce(r.raw_action_context->'matchingFeedback'->'corrections','[]'::jsonb)) correction
      where r.asin=p.asin and r.raw_action_context->'matchingFeedback'->>'version'='matching_feedback_v3'
        and (r.ebay_item_id=p.ebay_item_id or (correction->>'scope'='asin' and correction->>'side'='amazon'))
      order by correction->>'side',correction->>'field',correction->>'scope',r.created_at desc,r.action_id desc
    ) latest
  ) c on true;
$$;
revoke all on function public.sourcing_latest_reviews(jsonb) from public,anon,authenticated;
grant execute on function public.sourcing_latest_reviews(jsonb) to service_role;

