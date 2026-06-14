import { NextRequest, NextResponse } from "next/server";
import { supabase, toNumber } from "../_supabase";

export async function GET(request: NextRequest) {
  const limit = Math.min(toNumber(new URL(request.url).searchParams.get("limit"), 50), 100);
  const { data, error } = await supabase
    .from("sourcing_runs")
    .select("*")
    .order("started_at", { ascending: false })
    .limit(limit);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({
    runs: (data ?? []).map((row) => ({
      ...row,
      seed_asin_count: row.source_count,
      ebay_candidate_count: row.candidate_count,
    })),
  });
}
