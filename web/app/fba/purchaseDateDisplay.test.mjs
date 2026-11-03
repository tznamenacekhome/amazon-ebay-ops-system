import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");
const tree = ts.createSourceFile("page.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const formatter = tree.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === "formatDate");
assert.ok(formatter);
const js = ts.transpileModule(formatter.getText(tree), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const format = new Function(`${js}; return formatDate;`)();
for (const tz of ["UTC", "America/Los_Angeles", "Pacific/Honolulu"]) {
  process.env.TZ = tz;
  assert.equal(format("2025-04-28"), "04/28/25");
  assert.equal(format("2025-12-21"), "12/21/25");
  assert.equal(format(null), "--");
}
console.log("FBA purchase date display preserves date-only values across timezones.");
