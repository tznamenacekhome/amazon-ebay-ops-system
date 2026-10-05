import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const route = readFileSync(new URL("./opportunities/route.ts", import.meta.url), "utf8");
const start = route.indexOf("function keepaCurrentPriceContext(");
const end = route.indexOf("function hasKeepaOfferData(", start);
assert(start >= 0 && end > start, "Keepa price helper source must be present");

const exports = {};
const source = `${route.slice(start, end)}\nexports.keepaCurrentPriceContext = keepaCurrentPriceContext;`;
new Function(
  "exports",
  ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText,
)(exports);

const base = {
  hasOfferData: false,
  buyBoxCurrent: null,
  buyBoxIsUsed: null,
  buyBoxIsFba: null,
  lowFbaCurrent: null,
  lowFbmCurrent: null,
  lowNewCurrent: null,
  usedCurrent: null,
};

assert.deepEqual(exports.keepaCurrentPriceContext({ ...base, lowNewCurrent: 49.41 }), {
  price: 49.41,
  label: "Low New",
  source: "new",
  fulfillment: null,
  isBuyBox: false,
});
assert.equal(exports.keepaCurrentPriceContext(base).source, "no_data");
assert.equal(
  exports.keepaCurrentPriceContext({ ...base, lowFbaCurrent: 39.99, lowNewCurrent: 49.41 }).source,
  "fba",
);

console.log("Keepa Price now uses generic New fallback after Buy Box/FBA/FBM.");
