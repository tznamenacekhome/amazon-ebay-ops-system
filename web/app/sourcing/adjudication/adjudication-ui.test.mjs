import assert from 'node:assert/strict';
import {readFileSync,existsSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),state=[];let cursor=0;
function useState(initial){const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];}
const cache=new Map();function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);const out={};cache.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText)(name=>{if(name==='react')return {...require(name),useState};if(name.endsWith('/_supabase'))return {supabase:{rpc:async()=>({data:{revision:'empty',actions:[]},error:null})}};if(name.startsWith('.')){if(name.endsWith('.json'))return JSON.parse(readFileSync(resolve(dirname(file),name)));let f=resolve(dirname(file),name+'.ts');if(!existsSync(f))f=resolve(dirname(file),name+'.tsx');return load(f);}return require(name);},out);return out;}
const service=load('web/app/api/sourcing/adjudication/service.ts'),{AdjudicationEditor}=load('web/app/sourcing/adjudication/page.tsx');const rows=await service.loadQueue();let saved=0,closed=0,stale=false;const payloads=[];
globalThis.window={confirm:()=>true};globalThis.fetch=async(url,opts)=>{assert.equal(url,'/api/sourcing/adjudication');assert.equal(opts.headers['x-mbop-csrf'],'1');payloads.push(JSON.parse(opts.body));return {ok:!stale,status:stale?409:200,json:async()=>stale?{error:'A newer review exists. Reload'}:{}};};
const props={row:rows[0],onClose:()=>closed++,onSaved:async()=>saved++};
function render(){cursor=0;return AdjudicationEditor(props);}
function nodes(el){if(!el||typeof el!=='object')return [];if(typeof el.type==='function')return nodes(el.type(el.props));return [el,...[el.props?.children].flat(Infinity).flatMap(nodes)];}
function control(label){return nodes(render()).find(n=>n.props?.['aria-label']===label);}
function button(label){return nodes(render()).find(n=>n.type==='button'&&n.props.children===label);}
function change(label,value){const n=control(label);assert(n,label);n.props.onChange({target:{value,checked:value}});}
function reset(){state.length=0;stale=false;}
const html=renderToStaticMarkup(render());assert(!html.includes('<img'));assert(html.includes('Unknown'));for(const field of ['Core Game','Installment / Sequel','Generation','Theme','Platform','Edition / Version','Region','Package Contents','Included contents','Assigned release year','Completeness','Digital vs Physical'])assert(html.includes(field),field);
assert.equal(nodes(render()).filter(n=>n.type==='textarea').length,1);assert(button('Confirm Match').props.disabled);
change('Core Game Wrong',true);assert(control('Core Game amazon value'));change('Core Game ebay value','Changed eBay');change('Core Game amazon value','Changed Amazon');assert.equal(state[0].length,2);
button('Undo row').props.onClick();assert.equal(state[0].length,0);assert(control('Core Game Wrong').props.checked);
await button('Incorrect Match').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'incorrect');assert.equal(payloads.at(-1).feedback.corrections.length,0);assert(payloads.at(-1).feedback.flaggedFields.includes('coreGame'));
reset();await button('Incorrect Match').props.onClick();assert.equal(payloads.at(-1).feedback.flaggedFields.length,0);
reset();change('Edition / Version Wrong',true);change('Edition / Version amazon value','Deluxe Edition');const asinBox=nodes(render()).find(n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props['aria-label']);assert(asinBox);asinBox.props.onChange({target:{checked:true}});assert.equal(state[0][0].scope,'asin');await button('Not Sure').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'unsure');
reset();change('Core Game Wrong',true);change('Core Game ebay value','Corrected');await button('Save corrections only').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'not_provided');assert.equal(payloads.at(-1).feedback.corrections[0].scope,'pair');
reset();const attest=nodes(render()).filter(n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props['aria-label']);assert.equal(attest.length,2);attest.forEach(n=>n.props.onChange({target:{checked:true}}));await button('Confirm Match').props.onClick();assert.equal(payloads.at(-1).feedback.pairVerdict,'correct');assert(payloads.at(-1).identityAttested&&payloads.at(-1).variationVerified);
reset();stale=true;const oldClosed=closed;await button('Not Sure').props.onClick();assert.equal(closed,oldClosed);assert(renderToStaticMarkup(render()).includes('Reload'));
reset();mkdirSync('tmp/sourcing-adjudication',{recursive:true});writeFileSync('tmp/sourcing-adjudication/editor.html','<!doctype html><html><body>'+renderToStaticMarkup(render())+'</body></html>');
console.log('Adjudication actual component contracts passed: fields, no photos, wrong/edit/undo, all verdicts, scopes, CSRF, and stale dialog preservation. Saves:',saved);
