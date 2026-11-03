// Read-only production verification of the same resolver used by the APIs.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
const require = createRequire(new URL("../package.json", import.meta.url));
const ts = require("typescript");
const { createClient } = require("@supabase/supabase-js");
const order = process.argv[2];
if (!/^\d{3}-\d{7}-\d{7}$/.test(order || "")) throw new Error("Pass one Amazon order ID.");
if (process.env.SUPABASE_URL !== "https://froeucjkcepuhgwisped.supabase.co") throw new Error("Unexpected target project.");
const db = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false } });
const source = readFileSync(new URL("../app/api/fba-shipments/returnPurchaseBasis.ts", import.meta.url), "utf8");
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const mod = {};
new Function("exports", js)(mod);
const { data, error } = await db.from("amazon_return_recovery_cases")
  .select("amazon_order_id,asin,seller_sku,sku,raw_evidence_json").eq("amazon_order_id", order).limit(10);
if (error) throw error;
if (!data?.length) throw new Error("No return case found.");
const resolved = await mod.resolveReturnPurchaseBases(db, data);
for (const row of resolved) {
  const basis = mod.returnPurchaseBasis(row);
  console.log(JSON.stringify({ amazon_order_id: row.amazon_order_id, seller_sku: row.seller_sku, purchase_basis: basis }));
  if (!basis) throw new Error("Original purchase basis remains unresolved.");
}
