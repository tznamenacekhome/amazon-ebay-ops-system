import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");
const ast = ts.createSourceFile("page.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = ["CostCell", "money", "originalCurrencyCostLabel", "formatCurrency"];
const functions = ast.statements.filter(s => ts.isFunctionDeclaration(s) && names.includes(s.name?.text)).map(s => s.getText(ast)).join("\n");
assert.equal(ast.statements.filter(s => ts.isFunctionDeclaration(s) && names.includes(s.name?.text)).length, names.length);
const out = {};
new Function("require", "exports", ts.transpileModule(functions + "\nexport { CostCell };", { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText)(require, out);
const base = { landedCost: 20, itemPrice: 15, shippingPrice: 5, originalCurrency: null, originalItemPrice: null, originalShippingPrice: null, shippingQuoteStatus: "known", buyingOptions: [], bestOfferEnabled: false };
const render = changes => renderToStaticMarkup(React.createElement(out.CostCell, { row: { ...base, ...changes } }));
assert(render({ buyingOptions: ["FIXED_PRICE"] }).includes("BuyItNow"));
assert(render({ buyingOptions: ["FIXED_PRICE", "BEST_OFFER"] }).includes("Best Offer"));
assert(render({ bestOfferEnabled: true }).includes("Best Offer"));
const auction = render({ buyingOptions: ["AUCTION", "BEST_OFFER"], bestOfferEnabled: true });
assert(auction.includes("Auction")); assert(!auction.includes("Best Offer"));
for (const shippingQuoteStatus of ["unknown_no_cost", "unknown_no_options"]) {
 const html = render({ buyingOptions: ["AUCTION"], shippingQuoteStatus, shippingQuoteLabel: "Shipping unknown" });
 assert(html.includes("Auction")); assert(html.includes("Shipping unknown"));
}
assert(render({ shippingQuoteStatus: "known_free", buyingOptions: ["FIXED_PRICE"] }).includes("Free shipping"));
assert(render({ originalCurrency: "GBP", originalItemPrice: 10, originalShippingPrice: 3, buyingOptions: ["FIXED_PRICE"] }).includes("Orig"));
const authoritative = render({ landedCost: 123.45, itemPrice: 1, shippingPrice: 2 });
assert(authoritative.includes("$123.45")); assert(!authoritative.includes("$3.00"));
assert(!render({}).includes("BuyItNow"), "No listing type is inferred when metadata is missing");
console.log("Cost cell passed: authoritative cost, listing-type precedence, unknown/free shipping, and original currency.");
