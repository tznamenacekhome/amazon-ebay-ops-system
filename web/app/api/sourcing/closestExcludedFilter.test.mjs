import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),root=dirname(fileURLToPath(import.meta.url));
const rows=Array.from({length:53},(_,i)=>({opportunity_id:`opp-${i}`,candidate_id:`candidate-${i}`,asin:`ASIN${i}`,ebay_item_id:`listing-${i}`,status:'rejected',opportunity_type:'review',score:100-i,profit:i===51?-1:10,matching_diagnostics_json:i===52?{hard_blocks:['wrong platform']}:{recommendation:'Review'},sourcing_seed_asins:{asin:`ASIN${i}`,amazon_title:'Game',source_mode:'recent_sales'},sourcing_ebay_candidates:{ebay_item_id:`listing-${i}`,ebay_title:'Game listing',listing_status:'active',display_price:{currency:'USD'},display_shipping:[]}}));
const db={rpc:async()=>({data:[],error:null}),from(table){
 const query=new Proxy({}, {get(_,method){if(method==='then')return done=>Promise.resolve(done({data:table==='sourcing_opportunities'?rows:[],error:null}));return ()=>query;}});return query;
}};
const modules=new Map();function load(file){file=resolve(file);if(modules.has(file))return modules.get(file);const out={};modules.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name==='next/server')return {NextResponse:{json:(body,init)=>({body,json:async()=>body,ok:!init?.status||init.status<400,status:init?.status??200,headers:new Headers()})}};
 if(name.endsWith('/_supabase')||name==='./_supabase')return {supabase:db,toNumber:(v,d=0)=>Number.isFinite(Number(v))?Number(v):d};
 // Exercise actual list building without the independent server-cache layer.
 if(name==='../readCache')return {cachedSourcingList:async(_key,_fresh,build)=>({body:await build(),hit:false})};
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
