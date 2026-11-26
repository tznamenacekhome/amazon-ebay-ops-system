import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import ts from 'typescript';
const out={};
new Function('require','exports',ts.transpileModule(readFileSync(new URL('./platformPolicy.ts',import.meta.url),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText)(name=>({default:JSON.parse(readFileSync(new URL(name,new URL('./platformPolicy.ts',import.meta.url)),'utf8'))}),out);
const {sourcingPlatformEligibility:eligibility,platformOpportunityAllowed:allowed}=out;
const policy=JSON.parse(readFileSync(new URL('../../../lib/sourcingPlatformPolicy.json',import.meta.url),'utf8'));
const seed=(system,format)=>({asin:'B000TEST00',amazon_title:'Example Quest',system,raw_context_json:{amazon_catalog_identity:{asin:'B000TEST00',normalized_platform:system,normalized_format:format}}});
const cases=[];
for(const system of [...policy.excludedCartridgePlatforms,...policy.explicitExcludedPlatforms]){const s=seed(system,'dvd_rom');assert.equal(eligibility(s).result,'blocked');assert.equal(allowed({sourcing_seed_asins:s,status:'open',matching_diagnostics_json:{recommendation:'Match'}}),false);cases.push({seed:s});}
for(const system of [...policy.explicitEligiblePlatforms,...policy.discOrComputerPlatforms]){const s=seed(system,system==='PSP'?'UMD':null);assert.equal(eligibility(s).result,'pass',system);cases.push({seed:s});}
for(const system of policy.mixedFormatPlatforms)for(const [format,result]of [[null,'unresolved'],['cartridge','blocked'],['CD-ROM','unresolved']]){const s=seed(system,format);assert.equal(eligibility(s).result,result);cases.push({seed:s});}
for(const system of policy.mixedFormatPlatforms){const s=seed(system,'CD-ROM');s.raw_context_json.amazon_catalog_identity.relevant_attributes_json={physical_format:'CD-ROM'};assert.equal(eligibility(s).result,'pass');cases.push({seed:s});}
for(const system of ['Nintendo Game Boy Advance','Mega Drive','Nintendo 3DS / Nintendo Switch','SNES','Unknown'])cases.push({seed:seed(system)});
assert.equal(eligibility(seed('Unknown')).result,'unresolved');
const captures=JSON.parse(readFileSync(new URL('../../../../tests/fixtures/typed_metadata_phase1_20261125.json',import.meta.url),'utf8'));
cases.push(...captures.map(r=>({seed:r.seed,candidate:r.candidate})));
const root=fileURLToPath(new URL('../../../../',import.meta.url));
const run=spawnSync(resolve(root,'.venv/Scripts/python.exe'),['-c',`import sys,json;sys.path.insert(0,'integrations');from sourcing_platform_policy import platform_eligibility;print(json.dumps([platform_eligibility(r['seed'],r.get('candidate')) for r in json.load(sys.stdin)]))`],{cwd:root,input:JSON.stringify(cases),encoding:'utf8'});
assert.equal(run.status,0,run.stderr);
JSON.parse(run.stdout).forEach((expected,index)=>{const actual=eligibility(cases[index].seed,cases[index].candidate);assert.equal(actual.result,expected.result,JSON.stringify(cases[index]));assert.deepEqual([...actual.platforms].sort(),expected.platforms);});
const mario=captures.find(r=>r.row===238);assert.equal(eligibility(mario.seed,mario.candidate).result,'blocked');
console.log(`${cases.length} actual/synthetic Python-server policy parity checks passed; Switch/disc/UMD preserved, cartridge/unknown/mixed cases fail closed.`);
