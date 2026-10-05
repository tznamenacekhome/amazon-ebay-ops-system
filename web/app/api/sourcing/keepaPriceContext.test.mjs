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

const helperExports = {};
const helperSource = `${route.slice(start, end)}\nexports.lowestLiveNewOfferPrice = lowestLiveNewOfferPrice;`;
new Function(
  "exports",
  ts.transpileModule(helperSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText,
)(helperExports);
assert.equal(helperExports.lowestLiveNewOfferPrice({ offers: [{ condition: 1, isFBA: true, isShippable: true, offerCSV: [8286419, 3999, 0] }] }, true), 39.99);
assert.equal(helperExports.lowestLiveNewOfferPrice({ offers: [{ condition: 1, isFBA: false, isShippable: true, offerCSV: [8285166, 7210, 1020] }] }, false), 82.3);
assert.equal(helperExports.lowestLiveNewOfferPrice({ offers: [{ condition: 2, isFBA: true, isShippable: true, offerCSV: [8286419, 2599, 0] }] }, true), null);

console.log("Keepa Price now uses generic New fallback after Buy Box/FBA/FBM.");
