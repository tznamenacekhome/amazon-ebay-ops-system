import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("./declinedOffers.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
let failure = false;
const batches = [];
const db = { from(table) {
  assert.equal(table, "sourcing_declined_ebay_offers");
  return { select() { return { async in(column, ids) {
    assert.equal(column, "ebay_legacy_item_id");
    batches.push(ids);
    return failure ? { error: { message: "offline" } } : { data: ids.map(id => ({ ebay_legacy_item_id: id, declined_offer_amount: "60.00" })) };
  } }; } };
} };
const mod = {};
new Function("require", "exports", js)(() => ({ supabase: db }), mod);
const row = (max, id = "123") => ({ opportunity_type: "best_offer", max_offer_price: max,
  sourcing_ebay_candidates: { ebay_item_id: `v1|${id}|0`, ebay_legacy_item_id: id, raw_ebay_json: { price: { currency: "USD" } } } });
const declines = new Map([["123", 60]]);
for (const max of [55, 60, null]) assert.equal(mod.isDeclinedOfferSuppressed(row(max), declines), true);
assert.equal(mod.isDeclinedOfferSuppressed(row(60.01), declines), false);
assert.equal(mod.isDeclinedOfferSuppressed(row(65), declines), false);
assert.equal(mod.isDeclinedOfferSuppressed(row(50, "999"), declines), false);
assert.equal(mod.isDeclinedOfferSuppressed({ ...row(60), opportunity_type: "buy_now" }, declines), false);
const variation = row(60); variation.sourcing_ebay_candidates.ebay_item_id = "v1|123|456";
assert.equal(mod.isDeclinedOfferSuppressed(variation, declines), false);
const foreign = row(60); foreign.sourcing_ebay_candidates.raw_ebay_json.price.convertedFromCurrency = "GBP";
assert.equal(mod.isDeclinedOfferSuppressed(foreign, declines), false);
// The same listing on another ASIN/run or Watch is still excluded; higher caps return.
const rows = [{ ...row(60), status: "watching" }, { ...row(60), sourcing_run_id: "new" }, row(65)];
assert.deepEqual(await mod.excludeDeclinedOffers(rows), [rows[2]]);
assert.equal(batches[0].length, 1);
batches.length = 0;
await mod.excludeDeclinedOffers(Array.from({ length: 205 }, (_, i) => row(60, String(i + 1))));
assert.deepEqual(batches.map(b => b.length), [100, 100, 5]);
failure = true;
await assert.rejects(mod.excludeDeclinedOffers([row(60)]), /Could not verify declined eBay offers/);
console.log("Declined offer tests passed: cents boundary, reappearance, identity, currency, Watch, batches, failure.");
