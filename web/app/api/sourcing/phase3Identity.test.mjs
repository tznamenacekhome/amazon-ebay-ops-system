import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url);
function load(source){const exports={};new Function('require','exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText)(require,exports);return exports;}
const python=existsSync('.venv/Scripts/python.exe')?resolve('.venv/Scripts/python.exe'):'python3';
const run=spawnSync(python,['-c',`
import json,sys
sys.path.insert(0,'integrations')
from sourcing_match_rules import evaluate_static_match_rules
from sourcing_decision_trace import enrich_sourcing_diagnostics
cases=json.load(open('tests/fixtures/sourcing_phase3_reviewed.json',encoding='utf8'))['cases']
out=[]
for case in cases:
 seed={'asin':case['asin'],'amazon_title':case['amazon']}
 candidate={'ebay_title':case['ebay'],'raw_ebay_json':{}}
 static=evaluate_static_match_rules(candidate,seed,identity_policy='phase3_shadow')
 diagnostics=enrich_sourcing_diagnostics({'static_rules':static,'recommendation':static['recommendation']},status='rejected',opportunity_type='no_profitable_source_found',profit=1,roi_percent=2)
 out.append({'opportunity':{'asin':case['asin']},'seed':seed,'candidate':candidate,'diagnostics':diagnostics})
print(json.dumps(out))
`],{encoding:'utf8'});
assert.equal(run.status,0,run.stderr);
const {buildDiagnosticComparison}=load(readFileSync(new URL('./diagnosticComparison.ts',import.meta.url),'utf8'));
const page=readFileSync(new URL('../../sourcing/page.tsx',import.meta.url),'utf8');
const start=page.indexOf('function DiagnosticComparisonPanel('),end=page.indexOf('function DismissReasonButtons(');
const {DiagnosticComparisonPanel,summaryStatusForRow}=load(page.slice(start,end)+'\nexport {DiagnosticComparisonPanel,summaryStatusForRow};');
const mappings={core_game_identity:'coreGame',installment_number:'installment',edition_version:'edition',platform_system:'platform',region:'region',package_bundle_contents:'packageType',completeness:'completeness',digital_physical:'digitalPhysical',generation:'generation',theme:'theme'};
let checks=0;
for(const input of JSON.parse(run.stdout)){
 const canonical=input.diagnostics.static_rules.identity_comparison,comparison=buildDiagnosticComparison(input);
 assert.equal(comparison.productIdentityVerdict,canonical.evidenceDecision.productIdentityVerdict);
 for(const [key,field] of Object.entries(mappings)){
  const row=comparison.rows.find(r=>r.key===key);assert(row,key);
  assert.equal(row.comparisonResult,canonical.comparisons[field].result,key);
  const expected={match:'pass',conflict:'fail',review:'warning',unknown:'unknown'}[canonical.comparisons[field].result];
  assert.equal(summaryStatusForRow(row,[],[]),expected,key);checks++;
 }
 const html=renderToStaticMarkup(React.createElement(DiagnosticComparisonPanel,{row:{status:'rejected',diagnosticComparison:comparison,matchingDiagnostics:input.diagnostics},allAssumptionsCorrect:false,failedRuleFamilies:[],onAllCorrectChange(){},onFailedRuleFamiliesChange(){}}));
 assert(html.includes('Product identity:'));
 assert(!html.includes('Base / Standard'));
}
console.log(`${checks} actual Python -> API -> UI indicator comparisons passed; actual panels rendered offline.`);
