import assert from 'node:assert/strict';
import {readFileSync,existsSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
const state=[];let cursor=0;
function useState(initial){const index=cursor++;if(!(index in state))state[index]=typeof initial==='function'?initial():initial;return [state[index],value=>{state[index]=typeof value==='function'?value(state[index]):value;}];}
const cache=new Map();
function load(file){file=resolve(file);if(cache.has(file))return cache.get(file);let source=readFileSync(file,'utf8');if(file.endsWith('page.tsx'))source+='\nexport {DismissOpportunityDialog,DismissReasonButtons,BulkDismissOpportunityDialog};';const out={};cache.set(file,out);new Function('require','exports',ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{if(name==='react')return {...require(name),useState};if(name.startsWith('.')){let next=resolve(dirname(file),name+'.ts');if(!existsSync(next))next=resolve(dirname(file),name+'.tsx');return load(next);}return require(name);},out);return out;}
const {DismissOpportunityDialog,DismissReasonButtons,BulkDismissOpportunityDialog}=load('web/app/sourcing/page.tsx');
const {buildDiagnosticComparison}=load('web/app/api/sourcing/diagnosticComparison.ts');
const {incorrectMatchReason}=load('web/app/sourcing/reviewFields.ts');
const fixture=JSON.parse(readFileSync('tests/fixtures/sourcing_review_prey.json','utf8'));
const saves=[];let closed=0,confirmDiscard=false;
globalThis.window={confirm:()=>confirmDiscard};
const props={row:{opportunityId:'pair',asin:fixture.opportunity.asin,ebayTitle:fixture.candidate.ebay_title,diagnosticComparison:buildDiagnosticComparison(fixture)},initialDiagnosticsOpen:false,onClose:()=>closed++,onReview:async p=>saves.push(p),actionBusyId:null};
function render(){cursor=0;return DismissOpportunityDialog(props);}
function nodes(el,expand=false){if(!el||typeof el!=='object')return [];if(expand&&typeof el.type==='function')return nodes(el.type(el.props),expand);return [el,...[el.props?.children].flat(Infinity).flatMap(n=>nodes(n,expand))];}
function named(name){return nodes(render()).find(n=>n.type?.name===name);}
function button(text){return nodes(render(),true).find(n=>n.type==='button'&&n.props.children===text);}
function control(aria){return nodes(render(),true).find(n=>n.props?.['aria-label']===aria);}
function change(aria,value){const n=control(aria);assert(n,aria);n.props.onChange({target:{value,checked:value}});}
const before=renderToStaticMarkup(render());
assert(!before.includes('Wrong Platform'));assert(!before.includes('Wrong Edition / Version'));
assert(before.includes('Product Comparison'));assert(!before.includes('Why MBOP'));assert(!before.includes('Matching Summary'));assert(!before.includes('Correct Details'));assert(!before.includes('<img'));assert(!before.includes('images available'));
for(const label of ['Core Game','Installment / Sequel','Edition / Version','Platform','Region'])assert(before.includes(label));
assert.equal(nodes(render(),true).filter(n=>n.type==='textarea').length,1,'Only Notes editable initially');
const historical=renderToStaticMarkup(DismissReasonButtons({busy:false,onChoose(){}}));assert(historical.includes('Wrong Platform'));assert(historical.includes('Wrong Edition / Version'));
named('DismissReasonButtons').props.onChoose('roi_too_low');assert.equal(saves.length,0);
change('Core Game Wrong',true);assert.equal(nodes(render(),true).filter(n=>n.type==='textarea').length,3);
change('Core Game ebay value',fixture.corrections.ebay);assert.equal(named('MatchingReviewControls').props.corrections.length,1);assert.equal(named('MatchingReviewControls').props.corrections[0].side,'ebay');
change('Core Game amazon value',fixture.corrections.amazon);assert.equal(named('MatchingReviewControls').props.corrections.length,2);
change('Core Game Wrong',false);assert.equal(control('Core Game Wrong').props.checked,true);assert.equal(control('Core Game ebay value').props.value,fixture.corrections.ebay);
confirmDiscard=true;change('Core Game Wrong',false);assert.equal(named('MatchingReviewControls').props.corrections.length,0);assert(!control('Core Game ebay value'));
change('Core Game Wrong',true);change('Core Game ebay value','');assert.equal(named('MatchingReviewControls').props.corrections[0].state,'unknown');
change('Core Game ebay state','not_applicable');assert.equal(named('MatchingReviewControls').props.corrections[0].state,'not_applicable');
button('Undo row').props.onClick();assert.equal(control('Core Game ebay value').props.value,'Prey');assert.equal(named('MatchingReviewControls').props.corrections.length,0);
button('Save feedback').props.onClick();assert.equal(saves.at(-1).diagnosticsFeedback.pairVerdict,'not_provided');assert.deepEqual(saves.at(-1).diagnosticsFeedback.failedRuleFamilies,['core_game_identity']);assert.equal(saves.at(-1).diagnosticsFeedback.corrections.length,0);
change('Core Game amazon value',fixture.corrections.amazon);change('Core Game ebay value',fixture.corrections.ebay);
const after=renderToStaticMarkup(render());button('Incorrect Match').props.onClick();const preyPayload=saves.at(-1);
assert.equal(preyPayload.actionType,'dismiss');assert.equal(preyPayload.reason,'wrong_product');assert.equal(preyPayload.diagnosticsFeedback.pairVerdict,'incorrect');assert.equal(preyPayload.diagnosticsFeedback.corrections.length,2);assert.equal(preyPayload.diagnosticsFeedback.corrections.find(c=>c.side==='ebay').value,fixture.corrections.ebay);assert(!preyPayload.diagnosticsFeedback.allAssumptionsCorrect);
button('Confirm Match').props.onClick();assert.equal(saves.at(-1).diagnosticsFeedback.pairVerdict,'correct');assert.equal(saves.at(-1).diagnosticsFeedback.corrections.length,2);
button('Save feedback').props.onClick();assert.equal(saves.at(-1).diagnosticsFeedback.pairVerdict,'not_provided');
change('Product pair verdict','unsure');button('Save feedback').props.onClick();assert.equal(saves.at(-1).diagnosticsFeedback.pairVerdict,'unsure');
props.saveError='Stale pairing';assert(renderToStaticMarkup(render()).includes('Stale pairing'));assert.equal(control('Core Game ebay value').props.value,fixture.corrections.ebay);
button('Cancel').props.onClick();assert.equal(closed,1);
state.length=0;props.saveError=null;button('Incorrect Match').props.onClick();assert.equal(saves.at(-1).reason,'wrong_product');assert.deepEqual(saves.at(-1).diagnosticsFeedback.failedRuleFamilies,[]);assert.deepEqual(saves.at(-1).diagnosticsFeedback.corrections,[]);
for(const [families,reason] of [[['platform'],'wrong_platform'],[['edition_version'],'wrong_edition_version'],[['platform','edition_version'],'wrong_product'],[[],'wrong_product']])assert.equal(incorrectMatchReason(families),reason);
props.row.latestReview={pairVerdict:'correct',corrections:preyPayload.diagnosticsFeedback.corrections.map(c=>({...c,actionId:'prior',recordedAt:'2026-09-13T00:00:00Z'}))};
assert(renderToStaticMarkup(render()).includes('Operator correction'));change('Core Game Wrong',true);assert.equal(control('Core Game ebay value').props.value,fixture.corrections.ebay);assert.equal(named('MatchingReviewControls').props.corrections.length,0);change('Core Game ebay value',fixture.corrections.ebay+' Updated');assert.equal(named('MatchingReviewControls').props.corrections.length,1);assert.equal(named('MatchingReviewControls').props.corrections[0].before.actionId,'prior');
props.row={...props.row,ebayTitle:'Prey Xbox 360 Sealed',latestReview:null,diagnosticComparison:buildDiagnosticComparison({...fixture,candidate:{...fixture.candidate,ebay_title:'Prey Xbox 360 Sealed'}})};state.length=0;change('Core Game Wrong',true);change('Core Game amazon value','Prey');const valid=renderToStaticMarkup(render());button('Confirm Match').props.onClick();assert.equal(saves.at(-1).diagnosticsFeedback.pairVerdict,'correct');
const page=readFileSync('web/app/sourcing/page.tsx','utf8');assert(page.includes('if (selectedRows.length === 1)'));assert(page.includes('activeTab === "Buy List" || activeTab === "Closest Excluded" || activeTab === "Business Excluded" ? setDismissRow'));const bulk=page.slice(page.indexOf('function BulkDismissOpportunityDialog('),page.indexOf('function DiagnosticComparisonPanel('));assert(!bulk.includes('MatchingReviewControls'));
mkdirSync('tmp/sourcing-review-ui',{recursive:true});for(const [name,html] of Object.entries({before,prey:after,valid}))writeFileSync(`tmp/sourcing-review-ui/${name}-component.html`,html);writeFileSync('tmp/sourcing-review-ui/prey-payload.json',JSON.stringify(preyPayload,null,2));
console.log('Actual dialog and row controls passed: toggles/paste/side edits/undo/discard/unknowns; negative/positive/unchanged/unsure; saved overlays; three views/single selection; bulk isolation; no photos/duplicate panels.');

state.length=0;cursor=0;let bulkSaved=null;const bulkTree=BulkDismissOpportunityDialog({rows:[props.row,{...props.row,asin:"OTHER"}],busy:false,onClose(){},onBlockAsins(){},onDismiss:(...args)=>bulkSaved=args});nodes(bulkTree).find(n=>n.type?.name==="DismissReasonButtons").props.onChoose("wrong_platform");assert.deepEqual(bulkSaved,["wrong_platform","",[]]);

state.length=0;props.row.diagnosticComparison.rows.find(r=>r.key==="core_game_identity").amazonEvidence={state:"conflicting_sources"};props.row.diagnosticComparison.rows.find(r=>r.key==="core_game_identity").amazon=null;change("Core Game Wrong",true);assert.equal(control("Core Game amazon state").props.value,"unknown");assert.equal(named("MatchingReviewControls").props.corrections.length,0);
