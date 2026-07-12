import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../../_server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const page = Math.max(Number(searchParams.get("page") ?? "1"), 1);
  const pageSize = Math.min(Math.max(Number(searchParams.get("pageSize") ?? "50"), 1), 200);
  const priorityBucket = searchParams.get("priorityBucket");
  const status = searchParams.get("status");
  const search = (searchParams.get("search") ?? "").trim();
  const supabase = createServerSupabaseClient();

  const { data: cycle, error: cycleError } = await supabase
    .from("sourcing_coverage_cycles")
    .select("coverage_cycle_id")
    .in("status", ["active", "completed"])
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (cycleError) return noStoreJson({ error: cycleError.message }, { status: 500 });
  if (!cycle?.coverage_cycle_id) return noStoreJson({ items: [], page, pageSize, total: 0 });

  let query = supabase
    .from("sourcing_coverage_cycle_items")
    .select("*", { count: "exact" })
    .eq("coverage_cycle_id", cycle.coverage_cycle_id)
    .order("queue_position");
  if (priorityBucket && priorityBucket !== "all") query = query.eq("priority_bucket", priorityBucket);
  if (status && status !== "all") query = query.eq("processing_status", status);
  if (search) query = query.or(`asin.ilike.%${escapeFilter(search)}%,amazon_title.ilike.%${escapeFilter(search)}%`);
  const from = (page - 1) * pageSize;
  const to = from + pageSize - 1;
  const { data, error, count } = await query.range(from, to);
  if (error) return noStoreJson({ error: error.message }, { status: 500 });
  return noStoreJson({ items: data ?? [], page, pageSize, total: count ?? 0 });
}

function escapeFilter(value: string) {
  return value.replaceAll("%", "\\%").replaceAll(",", "\\,");
}

function noStoreJson(body: unknown, init?: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}
