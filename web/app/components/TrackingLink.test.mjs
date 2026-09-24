import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { renderToStaticMarkup } from "react-dom/server";

const require = createRequire(import.meta.url);
const source = readFileSync("web/app/components/TrackingLink.tsx", "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const exports = {};
new Function("require", "exports", output)(require, exports);

const { carrierTrackingUrl, TrackingLink } = exports;
assert.equal(
  carrierTrackingUrl("1Z999", "UPS"),
  "https://www.ups.com/track?loc=en_US&tracknum=1Z999"
);
assert.equal(
  carrierTrackingUrl("9400 1000", "USPS"),
  "https://tools.usps.com/go/TrackConfirmAction?tLabels=9400%201000"
);
assert.equal(
  carrierTrackingUrl("123456789012", "FedEx"),
  "https://www.fedex.com/fedextrack/?trknbr=123456789012"
);
assert.equal(
  carrierTrackingUrl("abc", "Unknown", "https://track.example.com/abc"),
  "https://track.example.com/abc"
);
assert(!carrierTrackingUrl("abc", "Unknown", "javascript:alert(1)").startsWith("javascript:"));

const html = renderToStaticMarkup(
  TrackingLink({ trackingNumber: "1Z999", carrier: "UPS" })
);
assert(html.includes("href=\"https://www.ups.com/track?loc=en_US&amp;tracknum=1Z999\""));
assert(html.includes(">1Z999</a>"));

console.log("Tracking links use stored URLs or carrier-specific status pages.");
