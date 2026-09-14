import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

let cursor=0, slots=[], pendingEffects=[];
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
const react={
 useState(initial){const i=cursor++;if(!(i in slots))slots[i]=initial;return [slots[i],v=>slots[i]=typeof v==="function"?v(slots[i]):v];},
 useRef(initial){const i=cursor++;return slots[i]??=( {current:initial} );},
 useCallback(fn,deps){const i=cursor++;if(!same(slots[i]?.deps,deps))slots[i]={fn,deps};return slots[i].fn;},
 useEffect(fn,deps){const i=cursor++;if(!same(slots[i]?.deps,deps)){const old=slots[i];slots[i]={deps};pendingEffects.push(()=>{old?.cleanup?.();slots[i].cleanup=fn();});}},
};
const exports={};
new Function("require","exports",ts.transpileModule(readFileSync(new URL("./useSourcingOpportunities.ts",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(()=>react,exports);
let args=["open","all","","all","all_open","all",true];
const render=()=>{cursor=0;const value=exports.useSourcingOpportunities(...args);pendingEffects.splice(0).forEach(fn=>fn());return value;};
const requests=[];
globalThis.fetch=(url,init)=>new Promise(resolve=>requests.push({url,init,resolve}));
const finish=async(index,id,status=200)=>{requests[index].resolve({ok:status===200,json:async()=>status===200?{opportunities:[{opportunityId:id}],summary:{total:1}}:{error:"Actual error"}});await new Promise(r=>setImmediate(r));};
render();assert.equal(requests.length,1);
args[4]="closest_excluded";render();assert(requests[0].init.signal.aborted);
await finish(1,"closest");await finish(0,"stale");assert.equal(render().rows[0].opportunityId,"closest","Old tab cannot overwrite new tab");
args[4]="all_open";render();await finish(2,"buy");
args[4]="closest_excluded";render();assert.equal(requests.length,3);assert.equal(render().rows[0].opportunityId,"closest","Returning tab uses short cache");
const reload=render().reload();assert.equal(requests.length,4);await finish(3,"updated");await reload;
args[4]="all_open";render();assert.equal(requests.length,5,"Mutation reload invalidates other tabs");await finish(4,"fresh-buy");
args[6]=false;render();assert.equal(requests.length,5,"Inactive panels do not load opportunities");
args[6]=true;render();assert.equal(requests.length,5);
render().removeRows(["fresh-buy"]);assert.equal(render().rows.length,0);
args[4]="closest_excluded";render();assert.equal(requests.length,6,"Removal invalidates other tabs");await finish(5,"",500);assert.equal(render().error,"Actual error");
args[2]="m";render();args[2]="minecraft";render();assert.equal(requests.length,6,"Search is debounced");
await new Promise(r=>setTimeout(r,280));render();assert.equal(requests.length,7);assert(requests[6].url.includes("q=minecraft"));await finish(6,"search");
const realNow=Date.now;Date.now=()=>realNow()+16000;args[2]="";render();await new Promise(r=>setTimeout(r,280));render();assert.equal(requests.length,8,"Expired cache reloads");await finish(7,"expired");Date.now=realNow;
slots.forEach(slot=>slot?.cleanup?.());
console.log("Sourcing hook: cancellation, cache, expiry, mutation invalidation, inactive panels, errors and debounce passed");
