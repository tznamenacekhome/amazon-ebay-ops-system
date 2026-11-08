import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
function module(file,require=()=>{throw Error("Unexpected import");}){const out={};new Function("exports","require",ts.transpileModule(readFileSync(new URL(file,import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(out,require);return out;}
const helpers=module("./listingBatch.ts"),exporter=module("../api/fba-shipments/inventoryLabExport.ts");
const id="00000000-0000-0000-0000-000000000001",item="00000000-0000-0000-0000-000000000002",other="00000000-0000-0000-0000-000000000003";
const detail={item_id:item,purchase_id:other,source_type:"purchase_item",asin:"B07RCCHQLD",amazon_title:"Game",quantity:3,unit_cost:12.34,order_date:"2026-01-01",received_date:"2026-01-05",condition:"new",supplier:"eBay"};
let existing=null,calls=[],preparations=0;
const db={from:()=>({select(){return this;},eq(){return this;},async maybeSingle(){return {data:existing};}}),async rpc(name,args){calls.push({name,args});return {data:{id,export_csv:args.p_csv}};}};
const route=module("../api/amazon-listing-batches/route.ts",name=>{
 if(name==="next/server")return {NextRequest:class{constructor(url){this.url=String(url);}},NextResponse:{json:(body,options)=>({status:options?.status||200,json:async()=>body})}};
 if(name==="../_server")return {createServerSupabaseClient:()=>db,requireAdminApiToken:()=>null};
 if(name==="../fba-shipments/route")return {GET:async()=>{preparations++;return {ok:true,json:async()=>({rows:[{asin:detail.asin,msku:"FBA-ONLY-SKU",title:"Game",system:"PS 4",sell_price:47.99,details:[{...detail},{...detail,item_id:other,unit_cost:20}]}]})};}};
 if(name.endsWith("inventoryLabExport"))return exporter;
 if(name.endsWith("listingBatch"))return helpers;
 throw Error(name);
});
async function request(body){return route.POST({url:"https://mbop.example/api/amazon-listing-batches",json:async()=>({id,local:"2026-01-17T17:42",method:"MF",...body})});}
let response=await request({action:"export",quantities:{[item]:"2",[other]:"0"}});assert.equal(response.status,200);
let call=calls.at(-1);assert.equal(call.args.p_reference,"MF 2026-01-17 05:42 PM");assert.equal(call.args.p_allocations.length,1);assert.equal(call.args.p_allocations[0].quantity,2);assert.equal(call.args.p_allocations[0].purchase_id,other);assert.equal(call.args.p_allocations[0].condition,"new");assert.equal(call.args.p_allocations[0].unit_cost,12.34);assert.ok(!call.args.p_csv.includes("FBA-ONLY-SKU"));assert.ok(call.args.p_csv.includes('"12.34","47.99","2"'));
const csv=call.args.p_csv;calls=[];existing={id,export_csv:csv};const before=preparations;response=await request({action:"export",quantities:{[item]:"99"}});assert.equal(response.status,200);assert.equal((await response.json()).export_csv,csv);assert.equal(preparations,before);assert.equal(calls.length,0);
existing=null;response=await request({action:"draft",quantities:{[item]:"0",[other]:"1"}});assert.equal(response.status,200);assert.deepEqual(calls.at(-1).args.p_selection,{[item]:"0",[other]:"1"});
response=await request({action:"export",quantities:{[item]:"1.5"}});assert.equal(response.status,400);
response=await request({action:"export",quantities:{"00000000-0000-0000-0000-000000000099":"1"}});assert.equal(response.status,400);
console.log("Listing API checks passed: selected allocation snapshots, exact CSV, MF reference, FBA SKU exclusion, draft zeroes, stale/invalid selections, immutable retry.");
