import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),root=dirname(fileURLToPath(import.meta.url));
const rows=Array.from({length:53},(_,i)=>({opportunity_id:`opp-${i}`,candidate_id:`candidate-${i}`,asin:`ASIN${i}`,ebay_item_id:`listing-${i}`,status:'rejected',opportunity_type:'review',score:100-i,profit:i===51?-1:10,matching_diagnostics_json:i===52?{hard_blocks:['wrong platform']}:{recommendation:'Review'},sourcing_seed_asins:{asin:`ASIN${i}`,amazon_title:'Game',source_mode:'recent_sales',raw_context_json:{inferred_system:'PS 3'}},sourcing_ebay_candidates:{ebay_item_id:`listing-${i}`,ebay_title:'Game listing',listing_status:'active',display_price:{currency:'USD'},display_shipping:[]}}));
let reviews=[];
let priorRows=[];
let listingActions=[];
let flipmineRows=[];
let compactDiagnostics=false;
const cycles=[{coverage_cycle_id:'cycle-2',cycle_number:2,status:'completed',started_at:'2026-10-15T00:00:00Z'}];
const db={rpc:async()=>({data:reviews,error:null}),from(table){
 let selection='',filters=[];
 const query=new Proxy({}, {get(_,method){
  if(method==='then')return done=>{
   let data=table==='sourcing_opportunities'?(selection.includes('sourcing_runs!inner')?priorRows:rows):
     table==='sourcing_coverage_cycles'?cycles:table==='sourcing_runs'?[{sourcing_run_id:'run-2',coverage_cycle_id:'cycle-2'}]:
     table==='sourcing_actions'?(listingActions.length?listingActions:reviews.length?[{opportunity_id:'opp-0',action_type:'matching_feedback'}]:[]):table==='sourcing_flipmine_rows'?flipmineRows:[];
   if(table==='sourcing_opportunities') for(const [method,column,value] of filters) {
    if(method==='eq'&&column==='status')data=data.filter(row=>row.status===value);
    if(method==='in'&&column==='opportunity_id')data=data.filter(row=>value.includes(row.opportunity_id));
   }
   if(selection.includes('sourcing_runs!inner')) {
    assert(filters.some(([method,column])=>method==='lt'&&column==='sourcing_runs.started_at'));
    assert(filters.some(([method,column])=>method==='neq'&&column==='sourcing_runs.coverage_cycle_id'));
   }
   if(compactDiagnostics&&table==='sourcing_opportunities'&&selection.includes('matching_diagnostics_json:sourcing_list_diagnostics')) {
    assert(selection.includes('edition_policy_version:'),'Compact qualification must request the narrow policy marker');
    data=data.map(row=>{
     const d=row.matching_diagnostics_json??{},identity=d.static_rules?.identity_comparison??{};
     return {...row,edition_policy_version:identity.comparisons?.edition?.policy?.version??null,
      matching_diagnostics_json:{recommendation:d.recommendation,businessEligibilityChecks:d.businessEligibilityChecks,
       presentationDecision:d.presentationDecision,decisionTrace:d.decisionTrace,
       static_rules:{hard_blocks:d.static_rules?.hard_blocks,identity_comparison:{evidenceDecision:identity.evidenceDecision}}}};
    });
   }
   return Promise.resolve(done({data,error:null}));
  };
  return (...args)=>{if(method==='select')selection=args[0];else filters.push([method,...args]);return query;};
 }});return query;
}};
const modules=new Map();function load(file){file=resolve(file);if(modules.has(file))return modules.get(file);const out={};modules.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name==='next/server')return {NextResponse:{json:(body,init)=>({body,json:async()=>body,ok:!init?.status||init.status<400,status:init?.status??200,headers:new Headers()})}};
 if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db,toNumber:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d};
 // Exercise actual list building without the independent server-cache layer.
 if(name==='../readCache')return {cachedSourcingList:async(_key,_fresh,build)=>({body:await build(),hit:false})};
 if(name.endsWith('.json')){const value=JSON.parse(readFileSync(resolve(dirname(file),name),'utf8'));return {default:value,...value};}
 if(name.startsWith('.'))return load(resolve(dirname(file),name+'.ts'));return require(name);
},out);return out;}
const route=load(resolve(root,'opportunities/route.ts'));
const get=reason=>route.GET({url:`https://example.test/api/sourcing/opportunities?status=all&scope=closest_excluded&format=list&limit=50&exclusionReason=${reason}`});
const all=await get('all');assert.equal(all.status,200,JSON.stringify(all.body));assert.equal(all.body.opportunities.length,50);assert.equal(all.body.summary.total,53);
const profit=await get('profitability');assert.equal(profit.body.summary.total,1);assert.equal(profit.body.opportunities[0].opportunityId,'opp-51','Find a match beyond first 50');
const review=await get('review_threshold');assert.equal(review.body.summary.total,51);assert.equal(review.body.opportunities.length,50);
assert(profit.body.exclusionOptions.some(o=>o.code==='wrong_platform'&&o.count===1));
const platform=await get('wrong_platform');assert.equal(platform.body.opportunities[0].opportunityId,'opp-52');
const empty=await get('absent');assert.equal(empty.body.summary.total,0);assert.equal(empty.body.opportunities.length,0);
console.log('Actual Closest Excluded GET: full-set filtering before limit, reason counts, review/profitability/other/all/empty passed');

