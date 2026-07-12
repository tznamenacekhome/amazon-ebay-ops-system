import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const limit = Math.min(Number(new URL(request.url).searchParams.get("limit") ?? "30"), 100);
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase
    .from("sourcing_runs")
    .select("*")
    .eq("run_type", "daily_catalog_sourcing")
    .order("started_at", { ascending: false })
    .limit(limit);
  if (error) return noStoreJson({ error: error.message }, { status: 500 });
  return noStoreJson({ runs: data ?? [], refreshedAt: new Date().toISOString() });
}

function noStoreJson(body: unknown, init?: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}
