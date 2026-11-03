import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("./returnPurchaseBasis.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const mod = {};
new Function("exports", js)(mod);
const basis = { verified: true, asin: "B07FYN3JDL", seller_sku: "1070891208", unit_cost: 35,
  purchase_date: "2025-12-21", supplier: "eBay", supplier_order_id: "25-13983-50117" };
const row = (value = basis) => ({ asin: basis.asin, seller_sku: basis.seller_sku, raw_evidence_json: { purchase_basis: value } });
assert.deepEqual(mod.returnPurchaseBasis(row()), { unitCost: 35, purchaseDate: "2025-12-21", supplier: "eBay", supplierOrderId: "25-13983-50117" });
assert.equal(mod.returnPurchaseBasis({ ...row(), seller_sku: "another-copy" }), null);
for (const patch of [{ verified: false }, { asin: "OTHER" }, { unit_cost: null }, { unit_cost: -1 },
  { unit_cost: "35" }, { unit_cost: Infinity }, { purchase_date: "2025-02-30" }, { purchase_date: "2025-12-21T00:00:00Z" }]) {
  assert.equal(mod.returnPurchaseBasis(row({ ...basis, ...patch })), null);
}
assert.equal(mod.returnPurchaseBasis(row({ ...basis, unit_cost: 0 })).unitCost, 0);
assert.equal(mod.returnPurchaseBasis({ ...row(), raw_evidence_json: null }), null);
console.log("Return purchase basis tests passed: verified exact SKU/ASIN, dates, unknown cost, zero cost.");