reviews=[{asin:'ASIN0',ebayItemId:'listing-0',actionId:'saved',pairVerdict:'correct',feedback:{queueChoice:'keep_closest',parserAssessment:'correct',sourceAccuracy:'listing_error'}}];
assert.equal((await get('all')).body.summary.total,53,'Confirmed kept pair must remain in Closest Excluded');
assert.equal((await get('all')).body.opportunities[0].latestReview.feedback.parserAssessment,'correct');
reviews[0].feedback.queueChoice='move_buy_list';
assert.equal((await get('all')).body.summary.total,52,'Promoted pair is removed from Closest Excluded');
reviews[0].feedback={};
assert.equal((await get('all')).body.summary.total,52,'Legacy review behavior is preserved');
console.log('Explicit keep survives confirmation and reload; move leaves Closest; legacy behavior retained');

reviews=[];
const specificReason='Unresolved identity detail on one side: edition';
rows[0].matching_diagnostics_json={recommendation:'Review',presentationDecision:{eligible:false,finalRecommendation:'Review',primaryReason:{code:'review_threshold',label:'Review threshold',summary:'Final matching recommendation required review and did not enter presentation.',severity:'review_threshold'}},decisionTrace:[
 {stage:'Video game identity',diagnosticKey:'core_game_identity',result:'warning',summary:specificReason},
 {stage:'Final recommendation',diagnosticKey:'final_recommendation',result:'warning',summary:'Final recommendation is Review.'},
 {stage:'Presentation gate',diagnosticKey:'opportunity_context',result:'fail',summary:'Opportunity type is no_profitable_source_found.'},
]};
let reason=(await get('review_threshold')).body.opportunities[0].exclusionReason;
assert.equal(reason.summary,specificReason);assert.equal(reason.label,'Video game identity');assert.equal(reason.code,'review_threshold');assert.equal(reason.source,'decision_trace');
assert.deepEqual(reason.diagnosticKeys,['core_game_identity']);
rows[0].matching_diagnostics_json.decisionTrace.push({stage:'Package contents',diagnosticKey:'package_contents',result:'warning',summary:'Package contents unresolved'});
reason=(await get('review_threshold')).body.opportunities[0].exclusionReason;
assert.equal(reason.summary,`${specificReason}; Package contents unresolved`);
delete rows[0].matching_diagnostics_json.presentationDecision;
assert.equal((await get('review_threshold')).body.opportunities[0].exclusionReason.summary,reason.summary,'Legacy fallback also uses actual trace');
rows[0].matching_diagnostics_json.decisionTrace=[];
assert((await get('review_threshold')).body.opportunities[0].exclusionReason.summary.includes('did not record a specific matching reason'));
assert.equal((await get('profitability')).body.opportunities[0].exclusionReason.code,'profitability');
console.log('Specific saved review reasons replace generic gate text; multiple reasons, legacy/missing trace and category filters preserved');

// The same pair gets a new opportunity ID in each cycle. Suppress that pair,
// while keeping another ASIN for the same listing and another listing for the ASIN.
priorRows=[{opportunity_id:'old-pair',asin:'ASIN1',sourcing_ebay_candidates:{ebay_item_id:'listing-1'}},
 {opportunity_id:'different-asin',asin:'OTHER',sourcing_ebay_candidates:{ebay_item_id:'listing-2'}},
 {opportunity_id:'different-listing',asin:'ASIN3',sourcing_ebay_candidates:{ebay_item_id:'another-listing'}}];
