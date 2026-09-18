import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Exercise the actual page and its effects: the regression was an effect
// reopening the selection after a successful close, not a disabled button.
const require = createRequire(import.meta.url);
const slots = [];
let cursor = 0, dirty = false, pending = [], tree;
const listeners = new Map();
const requests = [];
const row = {item_id:"item",purchase_id:"purchase",supplier_order_id:"23-15127-96456",
  title:"Ghost Recon Breakpoint",system:"Xbox One",quantity:1,current_status:"shipped_no_tracking",
  asin:null,target_price:null,unit_cost:13.99};
globalThis.fetch = async (url, options) => {requests.push({url,options});return {ok:true,json:async()=>[row]};};
globalThis.window = {setTimeout,clearTimeout,addEventListener:(k,v)=>listeners.set(k,v),
  removeEventListener:(k,v)=>{if(listeners.get(k)===v)listeners.delete(k);}};
const same = (a,b) => a && b && a.length===b.length && a.every((v,i)=>Object.is(v,b[i]));
const hooks = {
  useState(initial){const i=cursor++;if(!slots[i])slots[i]={value:typeof initial==="function"?initial():initial};
    return [slots[i].value, v=>{const next=typeof v==="function"?v(slots[i].value):v;
      if(!Object.is(next,slots[i].value)){slots[i].value=next;dirty=true;}}];},
  useRef(value){const i=cursor++;return slots[i]??=( {current:value} );},
  useMemo(fn,deps){const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps))slots[i]={deps,value:fn()};return slots[i].value;},
  useCallback(fn,deps){return hooks.useMemo(()=>fn,deps);},
  useEffect(fn,deps){const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps)){
    const previous=slots[i];slots[i]={deps};pending.push(()=>{previous?.cleanup?.();slots[i].cleanup=fn();});}}
};
const cache = new Map();
function load(file){
  file=resolve(file);if(cache.has(file))return cache.get(file);
  const exports={};cache.set(file,exports);
  const source=readFileSync(file,"utf8");
  const code=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  new Function("require","exports",code)(name=>{
    if(name==="react")return {...require(name),...hooks};
    if(name==="../DataFreshness")return {DataFreshness:()=>null};
    if(name==="./ReceivingMetrics")return {ReceivingMetrics:()=>null};
    if(name.startsWith(".")){let next=resolve(dirname(file),name+".ts");if(!existsSync(next))next=resolve(dirname(file),name+".tsx");return load(next);}
    return require(name);
  },exports);return exports;
}
const Page=load(resolve(dirname(fileURLToPath(import.meta.url)),"page.tsx")).default;
function render(){for(let i=0;i<20;i++){dirty=false;cursor=0;tree=Page();const effects=pending;pending=[];effects.forEach(fn=>fn());if(!dirty)return tree;}throw Error("Effects did not settle");}
function nodes(el=tree){if(!el||typeof el!=="object")return [];return [el,...[el.props?.children].flat(Infinity).flatMap(n=>nodes(n ?? null))];}
function button(text){return nodes().find(n=>n.type==="button"&&[n.props.children].flat(Infinity).includes(text));}
function search(text){nodes().find(n=>n.props?.placeholder?.startsWith("Scan label")).props.onChange({target:{value:text}});render();}
function hasDetail(){return Boolean(nodes().find(n=>n.props?.["aria-label"]==="Close receiving detail without saving"));}
render();await new Promise(r=>setTimeout(r,0));render();
for(const close of ["Cancel","X","Escape"]){
  search("");search(row.supplier_order_id);
  assert(hasDetail());assert(button("Received").props.disabled,"Missing ASIN must block save only");
  if(close==="Escape")listeners.get("keydown")({key:"Escape",preventDefault(){}});
  else if(close==="X")nodes().find(n=>n.props?.["aria-label"]==="Close receiving detail without saving").props.onClick();
  else button("Cancel").props.onClick();
  render();assert(!hasDetail(),close+" must remain closed despite the single matching search result");
  await new Promise(r=>setTimeout(r,140));render();
  assert(!hasDetail(),"Late scan results must not reopen a dismissed detail");
}
// Explicit reopening is still allowed; drafts are discarded rather than saved.
nodes().find(n=>n.type==="tr"&&n.props.onClick).props.onClick();render();assert(hasDetail());
const asin=nodes().find(n=>n.type==="input"&&n.props.placeholder==="ASIN");
assert(asin);asin.props.onChange({target:{value:"UNSAVED"}});render();
button("Cancel").props.onClick();render();
nodes().find(n=>n.type==="tr"&&n.props.onClick).props.onClick();render();
assert.equal(nodes().find(n=>n.type==="input"&&n.props.placeholder==="ASIN").props.value,"");
assert(!requests.some(r=>r.options?.method==="POST"),"Dismissal must never persist receiving data");
console.log("Receiving dismissal regression passed: Cancel, X, Escape, delayed scan, explicit reopen, draft discard, zero writes.");


