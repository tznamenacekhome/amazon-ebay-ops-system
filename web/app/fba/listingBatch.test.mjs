import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
function load(name){const source=readFileSync(new URL(name,import.meta.url),"utf8");const mod={};new Function("exports",ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(mod);return mod;}
const selection=load("./allocationSelection.ts");const batch=load("./listingBatch.ts");
const a="00000000-0000-0000-0000-000000000001",b="00000000-0000-0000-0000-000000000002",c="00000000-0000-0000-0000-000000000003";
const details=[{item_id:a,quantity:3},{item_id:b,quantity:2},{item_id:c,quantity:1,source_type:"amazon_return_recovery",source_status:"Blocked"}];
let q=selection.toggleAsin(details,{},true);assert.deepEqual(q,{[a]:"3",[b]:"2",[c]:"0"});assert.equal(selection.allocationSelection(details,q).checked,true);
q[b]="0";q[a]="1";assert.equal(selection.allocationSelection(details,q).indeterminate,true);
assert.deepEqual(batch.selectedQuantities(q),{[a]:"1"});
const restored=JSON.parse(JSON.stringify(q));assert.deepEqual(batch.selectedQuantities(restored),{[a]:"1"});
q=selection.toggleAsin(details,q,false);assert.deepEqual(batch.selectedQuantities(q),{});assert.equal(selection.allocationSelection(details,q).indeterminate,false);
assert.equal(batch.mfReference("2026-01-17T17:42"),"MF 2026-01-17 05:42 PM");assert.equal(batch.mfReference("2026-01-17T00:01"),"MF 2026-01-17 12:01 AM");
assert.equal(batch.businessLocalNow(new Date("2026-01-18T01:42:00Z")),"2026-01-17T17:42");assert.equal(batch.businessLocalNow(new Date("2026-07-18T00:42:00Z")),"2026-07-17T17:42");
assert.throws(()=>batch.mfReference("2026-02-30T12:00"));assert.throws(()=>batch.selectedQuantities({[a]:"1.5"}));assert.throws(()=>batch.selectedQuantities({[a]:"-1"}));
console.log("Listing selection, draft zeroes, partial quantities, MF reference and Pacific timezone checks passed.");
