import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";
import { fetchBuyBoxFulfillmentByAsin, fulfillmentForAsin } from "../_keepa";

export const dynamic = "force-dynamic";
const MARKETPLACE_ID = "ATVPDKIKX0DER";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const supabase = createServerSupabaseClient();
  const supplierId = url.searchParams.get("supplierId") || null;
  const requestedImportId = url.searchParams.get("importId") || null;
  const page = Math.max(Number(url.searchParams.get("page") || 1), 1);
  const pageSize = Math.min(Math.max(Number(url.searchParams.get("pageSize") || 100), 1), 200);

  let importQuery = supabase.from("wholesale_imports").select("*").eq("status", "completed")
    .order("effective_date", { ascending: false }).order("revision", { ascending: false });
  if (supplierId) importQuery = importQuery.eq("supplier_id", supplierId);
  const [{ data: imports, error: importError }, { data: suppliers, error: supplierError }] = await Promise.all([
    importQuery.limit(500), supabase.from("wholesale_suppliers").select("supplier_id,name,is_active").order("name"),
  ]);
  if (importError || supplierError) return json({ error: (importError || supplierError)?.message }, 500);
  const selectedImport = requestedImportId ? (imports ?? []).find(row => row.import_id === requestedImportId) : imports?.[0];
  if (!selectedImport) return json({ imports: [], suppliers: suppliers ?? [], rows: [], total: 0 }, 200);

  let observations: any[];
  try {
    observations = await fetchImportObservations(supabase, selectedImport.import_id);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Unable to load import observations" }, 500);
  }
  const productIds = unique(observations.map(row => row.supplier_product_id));
  const [opportunities, states, candidates, drafts, classifications] = await Promise.all([
    fetchChunks(supabase, "wholesale_opportunities", "supplier_product_id", productIds, "supplier_product_id,opportunity_id,current_evaluation_id,current_candidate_id,active_decision_scope,opportunity_status"),
    fetchChunks(supabase, "wholesale_match_states", "supplier_product_id", productIds, "supplier_product_id,marketplace_id,selected_candidate_id,match_status"),
    fetchChunks(supabase, "wholesale_amazon_candidates", "supplier_product_id", productIds, "candidate_id,supplier_product_id,asin,eligibility_status,compatibility_reason_codes"),
    fetchChunks(supabase, "wholesale_order_candidates", "supplier_product_id", productIds, "supplier_product_id,order_candidate_id,quantity,extended_supplier_cost,commitment_status").then(rows => rows.filter(row => row.commitment_status === "draft")),
    fetchChunks(supabase, "wholesale_product_classifications", "supplier_product_id", productIds, "supplier_product_id,classification_code,classification_status").then(rows => rows.filter(row => row.classification_status === "active")),
  ]);
  const evaluationIds = unique(opportunities.map(row => row.current_evaluation_id));
  const opportunityIds = unique(opportunities.map(row => row.opportunity_id));
  const [evaluations, decisions] = await Promise.all([
    fetchChunks(supabase, "wholesale_evaluations", "evaluation_id", evaluationIds,
      "evaluation_id,asin,source_evidence_json,current_buy_box_price,keepa_avg90_price,current_true_roi,avg90_true_roi,eligibility_status,purchase_capacity,fba_fulfillable_units,inbound_units,evaluation_status,allowance_status,incomplete_reasons,is_financially_qualified"),
    fetchChunks(supabase, "wholesale_decisions", "opportunity_id", opportunityIds,
      "decision_id,opportunity_id,decision_action,decision_scope,reason_code,notes,decision_context,created_at"),
  ]);
  let fulfillmentByAsin;
  try {
    fulfillmentByAsin = await fetchBuyBoxFulfillmentByAsin(supabase, evaluations.map(row => row.asin));
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Could not load Keepa fulfillment." }, 500);
  }

  const supplierNames = new Map((suppliers ?? []).map(row => [row.supplier_id, row.name]));
  const byProduct = <T extends Record<string, any>>(rows: T[]) => new Map(rows.map(row => [row.supplier_product_id, row]));
  const opportunityMap = byProduct(opportunities);
  const stateMap = byProduct(states.filter(row => row.marketplace_id === MARKETPLACE_ID));
  const draftMap = byProduct(drafts);
  const classificationMap = byProduct(classifications);
  const evaluationMap = new Map(evaluations.map(row => [row.evaluation_id, row]));
  const candidateMap = new Map(candidates.map(row => [row.candidate_id, row]));
  const candidateGroups = new Map<string, any[]>();
  for (const candidate of candidates) candidateGroups.set(candidate.supplier_product_id, [...(candidateGroups.get(candidate.supplier_product_id) ?? []), candidate]);
  const decisionMap = new Map<string, any>();
  for (const decision of decisions.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))) {
    if (!decisionMap.has(decision.opportunity_id) && ["temporary", "hard"].includes(decision.decision_scope)) decisionMap.set(decision.opportunity_id, decision);
  }

  let rows = observations.map(observation => {
    const opportunity = opportunityMap.get(observation.supplier_product_id);
    const evaluation = opportunity ? evaluationMap.get(opportunity.current_evaluation_id) : null;
    const state = stateMap.get(observation.supplier_product_id);
    const selected = candidateMap.get(opportunity?.current_candidate_id ?? state?.selected_candidate_id);
    const decision = opportunity ? decisionMap.get(opportunity.opportunity_id) : null;
    const classification = classificationMap.get(observation.supplier_product_id);
    const draft = draftMap.get(observation.supplier_product_id);
    const status = classify({ opportunity, evaluation, state, decision, classification, draft,
      candidates: candidateGroups.get(observation.supplier_product_id) ?? [] });
    return {
      supplierProductId: observation.supplier_product_id, opportunityId: opportunity?.opportunity_id ?? null,
      evaluationId: opportunity?.current_evaluation_id ?? null, supplier: supplierNames.get(selectedImport.supplier_id) ?? "Unknown supplier",
      supplierId: selectedImport.supplier_id, supplierTitle: observation.raw_title, system: observation.raw_system,
      rawIdentifier: observation.raw_identifier, supplierCost: number(observation.supplier_price), availabilityRaw: observation.availability_raw,
      statusKey: status.key, statusLabel: status.label, statusDetail: status.detail,
      asin: evaluation?.asin ?? selected?.asin ?? null, amazonTitle: evaluation?.source_evidence_json?.amazon_title ?? null,
      currentBuyBox: number(evaluation?.current_buy_box_price), keepaAvg90: number(evaluation?.keepa_avg90_price),
      currentPriceSource: evaluation?.source_evidence_json?.current_price_source ?? (number(evaluation?.current_buy_box_price) !== null ? "buy_box" : "no_data"),
      currentPriceLabel: evaluation?.source_evidence_json?.current_price_label ?? (number(evaluation?.current_buy_box_price) !== null ? "Buy Box" : "No Data"),
      currentPriceIsBuyBox: evaluation?.source_evidence_json?.current_price_is_buy_box ?? (number(evaluation?.current_buy_box_price) !== null),
      currentBuyBoxFulfillment: evaluation?.source_evidence_json?.current_price_fulfillment ??
        (number(evaluation?.current_buy_box_price) !== null ? fulfillmentForAsin(fulfillmentByAsin, evaluation?.asin) : null),
      currentRoi: number(evaluation?.current_true_roi), avg90Roi: number(evaluation?.avg90_true_roi),
      eligibilityStatus: evaluation?.eligibility_status ?? selected?.eligibility_status ?? null,
      purchaseCapacity: number(evaluation?.purchase_capacity), fbaUnits: number(evaluation?.fba_fulfillable_units) ?? 0,
      inboundUnits: number(evaluation?.inbound_units) ?? 0,
      draft: draft ? { id: draft.order_candidate_id, quantity: draft.quantity, extendedCost: number(draft.extended_supplier_cost) } : null,
      passedAt: decision?.created_at ?? null, passReason: decision?.reason_code ?? null,
    };
  });

  const statusFilter = url.searchParams.get("filter") || "all";
  const system = (url.searchParams.get("system") || "").toLowerCase();
  const search = (url.searchParams.get("search") || "").toLowerCase();
  if (statusFilter !== "all") rows = rows.filter(row => row.statusKey === statusFilter);
  if (system) rows = rows.filter(row => row.system?.toLowerCase() === system);
  if (search) rows = rows.filter(row => [row.supplierTitle, row.rawIdentifier, row.asin, row.amazonTitle]
    .some(value => String(value ?? "").toLowerCase().includes(search)));
  const systems = unique(observations.map(row => row.raw_system)).sort();
  const total = rows.length;
  rows = rows.slice((page - 1) * pageSize, page * pageSize);

  return json({
    suppliers: suppliers ?? [],
    imports: (imports ?? []).map(row => ({ importId: row.import_id, supplierId: row.supplier_id,
      supplier: supplierNames.get(row.supplier_id) ?? "Unknown supplier", effectiveDate: row.effective_date,
      importedAt: row.imported_at, productCount: row.summary?.rows_imported ?? row.source_row_count, revision: row.revision })),
    selectedImport: { importId: selectedImport.import_id, supplierId: selectedImport.supplier_id,
      supplier: supplierNames.get(selectedImport.supplier_id) ?? "Unknown supplier", effectiveDate: selectedImport.effective_date,
      importedAt: selectedImport.imported_at, productCount: selectedImport.summary?.rows_imported ?? selectedImport.source_row_count },
    systems, rows, page, pageSize, total,
  });
}

