import "server-only";
import { createHash, timingSafeEqual, randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { createServerSupabaseClient, isCloudDeployment } from "../../../_server";
import { readSchedulerTask, runSchedulerGroupTask } from "../../../_awsScheduler";

export const VERSION = "2026-09-07";
export const FIELDS = "contract_version,source_purchase_id,ebay_order_id,purchase_date,date_needs_review,cost_currency,unit_count,recorded_unit_count,excluded_unit_count,acquisition_cost_total,recorded_acquisition_cost_total,cost_needs_review,exclusion_status,purchase_status,source_purchase_count,source_item_count,manual_split_item_count,cost_basis,refund_amount,refund_status,source_updated_at";
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const REQUESTS = "mbop_purchase_ingestion_requests";
const requestFields = "run_id,status,requested_at,started_at,completed_at,task_arn,source,error_code";
export function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

export function authorize(request: Request, write = false) {
  if (process.env.MBOP_ZFI_BUYING_READ_TOKEN && process.env.MBOP_ZFI_BUYING_READ_TOKEN === process.env.MBOP_ZFI_BUYING_REFRESH_TOKEN) {
    return json({ error: "distinct_credentials_required" }, 503);
  }
  const names = write ? ["MBOP_ZFI_BUYING_REFRESH_TOKEN"] : ["MBOP_ZFI_BUYING_READ_TOKEN", "MBOP_ZFI_BUYING_REFRESH_TOKEN"];
  const keys = names.map(name => process.env[name] || "").filter(key => key.length >= 32);
  const supplied = request.headers.get("authorization")?.match(/^Bearer ([^\s]+)$/i)?.[1] || "";
  const digest = (value: string) => createHash("sha256").update(value).digest();
  if (!keys.length) return json({ error: "integration_not_configured" }, 503);
  if (!supplied || !keys.some(key => timingSafeEqual(digest(key), digest(supplied)))) return json({ error: "unauthorized" }, 401);
  return null;
}

export function parseFactsQuery(url: URL) {
  const date = (value: string | null) => value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value ? value : null;
  const from = date(url.searchParams.get("from"));
  const to = date(url.searchParams.get("to"));
  const limitText = url.searchParams.get("limit") || "200";
  const after = url.searchParams.get("after");
  if (!from || !to || to <= from || Date.parse(to) - Date.parse(from) > 93 * 86400000
      || !/^\d+$/.test(limitText) || +limitText < 1 || +limitText > 500 || (after && !UUID.test(after))) {
    throw new Error("Use from/to YYYY-MM-DD (exclusive to, maximum 93 days), limit 1-500, and optional UUID after.");
  }
  return { from, to, limit: +limitText, after };
}

export type Refresh = { run_id: string; status: string; requested_at: string; started_at: string | null;
  completed_at: string | null; task_arn: string | null; source: string; error_code: string | null; acquired?: boolean };
export function publicRefresh(row: Refresh) {
  return { contract_version: VERSION, run_id: row.run_id, status: row.status,
    requested_at: row.requested_at, started_at: row.started_at, completed_at: row.completed_at,
    error_code: row.error_code,
    result_summary: row.status === "succeeded" ? "Purchase ingestion and sourcing purchase matching completed; purchase facts can be read now."
      : row.status === "failed" ? "Purchase ingestion did not complete successfully. Consult MBOP System Health."
      : "Purchase refresh is pending completion.",
    status_url: `/api/integrations/zfi/buying/refresh/${row.run_id}` };
}

export function finalStatus(schedulerStatus: string | undefined, stopped: boolean) {
  if (schedulerStatus === "ok") return "succeeded";
  if (["failed", "degraded", "blocked", "cancelled"].includes(schedulerStatus || "")) return "failed";
  return stopped ? "failed" : null;
}

export async function readRefresh(runId: string, db = createServerSupabaseClient()) {
  const result = await db.from(REQUESTS).select(requestFields).eq("run_id", runId).maybeSingle();
  if (result.error) throw new Error("status_unavailable");
  if (!result.data) return null;
  let row = result.data as Refresh;
  if (!["queued", "running"].includes(row.status)) return row;
  const telemetry = await db.from("scheduler_runs").select("status,started_at,finished_at,ecs_task_arn")
    .eq("run_id", runId).maybeSingle();
  if (telemetry.error) throw new Error("status_unavailable");
  const taskArn = row.task_arn || telemetry.data?.ecs_task_arn;
  const task = taskArn ? await readSchedulerTask(taskArn) : null;
  const status = finalStatus(telemetry.data?.status, task?.lastStatus === "STOPPED");
  if (status) {
    const update = { status, completed_at: telemetry.data?.finished_at || task?.stoppedAt?.toISOString() || new Date().toISOString(),
      error_code: status === "failed" ? "purchase_ingestion_failed" : null };
    const saved = await db.from(REQUESTS).update(update).eq("run_id", runId).in("status", ["queued", "running"]);
    if (saved.error) throw new Error("status_unavailable");
    row = { ...row, ...update };
  }
  return row;
}

export async function requestRefresh(db = createServerSupabaseClient()) {
  if (!isCloudDeployment() || process.env.MBOP_ZFI_REFRESH_ENABLED !== "true") throw new Error("refresh_not_enabled");
  const definition = process.env.MBOP_ZFI_PURCHASE_TASK_DEFINITION || "";
  if (!/mbop-scheduler-task:\d+$/.test(definition)) throw new Error("pinned_scheduler_required");
  const claimed = await db.rpc("mbop_claim_purchase_ingestion", { p_run_id: randomUUID() });
  if (claimed.error || !claimed.data) throw new Error("refresh_reservation_unavailable");
  let row = claimed.data as Refresh;
  if (row.status === "running" || row.task_arn) return { ...publicRefresh(row), disposition: "already_running" };
  if (Date.now() - Date.parse(row.requested_at) > 30 * 60000) throw new Error("queued_run_requires_reconciliation");
  // A lost launch response is retried with the same ECS client token. Never
  // release the reservation on ambiguous transport failures.
  try {
    const task = await runSchedulerGroupTask({ group: "purchase-ingestion", source: "zfi-buying", job: "purchase-ingestion",
      runId: row.run_id, clientToken: row.run_id, taskDefinition: definition });
    const saved = await db.from(REQUESTS).update({ task_arn: task.taskArn, error_code: null })
      .eq("run_id", row.run_id).in("status", ["queued", "running"]);
    if (saved.error) throw new Error("launch_record_unconfirmed");
  } catch {
    await db.from(REQUESTS).update({ error_code: "launch_unconfirmed_retry_post" }).eq("run_id", row.run_id).eq("status", "queued");
    row = { ...row, error_code: "launch_unconfirmed_retry_post" };
  }
  return { ...publicRefresh(row), disposition: row.acquired ? "accepted" : "already_running" };
}
