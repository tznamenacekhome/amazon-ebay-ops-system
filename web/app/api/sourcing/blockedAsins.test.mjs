import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("./blockedAsins.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
let failure = false;
const batches = [];
const db = { from(table) {
  assert.equal(table, "sourcing_blocked_asins");
  return { select() { return { async in(column, asins) {
    assert.equal(column, "asin");
    batches.push(asins);
    return failure ? { error: { message: "unavailable" } } : {
      data: asins.filter((asin) => asin === "B001C0L7QI").map((asin) => ({ asin })), error: null,
    };
  } }; } };
} };
const exports = {};
new Function("require", "exports", outputText)((name) => {
  assert.equal(name, "./_supabase");
  return { supabase: db };
}, exports);
const rows = ["open", "watching", "roi_snoozed", "inventory_snoozed"].map((status) => ({ asin: "b001c0l7qi", status }));
rows.push({ asin: "ELIGIBLE01", status: "open" }, { asin: "ELIGIBLE02", status: "watching" });
assert.deepEqual(await exports.excludeBlockedOpportunities(rows), rows.slice(-2));
assert.equal(batches[0].filter((asin) => asin === "B001C0L7QI").length, 1);
batches.length = 0;
const many = Array.from({ length: 205 }, (_, i) => `ASIN${i}`);
many.push("B001C0L7QI");
assert((await exports.fetchBlockedAsins(many)).has("B001C0L7QI"));
assert.deepEqual(batches.map((batch) => batch.length), [100, 100, 6]);
failure = true;
await assert.rejects(exports.excludeBlockedOpportunities(rows), /Could not verify sourcing ASIN eligibility/);
console.log("Blocked opportunity tests passed: open, Watch, snoozed, pagination, fail-closed.");

// Exercise the real POST entry point: stale browser actions must return before
// any mutation, rather than relying solely on the list being filtered.
const actionSource = readFileSync(new URL("./opportunities/[id]/actions/route.ts", import.meta.url), "utf8");
const actionJs = ts.transpileModule(actionSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const actionExports = {};
let currentOpportunity={asin:"B001C0L7QI"};
const opportunityDb = { from() { return { select() { return { eq() { return {
  async single() { return { data: currentOpportunity, error: null }; },
}; } }; } }; } };
new Function("require", "exports", actionJs)((name) => {
  if (name === "next/server") return { NextResponse: { json: (body, options) => ({ body, status: options?.status ?? 200 }) } };
  if (name.endsWith("/blockedAsins")) return exports;
  if (name.endsWith("/platformPolicy")) return platformExports;
  if (name.endsWith("/_supabase")) return { supabase: opportunityDb };
  if (name.endsWith("/_server")) return { requireAdminApiToken: () => null };
  if (name.endsWith("/_asinMetadata")) return { normalizeAsin: (value) => String(value ?? "").toUpperCase() };
  if (name.endsWith("/matchingFeedback")) return { normalizeMatchingFeedback: () => ({}) };
  if (name.endsWith("/reviewActions")) return {reviewActions:new Set(["mark_valid_match"]),saveMatchingReview:async()=>({status:200})};
  return {};
}, actionExports);
failure = false;
for (const actionType of ["watch", "purchased", "snooze_roi", "inventory_snooze", "update_asin"]) {
  const response = await actionExports.POST({ json: async () => ({ actionType, asin: "B001C0L7QI" }) }, { params: Promise.resolve({ id: "existing" }) });
  assert.equal(response.status, 409, actionType);
}
assert.equal((await actionExports.POST({json:async()=>({actionType:"mark_valid_match"})},{params:Promise.resolve({id:"existing"})})).status,200);
failure = true;
assert.equal((await actionExports.POST({ json: async () => ({ actionType: "watch" }) }, { params: Promise.resolve({ id: "existing" }) })).status, 503);
console.log("Stale blocked-ASIN action tests passed: five buying actions rejected; review allowed; lookup failure returns 503.");

const platformExports={};
const policySource=readFileSync(new URL('./platformPolicy.ts',import.meta.url),'utf8');
new Function('require','exports',ts.transpileModule(policySource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText)(name=>({default:JSON.parse(readFileSync(new URL(name,new URL('./platformPolicy.ts',import.meta.url)),'utf8'))}),platformExports);
failure=false;
currentOpportunity={asin:'ELIGIBLE01',status:'open',sourcing_seed_asins:{asin:'ELIGIBLE01',raw_context_json:{inferred_system:'Game Boy Advance'}},matching_diagnostics_json:{recommendation:'Match'}};
for(const actionType of ['watch','purchased','snooze_roi','inventory_snooze']) {
 const response=await actionExports.POST({json:async()=>({actionType})},{params:Promise.resolve({id:'old-cartridge-row'})});
 assert.equal(response.status,409);assert(response.body.error.includes('Cartridge-based platform excluded'));
}
assert.equal((await actionExports.POST({json:async()=>({actionType:'mark_valid_match'})},{params:Promise.resolve({id:'old-cartridge-row'})})).status,200);
console.log('Stale cartridge buying actions fail closed; matching reviews remain available and prior decisions are untouched.');

currentOpportunity.sourcing_seed_asins.raw_context_json.inferred_system='Gamecube';
for(const actionType of ['watch','purchased','snooze_roi','inventory_snooze']){
 const response=await actionExports.POST({json:async()=>({actionType})},{params:Promise.resolve({id:'stale-gamecube-row'})});
 assert.equal(response.status,409);assert(response.body.error.includes('operator sourcing preference'));
}
console.log('Stale GameCube purchasing actions are blocked by explicit operator preference.');
