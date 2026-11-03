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
