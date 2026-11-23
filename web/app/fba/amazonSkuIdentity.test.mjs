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
assert.equal(api.resolveMfExportSku(mappings, "ASIN", "new"), "MF-SKU");
assert.equal(api.resolveMfExportSku(mappings.slice(0, 1), "ASIN", "new"), "MF-FBA-SKU");
const generated = api.resolveMfExportSku([], "B07FYN3JDL", "new");
assert.match(generated, /^MF-\d+$/);
assert.ok(generated.length <= 40);
assert.equal(api.resolveMfExportSku([], "B07FYN3JDL", "11"), generated);
assert.notEqual(api.resolveMfExportSku([], "B07FYN3JDL", "used_good"), generated);
assert.notEqual(api.resolveMfExportSku([], "B07FYN3JDM", "new"), generated);
assert.throws(() => api.resolveMfExportSku([...mappings, { ...mappings[1], seller_sku: "OTHER" }], "ASIN", "new"), /Multiple MF/);
assert.throws(() => api.resolveMfExportSku([{ ...mappings[0], seller_sku: "X".repeat(38) }], "ASIN", "new"), /40-character/);
assert.throws(() => api.resolveMfExportSku([{ ...mappings[0], asin: "OTHER", seller_sku: generated }], "B07FYN3JDL", "new"), /conflicts/);
console.log("MF export fallback, stable numeric SKUs, condition separation, ambiguity and collision checks passed.");
