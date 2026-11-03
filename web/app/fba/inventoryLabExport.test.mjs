import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("./inventoryLabExport.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const mod = {};
new Function("exports", js)(mod);
for (const value of [null, undefined, "", "--", "invalid", "2025-02-29", "2026-13-01"]) {
  assert.equal(mod.inventoryLabPurchaseDate(value), "");
}
for (const tz of ["UTC", "America/Los_Angeles", "Pacific/Honolulu"]) {
  process.env.TZ = tz;
  assert.equal(mod.inventoryLabPurchaseDate("2025-12-21"), "12/21/2025");
  assert.equal(mod.inventoryLabPurchaseDate("2024-02-29"), "02/29/2024");
  assert.equal(mod.inventoryLabPurchaseDate("2026-11-02T00:00:00Z"), "11/02/2026");
}
console.log("InventoryLab export date tests passed: missing dates, invalid dates, four-digit years, timezone independence.");
const detail = { item_id: "a", asin: "B07FYN3JDL", amazon_title: "Labo", quantity: 2,
  unit_cost: 35, order_date: "2025-12-21", supplier: "eBay" };
const group = { asin: detail.asin, msku: "existing-sku", title: "Labo", system: "Switch", sell_price: 114.99,
  purchase_date: "2025-01-01", cost_per_unit: 99, details: [detail, { ...detail, item_id: "b", unit_cost: 47.2, order_date: "2025-12-07" }] };
const rows = mod.inventoryLabExportRows([group], { a: "1", b: "2" });
assert.equal(rows.length, 2);
assert.equal(rows[0][4], "35.00");
assert.equal(rows[1][4], "47.20");
assert.equal(rows[0][7], "12/21/2025");
assert.equal(rows[1][7], "12/07/2025");
for (const [field, value, label] of [["unit_cost", null, "purchase cost"], ["order_date", null, "purchase date"],
  ["supplier", "", "supplier"], ["asin", "", "ASIN"], ["amazon_title", "", "title"]]) {
  const changed = { ...detail, [field]: value };
  const testGroup = { ...group, title: field === "amazon_title" ? null : group.title, details: [changed] };
  assert.throws(() => mod.inventoryLabExportRows([testGroup], { a: "1" }), new RegExp(label));
  // An excluded incomplete unit must not block a complete selected unit.
  assert.equal(mod.inventoryLabExportRows([{ ...group, details: [changed, { ...detail, item_id: "b" }] }], { a: "0", b: "1" }).length, 1);
}
assert.equal(mod.inventoryLabExportRows([{ ...group, msku: null }], { a: "1" })[0][1], "");
assert.throws(() => mod.inventoryLabExportRows([{ ...group, sell_price: null }], { a: "1" }), /list price/);
for (const value of ["-1", "1.5", "3", "bad"]) assert.throws(() => mod.inventoryLabExportRows([group], { a: value }), /quantity/);
assert.throws(() => mod.inventoryLabExportRows([group], {}), /at least one/);
assert.equal(mod.inventoryLabExportRows([{ ...group, details: [{ ...detail, unit_cost: 0 }] }], { a: "1" })[0][4], "0.00");
// MSKU and FNSKU are optional for listings InventoryLab will create.
console.log("InventoryLab export gate tests passed: every selected source, no averaging, required fields, optional MSKU/FNSKU, excluded rows.");
