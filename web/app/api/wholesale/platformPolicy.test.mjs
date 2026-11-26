import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url),root=dirname(fileURLToPath(import.meta.url));
const evaluation=(platform)=>({evaluation_id:platform,asin:'EXACT',source_evidence_json:{amazon_title:'Example Quest',amazon_platform:platform}});
let current=evaluation('Game Boy Advance'),writes=0;
const db={from:()=>({select:()=>({in:async()=>({data:[evaluation('Game Boy Advance'),evaluation('Switch'),evaluation('PSP')],error:null}),eq(){return {eq(){return {single:async()=>({data:current,error:null})};}};}})}),rpc:async()=>{writes++;return {data:{ok:true},error:null};}};
const modules=new Map();
function load(file){file=resolve(file);if(modules.has(file))return modules.get(file);const out={};modules.set(file,out);new Function('require','exports',ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>{
 if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status??200,headers:new Headers()})}};
 if(name.endsWith('/_server'))return {createServerSupabaseClient:()=>db,requireAdminApiToken:()=>null};
 if(name.endsWith('.json')){const value=JSON.parse(readFileSync(resolve(dirname(file),name),'utf8'));return {default:value,...value};}
 if(name.startsWith('.'))return load(resolve(dirname(file),name+'.ts'));
 return require(name);
},out);return out;}
const policy=load(resolve(root,'_platformPolicy.ts'));
const rows=['Game Boy Advance','Switch','PSP'].map(id=>({current_evaluation_id:id,opportunity_status:'ready_for_review'}));
const original=JSON.stringify(rows);
assert.deepEqual((await policy.filterWholesalePlatforms(db,rows)).map(r=>r.current_evaluation_id),['Switch','PSP']);
assert.equal(JSON.stringify(rows),original,'No historical/manual workflow mutation');
const route=load(resolve(root,'opportunities/[opportunityId]/actions/route.ts'));
const invoke=()=>route.POST({json:async()=>({action:'add_to_order',evaluationId:'current',quantity:1,requestId:'test-request'})},{params:Promise.resolve({opportunityId:'opportunity'})});
assert.equal((await invoke()).status,409);assert.equal(writes,0,'Cartridge cannot create draft commitment');
current=evaluation('Unknown');assert.equal((await invoke()).status,409);assert.equal(writes,0);
current=evaluation('Switch');assert.equal((await invoke()).status,200);assert.equal(writes,1);
console.log('Wholesale platform eligibility filters before presentation and rejects stale cartridge/unknown draft actions; Switch passes and manual/history records remain unchanged.');
