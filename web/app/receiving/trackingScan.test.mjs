import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(testDir, "trackingScan.ts"), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString(
  "base64"
)}`;
const { isLikelyTrackingScan, normalizeTrackingScan } = await import(moduleUrl);

function candidates(input) {
  return normalizeTrackingScan(input).candidates;
}

assert(candidates("4209302296029400108106244123397059").includes("9400108106244123397059"));
assert(candidates("4209302296029400108106244123397059").includes("96029400108106244123397059"));
assert(candidates("9400108106244123397059").includes("9400108106244123397059"));
assert(candidates("xx1z9999999999999999yy").includes("1Z9999999999999999"));
assert(candidates("123456789012").includes("123456789012"));
assert(candidates("9400-1081-0624-4123-3970-59").includes("9400108106244123397059"));
assert(candidates("9622085030004218180500874318041633").includes("874318041633"));
assert(candidates("9622085030004218180500874324286158").includes("874324286158"));
assert.deepEqual(candidates(""), []);
assert.equal(isLikelyTrackingScan("9622085030004218180500874318041633"), true);
assert.equal(isLikelyTrackingScan("9622085030004218180500874324286158"), true);
assert.equal(isLikelyTrackingScan("874318041633"), true);
assert.equal(isLikelyTrackingScan("18-14871-25169"), false);

console.log("trackingScan tests passed");
