import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync,spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import ts from 'typescript';
const require=createRequire(import.meta.url),container=process.env.MBOP_REVIEW_TEST_CONTAINER;
assert.equal(container,'mbop-phase2-review-test','Only the named disposable container is allowed');
const sql=q=>execFileSync('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],{input:q,encoding:'utf8'}).trim();
const quote=v=>v===null||v===undefined?'null':"'"+String(typeof v==='object'?JSON.stringify(v):v).replaceAll("'","''")+"'";
let calls=0,denied=false,failSnapshot=false,lastSave;
const db={rpc:async(name,args)=>{calls++;assert(['sourcing_adjudication_state','sourcing_save_adjudication'].includes(name));try{
 if(name==='sourcing_save_adjudication')lastSave=structuredClone(args);
 if(failSnapshot&&name==='sourcing_save_adjudication')args.p_snapshot.ebay_item_id='different';
 return {data:JSON.parse(sql(`select public.${name}(${Object.entries(args).map(([k,v])=>k+'=>'+quote(v)).join(',')})`)),error:null};
}catch(e){return {data:null,error:{message:String(e.stderr),code:String(e.stderr).includes('newer pair review')?'40001':'22023'}};}}};
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);const js=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
new Function('require','exports',js)(name=>{if(name==='next/server')return {NextResponse:{json:(body,opts)=>({body,status:opts?.status??200})}};if(name.endsWith('/_server'))return {isCloudDeployment:()=>false,requireAdminApiToken:()=>denied?{status:401}:null};if(name.endsWith('/_supabase'))return {supabase:db};if(name.startsWith('.')){if(name.endsWith('.json'))return JSON.parse(readFileSync(resolve(dirname(file),name)));let next=resolve(dirname(file),name+'.ts');if(!existsSync(next))next=resolve(dirname(file),name+'.tsx');return load(next);}return require(name);},out);return out;}
const service=load('web/app/api/sourcing/adjudication/service.ts'),route=load('web/app/api/sourcing/adjudication/route.ts');
assert.equal(service.queue.length,16);const manifest=JSON.parse(readFileSync('docs/sourcing_identity_adjudication_manifest_2026-09-13.json'));
assert.deepEqual(service.queue.map(x=>[x.queueId,x.asin,x.ebayLegacyItemId]).sort(),manifest.manualReviewQueue.map(x=>[x.sourceId,x.asin,x.ebayItemId]).sort());
const row=service.queue.find(x=>!x.opportunityId);assert(row,'Exercise a historic pair with no live opportunity');
const before=sql("select jsonb_build_object('op',(select jsonb_agg(to_jsonb(t)) from sourcing_opportunities t),'holds',(select jsonb_agg(to_jsonb(t)) from sourcing_sales_velocity_suppressions t),'blocks',(select jsonb_agg(to_jsonb(t)) from sourcing_blocked_asins t))");
const state=await service.loadState(row);let body={queueId:row.queueId,requestId:randomUUID(),expectedAsin:row.asin,expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:state.revision,identityAttested:true,variationVerified:true,notes:'Synthetic disposable test only',feedback:{pairVerdict:'correct',corrections:[]}};
const post=body=>route.POST({headers:new Headers(),json:async()=>body});
denied=true;assert.equal((await post(body)).status,401);denied=false;
assert.equal((await post({...body,expectedAsin:'OTHER'})).status,409);
assert.equal((await post({...body,expectedSnapshotHash:'stale'})).status,409);
assert.equal((await post({...body,identityAttested:false})).status,400);
let saved=await post(body);assert.equal(saved.status,200,JSON.stringify(saved));assert.equal((await post(body)).body.review.replayed,true);
assert.equal((await post({...body,notes:'different'})).status,400);
const staleArgs={...lastSave,p_request_id:randomUUID()};assert((await db.rpc('sourcing_save_adjudication',staleArgs)).error,'Transaction must reject a stale revision independently of API');
let current=await service.loadState(row),latest=service.summarize(row,current);assert.equal(latest.pairVerdict,'correct');assert.equal(latest.tierA,true);
assert.equal(JSON.parse(sql(`select public.sourcing_latest_reviews(${quote([{asin:row.asin,ebay_item_id:row.ebayItemId}])})`))[0].pairVerdict,null,'Adjudication cannot enter live business routing');
assert.equal(service.summarize({...row,asin:'OTHER'}, {revision:'x',actions:current.actions.filter(a=>a.asin==='OTHER')}).pairVerdict,null);
assert.equal((await post({...body,requestId:randomUUID(),feedback:{pairVerdict:'incorrect',corrections:[]}})).status,409);
async function save(feedback,extra={}){const s=await service.loadState(row);body={...body,requestId:randomUUID(),expectedRevision:s.revision,feedback,...extra};const result=await post(body);assert.equal(result.status,200,JSON.stringify(result));return service.summarize(row,await service.loadState(row));}
latest=await save({pairVerdict:'incorrect',corrections:[]});assert.equal(latest.pairVerdict,'incorrect');assert(!latest.tierA);
latest=await save({pairVerdict:'unsure',flaggedFields:['edition'],corrections:[]});assert.equal(latest.pairVerdict,'unsure');assert(!latest.tierA);
const c={field:'coreGame',side:'ebay',scope:'pair',state:'value',value:'Corrected game',note:null};
latest=await save({pairVerdict:'correct',flaggedFields:['coreGame'],corrections:[c]});assert(latest.tierA);assert.equal(latest.corrections[0].value,'Corrected game');assert(latest.corrections[0].before);
latest=await save({pairVerdict:'not_provided',flaggedFields:['coreGame'],corrections:[{...c,value:'Later correction'}]});assert.equal(latest.pairVerdict,'correct');assert(!latest.tierA,'New evidence after confirmation requires re-review');assert.equal(latest.corrections[0].value,'Later correction');
latest=await save({pairVerdict:'incorrect',flaggedFields:['edition'],corrections:[{field:'edition',side:'amazon',scope:'asin',state:'unknown',value:null}]});assert.equal(latest.pairVerdict,'incorrect');
const sibling={...row,ebayItemId:'v1|999999999999|0'};const other=service.summarize(sibling,await service.loadState(sibling));assert.equal(other.pairVerdict,null);assert(other.corrections.some(c=>c.side==='amazon'));assert(!other.corrections.some(c=>c.side==='ebay'));
assert.equal((await post({...body,requestId:randomUUID(),feedback:{pairVerdict:'incorrect',flaggedFields:['coreGame'],corrections:[{...c,scope:'asin'}]}})).status,400);
failSnapshot=true;const bad={...body,requestId:randomUUID(),expectedRevision:(await service.loadState(row)).revision};assert.equal((await post(bad)).status,400);assert.equal(sql(`select count(*) from sourcing_actions where action_id=${quote(bad.requestId)}`),'0');failSnapshot=false;
// Force failure after action and snapshot inserts; all three writes must roll back.
const rollbackArgs={...lastSave,p_request_id:randomUUID(),p_expected_revision:(await service.loadState(row)).revision};
sql("create or replace function public.adjudication_test_fail() returns trigger language plpgsql as $$ begin raise exception 'injected label failure'; end $$; create trigger adjudication_test_fail before insert on public.matching_intelligence_examples for each row execute function public.adjudication_test_fail();");
try {assert((await db.rpc('sourcing_save_adjudication',rollbackArgs)).error);assert.equal(sql(`select count(*) from sourcing_actions where action_id=${quote(rollbackArgs.p_request_id)}`),'0');assert.equal(sql(`select count(*) from sourcing_listing_snapshots where action_id=${quote(rollbackArgs.p_request_id)}`),'0');}
finally {sql('drop trigger adjudication_test_fail on public.matching_intelligence_examples; drop function public.adjudication_test_fail();');}
const raceRevision=(await service.loadState(row)).revision;
const race=()=>new Promise(resolve=>{const args={...lastSave,p_request_id:randomUUID(),p_expected_revision:raceRevision};const proc=spawn('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1']);proc.stdout.resume();proc.stderr.resume();proc.on('close',resolve);proc.stdin.end(`select public.sourcing_save_adjudication(${Object.entries(args).map(([k,v])=>k+'=>'+quote(v)).join(',')})`);});
assert.deepEqual((await Promise.all([race(),race()])).sort(),[0,3],'One concurrent writer wins; the other rejects stale state');
for (const field of ['coreProduct','includedContents','releaseYear']) {latest=await save({pairVerdict:'incorrect',flaggedFields:[field],corrections:[{field,side:'ebay',scope:'pair',state:'unknown',value:null}]});assert(latest.corrections.some(c=>c.field===field));}
const after=sql("select jsonb_build_object('op',(select jsonb_agg(to_jsonb(t)) from sourcing_opportunities t),'holds',(select jsonb_agg(to_jsonb(t)) from sourcing_sales_velocity_suppressions t),'blocks',(select jsonb_agg(to_jsonb(t)) from sourcing_blocked_asins t))");assert.equal(before,after);
assert(latest.lineage.length>=6);
const exported=await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/?report=1')});assert.equal(exported.status,200);assert.equal(exported.body.positives.length+exported.body.negatives.length+exported.body.unresolved.length,16);
const listed=await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/')});assert.equal(listed.body.total,16);assert.equal(listed.body.reviewed,listed.body.rows.filter(r=>r.latestReview.pairVerdict).length);
const all=await service.loadQueue();assert.equal(all.length,16);assert(all.find(x=>x.queueId===row.queueId).latestReview.pairVerdict==='incorrect');
console.log('Exact 16-row API -> disposable PostgreSQL -> reload/export contracts passed; no provider path. RPC calls:',calls);