function classify(input: any) {
  const { opportunity, evaluation, state, decision, classification, draft, candidates } = input;
  if (draft) return result("order_list", "On Order List");
  if (classification?.classification_code === "non_na_version") return result("non_na", "Non-NA Version", "Persistent product classification");
  if (opportunity?.active_decision_scope && decision) {
    const labels: Record<string, string> = { too_much_inventory: "Passed — Too Much Inventory", price_risk: "Passed — Price Risk",
      competition: "Passed — Competition", other: "Passed — Other", listing_asin_issue: "Listing / ASIN Issue" };
    const snapshots = decision.decision_context?.condition_snapshot ?? {};
    const detail = decision.reason_code === "too_much_inventory" ? `Capacity at pass: ${snapshots.purchase_capacity ?? "unknown"}` : "Condition unchanged";
    return result(decision.reason_code === "listing_asin_issue" ? "listing_issue" : `passed_${decision.reason_code}`, labels[decision.reason_code] ?? "Passed", detail);
  }
  if (state?.match_status === "restricted_no_eligible" || evaluation?.evaluation_status === "restricted") return result("restricted", "Restricted");
  if (!state || ["discovery_pending", "no_candidates"].includes(state.match_status)) return result("unmatched", "Unmatched");
  if (state.match_status === "identity_review") {
    const nonNa = candidates.some((candidate: any) => (candidate.compatibility_reason_codes ?? []).includes("region_mismatch"));
    return nonNa ? result("non_na", "Non-NA Version", "Amazon region evidence conflicts") : result("match_review", "Match Review Needed");
  }
  if (state.match_status === "eligibility_pending" || evaluation?.evaluation_status === "pending_eligibility") return result("eligibility_pending", "Eligibility Pending");
  if (!evaluation || evaluation.evaluation_status === "incomplete") {
    const unsupported = evaluation?.allowance_status === "accessory_review_required" || (evaluation?.incomplete_reasons ?? []).includes("accessory_policy_required");
    return unsupported ? result("unsupported_economics", "Unsupported Product Economics") : result("pricing_pending", "Pricing / Keepa Pending");
  }
  if (!evaluation.is_financially_qualified) return result("roi_too_low", "ROI Too Low");
  if (opportunity?.opportunity_status === "ready_for_review") return result("ready", "Ready to Review");
  return result("pricing_pending", "Pricing / Keepa Pending");
}

