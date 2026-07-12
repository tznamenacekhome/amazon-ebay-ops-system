import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const limitParam = new URL(request.url).searchParams.get("limit");
  const limit = Math.min(limitParam === null ? 50 : toNumber(limitParam, 50), 100);
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase
    .from("sourcing_runs")
    .select(
      "sourcing_run_id,run_type,status,started_at,completed_at,source_count,search_count,candidate_count,opportunity_count,api_call_count,error_message,raw_summary_json",
    )
    .order("started_at", { ascending: false })
    .limit(limit);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const rows = data ?? [];
  const runIds = rows.map((row) => row.sourcing_run_id).filter(Boolean);
  const batchByRunId = await fetchLatestBatchByRunId(supabase, runIds);
  const response = NextResponse.json({
    runCount: rows.length,
    refreshedAt: new Date().toISOString(),
    runs: rows.map((row) => {
      const batch = batchByRunId.get(row.sourcing_run_id);
      return {
        ...row,
        seed_asin_count: row.source_count,
        ebay_candidate_count: row.candidate_count,
        scored_opportunity_count: row.opportunity_count,
        presented_opportunity_count: batch?.qualifying_opportunity_count ?? null,
        batch_stop_reason: batch?.stop_reason ?? null,
      };
    }),
  });
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}

async function fetchLatestBatchByRunId(supabase: ReturnType<typeof createServerSupabaseClient>, runIds: string[]) {
  const byRunId = new Map<string, { qualifying_opportunity_count: number | null; stop_reason: string | null }>();
  if (!runIds.length) return byRunId;
  const { data, error } = await supabase
    .from("sourcing_opportunity_batches")
    .select("sourcing_run_id,qualifying_opportunity_count,stop_reason,completed_at")
    .in("sourcing_run_id", runIds)
    .eq("status", "completed")
    .order("completed_at", { ascending: false });
  if (error) return byRunId;
  for (const row of data ?? []) {
    if (!row.sourcing_run_id || byRunId.has(row.sourcing_run_id)) continue;
    byRunId.set(row.sourcing_run_id, {
      qualifying_opportunity_count: row.qualifying_opportunity_count ?? null,
      stop_reason: row.stop_reason ?? null,
    });
  }
  return byRunId;
}

function toNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
