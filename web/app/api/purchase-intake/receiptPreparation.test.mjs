import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const exports = {}; cache.set(file, exports);
  const source = readFileSync(file, 'utf8');
  new Function('require', 'exports', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText)(
    (name) => { assert.ok(name.startsWith('.')); return load(resolve(dirname(file), `${name}.ts`)); }, exports);
  return exports;
}
const { prepareReceipt, chooseReceiptAsin, matchReceiptItems } = load(fileURLToPath(new URL('./receiptPreparation.ts', import.meta.url)));
const product = { title: 'Tilly Tacker 3.7 oz', quantity: 50, line_total: 300, supplier_sku: 'H10030', condition: 'new', system: '', exclude_from_purchase_reporting: false, asin: '', sell_price: '' };
const packing = { ...product, title: 'Packing', quantity: 2, line_total: 10, supplier_sku: 'H11450', exclude_from_purchase_reporting: true };
const original = { currency: 'USD', supplier: 'Rainforest Flora Inc', order_date: '2026-11-04', order_id: 'INV/2026/00714', order_total: 333, shipping: 23, tax: 0, discount: 0, items: [product, packing], cost_basis: 'itemized' };
const prepared = prepareReceipt(original, original);
assert.equal(prepared.items.length, 1); assert.equal(prepared.items[0].quantity, 50);
assert.equal(prepared.other_charges, '10.00'); assert.equal(prepared.charge_lines[0].amount, '10.00');
assert.deepEqual(prepareReceipt(prepared, original), prepared, 'Preparing/reopening must not duplicate charges');
const removed = prepareReceipt({ ...original, items: [product] }, original);
assert.equal(removed.other_charges, '10.00', 'Known removed packing fee is recovered as a charge');
const unknown = prepareReceipt({ ...original, items: [product] }, { ...original, items: [product, { ...packing, title: 'Second product' }] });
assert.equal(unknown.other_charges, '0.00', 'An arbitrary missing product must not become a fee');
const supply = prepareReceipt({ ...original, items: [product, { ...packing, title: 'Packing tape' }] }, null);
assert.equal(supply.items.length, 2, 'Real non-resale supplies stay separate receipt items');
const multiple = prepareReceipt({ ...original, order_total: 343, items: [product, packing, packing] }, original);
assert.equal(multiple.other_charges, '20.00');
assert.deepEqual(prepareReceipt(multiple, original), multiple);
const removedMultiple = prepareReceipt({ ...original, order_total: 343, items: [product] }, { ...original, items: [product, packing, packing] });
assert.equal(removedMultiple.other_charges, '20.00');
const candidate = { asin: 'B092FLB415', title: 'Tilly Tacker, 3.7 oz', system: null };
assert.equal(chooseReceiptAsin(product, [candidate]), 'B092FLB415');
assert.equal(chooseReceiptAsin(product, [candidate, { ...candidate, asin: 'B000000001' }]), null, 'Ambiguous matches stay unresolved');
assert.equal(chooseReceiptAsin({ ...product, title: 'Minecraft', system: 'Switch' }, [{ asin: 'B000000002', title: 'Minecraft', system: 'PS 4' }]), null, 'Never cross game platforms');
assert.equal(chooseReceiptAsin({ ...product, title: 'Minecraft', system: '' }, [{ asin: 'B000000002', title: 'Minecraft', system: 'Switch' }]), null, 'Unknown platform never auto-matches a platform-specific record');
function fakeDb() {
  return { from(table) {
    const rows = table === 'amazon_skus' ? [{ asin: 'B092FLB415', product_name: 'Tilly Tacker, 3.7 oz', listing_price: 31.99 }]
      : table === 'amazon_mf_offers' ? [{ asin: 'B092FLB415', title: 'Tilly Tacker, 3.7 oz' }] : [];
    const builder = { then(resolve) { return Promise.resolve({ data: rows, error: null }).then(resolve); } };
    for (const method of ['select', 'ilike', 'eq', 'order', 'limit', 'not', 'gt']) builder[method] = () => builder;
    return builder;
  } };
}
const matched = await matchReceiptItems(fakeDb(), prepared);
assert.equal(matched.items[0].asin, 'B092FLB415'); assert.equal(matched.items[0].sell_price, 31.99);
const manual = await matchReceiptItems(fakeDb(), { ...prepared, items: [{ ...product, asin: 'B000000003', sell_price: '24.99' }] });
assert.equal(manual.items[0].asin, 'B000000003'); assert.equal(manual.items[0].sell_price, '24.99');
console.log('Receipt packing charges, removed fees, retries, supplies, exact ASIN matching, platform guards and manual prices passed.');