const cycleResult=await route.GET({url:'https://example.test/api/sourcing/opportunities?status=all&scope=closest_excluded&format=list&limit=50&coverageCycleId=cycle-2'});
assert.equal(cycleResult.status,200,JSON.stringify(cycleResult.body));
assert.equal(cycleResult.body.summary.total,52);
assert(!cycleResult.body.opportunities.some(row=>row.opportunityId==='opp-1'));
assert(cycleResult.body.opportunities.some(row=>row.opportunityId==='opp-2'));
assert(cycleResult.body.opportunities.some(row=>row.opportunityId==='opp-3'));
assert.equal((await get('all')).body.summary.total,53,'Latest runs retain their existing behavior');
priorRows=[];
rows[0].matching_diagnostics_json={hard_blocks:['game name mismatch'],static_rules:{identity_comparison:{amazon:{coreGame:'Blazing Angels 2'},ebay:{coreGame:'Blazing Angels'},evidenceDecision:{comparisons:{coreGame:{result:'conflict',reason:'Different installment'}}}}}};
const identityReason=(await get('game_name_conflict')).body.opportunities.find(row=>row.opportunityId==='opp-0').exclusionReason;
assert(identityReason.summary.includes('Amazon Blazing Angels 2; eBay Blazing Angels'));
assert(identityReason.summary.includes('Different installment'));
console.log('Prior-cycle pair suppression before counts/limit, pair identity boundaries, latest-run behavior and specific mismatch evidence passed');

for (const row of rows.slice(0,2)) {
 row.ebay_item_id='v1|287652912629|0';
 row.sourcing_ebay_candidates.ebay_item_id=row.ebay_item_id;
}
listingActions=[{asin:'ASIN0',ebay_item_id:'v1|287652912629|0',action_type:'purchased',created_at:'2026-10-18T00:00:00Z',action_id:'purchase'}];
const actioned=await get('all');
assert.equal(actioned.status,200,JSON.stringify(actioned.body));
assert.equal(actioned.body.summary.total,51,'Actioned listings are removed before summary and row limit');
assert(!actioned.body.opportunities.some(row=>['opp-0','opp-1'].includes(row.opportunityId)),'A purchase hides duplicate ASIN candidates without relabeling either record');
assert.equal(rows[1].status,'rejected','Presentation suppression must not alter stored lifecycle status');
console.log('Actual GET suppresses purchased duplicate listings before counts/limits without mutating lifecycle status.');

listingActions=[];reviews=[];
rows[4].status='open';rows[4].matching_diagnostics_json={hard_rule_pass:true,recommendation:'Strong Match'};
rows[4].sourcing_ebay_candidates.source_tags=['normal-source','flipmine'];
rows[5].sourcing_ebay_candidates.source_tags=['flipmine'];
flipmineRows=[{opportunity_id:'opp-4'},{opportunity_id:'opp-5'}];
const buyFM=await route.GET({url:'https://example.test/api/sourcing/opportunities?scope=all_open&status=open&sourceMode=flipmine&limit=250'});
assert.equal(buyFM.status,200,JSON.stringify(buyFM.body));assert.equal(buyFM.body.summary.total,1);
assert.equal(buyFM.body.opportunities[0].opportunityId,'opp-4');
assert.deepEqual(buyFM.body.opportunities[0].sourceTags,['normal-source','flipmine']);
const closestFM=await route.GET({url:'https://example.test/api/sourcing/opportunities?scope=closest_excluded&status=all&sourceMode=flipmine&limit=250'});
assert.equal(closestFM.status,200,JSON.stringify(closestFM.body));assert.equal(closestFM.body.summary.total,1);
assert.equal(closestFM.body.opportunities[0].opportunityId,'opp-5');
console.log('Flipmine uses normal Buy List / Closest Excluded gates and retains existing provenance.');

