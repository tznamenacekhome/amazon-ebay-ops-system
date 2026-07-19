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
  if (!cycle) return noStoreJson({ cycle: null, bucketSummary: [], lastRun: null, completedCycles: [] });

  const completedResult = await supabase
    .from("sourcing_coverage_cycles")
    .select("*")
    .eq("status", "completed")
    .neq("coverage_cycle_id", cycle.coverage_cycle_id)
    .order("completed_at", { ascending: false })
    .limit(3);
  if (completedResult.error) return noStoreJson({ error: completedResult.error.message }, { status: 500 });

  let currentSummary;
  let completedCycles;
  try {
    [currentSummary, completedCycles] = await Promise.all([
      buildCycleSummary(supabase, cycle),
      Promise.all((completedResult.data ?? []).map((row) => buildCycleSummary(supabase, row))),
    ]);
  } catch (summaryError) {
    const message = summaryError instanceof Error ? summaryError.message : "Failed to build coverage cycle summary.";
    return noStoreJson({ error: message }, { status: 500 });
  }

  return noStoreJson({
    ...currentSummary,
    completedCycles,
  });
}

async function buildCycleSummary(supabase: ReturnType<typeof createServerSupabaseClient>, cycle: Record<string, unknown>) {
  const cycleId = String(cycle.coverage_cycle_id ?? "");
  const [itemsResult, lastRunResult, opportunitiesPresented] = await Promise.all([
    fetchCycleItems(supabase, cycleId),
    fetchLastRun(supabase, cycle),
    fetchOpportunitiesPresented(supabase, cycleId),
  ]);
  if (itemsResult.error) throw new Error(itemsResult.error.message);
  if (lastRunResult.error) throw new Error(lastRunResult.error.message);

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

  return {
    cycle,
    bucketSummary,
    lastRun: lastRunResult.data ?? null,
    opportunitiesPresented,
    statusMessage: statusMessage(cycle, bucketSummary),
  };
}

async function fetchLastRun(supabase: ReturnType<typeof createServerSupabaseClient>, cycle: Record<string, unknown>) {
  const lastRunId = cycle.last_run_id ? String(cycle.last_run_id) : "";
  if (lastRunId) {
    return supabase
      .from("sourcing_runs")
      .select("*")
      .eq("sourcing_run_id", lastRunId)
      .maybeSingle();
  }

  return supabase
    .from("sourcing_runs")
    .select("*")
    .eq("coverage_cycle_id", String(cycle.coverage_cycle_id ?? ""))
    .order("started_at", { ascending: false })
    .limit(1)
    .maybeSingle();
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

async function fetchOpportunitiesPresented(supabase: ReturnType<typeof createServerSupabaseClient>, cycleId: string) {
  const { data: runs, error: runError } = await supabase
    .from("sourcing_runs")
    .select("sourcing_run_id")
    .eq("coverage_cycle_id", cycleId);
  if (runError) throw new Error(runError.message);
  const runIds = (runs ?? []).map((row) => row.sourcing_run_id).filter(Boolean) as string[];
  if (!runIds.length) return { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 };

  const { data: batches, error: batchError } = await supabase
    .from("sourcing_opportunity_batches")
    .select("batch_id")
    .in("sourcing_run_id", runIds)
    .eq("status", "completed");
  if (batchError) {
    if (isMissingBatchTableError(batchError.message)) return { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 };
    throw new Error(batchError.message);
  }
  const batchIds = (batches ?? []).map((row) => row.batch_id).filter(Boolean) as string[];
  if (!batchIds.length) return { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 };

  const byOpportunityId = new Map<string, string | null>();
  for (let index = 0; index < batchIds.length; index += 100) {
    const chunk = batchIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("sourcing_opportunity_batch_items")
      .select("opportunity_id,opportunity_type")
      .in("batch_id", chunk);
    if (error) {
      if (isMissingBatchTableError(error.message)) return { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 };
      throw new Error(error.message);
    }
    for (const row of data ?? []) {
      if (row.opportunity_id && !byOpportunityId.has(row.opportunity_id)) {
        byOpportunityId.set(row.opportunity_id, row.opportunity_type ?? null);
      }
    }
  }

  const types = [...byOpportunityId.values()];
  return {
    total: byOpportunityId.size,
    buyNow: types.filter((value) => value === "buy_now").length,
    bestOffer: types.filter((value) => value === "best_offer").length,
    auction: types.filter((value) => value === "auction").length,
    multiUnit: types.filter((value) => value === "multi_unit").length,
  };
}

function isMissingBatchTableError(message: string) {
  return message.includes("sourcing_opportunity_batches") || message.includes("sourcing_opportunity_batch_items");
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
