import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {createClient} from '@supabase/supabase-js';
const require=createRequire(import.meta.url);
const captured=JSON.parse(readFileSync('tmp/sourcing-phase3/responses.json','utf8'));
const fixtures=new Map(captured.filter(r=>r.method==='GET').map(r=>[r.url,r]));
let reads=0;const db=createClient('https://froeucjkcepuhgwisped.supabase.co','offline-test-key',{auth:{persistSession:false},global:{fetch:async(url,init)=>{
 const method=init?.method??'GET';assert.equal(method,'GET');const row=fixtures.get(String(url));assert(row,'Uncaptured request; network is forbidden: '+url);reads++;return new Response(JSON.stringify(row.body),{status:row.status,headers:{'content-type':'application/json'}});
}}});
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db,toNumber:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d};
 if(name.endsWith('/reviewActions'))return {fetchLatestReviews:async()=>new Map()}; // capture explicitly contains zero v3 reviews
 if(name.startsWith('.')){const next=resolve(dirname(file),name+'.ts');assert(existsSync(next));return load(next);}return require(name);
},out);return out;}
const baseline=JSON.parse(readFileSync('tmp/sourcing-phase3/current.json','utf8'));assert.equal(baseline.reviews.length,0);
const route=load('web/app/api/sourcing/opportunities/route.ts'),result={networkCalls:0,views:{}};
for(const [name,query] of Object.entries({buy_list:'status=open&type=all&sourceMode=all&scope=all_open&limit=150',closest_excluded:'status=open&type=all&sourceMode=all&scope=closest_excluded&limit=50',business_excluded:'status=business_excluded&type=all&scope=all_open&limit=50'})){
 const response=await route.GET({url:'https://example.test/api/sourcing/opportunities?'+query}),body=await response.json();assert.equal(response.status,200,JSON.stringify(body));
 assert.deepEqual(body.opportunities.map(r=>r.opportunityId),baseline.views[name].opportunities.map(r=>r.opportunityId),name+' ordered IDs');assert.deepEqual(body.summary,baseline.views[name].summary,name+' summaries');
 for(let i=0;i<body.opportunities.length;i++){const a={...body.opportunities[i]},b={...baseline.views[name].opportunities[i]};delete a.diagnosticComparison;delete b.diagnosticComparison;assert.deepEqual(a,b,name+' routing/scoring/presentation');}
 result.views[name]={count:body.opportunities.length,orderedIds:body.opportunities.map(r=>r.opportunityId),summary:body.summary};
}
result.fixtureReads=reads;writeFileSync('tmp/sourcing-review-ui/routing.json',JSON.stringify(result,null,2));console.log('Frozen populated actual API routing unchanged: '+JSON.stringify(Object.fromEntries(Object.entries(result.views).map(([k,v])=>[k,v.count]))));
