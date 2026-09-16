"""Run only against the network-disabled disposable review database."""
import json,subprocess
from uuid import uuid4
DB='mbop-review-choice-test'
assert subprocess.check_output(['docker','inspect',DB,'--format','{{.HostConfig.NetworkMode}}'],text=True).strip()=='none'
def sql(q):
 r=subprocess.run(['docker','exec','-i',DB,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],input=q,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stderr)
 return r.stdout.strip()
def q(x):return "'"+str(json.dumps(x) if isinstance(x,(dict,list)) else x).replace("'","''")+"'"
sql('insert into sourcing_settings default values;')
def seed(price=70,best=False):
 o,c,s,e=[str(uuid4()) for _ in range(4)];asin='T'+uuid4().hex[:9];item='v1|'+str(uuid4().int % 900000000000 + 100000000000)+'|0'
 checks=[{'code':k,'result':'pass','blocking':False} for k in ['shipping','minimum_profit','minimum_roi']]
 d={'canonicalDecision':{'evaluationId':e,'evaluatedAt':'2026-01-01'},'recommendation':'Review','businessEligibilityChecks':checks,'pricing_reference':{'estimated_fees':35.81},'static_rules':{'recommendation':'Review','identity_comparison':{'reason':'Seller states Complete Edition','evidenceDecision':{'productIdentityVerdict':'needs_review'}}}}
 sql(f"insert into sourcing_seed_asins(seed_id,asin,source_mode) values({q(s)},{q(asin)},'recent_sales');insert into sourcing_ebay_candidates(candidate_id,seed_id,asin,ebay_item_id,price,shipping_cost,available_quantity,listing_status,best_offer_enabled) values({q(c)},{q(s)},{q(asin)},{q(item)},{price},8.60,1,'active',{str(best).lower()});insert into sourcing_opportunities(opportunity_id,candidate_id,seed_id,asin,ebay_item_id,status,opportunity_type,landed_cost,target_sale_price,matching_diagnostics_json) values({q(o)},{q(c)},{q(s)},{q(asin)},{q(item)},'rejected','no_profitable_source_found',{price+8.6},144.59,{q(d)});update sourcing_opportunities set matching_diagnostics_json=jsonb_set(matching_diagnostics_json,'{{canonicalDecision,evaluatedAt}}',to_jsonb(clock_timestamp())) where opportunity_id={q(o)};")
 return {'o':o,'c':c,'s':s,'asin':asin,'item':item,'e':e}
def body(r,choice='move_buy_list',verdict='correct'):
 h=sql(f"select sourcing_guard_hash(sourcing_decision_guard_state({q(r['o'])}))")
 ctx={'reviewGuardHash':h,'pair':{'ebayItemId':r['item']},'evaluation':{'id':r['e']},'matchingFeedback':{'version':'matching_feedback_v3','pairVerdict':verdict,'parserAssessment':'correct','sourceAccuracy':'listing_error','queueChoice':choice,'corrections':[]}}
 request=str(uuid4());return [r['o'],request,r['asin'],r['c'],'mark_valid_match' if choice=='move_buy_list' else 'save_match_feedback',None,'Seller supplied wrong edition','test-operator',request,ctx,{}, {'match_label':'match' if verdict=='correct' else 'needs_review','label_type':'positive_identity' if verdict=='correct' else 'unknown'}]
def save(b):return json.loads(sql('select sourcing_save_review_choice('+','.join('null' if x is None else q(x) for x in b)+');'))
def fail(b,part):
 before=sql('select count(*) from sourcing_actions')
 try:save(b);raise AssertionError('Unexpected save')
 except RuntimeError as e:assert part.lower() in str(e).lower(),str(e)
 assert before==sql('select count(*) from sourcing_actions'),'Failed transaction recorded feedback'
r=seed(best=True);b=body(r);a=save(b);assert a['opportunityType']=='best_offer';assert save(b)['replayed'];assert sql(f"select count(*) from sourcing_actions where action_id={q(b[1])}")=='1'
assert sql(f"select matching_diagnostics_json->'static_rules'->>'recommendation' from sourcing_opportunities where opportunity_id={q(r['o'])}")=='Review','Parser decision must remain intact'
r=seed(50);assert save(body(r))['opportunityType']=='buy_now'
r=seed(90);b=body(r,'keep_closest');save(b);assert sql(f"select status from sourcing_opportunities where opportunity_id={q(r['o'])}")=='rejected';assert json.loads(sql(f"select sourcing_latest_reviews({q([{'asin':r['asin'],'ebay_item_id':r['item']}])})"))[0]['feedback']['queueChoice']=='keep_closest'
r=seed(90);fail(body(r),'profitability')
r=seed(50);fail(body(r,verdict='unsure'),'Confirm this exact')
r=seed(50);b=body(r);sql(f"update sourcing_ebay_candidates set price=51 where candidate_id={q(r['c'])}");fail(b,'changed')
r=seed(50);b=body(r);sql(f"insert into sourcing_actions(asin,ebay_item_id,action_type) values({q(r['asin'])},{q(r['item'])},'matching_feedback')");fail(b,'changed')
r=seed(50);sql(f"insert into sourcing_blocked_asins(asin) values({q(r['asin'])})");fail(body(r),'business hold')
r=seed(50);sql(f"update sourcing_opportunities set status='purchased' where opportunity_id={q(r['o'])}");fail(body(r),'Only an excluded')
r=seed(50);sql(f"update sourcing_ebay_candidates set listing_status='ended' where candidate_id={q(r['c'])}");fail(body(r),'unavailable')
r=seed(50);sql(f"update sourcing_opportunities set matching_diagnostics_json=jsonb_set(matching_diagnostics_json,'{{businessEligibilityChecks,0,result}}','\"unknown\"') where opportunity_id={q(r['o'])}");fail(body(r),'business checks')
r=seed(best=True);sql(f"insert into sourcing_declined_ebay_offers(ebay_legacy_item_id,declined_offer_amount) values({q(r['item'].split('|')[1])},100)");fail(body(r),'declined')
print('Atomic scenarios passed: keep, buy, offer, independent parser/source evidence, replay, profitability, unsure, source/review staleness, block, lifecycle, availability, unknown shipping, declined offer; failures roll back.')

r=seed(50);b=body(r);save(b);changed=list(b);changed[8]='different-fingerprint';fail(changed,'different feedback')
r=seed(50);b=body(r);sql("update sourcing_settings set min_roi_percent=200");fail(b,'changed');fail(body(r),'Profitability')
sql("update sourcing_settings set min_roi_percent=40")
r=seed(50);sql(f"update sourcing_opportunities set matching_diagnostics_json=jsonb_set(matching_diagnostics_json,'{{condition_mismatch}}','{{\"result\":\"fail\"}}') where opportunity_id={q(r['o'])}");fail(body(r),'Condition')
print('Additional checks passed: conflicting retry, changed/current thresholds, condition restrictions.')
