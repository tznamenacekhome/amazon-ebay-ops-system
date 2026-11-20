import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("../api/amazonSkuIdentity.ts", import.meta.url), "utf8");
const api = {};
new Function("exports", ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText)(api);
for (const value of ["DEFAULT", "MFN", "MF", "FBM", "MERCHANT_NA"]) assert.equal(api.fulfillmentMethod(value), "MF");
for (const value of ["Amazon", "AMAZON_NA", "AFN", "FBA"]) assert.equal(api.fulfillmentMethod(value), "FBA");
assert.equal(api.fulfillmentMethod("AMAZON_NA,DEFAULT"), null);
const mappings = [
  { asin: "ASIN", seller_sku: "FBA-SKU", fulfillment_method: "FBA", condition: "11" },
  { asin: "ASIN", seller_sku: "MF-SKU", fulfillment_method: "MF", condition: "new_new" },
];
assert.equal(api.resolveListingSku(mappings, "ASIN", "FBA", "new"), "FBA-SKU");
assert.equal(api.resolveListingSku(mappings, "ASIN", "MF", "11"), "MF-SKU");
assert.equal(api.resolveListingSku(mappings, "ASIN", "MF", "unknown"), "MF-SKU");
assert.equal(api.resolveListingSku(mappings.slice(0, 1), "ASIN", "MF", "new"), null);
assert.equal(api.resolveListingSku([...mappings, { ...mappings[1], seller_sku: "MF-OTHER" }], "ASIN", "MF", "new"), null);
console.log("Fulfillment-scoped MSKU selection, DEFAULT normalization, conditions, missing and ambiguous mappings passed.");
