import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const buckets = [
  ["1_recently_sold", "Sold in last 90 days"],
  ["2_purchased_not_sent", "Purchased, not sent to Amazon"],
  ["3_catalog_remaining", "Remaining catalog"],
] as const;

export async function GET() {
  const supabase = createServerSupabaseClient();
  const { data: cycle, error } = await supabase
    .from("sourcing_coverage_cycles")
    .select("*")
    .in("status", ["active", "completed"])
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) return noStoreJson({ error: error.message }, { status: 500 });
  if (!cycle) return noStoreJson({ cycle: null, bucketSummary: [], lastRun: null });

  const [itemsResult, lastRunResult] = await Promise.all([
    fetchCycleItems(supabase, cycle.coverage_cycle_id),
    supabase
      .from("sourcing_runs")
      .select("*")
      .eq("coverage_cycle_id", cycle.coverage_cycle_id)
      .order("started_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
  ]);
  if (itemsResult.error) return noStoreJson({ error: itemsResult.error.message }, { status: 500 });
  if (lastRunResult.error) return noStoreJson({ error: lastRunResult.error.message }, { status: 500 });

  const items = itemsResult.data;
  const bucketSummary = buckets.map(([bucket, label]) => {
    const rows = items.filter((item) => item.priority_bucket === bucket);
    const searched = rows.filter((item) => item.processing_status === "searched").length;
    const remaining = rows.filter((item) => item.processing_status === "pending" || item.processing_status === "retryable_failed" || item.processing_status === "paused").length;
    const next = rows
      .filter((item) => item.processing_status === "pending" || item.processing_status === "retryable_failed")
      .sort((left, right) => (left.queue_position ?? 0) - (right.queue_position ?? 0))[0];
    return {
      priorityBucket: bucket,
      label,
      total: rows.length,
      searched,
      remaining,
      progress: rows.length ? Math.round((searched / rows.length) * 1000) / 10 : 0,
      nextItem: next ? { asin: next.asin, amazonTitle: next.amazon_title, queuePosition: next.queue_position } : null,
    };
  });

  return noStoreJson({
    cycle,
    bucketSummary,
    lastRun: lastRunResult.data ?? null,
    statusMessage: statusMessage(cycle, bucketSummary),
  });
}

async function fetchCycleItems(supabase: ReturnType<typeof createServerSupabaseClient>, cycleId: string) {
  const rows: Array<{
    priority_bucket: string | null;
    processing_status: string | null;
    queue_position: number | null;
    asin: string | null;
    amazon_title: string | null;
  }> = [];
  let start = 0;

  while (true) {
    const { data, error } = await supabase
      .from("sourcing_coverage_cycle_items")
      .select("priority_bucket,processing_status,queue_position,asin,amazon_title")
      .eq("coverage_cycle_id", cycleId)
      .range(start, start + 999);

    if (error) return { data: rows, error };
    const batch = data ?? [];
    rows.push(...batch);
    if (batch.length < 1000) return { data: rows, error: null };
    start += 1000;
  }
}

function statusMessage(cycle: Record<string, unknown>, bucketSummary: Array<{ label: string; remaining: number }>) {
  if (cycle.status === "completed") return "Cycle complete; next run starts a fresh pass";
  const active = bucketSummary.find((bucket) => bucket.remaining > 0);
  if (!active) return "Cycle complete; next run starts a fresh pass";
  if (active.label === "Remaining catalog") return `${active.remaining.toLocaleString()} catalog ASINs remain in this coverage cycle`;
  return `Working through ${active.label}`;
}

function noStoreJson(body: unknown, init?: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}
