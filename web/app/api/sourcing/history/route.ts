import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const limit = Math.min(toNumber(new URL(request.url).searchParams.get("limit"), 50), 100);
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase
    .from("sourcing_runs")
    .select(
      "sourcing_run_id,run_type,status,started_at,completed_at,source_count,search_count,candidate_count,opportunity_count,api_call_count,error_message",
    )
    .order("started_at", { ascending: false })
    .limit(limit);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const response = NextResponse.json({
    runCount: data?.length ?? 0,
    refreshedAt: new Date().toISOString(),
    runs: (data ?? []).map((row) => ({
      ...row,
      seed_asin_count: row.source_count,
      ebay_candidate_count: row.candidate_count,
    })),
  });
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}

function toNumber(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}
