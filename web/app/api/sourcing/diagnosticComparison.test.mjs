import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
import {renderToStaticMarkup} from 'react-dom/server';
import React from 'react';
const require = createRequire(import.meta.url);
function load(source) {
  const exports = {};
  new Function('require','exports', ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(require,exports);
  return exports;
}
const {buildDiagnosticComparison} = load(readFileSync(new URL('./diagnosticComparison.ts',import.meta.url),'utf8'));
const page = readFileSync(new URL('../../sourcing/page.tsx',import.meta.url),'utf8');
// Render the actual panel and its current helpers; no parallel UI implementation.
const panelSource = page.slice(page.indexOf('function DiagnosticComparisonPanel('),page.indexOf('function DismissReasonButtons('));
const {DiagnosticComparisonPanel,summaryStatusForRow,diagnosticsIdentityRows} = load(panelSource+'\nexport {DiagnosticComparisonPanel,summaryStatusForRow,diagnosticsIdentityRows};');
const input = {
  opportunity:{asin:'EXACT'},seed:{asin:'EXACT',amazon_title:'Dirt PS3'},candidate:{ebay_title:'DiRT 3 PS3'},
  diagnostics:{static_rules:{identity_comparison:{version:'video_game_identity_v1',amazon:{edition:'Base / Standard',completeness:'Complete',digitalPhysical:'Physical'},ebay:{edition:'Base / Standard',completeness:'Complete',digitalPhysical:'Physical'},comparisons:{edition:{result:'match'}}}},
  normalized_evidence:{country_of_origin_values:['Japan'],features_values:['Multiplayer'],format_values:['Blu-ray']}}
};
const comparison = buildDiagnosticComparison(input);
assert.equal(comparison.evaluation.availability,'legacy');
assert.equal(comparison.evaluation.id,null);
assert.equal(comparison.evaluation.evaluatedAt,null);
assert.equal(comparison.productIdentityVerdict,'unknown');
const row = {status:'rejected',diagnosticComparison:comparison,matchingDiagnostics:input.diagnostics};
const visible = diagnosticsIdentityRows(row,comparison.rows);
for(const key of ['core_game_identity','edition_version','installment_number','region','digital_physical']){
  const field = visible.find(x=>x.key===key);assert(field,key);assert.equal(field.ebay,null,key);
  assert.equal(summaryStatusForRow(field,['arbitrary title warning'],[]),'unknown',key);
}
assert.equal(summaryStatusForRow({amazon:'A',ebay:'A',comparisonResult:'review'},[],[]),'warning');
assert.equal(summaryStatusForRow({amazon:'A',ebay:'B',comparisonResult:'conflict'},[],[]),'fail');
assert.equal(summaryStatusForRow({amazon:'A',ebay:'A',comparisonResult:'match'},[],['title warning']),'pass');
const html = renderToStaticMarkup(React.createElement(DiagnosticComparisonPanel,{row,allAssumptionsCorrect:false,failedRuleFamilies:[],onAllCorrectChange(){},onFailedRuleFamiliesChange(){}}));
assert(html.includes('Not identified'));assert(html.includes('Product identity: unknown'));assert(!html.includes('Blu-ray'));assert(!html.includes('Multiplayer'));assert(!html.includes('Japan'));
const changed = buildDiagnosticComparison({...input,opportunity:{asin:'DIFFERENT',amazon_title:'Exact new title'}});
assert.equal(changed.evaluation.metadataMatchesOpportunity,false);
assert.equal(changed.rows.find(x=>x.key==='amazon_title').ebay,'Exact new title');
assert.equal(changed.rows.find(x=>x.key==='platform_system').amazon,null);
console.log('Diagnostic contract and real panel rendering: legacy defaults, unknowns, canonical indicators, unrelated specifics, exact-ASIN change passed.');
