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
const exports={}; let invalidations=0, preloads=0;
let onChanged=()=>{};
const resources={get:(url)=>fetch(url,{}),invalidate:()=>invalidations++,subscribe:fn=>{onChanged=fn;return ()=>{};},prefetchAfterBuyList:()=>preloads++,getFreshnessError:()=>null,subscribeFreshness:()=>()=>{}};
new Function("require","exports",ts.transpileModule(readFileSync(new URL("./useSourcingOpportunities.ts",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>name==="react"?react:{sourcingResources:resources},exports);
let args=["open","all","","all","all_open","all",true];
const render=()=>{cursor=0;const value=exports.useSourcingOpportunities(...args);pendingEffects.splice(0).forEach(fn=>fn());return value;};
const requests=[];
globalThis.fetch=(url,init)=>new Promise(resolve=>requests.push({url,init,resolve}));
const finish=async(index,id,status=200)=>{requests[index].resolve({ok:status===200,json:async()=>status===200?{opportunities:[{opportunityId:id}],summary:{total:1}}:{error:"Actual error"}});await new Promise(r=>setImmediate(r));};
render();assert.equal(requests.length,1);assert.equal(preloads,0,"No background work before Buy List resolves");
args[4]="closest_excluded";render();
await finish(1,"closest");await finish(0,"stale");assert.equal(render().rows[0].opportunityId,"closest","Old tab cannot overwrite new tab");
args[4]="all_open";render();await finish(2,"buy");assert.equal(preloads,1,"Preload begins only after successful Buy List");
args[6]=false;render();assert.equal(requests.length,3,"Inactive panels do not fetch opportunities");
args[6]=true;render();await finish(3,"buy-again");
const reload=render().reload();assert.equal(invalidations,1);await finish(4,"new");await reload;assert.equal(render().rows[0].opportunityId,"new");
render().removeRows(["new"]);assert.equal(invalidations,2);assert.equal(render().rows.length,0);
const backgroundRefresh=render().refreshInBackground();assert.equal(invalidations,3);assert.equal(render().loading,false,"Post-dismiss refresh keeps the current table rendered");await finish(5,"background");await backgroundRefresh;assert.equal(render().rows[0].opportunityId,"background");
args[2]="m";render();args[2]="minecraft";render();assert.equal(requests.length,6,"Search is debounced");
await new Promise(r=>setTimeout(r,280));render();assert.equal(requests.length,7);assert(requests[6].url.includes("q=minecraft"));await finish(6,"",500);assert.equal(render().error,"Actual error");
args[4]="closest_excluded"; args[7]="profitability"; render();
assert(requests[7].url.includes("exclusionReason=profitability")); await finish(7,"filtered");
onChanged();assert.equal(render().loading,false,"Freshness update retains the rendered table without a loading flash");
assert.equal(render().rows[0].opportunityId,"filtered");await finish(8,"updated");assert.equal(render().rows[0].opportunityId,"updated");
slots.forEach(slot=>slot?.cleanup?.());
console.log("Sourcing hook: Buy List first, stale response isolation, mutation invalidation, inactive panels, errors and debounce passed");
