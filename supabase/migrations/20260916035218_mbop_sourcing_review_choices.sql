-- Explicit operator review destination. Existing parser diagnostics remain evidence.
-- No automatic promotion from parser feedback or historical matching examples.
create function public.sourcing_save_review_choice(
  p_opportunity_id uuid, p_request_id uuid, p_asin text, p_candidate_id uuid,
  p_action_type text, p_reason text, p_notes text, p_actor text,
  p_request_hash text, p_context jsonb, p_snapshot jsonb, p_label jsonb
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare
  op public.sourcing_opportunities%rowtype;
  prior public.sourcing_actions%rowtype;
  s jsonb; c jsonb; settings jsonb; checks jsonb; diag jsonb; result jsonb;
  choice text := p_context->'matchingFeedback'->>'queueChoice';
  evaluated timestamptz; fees numeric; sale numeric; cost numeric; cap numeric;
  item_price numeric; shipping numeric; offer numeric; kind text; decision jsonb;
begin
  if choice is null or choice not in ('keep_closest','move_buy_list') or
     p_action_type not in ('save_match_feedback','mark_valid_match') then
    raise exception 'Invalid review destination' using errcode='22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended(p_request_id::text,0));
  select * into prior from public.sourcing_actions where action_id=p_request_id;
  if found then
    -- Delegate fingerprint/actor validation to the existing append-only RPC.
    return public.sourcing_save_review(p_opportunity_id,p_request_id,p_asin,p_candidate_id,
      p_action_type,p_reason,p_notes,p_actor,p_request_hash,p_context,p_snapshot,p_label)
      || jsonb_build_object('queueChoice',choice);
  end if;
  perform pg_advisory_xact_lock(hashtextextended('identity-review-asin|'||p_asin,0));
  lock table public.sourcing_opportunities in exclusive mode nowait;
  lock table public.sourcing_actions,public.sourcing_ebay_candidates,public.sourcing_seed_asins,
    public.sourcing_settings,public.sourcing_blocked_asins,public.sourcing_sales_velocity_suppressions,
    public.sourcing_declined_ebay_offers,public.purchase_items,public.fba_shipment_items,public.fba_shipments
    in share row exclusive mode nowait;
  select * into op from public.sourcing_opportunities where opportunity_id=p_opportunity_id;
  s:=public.sourcing_decision_guard_state(p_opportunity_id);
  if s is null or p_context->>'reviewGuardHash' is distinct from public.sourcing_guard_hash(s) then
    raise exception 'Opportunity, review or business inputs changed. Reload before saving.' using errcode='40001';
  end if;
  if op.status is distinct from 'rejected' and not coalesce(op.status='open'
    and op.matching_diagnostics_json->'presentationDecision'->>'eligible'='false',false) then
    raise exception 'Only an excluded opportunity can use this review destination.' using errcode='22023';
  end if;
  if choice='move_buy_list' then
    if p_context->'matchingFeedback'->>'pairVerdict' is distinct from 'correct' then
      raise exception 'Confirm this exact product pair before moving to Buy List.' using errcode='22023';
    end if;
    if s->'blockedAsin'<>'null'::jsonb or s->'velocityHolds'<>'[]'::jsonb
      or public.sourcing_guard_active_hold(s,'open') is not null then
      raise exception 'An ASIN block or business hold prevents Buy List admission.' using errcode='22023';
    end if;
    if exists(select 1 from jsonb_array_elements(s->'pairHistory') h where h->>'status' not in ('open','rejected')) then
      raise exception 'This pair has protected lifecycle history. It cannot be reopened here.' using errcode='22023';
    end if;
    if exists(select 1 from public.sourcing_opportunities o where o.asin=op.asin and o.status='open' and o.opportunity_id<>op.opportunity_id) then
      raise exception 'This ASIN already has a Buy List opportunity. Review it before adding another.' using errcode='22023';
    end if;
    diag:=op.matching_diagnostics_json; c:=s->'candidate';
    checks:=diag->'businessEligibilityChecks';
    if jsonb_typeof(checks) is distinct from 'array' or jsonb_array_length(checks)<3 or
      exists(select 1 from jsonb_array_elements(checks) x where x->>'result' is distinct from 'pass' or x->>'blocking'='true') or
      (select count(distinct x->>'code') from jsonb_array_elements(checks) x where x->>'code' in ('shipping','minimum_profit','minimum_roi'))<>3 then
      raise exception 'Profitability or business checks do not pass. Save and keep in Closest Excluded.' using errcode='22023';
    end if;
    if exists(select 1 from jsonb_each(diag) x where x.key in ('condition_mismatch','region','delivery','location') and x.value->>'result'='fail') then
      raise exception 'Condition, region or delivery restrictions prevent promotion.' using errcode='22023';
    end if;
    evaluated:=(diag->'canonicalDecision'->>'evaluatedAt')::timestamptz;
    if evaluated is null or evaluated < now()-interval '48 hours' or
      (c->>'last_seen_at')::timestamptz>evaluated or lower(coalesce(c->>'listing_status','')) not in ('active','live') or
      coalesce((c->>'available_quantity')::numeric,0)<=0 or
      (c->>'auction_end_time')::timestamptz<=now() then
      raise exception 'Listing evaluation is stale or unavailable. Refresh sourcing before promotion.' using errcode='22023';
    end if;
    select value into settings from jsonb_array_elements(s->'settings') order by value->>'created_at' desc limit 1;
    if settings is null or coalesce(settings->>'min_profit_dollars','')='' or coalesce(settings->>'min_roi_percent','')='' then
      raise exception 'Profitability settings unavailable.' using errcode='22023';
    end if;
    item_price:=(c->>'price')::numeric; shipping:=(c->>'shipping_cost')::numeric;
    sale:=op.target_sale_price; fees:=(diag->'pricing_reference'->>'estimated_fees')::numeric;
    cost:=item_price+shipping;
    if item_price is null or item_price<=0 or shipping is null or shipping<0 or sale is null or sale<=0 or fees is null or fees<0
      or cost is distinct from op.landed_cost then
      raise exception 'Current pricing does not match the recorded evaluation. Refresh sourcing.' using errcode='22023';
    end if;
    cap:=round(least(greatest(sale-fees-(settings->>'min_profit_dollars')::numeric,0),
      greatest((sale-fees)/(1+(settings->>'min_roi_percent')::numeric/100),0)),2);
    -- Same item-only offer floor and full-shipping reservation as suggested_offer.
    if c->'buying_options' ? 'AUCTION' then
      if cost<=cap then kind:='auction'; end if;
    else
      if c->>'best_offer_enabled'='true' then
        offer:=round(least(greatest(cap-shipping,0),item_price*0.95),2);
        if offer<item_price-0.009 and offer>=item_price*coalesce((settings->>'best_offer_min_ask_percent')::numeric,60)/100 then kind:='best_offer'; end if;
      end if;
      if kind is null and cost<=cap then kind:=case when (c->>'available_quantity')::numeric>1 then 'multi_unit' else 'buy_now' end; end if;
    end if;
    if kind is null then raise exception 'Profitability is below the configured threshold. Keep this opportunity in Closest Excluded.' using errcode='22023'; end if;
    if kind='best_offer' and exists(select 1 from jsonb_array_elements(s->'declinedOffers') d where offer<=(d->>'declined_offer_amount')::numeric) then
      raise exception 'Seller already declined this profitable offer level.' using errcode='22023';
    end if;
    decision:=jsonb_build_object('eligible',true,'finalStatus','open','finalOpportunityType',kind,
      'finalRecommendation','Match','ruleVersion','operator_pair_promotion_v1','evaluatedAt',clock_timestamp(),
      'primaryReason',null,'secondaryReasons','[]'::jsonb);
  end if;
  -- Feedback, source snapshot and promotion either all commit or all roll back.
  p_context:=p_context||jsonb_build_object('reviewRouting',jsonb_build_object(
    'beforeStatus',op.status,'afterStatus',case when choice='move_buy_list' then 'open' else op.status end,
    'opportunityType',kind,'profitabilityOverride',false));
  result:=public.sourcing_save_review(p_opportunity_id,p_request_id,p_asin,p_candidate_id,
    p_action_type,p_reason,p_notes,p_actor,p_request_hash,p_context,p_snapshot,p_label);
  if choice='move_buy_list' then
    diag:=diag||jsonb_build_object('operatorIdentityOverride',jsonb_build_object('actionId',p_request_id,
      'scope','exact_pair','asin',op.asin,'ebayItemId',op.ebay_item_id,'parserAssessment',p_context->'matchingFeedback'->'parserAssessment',
      'originalPresentationDecision',diag->'presentationDecision'),
      'recommendation','Match','presentationDecision',decision,
      'canonicalDecision',coalesce(diag->'canonicalDecision','{}')||jsonb_build_object('productIdentityVerdict','match',
        'businessEligibility','eligible','lifecycleStatus','open','presentationDecision',decision));
    update public.sourcing_opportunities set status='open',opportunity_type=kind,matching_diagnostics_json=diag,
      max_profitable_landed_cost=cap,max_offer_price=case when kind='best_offer' then offer else null end,
      required_offer_percent_of_ask=case when kind='best_offer' then round(offer/item_price*100,1) else null end,
      max_bid=case when kind='auction' then greatest(cap-shipping,0) else null end,
      latest_listing_snapshot_id=(result->>'snapshotId')::uuid,updated_at=clock_timestamp()
      where opportunity_id=p_opportunity_id;
  end if;
  return result||jsonb_build_object('queueChoice',choice,'opportunityType',kind);
end $$;
revoke all on function public.sourcing_save_review_choice(uuid,uuid,text,uuid,text,text,text,text,text,jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.sourcing_save_review_choice(uuid,uuid,text,uuid,text,text,text,text,text,jsonb,jsonb,jsonb) to service_role;
