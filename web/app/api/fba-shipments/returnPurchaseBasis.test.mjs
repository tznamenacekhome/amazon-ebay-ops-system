import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("./returnPurchaseBasis.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
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

const tables = {
  amazon_sales_orders: [{ amazon_order_id: "sale", purchase_date: "2026-08-31" }],
  amazon_sales_cogs_consumption: [], amazon_sales_profitability: [], purchase_items: [], purchases: [],
  non_ebay_purchase_cogs_sources: [],
  inventorylab_active_inventory_backfill: [{ seller_sku: "1063375674", asin: "B00I6E6SH6",
    active_cost_per_unit: "24.84", active_date_purchased: "2025-04-28", active_supplier: "eBay" }],
};
const queries = [];
const db = { from(table) { return { select() { return { in(key, ids) {
  assert.ok(ids.length > 0 && ids.length <= 100);
  queries.push({ table, key, ids });
  return { async range(start, end) { return { data: (tables[table] || []).filter(r => ids.includes(r[key])).slice(start, end + 1) }; } };
} }; } }; } };
const unresolved = { amazon_order_id: "sale", seller_sku: "1063375674", asin: "B00I6E6SH6", raw_evidence_json: { inspection: { observed_condition: "new" } } };
const resolve = async () => mod.returnPurchaseBasis((await mod.resolveReturnPurchaseBases(db, [unresolved]))[0]);
let result = await resolve();
assert.equal(result.unitCost, 24.84);
assert.equal(result.purchaseDate, "2025-04-28");
assert.equal(result.supplier, "eBay");
// Same-ASIN other SKU is never used; future or conflicting exact-SKU sources fail closed.
tables.inventorylab_active_inventory_backfill.push({ ...tables.inventorylab_active_inventory_backfill[0], seller_sku: "other", active_cost_per_unit: 99 });
assert.equal((await resolve()).unitCost, 24.84);
tables.inventorylab_active_inventory_backfill.push({ ...tables.inventorylab_active_inventory_backfill[0], active_cost_per_unit: 20 });
assert.equal(await resolve(), null);
tables.inventorylab_active_inventory_backfill.pop();
tables.inventorylab_active_inventory_backfill[0].active_date_purchased = "2027-01-01";
assert.equal(await resolve(), null);
tables.inventorylab_active_inventory_backfill[0].active_date_purchased = "2025-04-28";
tables.amazon_sales_profitability = [{ ...unresolved, cogs: 30, quantity: 1 }];
assert.equal(await resolve(), null);
tables.amazon_sales_profitability = [];
// Original purchase allocation outranks the catalog snapshot and preserves consumed cost.
tables.amazon_sales_cogs_consumption = [{ ...unresolved, unit_cogs: "19.00", source_reference_type: "purchase_item", source_reference_id: "item" }];
tables.purchase_items = [{ item_id: "item", purchase_id: "purchase", asin: unresolved.asin, unit_cost: 100 }];
tables.purchases = [{ purchase_id: "purchase", order_date: "2025-10-18", supplier: "eBay", supplier_order_id: "original" }];
result = await resolve();
assert.equal(result.unitCost, 19);
assert.equal(result.purchaseDate, "2025-10-18");
assert.equal(result.supplierOrderId, "original");
// A broken allocation is not replaced with an unrelated same-SKU lot.
tables.purchases = [];
assert.equal(await resolve(), null);
tables.amazon_sales_cogs_consumption = [{ ...unresolved, unit_cogs: "5.99", source_reference_type: "non_ebay_purchase_cogs_source", source_reference_id: "source" }];
tables.non_ebay_purchase_cogs_sources = [{ non_ebay_purchase_cogs_source_id: "source", asin: unresolved.asin, order_date: "2025-01-01", supplier: "Petco" }];
assert.equal((await resolve()).unitCost, 5.99);
assert.equal((await resolve()).supplier, "Petco");
// Existing operator-verified evidence is preserved without any new database reads.
queries.length = 0;
const manual = await mod.resolveReturnPurchaseBases(db, [{ ...row(), amazon_order_id: "manual" }]);
assert.equal(mod.returnPurchaseBasis(manual[0]).unitCost, 35);
assert.equal(queries.length, 0);
await assert.rejects(mod.resolveReturnPurchaseBases({ from() { return { select() { return { in() { return { range: async () => ({ error: { message: "offline" } }) }; } }; } }; } }, [unresolved]), /offline/);
console.log("Automatic return purchase tests passed: exact SKU fallback, original allocations, non-eBay, ambiguity, chronology, preserved overrides, lookup failures.");
