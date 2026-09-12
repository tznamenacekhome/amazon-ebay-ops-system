import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),root=dirname(fileURLToPath(import.meta.url));
const check={code:'roi',label:'Estimated ROI',actual:18,threshold:30,units:'%',result:'fail',blocking:true,source:'existing scorer',scenario:'asking price',evaluatedAt:'2026-09-12'};
const full={opportunity_id:'fixture',candidate_id:'candidate',asin:'EXACT',ebay_item_id:'v1|1|2',status:'rejected',opportunity_type:'no_profitable_source_found',matching_diagnostics_json:{businessEligibilityChecks:[check],static_rules:{identity_comparison:{evidenceDecision:{productIdentityVerdict:'match'}}}},sourcing_seed_asins:{asin:'EXACT',amazon_title:'Amazon title',raw_context_json:{preserved:true}},sourcing_ebay_candidates:{ebay_item_id:'v1|1|2',ebay_title:'Listing title',listing_status:'active',raw_ebay_json:{description:'Original full description'}}};
const minimal={opportunity_id:full.opportunity_id,asin:full.asin,ebay_item_id:full.ebay_item_id,status:full.status,business_checks:[check],identity_verdict:'match',sourcing_seed_asins:{asin:'EXACT'},sourcing_ebay_candidates:{listing_status:'active'}};
let positive=true;const reads=[];
const db={rpc:async()=>({data:[],error:null}),from(table){let select='',held=false,ids=null;
 const query=new Proxy({}, {get(_,method){if(method==='then')return done=>{let data=[];if(table==='sourcing_opportunities')data=held?[]:ids?[full]:[{...minimal,identity_verdict:positive?'match':'unknown'}];reads.push({table,select,ids});return Promise.resolve(done({data,error:null}));};return (...args)=>{if(method==='select')select=args[0];if(method==='in'&&args[0]==='status')held=true;if(method==='in'&&args[0]==='opportunity_id')ids=args[1];return query;};}});return query;}};
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name==='next/server')return {NextResponse:{json:(body,init)=>({body,status:init?.status??200,headers:new Headers()})}};
 if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db,toNumber:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d};
 if(name.startsWith('.'))return load(resolve(dirname(file),name+'.ts'));return require(name);
},out);return out;}
const route=load(resolve(root,'opportunities/route.ts'));
const {selectRecordedHold,recordedHoldCheck}=load(resolve(root,'businessExclusion.ts'));
const activeInventory=selectRecordedHold({asin:'EXACT',status:'inventory_snoozed',ebay_item_id:'pair'},[
 {asin:'EXACT',action_type:'watching',ebay_item_id:'other'},
 {asin:'EXACT',action_type:'inventory_snoozed',raw_action_context:{inventorySnooze:{representAtUnits:9}},created_at:'2026-09-12'},
]);
assert.equal(activeInventory.action_type,'inventory_snoozed');
assert.equal(recordedHoldCheck({status:'inventory_snoozed',sourcing_seed_asins:{current_inventory_units:10}},activeInventory)[0].threshold,9);
const response=await route.GET({url:'https://example.test/api/sourcing/opportunities?status=business_excluded&limit=50'});
assert.equal(response.status,200,JSON.stringify(response.body));assert.equal(response.body.opportunities.length,1);
const row=response.body.opportunities[0];assert.equal(row.ebayTitle,'Listing title');assert.equal(row.diagnosticComparison.productIdentityVerdict,'match');assert.equal(row.exclusionReason.code,'roi');
assert(reads.some(q=>q.table==='sourcing_opportunities'&&!q.ids&&q.select.includes('identity_verdict:')&&!q.select.includes('raw_ebay_json')));
assert(reads.some(q=>q.table==='sourcing_opportunities'&&q.ids?.[0]==='fixture'&&q.select.includes('raw_ebay_json')));
positive=false;reads.length=0;const unknown=await route.GET({url:'https://example.test/api/sourcing/opportunities?status=business_excluded&limit=50'});
assert.equal(unknown.body.opportunities.length,0);assert(!reads.some(q=>q.ids),'Unknown identities must not hydrate raw listing payloads');
console.log('Actual Business Excluded GET passed: narrow qualification, exact-ASIN positive + genuine gate, bounded ID hydration preserves diagnostics; unknown excluded without full payload reads.');
