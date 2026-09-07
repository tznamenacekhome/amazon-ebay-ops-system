import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as crypto from "node:crypto";
import ts from "typescript";

const id = "00000000-0000-0000-0000-000000000001";
let launches = [], launchFails = false, task = null;
let refresh = { run_id: id, status: "queued", requested_at: new Date().toISOString(), started_at: null, completed_at: null, task_arn: null, source: "zfi", error_code: null, acquired: true };
let telemetry = null;
let facts = [], selected = [], queried = [];
const db = {
  async rpc(name) { assert.equal(name, "mbop_claim_purchase_ingestion"); return { data: { ...refresh }, error: null }; },
  from(table) {
    queried.push(table);
    let update;
    const result = () => update ? { error: null } : { data: table === "scheduler_runs" ? telemetry : table === "zfi_ebay_purchase_facts" ? facts : { ...refresh }, error: null };
    const q = { select(fields) { selected.push(fields); return q; }, eq() { return q; }, in() { return q; },
      gt() { return q; }, gte() { return q; }, lt() { return q; }, order() { return q; }, limit() { return q; },
      update(value) { update = value; refresh = { ...refresh, ...value }; return q; },
      async maybeSingle() { return result(); }, then(resolve, reject) { return Promise.resolve(result()).then(resolve, reject); } };
    return q;
  },
};
function load(relative, extras = {}) {
  const source = readFileSync(new URL(relative, import.meta.url), "utf8");
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  new Function("require", "exports", output)((name) => {
    if (name === "server-only") return {};
    if (name === "node:crypto") return crypto;
    if (name === "next/server") return { NextResponse: { json: (body, init) => new Response(JSON.stringify(body), init) } };
    if (name.endsWith("/_server")) return { createServerSupabaseClient: () => db, isCloudDeployment: () => true };
    if (name.endsWith("/_awsScheduler")) return {
      readSchedulerTask: async () => task,
      runSchedulerGroupTask: async request => { launches.push(request); if (launchFails) throw new Error("private AWS error"); return { taskArn: "task" }; },
    };
    if (name in extras) return extras[name];
    throw new Error(`Unexpected import: ${name}`);
  }, exports);
  return exports;
}
const savedEnv = { ...process.env };
try {
  process.env.MBOP_ZFI_BUYING_READ_TOKEN = "r".repeat(40);
  process.env.MBOP_ZFI_BUYING_REFRESH_TOKEN = "w".repeat(40);
  process.env.MBOP_ZFI_REFRESH_ENABLED = "true";
  process.env.MBOP_ZFI_PURCHASE_TASK_DEFINITION = "mbop-scheduler-task:99";
  const c = load("./contract.ts");
  const request = (token) => new Request("https://mbop.test/", { headers: { Authorization: `Bearer ${token}` } });
  assert.equal(c.authorize(request("bad")).status, 401);
  assert.equal(c.authorize(request("r".repeat(40))), null);
  assert.equal(c.authorize(request("r".repeat(40)), true).status, 401);
  assert.equal(c.authorize(request("w".repeat(40)), true), null);
  process.env.MBOP_ZFI_BUYING_REFRESH_TOKEN = "r".repeat(40);
  assert.equal(c.authorize(request("r".repeat(40))).status, 503);
  process.env.MBOP_ZFI_BUYING_REFRESH_TOKEN = "w".repeat(40);
  process.env.MBOP_ZFI_REFRESH_ENABLED = "false";
  await assert.rejects(c.requestRefresh(db), /refresh_not_enabled/);
  assert.equal(launches.length, 0);
  process.env.MBOP_ZFI_REFRESH_ENABLED = "true";
  for (const query of ["from=2026-02-30&to=2026-03-01", "from=2024-01-01&to=2026-01-01", "from=2026-01-01&to=2026-02-01&limit=10000", "from=2026-01-01&to=2026-02-01&after=bad"]) {
    assert.throws(() => c.parseFactsQuery(new URL("https://mbop.test/?" + query)));
  }
  const accepted = await c.requestRefresh(db);
  assert.equal(accepted.disposition, "accepted");
  assert.equal(launches[0].group, "purchase-ingestion");
  assert.equal(launches[0].clientToken, id);
  assert.equal(launches[0].taskDefinition, "mbop-scheduler-task:99");
  refresh.status = "running"; refresh.acquired = false;
  assert.equal((await c.requestRefresh(db)).disposition, "already_running");
  assert.equal(launches.length, 1);
  refresh.status = "queued"; refresh.task_arn = null; launchFails = true;
  await c.requestRefresh(db); await c.requestRefresh(db);
  assert.equal(refresh.status, "queued");
  assert.equal(launches.at(-1).clientToken, launches.at(-2).clientToken);
  assert.equal(refresh.error_code, "launch_unconfirmed_retry_post");
  refresh.requested_at = new Date(Date.now() - 31 * 60000).toISOString();
  await assert.rejects(c.requestRefresh(db), /requires_reconciliation/);
  refresh.requested_at = new Date().toISOString();
  telemetry = { status: "ok", finished_at: "2026-09-07T18:00:00Z" };
  assert.equal((await c.readRefresh(id, db)).status, "succeeded");
  refresh.status = "running"; telemetry = { status: "degraded", finished_at: "2026-09-07T18:01:00Z" };
  assert.equal((await c.readRefresh(id, db)).status, "failed");
  refresh.status = "running"; refresh.task_arn = "task"; telemetry = null; task = { lastStatus: "STOPPED", stoppedAt: new Date() };
  assert.equal((await c.readRefresh(id, db)).status, "failed");
  const dto = c.publicRefresh(refresh);
  assert(!("task_arn" in dto)); assert(!("source" in dto));
  const route = load("./purchases/route.ts", { "../contract": c });
  facts = [{ source_purchase_id: id }, { source_purchase_id: "00000000-0000-0000-0000-000000000002" }];
  const req = request("r".repeat(40)); req.nextUrl = new URL("https://mbop.test/?from=2026-01-01&to=2026-02-01&limit=1");
  const response = await route.GET(req);
  const payload = await response.json();
  assert.equal(payload.facts.length, 1); assert.equal(payload.next_cursor, id);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert(selected.includes(c.FIELDS)); assert(!c.FIELDS.includes("raw_import_json"));
  const refreshRoute = load("./refresh/route.ts", { "../contract": c });
  const before = launches.length;
  assert.equal((await refreshRoute.POST(request("r".repeat(40)))).status, 401);
  assert.equal(launches.length, before);
  assert.equal((await refreshRoute.POST(new Request("https://mbop.test/", { method: "POST", headers: { Authorization: `Bearer ${"w".repeat(40)}` }, body: '{"group":"all"}' }))).status, 400);
  console.log("ZFI contract tests passed: authorization, bounded reads, scoped launch, retry idempotency, active run, success/failure/crash status.");
} finally {
  for (const key of Object.keys(process.env)) if (!(key in savedEnv)) delete process.env[key];
  Object.assign(process.env, savedEnv);
}