const editionDiagnostics=code=>({recommendation:'Review',static_rules:{identity_comparison:{comparisons:{edition:{result:'review',amazon:'Deluxe Edition',ebay:null,policy:{version:'sourcing_edition_policy_v1',code}}}}},businessEligibilityChecks:['shipping','minimum_profit','minimum_roi'].map(code=>({code,result:'pass',blocking:false})),presentationDecision:{eligible:false,finalRecommendation:'Review',finalStatus:'rejected',primaryReason:{code,label:code==='contents_not_corroborated'?'Required contents not corroborated':'Edition not corroborated',summary:code==='contents_not_corroborated'?"Collector's Edition or required contents not corroborated.":'Deluxe Edition not corroborated.',source:'matching_diagnostics',severity:'review_threshold',category:'review_threshold',diagnosticKeys:['edition_version']},secondaryReasons:[]}});
const fmEdition=()=>route.GET({url:'https://example.test/api/sourcing/opportunities?scope=closest_excluded&status=all&sourceMode=flipmine&format=list&limit=250'});
for(const code of ['edition_not_corroborated','contents_not_corroborated']){
 rows[5].matching_diagnostics_json=editionDiagnostics(code);
 let response=await fmEdition();assert.equal(response.body.summary.total,1);assert(response.body.opportunities[0].exclusionReason.summary.includes('not corroborated'));
 assert(response.body.opportunities[0].sourceTags.includes('flipmine'));
 rows[5].matching_diagnostics_json.businessEligibilityChecks[2].result='fail';response=await fmEdition();assert.equal(response.body.summary.total,0,'Unattractive unresolved editions are not automatic near misses');
 rows[5].matching_diagnostics_json=editionDiagnostics(code);rows[5].matching_diagnostics_json.static_rules.identity_comparison.comparisons.edition.result='conflict';response=await fmEdition();assert.equal(response.body.summary.total,0,'Confirmed edition conflicts are not ordinary near misses');
 rows[5].matching_diagnostics_json=editionDiagnostics(code);rows[5].matching_diagnostics_json.businessEligibilityChecks.push({code:'inventory_hold',result:'fail',blocking:true});response=await fmEdition();assert.equal(response.body.summary.total,0,'Inventory holds remain excluded');
}
console.log('Actual GET: unresolved Deluxe/Collector editions retain actionable reasons and FM provenance, while bad economics, material conflicts and holds stay out.');
rows[5].matching_diagnostics_json=editionDiagnostics('condition_review');
const conditionDiag=rows[5].matching_diagnostics_json;
conditionDiag.static_rules.identity_comparison.comparisons.edition={result:'match',policy:{version:'sourcing_edition_policy_v1',code:null}};
conditionDiag.static_rules.condition_review={result:'review',reason:'Condition review — shrink-wrap damage'};
conditionDiag.presentationDecision.primaryReason.summary='Condition review — shrink-wrap damage';
let conditionResponse=await fmEdition();
assert.equal(conditionResponse.body.summary.total,1);
assert(conditionResponse.body.opportunities[0].exclusionReason.summary.includes('shrink-wrap damage'));
conditionDiag.static_rules.condition_mismatch={result:'blocked',hits:['missing the plastic seal']};
conditionResponse=await fmEdition();
assert.equal(conditionResponse.body.summary.total,0,'Confirmed unacceptable new condition cannot become a near miss');
compactDiagnostics=true;
rows[5].matching_diagnostics_json=editionDiagnostics('contents_not_corroborated');
let compactResponse=await fmEdition();
assert.equal(compactResponse.body.summary.total,1,'Unresolved contents survive the actual compact projection');
rows[5].matching_diagnostics_json.businessEligibilityChecks[0].result='fail';
compactResponse=await fmEdition();assert.equal(compactResponse.body.summary.total,0);
rows[5].matching_diagnostics_json=editionDiagnostics('condition_unacceptable');
rows[5].matching_diagnostics_json.static_rules.hard_blocks=['not new condition signal: missing the plastic seal'];
compactResponse=await fmEdition();assert.equal(compactResponse.body.summary.total,0,'Compact projection must exclude confirmed defects before counts and limits');
rows[5].matching_diagnostics_json=editionDiagnostics('contents_not_corroborated');
rows[5].matching_diagnostics_json.decisionTrace=[{stage:'Seller policy',reasonCode:'seller_policy',result:'fail'}];
compactResponse=await fmEdition();assert.equal(compactResponse.body.summary.total,0,'Compact seller-avoid trace cannot be discarded');

rows[5].matching_diagnostics_json=editionDiagnostics('contents_not_corroborated');
rows[5].sourcing_seed_asins.raw_context_json={inferred_system:'Game Boy Advance'};
assert.equal((await fmEdition()).body.summary.total,0,'Persisted cartridge near misses are suppressed before counts');
rows[4].sourcing_seed_asins.raw_context_json={inferred_system:'Game Boy Advance'};
let policyBuy=await route.GET({url:'https://example.test/api/sourcing/opportunities?scope=all_open&status=open&sourceMode=flipmine&limit=250'});
assert.equal(policyBuy.body.summary.total,0,'Previously Open cartridge opportunities cannot remain actionable');
assert.equal(rows[4].status,'open','Policy presentation must not rewrite history or manual status');
rows[4].sourcing_seed_asins.raw_context_json={inferred_system:'Switch'};
policyBuy=await route.GET({url:'https://example.test/api/sourcing/opportunities?scope=all_open&status=open&sourceMode=flipmine&limit=250'});
assert.equal(policyBuy.body.summary.total,1,'Switch remains eligible under normal existing gates');
rows[5].sourcing_seed_asins.raw_context_json={inferred_system:'PSP'};
assert.equal((await fmEdition()).body.summary.total,1,'PSP near misses retain existing eligibility');
console.log('Actual GET platform policy suppresses existing cartridge Buy List and Closest Excluded rows without changing persisted status; Switch and PSP remain.');
