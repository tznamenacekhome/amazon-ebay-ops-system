import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('./ebayQuota.ts',import.meta.url),'utf8');
const resource={resource:'trading',quota_limit:5000,calls_used:200,remaining:4800,observed_count:180,observed_remaining:4820,
 reset_at:'2099-01-01T08:00:00Z',observed_at:new Date().toISOString(),blocked_until:null,reason:null};
const db={from(name){const q={select(){return q;},eq(){return q;},order(){return q;},limit(){return Promise.resolve({data:name==='ebay_api_resource_limits'?[resource]:[],error:null});}};return q;}};
const out={};new Function('require','exports',ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(()=>({supabase:db}),out);
let result=await out.ebayQuotaOverview();
assert.equal(result.resources.length,1);assert.equal(result.resources[0].locallyReserved,20);
assert.equal(result.resources[0].utilization,4);assert.equal(result.resources[0].status,'Available');
resource.blocked_until='2099-01-01T08:00:00Z';resource.reason='daily_quota_exhausted';
result=await out.ebayQuotaOverview();assert.equal(result.resources[0].status,'Paused');
resource.blocked_until=null;resource.reset_at='2000-01-01T08:00:00Z';
result=await out.ebayQuotaOverview();assert.equal(result.resources[0].status,'Needs quota refresh');

// Existing Buy List deduplication must retain only one actionable listing even
// when the backend preserves several ASIN proposals for that same listing.
const route=readFileSync(new URL('./opportunities/route.ts',import.meta.url),'utf8');
const start=route.indexOf('function dedupeExactEbayListings');
const functions=route.slice(start,route.indexOf('function mergeFlags',start));
const compiled=ts.transpileModule(functions,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const dedupe=new Function(compiled+';return dedupeExactEbayListings;')();
const base={ebayItemId:'v1|123456789012|0',ebayLegacyItemId:'123456789012',ebayUrl:null,status:'open',createdAt:'2026-11-23'};
assert.equal(dedupe([{...base,asin:'B000000001',score:70},{...base,asin:'B000000002',score:90}]).length,1);
console.log('Shared Trading quota display, delayed counters, reset/pause state and competing-ASIN Buy List deduplication passed');
