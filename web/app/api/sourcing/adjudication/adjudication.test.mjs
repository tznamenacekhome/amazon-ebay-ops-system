import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import {execFileSync,spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import ts from 'typescript';
const require=createRequire(import.meta.url),container=process.env.MBOP_REVIEW_TEST_CONTAINER;
assert.equal(container,'mbop-phase2-review-test','Only the named disposable container is allowed');
// Repeated disposable runs retain append-only history; a valid bounded state
// can exceed Node's 1 MiB default stdout buffer without a database error.
const sql=q=>execFileSync('docker',['exec','-i',container,'psql','-U','postgres','-At','-v','ON_ERROR_STOP=1'],{input:q,encoding:'utf8',maxBuffer:32*1024*1024}).trim();
const quote=v=>v===null||v===undefined?'null':"'"+String(typeof v==='object'?JSON.stringify(v):v).replaceAll("'","''")+"'";
let calls=0,denied=false,failSnapshot=false,lastSave,failReadback=false,failNextRead=false;
const db={rpc:async(name,args)=>{calls++;assert(['sourcing_adjudication_state','sourcing_save_adjudication'].includes(name));try{
 if(name==='sourcing_adjudication_state'&&failNextRead){failNextRead=false;return {data:null,error:{message:'Injected readback failure'}};}
 if(name==='sourcing_save_adjudication')lastSave=structuredClone(args);
 if(failSnapshot&&name==='sourcing_save_adjudication')args.p_snapshot.ebay_item_id='different';
 const data=JSON.parse(sql(`select public.${name}(${Object.entries(args).map(([k,v])=>k+'=>'+quote(v)).join(',')})`));if(name==='sourcing_save_adjudication'&&failReadback)failNextRead=true;return {data,error:null};
}catch(e){return {data:null,error:{message:String(e.stderr),code:String(e.stderr).includes('newer pair review')?'40001':'22023'}};}}};
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);const js=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
new Function('require','exports',js)(name=>{if(name==='next/server')return {NextResponse:{json:(body,opts)=>({body,status:opts?.status??200})}};if(name.endsWith('/_server'))return {isCloudDeployment:()=>false,requireAdminApiToken:()=>denied?{status:401}:null};if(name.endsWith('/_supabase'))return {supabase:db};if(name.startsWith('.')){if(name.endsWith('.json'))return JSON.parse(readFileSync(resolve(dirname(file),name)));let next=resolve(dirname(file),name+'.ts');if(!existsSync(next))next=resolve(dirname(file),name+'.tsx');return load(next);}return require(name);},out);return out;}
const service=load('web/app/api/sourcing/adjudication/service.ts'),route=load('web/app/api/sourcing/adjudication/route.ts');
assert.equal(service.queue.length,16);const manifest=JSON.parse(readFileSync('docs/sourcing_identity_adjudication_manifest_2026-09-13.json'));
assert.deepEqual(service.queue.map(x=>[x.queueId,x.asin,x.ebayLegacyItemId]).sort(),manifest.manualReviewQueue.map(x=>[x.sourceId,x.asin,x.ebayItemId]).sort());
const row=service.queue.find(x=>!x.opportunityId && x.asin!=="B072JZB85B");assert(row,'Exercise a historic pair with no live opportunity');
const before=sql("select jsonb_build_object('op',(select jsonb_agg(to_jsonb(t)) from sourcing_opportunities t),'holds',(select jsonb_agg(to_jsonb(t)) from sourcing_sales_velocity_suppressions t),'blocks',(select jsonb_agg(to_jsonb(t)) from sourcing_blocked_asins t))");
const state=await service.loadState(row);let body={queueId:row.queueId,requestId:randomUUID(),expectedAsin:row.asin,expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:state.revision,identityAttested:true,variationResolution:'not_applicable',notes:'Synthetic disposable test only',feedback:{pairVerdict:'correct',corrections:[]}};
const post=body=>route.POST({headers:new Headers(),json:async()=>body});
denied=true;assert.equal((await post(body)).status,401);denied=false;
assert.equal((await post({...body,expectedAsin:'OTHER'})).status,409);
assert.equal((await post({...body,expectedSnapshotHash:'stale'})).status,409);
assert.equal((await post({...body,identityAttested:false})).status,400);
let saved=await post(body);assert.equal(saved.status,200,JSON.stringify(saved));assert.equal(saved.body.reviewState.latestReview.pairVerdict,'correct');assert(saved.body.reviewState.revision);assert.equal((await post(body)).body.review.replayed,true);
assert.equal((await post({...body,notes:'different'})).status,400);
const staleArgs={...lastSave,p_request_id:randomUUID()};assert((await db.rpc('sourcing_save_adjudication',staleArgs)).error,'Transaction must reject a stale revision independently of API');
let current=await service.loadState(row),latest=service.summarize(row,current);assert.equal(latest.pairVerdict,'correct');assert.equal(latest.tierA,true);
assert.equal(JSON.parse(sql(`select public.sourcing_latest_reviews(${quote([{asin:row.asin,ebay_item_id:row.ebayItemId}])})`))[0].pairVerdict,null,'Adjudication cannot enter live business routing');
assert.equal(service.summarize({...row,asin:'OTHER'}, {revision:'x',actions:current.actions.filter(a=>a.asin==='OTHER')}).pairVerdict,null);
assert.equal((await post({...body,requestId:randomUUID(),feedback:{pairVerdict:'incorrect',corrections:[]}})).status,409);
async function save(feedback,extra={}){const s=await service.loadState(row);body={...body,requestId:randomUUID(),expectedRevision:s.revision,feedback,...extra};const result=await post(body);assert.equal(result.status,200,JSON.stringify(result));return service.summarize(row,await service.loadState(row));}
latest=await save({pairVerdict:'incorrect',corrections:[]},{identityAttested:false,variationResolution:'unknown'});assert.equal(latest.pairVerdict,'incorrect');assert(!latest.tierA);
assert.equal(lastSave.p_context.identityAttested,false);assert.equal(lastSave.p_context.variationVerified,false);assert.deepEqual(lastSave.p_context.matchingFeedback.flaggedFields,[]);assert.deepEqual(lastSave.p_context.matchingFeedback.corrections,[]);
assert.equal(lastSave.p_context.source,'identity_adjudication_queue');assert.equal(lastSave.p_context.pair.asin,row.asin);assert.equal(lastSave.p_context.pair.ebayItemId,row.ebayItemId);assert.equal(lastSave.p_context.pair.variationId,row.variationId);assert(lastSave.p_context.queueSnapshotHash);assert(latest.actor&&latest.createdAt&&latest.snapshotId);
const bareNegative={...lastSave,p_request_id:randomUUID(),p_expected_revision:(await service.loadState(row)).revision};
assert(!(await db.rpc('sourcing_save_adjudication',bareNegative)).error,'RPC accepts exact-pair negative without positive assertions');
const barePositive={...bareNegative,p_request_id:randomUUID(),p_expected_revision:(await service.loadState(row)).revision,p_context:{...bareNegative.p_context,matchingFeedback:{...bareNegative.p_context.matchingFeedback,pairVerdict:'correct'}}};assert((await db.rpc('sourcing_save_adjudication',barePositive)).error,'RPC still rejects unattested Confirm Match');
latest=await save({pairVerdict:'incorrect',flaggedFields:['coreGame'],corrections:[]});assert.equal(latest.pairVerdict,'incorrect');assert.deepEqual(lastSave.p_context.matchingFeedback.corrections,[]);
latest=await save({pairVerdict:'correct',corrections:[]},{identityAttested:true,variationResolution:'unknown'});assert(!latest.tierA,'Unverified variation scope cannot qualify a positive as Tier A');
latest=await save({pairVerdict:'unsure',flaggedFields:['edition'],corrections:[]});assert.equal(latest.pairVerdict,'unsure');assert(!latest.tierA);
const c={field:'coreGame',side:'ebay',scope:'pair',state:'value',value:'Corrected game',note:null};
latest=await save({pairVerdict:'correct',flaggedFields:['coreGame'],corrections:[c]},{identityAttested:true,variationResolution:'not_applicable'});assert(latest.tierA);assert.equal(latest.corrections[0].value,'Corrected game');assert(latest.corrections[0].before);
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
// Cross-generation relationship evidence uses the supplied Xbox pair, never matcher exceptions.
const xbox=service.queue.find(r=>r.asin==='B07FF3F7F9'&&r.ebayItemId==='v1|267725836968|0');assert(xbox);
const originalPlatforms=JSON.stringify([xbox.identity.amazon.platform,xbox.identity.ebay.platform]);
let xboxBody;
async function xboxSave(verdict,relationship,corrections=[]) {
 const state=await service.loadState(xbox);
 xboxBody={queueId:xbox.queueId,requestId:randomUUID(),expectedAsin:xbox.asin,expectedEbayItemId:xbox.ebayItemId,expectedSnapshotHash:xbox.snapshotHash,expectedRevision:state.revision,identityAttested:true,variationResolution:'not_applicable',
 feedback:{pairVerdict:verdict,corrections,flaggedFields:corrections.map(c=>c.field),fieldRelationships:[{field:'platform',operatorRelationship:relationship,compatiblePlatforms:{amazon:['Xbox One'],ebay:['Xbox One','Xbox Series X']}}]}};
 const saved=await post(xboxBody);assert.equal(saved.status,200,JSON.stringify(saved));
 const latest=service.summarize(xbox,await service.loadState(xbox));assert.equal(latest.platformRelationship.operatorRelationship,relationship);assert(latest.platformRelationship.actor&&latest.platformRelationship.snapshotId&&latest.platformRelationship.reviewedAt);return latest;
}
for(const relationship of ['match','compatible','wrong','unknown']) await xboxSave('unsure',relationship);
let xr=await xboxSave('correct','compatible');assert(xr.tierA);assert.equal(xr.pairVerdict,'correct');assert.deepEqual(xr.platformRelationship.compatiblePlatforms.ebay,['Xbox One','Xbox Series X']);
assert.equal((await post(xboxBody)).body.review.replayed,true);
xr=await xboxSave('incorrect','compatible');assert(!xr.tierA);assert.equal(xr.pairVerdict,'incorrect');
xr=await xboxSave('unsure','compatible');assert(!xr.tierA);assert.equal(xr.pairVerdict,'unsure');
xr=await xboxSave('correct','wrong',[{field:'platform',side:'ebay',scope:'pair',state:'value',value:'Xbox One / Xbox Series X'}]);
xr=await xboxSave('not_provided','compatible');assert.equal(xr.pairVerdict,'correct');assert(!xr.tierA,'Later field relationship requires renewed pair confirmation');assert(xr.lineage.some(a=>a.fieldRelationships.some(r=>r.operatorRelationship==='wrong')));assert(xr.corrections.some(c=>c.field==='platform'));
xr=await xboxSave('correct','compatible',[{field:'platform',side:'amazon',scope:'pair',state:'value',value:'Xbox One'}]);assert(xr.tierA);assert.equal(JSON.stringify([xbox.identity.amazon.platform,xbox.identity.ebay.platform]),originalPlatforms);
const latestXboxState=await service.loadState(xbox);const malformed={...latestXboxState.actions[0],action_id:randomUUID(),created_at:'2099-01-01T00:00:00Z',raw_action_context:{...latestXboxState.actions[0].raw_action_context,matchingFeedback:{fieldRelationships:[null,{field:'platform',operatorRelationship:'invalid'}]}}};const invalidSummary=service.summarize(xbox,{revision:'test',actions:[malformed,...latestXboxState.actions]});assert(invalidSummary.requiresReReview);assert(!invalidSummary.tierA);
const report=(await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/?report=1')})).body;
const exportedXbox=report.positives.find(r=>r.asin===xbox.asin);assert(exportedXbox);assert.equal(exportedXbox.platform_operator_relationship,'compatible');assert.equal(exportedXbox.platform_amazon,xbox.identity.amazon.platform);assert.equal(exportedXbox.platform_ebay,xbox.identity.ebay.platform);assert.equal(exportedXbox.pair_verdict,'correct');assert(exportedXbox.platform_corrections.length);assert(exportedXbox.platform_relationship_provenance.actionId);
assert.equal((await post({...xboxBody,requestId:randomUUID(),feedback:{pairVerdict:'unsure',fieldRelationships:[{field:'edition',operatorRelationship:'compatible'}]}})).status,400);
const mixed=service.queue.find(r=>r.asin==='B072JZB85B');assert.equal((await post({...xboxBody,queueId:mixed.queueId,expectedAsin:mixed.asin,expectedEbayItemId:mixed.ebayItemId,expectedSnapshotHash:mixed.snapshotHash})).status,409);assert.equal(report.total,15);assert.equal(report.excluded[0].asin,mixed.asin);
const after=sql("select jsonb_build_object('op',(select jsonb_agg(to_jsonb(t)) from sourcing_opportunities t),'holds',(select jsonb_agg(to_jsonb(t)) from sourcing_sales_velocity_suppressions t),'blocks',(select jsonb_agg(to_jsonb(t)) from sourcing_blocked_asins t))");assert.equal(before,after);
assert(latest.lineage.length>=6);
const exported=await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/?report=1')});assert.equal(exported.status,200);assert.equal(exported.body.positives.length+exported.body.negatives.length+exported.body.unresolved.length+exported.body.unqualifiedConfirmations.length+exported.body.unreviewed.length,15);
const listed=await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/')});assert.equal(listed.body.total,15);assert.equal(listed.body.storedTotal,16);assert.equal(exported.body.excluded.length,1);assert.equal(listed.body.reviewed,listed.body.rows.filter(r=>r.adjudicationEligible&&r.latestReview.pairVerdict).length);
const all=await service.loadQueue();assert.equal(all.length,16);assert(all.find(x=>x.queueId===row.queueId).latestReview.pairVerdict==='incorrect');
failReadback=true;const readbackBody={...body,requestId:randomUUID(),expectedRevision:(await service.loadState(row)).revision,identityAttested:false,variationResolution:'unknown',feedback:{pairVerdict:'incorrect',corrections:[]}};const readbackResult=await post(readbackBody);failReadback=false;
assert.equal(readbackResult.status,200);assert(readbackResult.body.review.actionId);assert.equal(readbackResult.body.refreshError,'Injected readback failure');assert.equal(sql(`select count(*) from sourcing_actions where action_id=${quote(readbackBody.requestId)}`),'1');
// Variation-only events preserve every prior evidence source and the pair verdict.
latest=await save({pairVerdict:'correct',flaggedFields:['coreGame'],corrections:[c],fieldRelationships:[{field:'platform',operatorRelationship:'compatible'}]}, {identityAttested:true,variationResolution:'unknown',notes:'Keep original notes'});
const confirmed=structuredClone(latest),historyBefore=(await service.loadState(row)).actions;
async function variationSave(resolution,extra={}) {
 const state=await service.loadState(row);
 const request={queueId:row.queueId,requestId:randomUUID(),expectedAsin:row.asin,expectedEbayItemId:row.ebayItemId,expectedSnapshotHash:row.snapshotHash,expectedRevision:state.revision,
   reviewKind:'variation_scope',variationTargetActionId:confirmed.actionId,variationResolution:resolution,...extra};
 const result=await post(request);return {request,result};
}
for(const [resolution,qualified] of [['not_applicable',true],['verified',false],['unknown',false]]) {
 const {request,result}=await variationSave(resolution);assert.equal(result.status,200,JSON.stringify(result));
 const current=result.body.reviewState.latestReview;
 assert.equal(current.pairVerdict,'correct');assert.equal(current.actionId,confirmed.actionId);assert.equal(current.tierA,qualified);assert.equal(current.variationResolution,resolution);assert(current.variationScopeReviewed);
 assert.equal(current.notes,confirmed.notes);assert.deepEqual(current.feedback,confirmed.feedback);assert.deepEqual(current.corrections,confirmed.corrections);assert.deepEqual(current.platformRelationship,confirmed.platformRelationship);
 assert.equal(lastSave.p_context.matchingFeedback.pairVerdict,'not_provided');assert.deepEqual(lastSave.p_context.matchingFeedback.corrections,[]);
 assert.equal((await post(request)).body.review.replayed,true);
 assert.equal((await post({...request,variationResolution:resolution==='unknown'?'not_applicable':'unknown'})).status,400);
 assert.equal((await post({...request,requestId:randomUUID()})).status,409);
}
const retained=(await service.loadState(row)).actions;for(const original of historyBefore)assert.deepEqual(retained.find(a=>a.action_id===original.action_id),original);
assert.equal((await variationSave('not_applicable',{notes:'Must not overwrite'})).result.status,400);
assert.equal((await variationSave('invalid')).result.status,400);
// A real exact stored variation can qualify; neither zero nor missing IDs do.
const variant=structuredClone(row);variant.variationId='12345';variant.ebayItemId='v1|123456789012|12345';
const va=structuredClone(historyBefore.find(a=>a.action_id===confirmed.actionId));va.ebay_item_id=variant.ebayItemId;Object.assign(va.raw_action_context,{variationResolution:'verified',variationVerified:true,pair:{...va.raw_action_context.pair,ebayItemId:variant.ebayItemId,variationId:variant.variationId}});
assert(service.summarize(variant,{revision:'synthetic',actions:[va]}).tierA);
va.raw_action_context.variationResolution='unknown';assert(!service.summarize(variant,{revision:'synthetic',actions:[va]}).tierA);
await save({pairVerdict:'incorrect',corrections:[]},{identityAttested:false,variationResolution:'unknown'});
assert.equal((await variationSave('not_applicable')).result.status,409,'A superseding negative cannot inherit variation-only evidence');
const follow=(await route.GET({headers:new Headers(),nextUrl:new URL('https://example.test/?followup=variation')})).body;
assert(follow.rows.every(r=>r.adjudicationEligible&&r.latestReview.pairVerdict==='correct'&&!r.latestReview.tierA));
assert(!follow.rows.some(r=>r.asin==='B072JZB85B'||r.queueId===row.queueId));
console.log('Exact 16-row API -> disposable PostgreSQL -> reload/export contracts passed; no provider path. RPC calls:',calls);