function result(key: string, label: string, detail: string | null = null) { return { key, label, detail }; }
const IMPORT_OBSERVATION_PAGE_SIZE = 500;
async function fetchImportObservations(supabase: any, importId: string) {
  const output: any[] = [];
  for (let offset = 0; ; offset += IMPORT_OBSERVATION_PAGE_SIZE) {
    const { data, error } = await supabase.from("wholesale_supplier_observations")
      .select("observation_id,supplier_product_id,raw_title,raw_system,raw_identifier,supplier_price,availability_raw")
      .eq("import_id", importId).order("raw_title").order("observation_id")
      .range(offset, offset + IMPORT_OBSERVATION_PAGE_SIZE - 1);
    if (error) throw new Error(`wholesale_supplier_observations: ${error.message}`);
    output.push(...(data ?? []));
    if ((data ?? []).length < IMPORT_OBSERVATION_PAGE_SIZE) break;
  }
  return output;
}
async function fetchChunks(supabase: any, table: string, field: string, values: string[], select: string) {
  const output: any[] = [];
  for (let index = 0; index < values.length; index += 150) {
    const { data, error } = await supabase.from(table).select(select).in(field, values.slice(index, index + 150));
    if (error) throw new Error(`${table}: ${error.message}`);
    output.push(...(data ?? []));
  }
  return output;
}
function unique(values: Array<string | null | undefined>) { return Array.from(new Set(values.filter(Boolean) as string[])); }
function number(value: unknown) { const parsed = Number(value); return value === null || value === undefined || value === "" || !Number.isFinite(parsed) ? null : parsed; }
function json(body: unknown, status = 200) { const response = NextResponse.json(body, { status }); response.headers.set("Cache-Control", "no-store"); return response; }

