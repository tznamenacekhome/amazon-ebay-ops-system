// Set MBOP_REVIEW_TEST_CONTAINER to a disposable PostgreSQL container with the
// MBOP test schema + review migration. Never connects to a remote database.
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import ts from 'typescript';
const require=createRequire(import.meta.url),root=dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1'));
const container=process.env.MBOP_REVIEW_TEST_CONTAINER;
const sql=q=>execFileSync('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],{input:q,encoding:'utf8'}).trim();
const quote=v=>v===null||v===undefined?'null':"'"+String(typeof v==='object'?JSON.stringify(v):v).replaceAll("'","''")+"'";
let failLabel=false,authFail=false;
const rpc=async(name,args)=>{
  if(!container)throw new Error('Set MBOP_REVIEW_TEST_CONTAINER to the disposable local test container');
  try{
    if(failLabel&&name==='sourcing_save_review')args.p_label={match_label:'invalid',label_type:'unknown'};
    const query=`select public.${name}(${Object.entries(args).map(([k,v])=>k+'=>'+quote(v)).join(',')});`;
    return {data:JSON.parse(sql(query)),error:null};
  }catch(e){return {data:null,error:{message:String(e.stderr??e),code:String(e.stderr).includes('identity changed')?'40001':'23514'}};}
};
const db={rpc,from:()=>({select:()=>({eq:()=>({single:async()=>({data:op,error:null})})})})};
const cache=new Map();
function load(file){
  file=resolve(file);if(cache.has(file))return cache.get(file);
  const out={};cache.set(file,out);
  const js=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  new Function('require','exports',js)(name=>{
    if(name==='next/server')return {NextResponse:{json:(body,opts)=>({body,status:opts?.status??200})}};
    if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db};
    if(name.endsWith('/_server'))return {requireAdminApiToken:()=>authFail?{status:401}:null};
    if(name.startsWith('.')){let next=resolve(dirname(file),name+'.ts');if(!existsSync(next))next=resolve(dirname(file),name+'.tsx');return load(next);}
    return require(name);
  },out);return out;
}
const feedback=load(resolve(root,'matchingFeedback.ts'));
const normalized=feedback.normalizeMatchingFeedback({version:'matching_feedback_v3',allAssumptionsCorrect:true,pairVerdict:'incorrect',evidenceSources:['primary_image']});
assert.deepEqual(normalized.evidenceSources,['primary_image']);assert.equal(normalized.pairVerdict,'incorrect');
assert.equal(feedback.reviewSemantics('dismiss','roi_too_low','not_provided').label.label_type,'business_issue');
assert.equal(feedback.reviewSemantics('confirm_exclusion',null,'not_provided').label.label_type,'unknown');
assert.throws(()=>feedback.normalizeCorrections([{field:'edition',side:'ebay',scope:'asin',state:'unknown'}]));
const {businessExclusion}=load(resolve(root,'businessExclusion.ts'));
const hold={status:'active',current_velocity:null,required_velocity:1,last_evaluated_at:null};
const unknown={status:'open',matching_diagnostics_json:{recommendation:'Probable Match'}};
assert.equal(businessExclusion(unknown,undefined,hold),null);
const confirmed={pairVerdict:'correct'};
assert(businessExclusion(unknown,confirmed,hold).summary.includes('Data unavailable'));
assert.equal(businessExclusion({...unknown,status:'dismissed'},confirmed,hold),null);
assert.equal(businessExclusion(unknown,{pairVerdict:'incorrect'},hold),null);
assert.equal(businessExclusion(unknown,confirmed),null);
const positive={...unknown,asin:'TEST',sourcing_seed_asins:{asin:'TEST'},matching_diagnostics_json:{static_rules:{identity_comparison:{evidenceDecision:{productIdentityVerdict:'match'}}},businessEligibilityChecks:[{code:'roi',label:'ROI',actual:18,threshold:30,units:'%',result:'fail',blocking:true,scenario:'asking price',source:'scorer',evaluatedAt:'2026-09-12'}]}};
assert(businessExclusion(positive,undefined));
assert.equal(businessExclusion({...positive,asin:'OTHER'},undefined),null,'Stale ASIN metadata cannot certify identity');
assert.equal(businessExclusion({...positive,matching_diagnostics_json:{...positive.matching_diagnostics_json,businessEligibilityChecks:[{...positive.matching_diagnostics_json.businessEligibilityChecks[0],blocking:false,scenario:'best_offer'}]}},undefined),null);
console.log('Review normalization and Business Excluded contracts passed');
if(!container){console.log('Local PostgreSQL integration skipped (container not supplied)');process.exit(0);}
const id=randomUUID(),candidate=randomUUID();
let op={opportunity_id:id,candidate_id:candidate,asin:'B000TEST01',ebay_item_id:'v1|123|456',status:'open',opportunity_type:'buy_now',sourcing_seed_asins:{asin:'B000TEST01',amazon_title:'Test'},sourcing_ebay_candidates:{ebay_item_id:'v1|123|456',ebay_title:'Test'}};
sql(`insert into public.sourcing_opportunities(opportunity_id,candidate_id,asin,ebay_item_id,status,opportunity_type) values(${quote(id)},${quote(candidate)},'B000TEST01','v1|123|456','open','buy_now'); insert into public.sourcing_blocked_asins(asin) values('B000TEST01') on conflict do nothing;`);
const route=load(resolve(root,'opportunities/[id]/actions/route.ts'));
const post=body=>route.POST({headers:new Headers(),json:async()=>body},{params:Promise.resolve({id})});
const body={actionType:'mark_valid_match',requestId:randomUUID(),expectedAsin:op.asin,expectedEbayItemId:op.ebay_item_id,expectedCandidateId:candidate,expectedEvaluationId:null,sourceTab:'Closest Excluded',diagnosticsFeedback:{version:'matching_feedback_v3',pairVerdict:'correct',failedRuleFamilies:['edition_version'],evidenceSources:['ebay_game_name'],corrections:[{field:'edition',side:'amazon',scope:'asin',state:'unknown',value:null}]}};
authFail=true;assert.equal((await post(body)).status,401);authFail=false;
assert.equal((await post({...body,expectedAsin:'STALE'})).status,409);
assert.equal((await post({...body,actionType:'confirm_exclusion'})).status,400);
let result=await post(body);assert.equal(result.status,200,JSON.stringify(result));
assert.equal(result.body.review.replayed,false);
assert.equal((await post(body)).body.review.replayed,true);
assert.equal(Number(sql(`select count(*) from public.sourcing_actions where action_id=${quote(body.requestId)}`)),1);
assert.equal(sql(`select status from public.sourcing_opportunities where opportunity_id=${quote(id)}`),'open');
assert.equal(Number(sql("select count(*) from public.sourcing_blocked_asins where asin='B000TEST01'")),1);
assert.equal((await post({...body,notes:'different'})).status,500);
failLabel=true;const failedId=randomUUID();assert.equal((await post({...body,requestId:failedId})).status,500);failLabel=false;
assert.equal(Number(sql(`select count(*) from public.sourcing_actions where action_id=${quote(failedId)}`)),0);
assert.equal(Number(sql(`select count(*) from public.sourcing_listing_snapshots where action_id=${quote(failedId)}`)),0);
result=await rpc('sourcing_latest_reviews',{p_pairs:[{asin:op.asin,ebay_item_id:op.ebay_item_id}]});
assert.equal(result.data[0].pairVerdict,'correct');assert.equal(result.data[0].feedback.corrections[0].state,'unknown');
const sibling=await rpc('sourcing_latest_reviews',{p_pairs:[{asin:op.asin,ebay_item_id:'v1|another|variant'}]});
assert.equal(sibling.data[0].pairVerdict,null);assert.equal(sibling.data[0].corrections[0].scope,'asin');
assert.deepEqual(result.data[0].feedback.evidenceSources,['ebay_game_name']);
const unsure={...body,requestId:randomUUID(),actionType:'save_match_feedback',diagnosticsFeedback:{version:'matching_feedback_v3',pairVerdict:'unsure'}};
assert.equal((await post(unsure)).status,200);
result=await rpc('sourcing_latest_reviews',{p_pairs:[{asin:op.asin,ebay_item_id:op.ebay_item_id}]});assert.equal(result.data[0].pairVerdict,'unsure');
sql(`update public.sourcing_opportunities set status='purchased_pending_match' where opportunity_id=${quote(id)}`);
assert.equal((await post({...body,requestId:randomUUID(),actionType:'dismiss',reason:'wrong_product'})).status,200);
assert.equal(sql(`select status from public.sourcing_opportunities where opportunity_id=${quote(id)}`),'purchased_pending_match');
const persisted=sql(`select jsonb_agg(to_jsonb(a)) from public.sourcing_actions a where opportunity_id=${quote(id)}`);
const analyzerCode=`import sys,json;sys.path.insert(0,${JSON.stringify(resolve(root,'../../../../integrations')).replaceAll('\\','/')});from analyze_matching_feedback import summarize_feedback_rows;print(json.dumps(summarize_feedback_rows(json.load(sys.stdin))))`;
const analyzed=JSON.parse(execFileSync(resolve(root,'../../../../.venv/Scripts/python.exe'),['-c',analyzerCode],{input:persisted,encoding:'utf8'}));
assert.equal(analyzed.pair_verdict_counts.correct,1);assert.equal(analyzed.pair_verdict_counts.unsure,1);assert.equal(analyzed.pair_verdict_counts.incorrect,1);
assert(analyzed.correction_count>=1);assert.equal(analyzed.evidence_provenance_counts.explicit,3);
console.log('Actual action API → PostgreSQL → reload passed: auth, stale pair, blocked-ASIN positive, correction, unknown, idempotency, full rollback, protected purchase');
console.log('Persisted API review actions also survive the actual Python analyzer with distinct positive, negative, unsure and correction evidence.');
