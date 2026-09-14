import assert from 'node:assert/strict';
import {readFileSync,existsSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),state=[];let cursor=0;
function useState(initial){const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText)(name=>{if(name==='react')return {...require(name),useState,useEffect:()=>{}};if(name.endsWith('/_supabase'))return {supabase:{rpc:async()=>({data:{revision:'empty',actions:[]},error:null})}};if(name.startsWith('.')){if(name.endsWith('.json'))return JSON.parse(readFileSync(resolve(dirname(file),name)));let f=resolve(dirname(file),name+'.ts');if(!existsSync(f))f=resolve(dirname(file),name+'.tsx');return load(f);}return require(name);},out);return out;}
const service=load('web/app/api/sourcing/adjudication/service.ts'),{AdjudicationEditor}=load('web/app/sourcing/adjudication/page.tsx');const rows=await service.loadQueue();let saved=0,closed=0,stale=false;const payloads=[];
globalThis.window={confirm:()=>true};globalThis.fetch=async(url,opts)=>{assert.equal(url,'/api/sourcing/adjudication');assert.equal(opts.headers['x-mbop-csrf'],'1');payloads.push(JSON.parse(opts.body));return {ok:!stale,status:stale?409:200,json:async()=>stale?{error:'A newer review exists. Reload'}:{}};};
const props={row:rows.find(r=>r.asin==="B07FF3F7F9"),onClose:()=>closed++,onSaved:async()=>saved++};
function render(){cursor=0;return AdjudicationEditor(props);}
function nodes(el){if(!el||typeof el!=='object')return [];if(typeof el.type==='function')return nodes(el.type(el.props));return [el,...[el.props?.children].flat(Infinity).flatMap(nodes)];}
function control(label){return nodes(render()).find(n=>n.props?.['aria-label']===label);}
function button(label){return nodes(render()).find(n=>n.type==='button'&&n.props.children===label);}
function change(label,value){const n=control(label);assert(n,label);n.props.onChange({target:{value,checked:value}});}
function reset(){state.length=0;stale=false;}
const html=renderToStaticMarkup(render());assert(!html.includes('<img'));assert(html.includes('Not applicable \u2014 single-product listing')); assert(html.includes('Unknown'));for(const field of ['Core Game','Installment / Sequel','Generation','Theme','Platform','Edition / Version','Region','Package Contents','Included contents','Assigned release year','Completeness','Digital vs Physical'])assert(html.includes(field),field);
assert.equal(nodes(render()).filter(n=>n.type==='textarea').length,1);assert(button('Confirm Match').props.disabled);
change('Core Game Wrong',true);assert(control('Core Game amazon value'));change('Core Game ebay value','Changed eBay');change('Core Game amazon value','Changed Amazon');assert.equal(state[0].length,2);
button('Undo row').props.onClick();assert.equal(state[0].length,0);assert(control('Core Game Wrong').props.checked);
await button('Incorrect Match').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'incorrect');assert.equal(payloads.at(-1).feedback.corrections.length,0);assert(payloads.at(-1).feedback.flaggedFields.includes('coreGame'));
reset();await button('Incorrect Match').props.onClick();assert.equal(payloads.at(-1).feedback.flaggedFields.length,0);assert.deepEqual(payloads.at(-1).feedback.corrections,[]);assert.equal(payloads.at(-1).identityAttested,false);assert.equal(payloads.at(-1).variationResolution,undefined);
reset();change('Core Game Wrong',true);change('Core Game ebay value','Corrected product');await button('Incorrect Match').props.onClick();assert.equal(payloads.at(-1).feedback.corrections[0].value,'Corrected product');assert.equal(payloads.at(-1).identityAttested,false);
reset();change('Edition / Version Wrong',true);change('Edition / Version amazon value','Deluxe Edition');const asinBox=nodes(render()).find(n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props['aria-label']);assert(asinBox);asinBox.props.onChange({target:{checked:true}});assert.equal(state[0][0].scope,'asin');await button('Not Sure').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'unsure');
reset();change('Core Game Wrong',true);change('Core Game ebay value','Corrected');await button('Save corrections only').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'not_provided');assert.equal(payloads.at(-1).feedback.corrections[0].scope,'pair');
reset();const attest=nodes(render()).filter(n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props['aria-label']);assert.equal(attest.length,1);attest.forEach(n=>n.props.onChange({target:{checked:true}}));change('Variation scope','not_applicable');await button('Confirm Match').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'correct');assert(payloads.at(-1).identityAttested);assert.equal(payloads.at(-1).variationResolution,'not_applicable');
reset();stale=true;change('Adjudication notes','Keep these unsaved notes');const oldClosed=closed;await button('Incorrect Match').props.onClick();assert.equal(closed,oldClosed);assert(renderToStaticMarkup(render()).includes('A newer review exists. Reload'));assert.equal(control('Adjudication notes').props.value,'Keep these unsaved notes');assert(!button('Incorrect Match').props.disabled);
// Request construction used to escape the catch/finally and silently strand busy state.
reset();const uuid=crypto.randomUUID;crypto.randomUUID=()=>{throw new Error('Cannot prepare request identity');};
await button('Incorrect Match').props.onClick();assert(renderToStaticMarkup(render()).includes('Cannot prepare request identity'));assert(!button('Incorrect Match').props.disabled);crypto.randomUUID=uuid;
// A committed save followed by failed refresh is not a failed write or a retryable POST.
reset();const onSaved=props.onSaved;props.onSaved=async()=>{throw new Error('Queue read failed');};await button('Incorrect Match').props.onClick();assert(renderToStaticMarkup(render()).includes('Incorrect Match saved'));assert(renderToStaticMarkup(render()).includes('Queue read failed'));assert(!button('Retry save'));assert(button('Close saved review'));props.onSaved=onSaved;
// Pending writes are visible, and a lost response retries the identical request.
reset();const normalFetch=globalThis.fetch;let release;globalThis.fetch=()=>new Promise(r=>release=r);const saving=button('Incorrect Match').props.onClick();assert(renderToStaticMarkup(render()).includes('Saving review'));assert(!button('Retry save'));release({ok:false,status:503,json:async()=>({error:'Evidence store unavailable'})});await saving;assert(renderToStaticMarkup(render()).includes('Evidence store unavailable'));assert(button('Retry save'));globalThis.fetch=normalFetch;await button('Retry save').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'incorrect');
reset();assert.equal(control('Platform relationship').props.value,'');assert(!control('Platform amazon value'));
change('Platform relationship','wrong');assert(control('Platform amazon value'));assert(control('Platform ebay value'));
change('Platform ebay value','Xbox One / Xbox Series X');change('Platform relationship','compatible');assert(!control('Platform ebay value'));assert.equal(state[0][0].value,'Xbox One / Xbox Series X');
change('Amazon supported platforms','Xbox One');change('eBay supported platforms','Xbox One, Xbox Series X');await button('Not Sure').props.onClick();assert.equal(payloads.at(-1).feedback.fieldRelationships[0].operatorRelationship,'compatible');assert.equal(payloads.at(-1).feedback.corrections[0].field,'platform');assert.deepEqual(payloads.at(-1).feedback.fieldRelationships[0].compatiblePlatforms.ebay,['Xbox One','Xbox Series X']);
reset();for(const relationship of ['match','compatible','unknown']) {change('Platform relationship',relationship);assert.equal(control('Platform relationship').props.value,relationship);}
const {ListingLinks}=load('web/app/sourcing/adjudication/page.tsx');const helpers=load('web/app/sourcing/adjudication/evidence.ts');
assert.equal(helpers.amazonListingUrl('B07FF3F7F9'),'https://www.amazon.com/dp/B07FF3F7F9');assert.equal(helpers.amazonListingUrl(null),null);
const browse='v1|267725836968|0';assert.equal(helpers.ebayListingUrl(browse),'https://www.ebay.com/itm/267725836968');assert.equal(browse,'v1|267725836968|0');assert.equal(helpers.ebayListingUrl('267725836968'),'https://www.ebay.com/itm/267725836968');for(const id of ['v1|bad|0','junk267725836968','v1|267725836968|bad','javascript:alert(1)'])assert.equal(helpers.ebayListingUrl(id),null);
const links=nodes(ListingLinks({asin:'B07FF3F7F9',ebayItemId:browse})).filter(n=>n.type==='a');assert.equal(links.length,2);assert(links.every(n=>n.props.target==='_blank'&&n.props.rel==='noopener noreferrer'));assert(renderToStaticMarkup(ListingLinks({})).includes('Amazon link unavailable'));assert(renderToStaticMarkup(ListingLinks({})).includes('eBay link unavailable'));
const savedRow=props.row;props.row={...savedRow,latestReview:{...savedRow.latestReview,platformRelationship:{operatorRelationship:'compatible',compatiblePlatforms:{amazon:['Xbox One'],ebay:['Xbox One','Xbox Series X']}}}};reset();assert.equal(control('Platform relationship').props.value,'compatible');assert.equal(control('eBay supported platforms').props.value,'Xbox One, Xbox Series X');await button('Not Sure').props.onClick();assert.equal(payloads.at(-1).feedback.fieldRelationships,undefined,'Unedited relationship must keep its original reviewer/timestamp');props.row=savedRow;
props.row=rows.find(r=>!r.adjudicationEligible);reset();assert(renderToStaticMarkup(render()).includes('Excluded from adjudication / informational only'));assert(nodes(render()).some(n=>n.type==='fieldset'&&n.props.disabled));assert(!button('Confirm Match'));props.row=savedRow;
// The ordinary all-rows dialog must expose the dedicated action; no follow-up-mode prerequisite.
props.row={...savedRow,latestReview:{...savedRow.latestReview,pairVerdict:'correct',actionId:'saved-confirmation',identityAttested:true,notes:'Keep saved notes',feedback:{flaggedFields:['coreGame']}}};props.variationOnly=false;
const scopeFetch=globalThis.fetch;let scopeNotifications=[];const scopeSaved=props.onSaved;
props.onSaved=async(kind,current)=>{scopeNotifications.push({kind,current});};
globalThis.fetch=async(url,opts)=>{
 const p=JSON.parse(opts.body);payloads.push(p);
 const current={revision:'new-scope-revision',latestReview:{...props.row.latestReview,variationResolution:p.variationResolution,variationScopeReviewed:true,tierA:p.variationResolution==='not_applicable'}};
 return {ok:!stale,status:stale?409:200,json:async()=>stale?{error:'A newer review exists. Reload'}:{reviewState:current}};
};
for(const scope of ['not_applicable','verified','unknown']) {
 props.row={...props.row,latestReview:{...props.row.latestReview,variationResolution:scope==='unknown'?'not_applicable':'unknown'}};
 reset();assert.equal(control('Adjudication notes').props.value,'Keep saved notes');assert(control('Core Game Wrong').props.checked);assert(button('Confirm Match'));
 assert(button('Save variation scope').props.disabled);
 const section=nodes(render()).find(n=>n.type==='section'&&n.props['aria-labelledby']==='variation-heading');
 const children=[section.props.children].flat(Infinity).filter(n=>n&&typeof n==='object');
 assert.equal(children[children.findIndex(n=>n.type==='select')+1].props.children,'Save variation scope');
 change('Adjudication notes','Unsaved note must not be sent');change('Core Game ebay value','Unsaved correction must not be sent');
 change('Variation scope',scope);assert(!button('Save variation scope').props.disabled);
 if(scope==='verified')assert(renderToStaticMarkup(render()).includes('No exact variation identifier'));
 const oldClosed=closed;await button('Save variation scope').props.onClick();assert.equal(closed,oldClosed,'Keep dialog open for qualification readback');
 const p=payloads.at(-1);assert.equal(p.reviewKind,'variation_scope');assert.equal(p.variationResolution,scope);assert.equal(p.variationTargetActionId,'saved-confirmation');assert.equal(p.feedback,undefined);assert.equal(p.notes,undefined);assert.equal(p.identityAttested,undefined);
 assert(renderToStaticMarkup(render()).includes('Variation scope saved'));assert(renderToStaticMarkup(render()).includes('Current saved qualification: '+(scope==='not_applicable'?'Tier A':'Not Tier A')));
 assert(button('Save variation scope').props.disabled);assert.equal(control('Adjudication notes').props.value,'Unsaved note must not be sent');
 assert.equal(scopeNotifications.at(-1).kind,'variation_scope');assert.equal(scopeNotifications.at(-1).current.latestReview.variationScopeReviewed,true);
}
reset();stale=true;change('Variation scope','verified');await button('Save variation scope').props.onClick();assert.equal(control('Variation scope').props.value,'verified');assert(renderToStaticMarkup(render()).includes('A newer review exists'));
// A lost scope response retains the exact idempotent request for the dedicated button.
reset();change('Variation scope','verified');const scopeHandler=globalThis.fetch;const retries=[];let failScope=true;
globalThis.fetch=async(url,opts)=>{retries.push(JSON.parse(opts.body));if(failScope){failScope=false;return {ok:false,status:503,json:async()=>({error:'Temporary scope save failure'})};}return scopeHandler(url,opts);};
await button('Save variation scope').props.onClick();assert(renderToStaticMarkup(render()).includes('Temporary scope save failure'));assert(control('Variation scope').props.disabled);assert(!button('Save variation scope').props.disabled);
await button('Save variation scope').props.onClick();assert.deepEqual(retries[0],retries[1]);assert(renderToStaticMarkup(render()).includes('Variation scope saved'));
// Correction-only carries no variation scope even when the dropdown was edited.
reset();globalThis.fetch=scopeFetch;props.onSaved=scopeSaved;change('Variation scope','verified');await button('Save corrections only').props.onClick();assert.equal(payloads.at(-1).variationResolution,undefined);assert.equal(payloads.at(-1).reviewKind,undefined);assert.equal(payloads.at(-1).feedback.pairVerdict,'not_provided');
props.row=savedRow;props.variationOnly=false;
reset();mkdirSync('tmp/adjudication-negative-unit',{recursive:true});writeFileSync('tmp/adjudication-negative-unit/editor.html','<!doctype html><html><body>'+renderToStaticMarkup(render())+'</body></html>');
change('Platform relationship','compatible');change('Amazon supported platforms','Xbox One');change('eBay supported platforms','Xbox One, Xbox Series X');writeFileSync('tmp/adjudication-negative-unit/compatible.html','<!doctype html><html><body>'+renderToStaticMarkup(render())+'</body></html>');
reset();state[0]=rows;cursor=0;const QueuePage=load('web/app/sourcing/adjudication/page.tsx').default;const queueHtml=renderToStaticMarkup(QueuePage());assert(queueHtml.includes('0 of 15 reviewed'));assert.equal((queueHtml.match(/Open Amazon Listing/g)??[]).length,16);assert.equal((queueHtml.match(/Open eBay Listing/g)??[]).length,16);writeFileSync('tmp/adjudication-negative-unit/queue.html','<!doctype html><html><body>'+queueHtml+'</body></html>');
console.log('Adjudication actual component contracts passed: fields, no photos, wrong/edit/undo, all verdicts, scopes, CSRF, and stale dialog preservation. Saves:',saved);
