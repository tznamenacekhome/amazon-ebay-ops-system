import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import ts from 'typescript';
const require=createRequire(import.meta.url);
let denied=false,launch=true,launches=0,presentationOk=true,completes=0;
let run={run_id:'run-fixture',status:'evaluated',heartbeat_at:new Date().toISOString(),summary:{}};
let tabs=[{tab_id:'tab-fixture',status:'evaluated',summary:{failed:0}}];
const db={
 async rpc(name){
  if(name==='flipmine_begin')return {data:{run_id:run.run_id,launch},error:null};
  if(name==='flipmine_complete_tab'){completes++;return {data:true,error:null};}
  throw Error(name);
 },
 from(table){let update=null;const query=new Proxy({}, {get(_,key){
  if(key==='then')return resolve=>{
   if(update&&table==='sourcing_flipmine_runs')Object.assign(run,update);
   return Promise.resolve(resolve({data:table==='sourcing_flipmine_runs'?[structuredClone(run)]:structuredClone(tabs),error:null}));
  };
  return (...args)=>{if(key==='update')update=args[0];return query;};
 }});return query;}
};
class Request {constructor(url){this.url=String(url);}}
const presentation={};
new Function('exports',ts.transpileModule(readFileSync(new URL('./presentation.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(presentation);
const route={};
new Function('require','exports',ts.transpileModule(readFileSync(new URL('./route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(name=>{
 if(name==='next/server')return {NextRequest:Request,NextResponse:{json:(data,init)=>Response.json(data,init)}};
 if(name==='../_supabase')return {supabase:db};
 if(name==='../../_server')return {requireAdminApiToken:()=>denied?Response.json({error:'denied'},{status:403}):null,isCloudDeployment:()=>true,isLocalJobExecutionEnabled:()=>false};
 if(name==='../runs/route')return {runAwsSourcingTask:async(id,type)=>{assert.equal(type,'flipmine');launches++;return {taskArn:'fixture-task'};}};
 if(name==='../opportunities/route')return {GET:async()=>presentationOk?Response.json({summary:{total:0}}):Response.json({error:'offline'},{status:503})};
 if(name==='./presentation')return presentation;
 return require(name);
},route);
const request=new Request('https://mbop.test/api/sourcing/flipmine');
denied=true;assert.equal((await route.POST(request)).status,403);assert.equal(launches,0);
denied=false;assert.equal((await route.POST(request)).status,200);assert.equal(launches,1);
launch=false;assert.equal((await route.POST(request)).status,200);assert.equal(launches,1,'Active lease must not launch another task');
run.status='running';await route.GET(request);assert.equal(completes,0,'Never finalize a running worker');
run.status='evaluated';presentationOk=false;let body=await (await route.GET(request)).json();assert.equal(body.run.status,'evaluated');assert.equal(completes,0);
presentationOk=true;body=await (await route.GET(request)).json();assert.equal(body.run.status,'completed');assert.equal(completes,1,'Valid empty presentation completes');
run.status='partial';tabs=[{tab_id:'tab-fixture',status:'partial',summary:{failed:1}}];
body=await (await route.GET(request)).json();assert.equal(body.run.status,'partial');assert.equal(completes,1);
assert(!JSON.stringify(body).includes('spreadsheet_id'));
console.log('Flipmine route: authorization, single launch, pending presentation, valid empty completion and retained partial failure passed.');
