import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { supabase } from "../_supabase";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const runType = body.runType === "full_listings" ? "full_listings" : "recent_sales";
  const runId = randomUUID();

  const { data: settings } = await supabase
    .from("sourcing_settings")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  const { data, error } = await supabase
    .from("sourcing_runs")
    .insert({
      sourcing_run_id: runId,
      run_type: runType,
      status: "planned",
      started_at: new Date().toISOString(),
      settings_snapshot: settings ?? {},
    })
    .select("*")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({
    run: data,
    nextSteps: [
      `python integrations/build_sourcing_seed_asins.py --mode ${runType} --run-id ${runId}`,
      `python integrations/ebay_sourcing_search.py --run-id ${runId}`,
      `python integrations/score_sourcing_opportunities.py --run-id ${runId}`,
    ],
  });
}
