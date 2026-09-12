import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url);
const page=readFileSync(new URL('./page.tsx',import.meta.url),'utf8');
const state=[];let cursor=0;
function useState(initial){const index=cursor++;if(!(index in state))state[index]=initial;return [state[index],value=>{state[index]=typeof value==='function'?value(state[index]):value;}];}
const source=`const useState= require('react').useState;
function MatchingReviewControls(){} function DiagnosticComparisonPanel(){} function DismissReasonButtons(){} function ImageClueButtons(){} function Ban(){} function label(v){return v;}
${page.slice(page.indexOf('function DismissOpportunityDialog('),page.indexOf('function BulkDismissOpportunityDialog('))}
export {DismissOpportunityDialog};`;
const out={};new Function('require','exports',ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>name==='react'?{useState}:require(name),out);
const saves=[];let closed=0;
const props={row:{opportunityId:'pair',asin:'TEST',ebayTitle:'Example'},initialDiagnosticsOpen:true,onClose:()=>closed++,onReview:async p=>{saves.push(p);},actionBusyId:null};
function render(){cursor=0;return out.DismissOpportunityDialog(props);}
function nodes(el){if(!el||typeof el!=='object')return [];return [el,...[el.props?.children].flat(Infinity).flatMap(nodes)];}
function named(name){return nodes(render()).find(n=>n.type?.name===name);}
function button(text){return nodes(render()).find(n=>n.type==='button'&&n.props.children===text);}
named('DismissReasonButtons').props.onChoose('roi_too_low');assert.equal(saves.length,0);
named('MatchingReviewControls').props.onVerdict('correct');
named('MatchingReviewControls').props.onEvidence(['primary_image']);
named('MatchingReviewControls').props.onCorrections([{field:'edition',side:'amazon',scope:'pair',state:'unknown',value:null}]);
named('DiagnosticComparisonPanel').props.onFailedRuleFamiliesChange(['edition_version']);
button('Dismiss').props.onClick();
assert.equal(saves[0].reason,'roi_too_low');assert.equal(saves[0].diagnosticsFeedback.pairVerdict,'correct');
assert.deepEqual(saves[0].diagnosticsFeedback.evidenceSources,['primary_image']);assert.equal(saves[0].diagnosticsFeedback.corrections[0].state,'unknown');
assert.deepEqual(saves[0].diagnosticsFeedback.failedRuleFamilies,['edition_version']);
assert.equal(closed,0,'Dialog must not close merely on submit');
button('Confirm Match').props.onClick();assert.equal(saves[1].actionType,'mark_valid_match');assert.equal(saves[1].reason,undefined);
named('MatchingReviewControls').props.onVerdict('unsure');button('Save feedback').props.onClick();assert.equal(saves[2].diagnosticsFeedback.pairVerdict,'unsure');
button('Cancel').props.onClick();assert.equal(closed,1);assert.equal(saves.length,3);
props.saveError='Save failed';assert(nodes(render()).some(n=>n.props?.role==='alert'&&n.props.children==='Save failed'));
console.log('Actual shared dialog handlers passed: reason selection saves nothing; independent verdict/fields/photos/corrections; explicit save; cancel; save failure remains visible.');
