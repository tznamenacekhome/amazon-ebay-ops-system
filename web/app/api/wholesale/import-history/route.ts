import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

export const dynamic = "force-dynamic";

export async function GET() {
  const supabase = createServerSupabaseClient();
  const { data, error } = await supabase.from("wholesale_email_ingestions")
    .select("ingestion_id,supplier_id,source_type,source_name,source_host,sender_address,received_at,status,effective_date,wholesale_import_id,enrichment_run_id,error_summary,attempt_count,completed_at,wholesale_imports(summary,revision),wholesale_enrichment_runs(run_status,requested_limit,processed_count,matched_count,review_count,error_count)")
    .order("received_at", { ascending: false }).limit(25);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const resolved = await resolveLatestImports(supabase, data ?? []);
  const progress = await Promise.all(resolved.map((row: any) => downstreamProgress(supabase, row)));
  const rows = resolved.map((row: any, index) => ({
    ingestionId: row.ingestion_id, sourceType: row.source_type, sourceName: row.source_name,
    sourceHost: row.source_host, sender: row.sender_address, receivedAt: row.received_at,
    status: row.status, effectiveDate: row.effective_date, importId: row.wholesale_import_id,
    rowCount: row.wholesale_imports?.summary?.rows_imported ?? null,
    revision: row.wholesale_imports?.revision ?? null, attempts: row.attempt_count,
    error: row.error_summary, completedAt: row.completed_at,
    downstream: progress[index],
  }));
  return NextResponse.json({ rows }, { headers: { "Cache-Control": "no-store" } });
}

async function resolveLatestImports(supabase: any, rows: any[]) {
  const candidates = rows.filter(row => row.supplier_id && row.effective_date && row.wholesale_import_id);
  if (!candidates.length) return rows;
  const supplierIds = [...new Set(candidates.map(row => row.supplier_id))];
  const effectiveDates = [...new Set(candidates.map(row => row.effective_date))];
  const { data, error } = await supabase.from("wholesale_imports")
    .select("import_id,supplier_id,effective_date,revision,summary")
    .in("supplier_id", supplierIds).in("effective_date", effectiveDates)
    .eq("status", "completed").order("revision", { ascending: false });
  if (error) throw new Error(error.message);
  const latest = new Map<string, any>();
  for (const item of data ?? []) {
    const key = `${item.supplier_id}:${item.effective_date}`;
    if (!latest.has(key)) latest.set(key, item);
  }
  return rows.map(row => {
    const item = latest.get(`${row.supplier_id}:${row.effective_date}`);
    return item ? {
      ...row,
      wholesale_import_id: item.import_id,
      wholesale_imports: { revision: item.revision, summary: item.summary },
    } : row;
  });
}

async function downstreamProgress(supabase: any, row: any) {
  const total = Number(row.wholesale_imports?.summary?.rows_imported ?? 0);
  if (!row.wholesale_import_id || !total) return null;
  const observations: any[] = [];
  for (let from = 0; ; from += 1000) {
    const result = await supabase.from("wholesale_supplier_observations")
      .select("supplier_product_id").eq("import_id", row.wholesale_import_id).range(from, from + 999);
    if (result.error) throw new Error(result.error.message);
    observations.push(...(result.data ?? []));
    if ((result.data ?? []).length < 1000) break;
  }
  const productIds = observations.map(item => item.supplier_product_id);
  const states: any[] = [];
  const opportunities: any[] = [];
  for (let index = 0; index < productIds.length; index += 150) {
    const ids = productIds.slice(index, index + 150);
    const [stateResult, opportunityResult] = await Promise.all([
      supabase.from("wholesale_match_states").select("supplier_product_id,match_status,selected_candidate_id").in("supplier_product_id", ids),
      supabase.from("wholesale_opportunities").select("supplier_product_id,evaluation_requested,current_evaluation_id,opportunity_status").in("supplier_product_id", ids),
    ]);
    if (stateResult.error || opportunityResult.error) throw new Error((stateResult.error || opportunityResult.error).message);
    states.push(...(stateResult.data ?? []));
    opportunities.push(...(opportunityResult.data ?? []));
  }
  const evaluated = opportunities.filter(item => item.current_evaluation_id).length;
  const ready = opportunities.filter(item => ["ready_for_review", "not_financially_qualified", "temporarily_passed", "hard_passed", "added_to_order"].includes(item.opportunity_status)).length;
  return {
    total,
    matched: states.filter(item => item.selected_candidate_id).length,
    restrictionOrReview: states.filter(item => ["restricted_no_eligible", "identity_review", "eligibility_pending"].includes(item.match_status)).length,
    noCandidates: states.filter(item => item.match_status === "no_candidates").length,
    matchingPending: Math.max(total - states.length, 0),
    evaluated,
    evaluationPending: opportunities.filter(item => item.evaluation_requested).length,
    ready,
    runStatus: row.wholesale_enrichment_runs?.run_status ?? (total === states.length ? "completed" : "pending"),
    runErrors: Number(row.wholesale_enrichment_runs?.error_count ?? 0),
  };
}
