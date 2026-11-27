import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {execFileSync} from 'node:child_process';
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
const modules=new Map();function load(file){file=resolve(file);if(modules.has(file))return modules.get(file);const out={};modules.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8')+(file.endsWith('route.ts')?'\nexport {persistedExclusionReason,persistedDecisionTrace};':''),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name==='next/server')return {NextResponse:{json:(body,init)=>({body,json:async()=>body,ok:!init?.status||init.status<400,status:init?.status??200,headers:new Headers()})}};
 if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db,toNumber:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d};
 // Exercise actual list building without the independent server-cache layer.
 if(name==='../readCache')return {cachedSourcingList:async(_key,_fresh,build)=>({body:await build(),hit:false})};
 if(name.endsWith('.json')){const value=JSON.parse(readFileSync(resolve(dirname(file),name),'utf8'));return {default:value,...value};}
 if(name.startsWith('.'))return load(resolve(dirname(file),name+'.ts'));return require(name);
},out);return out;}
const route=load(resolve(root,'opportunities/route.ts'));
const python=resolve(root,'../../../../.venv/Scripts/python.exe');
const payload=JSON.parse(execFileSync(python,['-c',`import json,sys;sys.path.insert(0,'integrations');from sourcing_decision_trace import enrich_sourcing_diagnostics
cases=json.load(open('tests/fixtures/phase3a_exclusion_reasons_20261126.json'));out=[]
for c in cases:
 d=enrich_sourcing_diagnostics(c['diagnostics'],status=c['status'],opportunity_type=c['opportunity_type'],profit=c['profit'],roi_percent=c['roi_percent']);out.append(dict(row=c['row'],presentationDecision=d['presentationDecision'],decisionTrace=d['decisionTrace']))
print(json.dumps(out))`],{cwd:resolve(root,'../../../..'),encoding:'utf8'}));
const ui=readFileSync(resolve(root,'../../sourcing/page.tsx'),'utf8');
const fragment=ui.slice(ui.indexOf('function ExcludedBecause('),ui.indexOf('function OpportunityTypeCell('));
const out={};new Function('require','exports',ts.transpileModule(fragment+'\nexport {ExcludedBecause};',{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(require,out);
const {renderToStaticMarkup}=require('react-dom/server');
for(const c of payload){
 const compact={presentationDecision:c.presentationDecision,decisionTrace:c.decisionTrace};
 const reason=route.persistedExclusionReason(compact);
 assert.equal(reason.code,c.row===68?'duplicate_history':'condition_unacceptable');
 assert.deepEqual(reason.diagnosticKeys,c.presentationDecision.primaryReason.diagnosticKeys);
 assert.equal(reason.secondaryReasons.length,c.presentationDecision.secondaryReasons.length);
 const rendered=renderToStaticMarkup(out.ExcludedBecause({reason}));
 assert(rendered.includes('Excluded Because'));assert(!rendered.includes('mapped rule'));
 assert(rendered.includes(c.row===68?'dismissed':c.row===504?'visible cracks on case':'pre-owned'));
 assert.equal(compact.presentationDecision.finalStatus,'rejected');assert.equal(compact.presentationDecision.eligible,false);
}
console.log('Eight actual Python compact explanations survive API mapping and actual ExcludedBecause React rendering; secondary reasons and decisions preserved.');

