import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";
import { fetchBuyBoxFulfillmentByAsin, fulfillmentForAsin } from "../_keepa";

export const dynamic = "force-dynamic";
const STATUS_GROUPS: Record<string, string[]> = {
  ready: ["ready_for_review"], order: ["added_to_order"],
};

export async function GET(request: Request) {
  const url = new URL(request.url);
  const group = url.searchParams.get("status") || "ready";
  const statuses = STATUS_GROUPS[group];
  if (!statuses) return json({ error: "Unsupported wholesale status filter." }, 400);
  const page = Math.max(Number(url.searchParams.get("page") || 1), 1);
  const pageSize = Math.min(Math.max(Number(url.searchParams.get("pageSize") || 50), 1), 200);
  const supabase = createServerSupabaseClient();
  const start = (page - 1) * pageSize;
  const supplierId = url.searchParams.get("supplierId") || null;
  const requestedImportId = url.searchParams.get("importId") || null;
  let imports: any[] = [];
  let selectedImport: any = null;
  let supplierRows: any[] = [];
  let rows: any[] = [];
  let count = 0;

  if (group === "ready") {
    let importQuery = supabase.from("wholesale_imports").select("*").eq("status", "completed")
      .order("effective_date", { ascending: false }).order("revision", { ascending: false });
    if (supplierId) importQuery = importQuery.eq("supplier_id", supplierId);
    const [importsResult, suppliersResult] = await Promise.all([
      importQuery.limit(500),
      supabase.from("wholesale_suppliers").select("supplier_id,name,is_active").eq("is_active", true).order("name"),
    ]);
    if (importsResult.error || suppliersResult.error) return json({ error: (importsResult.error || suppliersResult.error)?.message }, 500);
    imports = importsResult.data ?? [];
    supplierRows = suppliersResult.data ?? [];
    selectedImport = requestedImportId ? imports.find(row => row.import_id === requestedImportId) : imports[0];
    if (selectedImport) {
      try {
        const importProductIds = await fetchImportProductIds(supabase, selectedImport.import_id);
        const filtered = await fetchOpportunitiesForProducts(supabase, importProductIds, statuses);
        count = filtered.length;
        rows = filtered.slice(start, start + pageSize);
      } catch (error) {
        return json({ error: error instanceof Error ? error.message : "Could not filter opportunities by supplier list." }, 500);
      }
    }
  } else {
    const result = await supabase.from("wholesale_opportunities")
      .select("*", { count: "exact" }).in("opportunity_status", statuses)
      .order("updated_at", { ascending: false }).range(start, start + pageSize - 1);
    if (result.error) return json({ error: result.error.message }, 500);
    rows = result.data ?? [];
    count = result.count ?? 0;
  }
  const productIds = unique(rows.map(row => row.supplier_product_id));
  const evaluationIds = unique(rows.map(row => row.current_evaluation_id));
  const candidateIds = unique(rows.map(row => row.current_candidate_id));
  const [productsResult, evaluationsResult, draftsResult, candidatesResult, statesResult, counts] = await Promise.all([
    productIds.length ? supabase.from("vw_wholesale_supplier_products").select("*").in("supplier_product_id", productIds) : Promise.resolve({ data: [], error: null }),
    evaluationIds.length ? supabase.from("wholesale_evaluations").select("*").in("evaluation_id", evaluationIds) : Promise.resolve({ data: [], error: null }),
    productIds.length ? supabase.from("wholesale_order_candidates").select("*").in("supplier_product_id", productIds).eq("commitment_status", "draft") : Promise.resolve({ data: [], error: null }),
    candidateIds.length ? supabase.from("wholesale_amazon_candidates").select("*").in("candidate_id", candidateIds) : Promise.resolve({ data: [], error: null }),
    productIds.length ? supabase.from("wholesale_match_states").select("*").in("supplier_product_id", productIds) : Promise.resolve({ data: [], error: null }),
    groupCounts(supabase),
  ]);
  const lookupError = productsResult.error || evaluationsResult.error || draftsResult.error || candidatesResult.error || statesResult.error;
  if (lookupError) return json({ error: lookupError.message }, 500);
  const products = new Map((productsResult.data ?? []).map(row => [row.supplier_product_id, row]));
  const evaluations = new Map((evaluationsResult.data ?? []).map(row => [row.evaluation_id, row]));
  const drafts = new Map((draftsResult.data ?? []).map(row => [row.supplier_product_id, row]));
  const candidates = new Map((candidatesResult.data ?? []).map(row => [row.candidate_id, row]));
  const states = new Map((statesResult.data ?? []).map(row => [`${row.supplier_product_id}:${row.marketplace_id}`, row]));
  const supplierIds = unique(Array.from(products.values()).map(row => row.supplier_id));
  const supplierResult = supplierIds.length ? await supabase.from("wholesale_suppliers").select("supplier_id,name").in("supplier_id", supplierIds) : { data: [], error: null };
  if (supplierResult.error) return json({ error: supplierResult.error.message }, 500);
  const suppliers = new Map([...supplierRows, ...(supplierResult.data ?? [])].map(row => [row.supplier_id, row.name]));
  let fulfillmentByAsin;
  try {
    fulfillmentByAsin = await fetchBuyBoxFulfillmentByAsin(supabase, Array.from(evaluations.values()).map(row => row.asin));
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "Could not load Keepa fulfillment." }, 500);
  }

  return json({
    rows: rows.map(opportunity => dto(opportunity, products.get(opportunity.supplier_product_id),
      evaluations.get(opportunity.current_evaluation_id), drafts.get(opportunity.supplier_product_id),
      candidates.get(opportunity.current_candidate_id),
      states.get(`${opportunity.supplier_product_id}:${opportunity.marketplace_id}`), suppliers, fulfillmentByAsin)),
    page, pageSize, total: count, counts,
    imports: imports.map(row => ({ importId: row.import_id, supplierId: row.supplier_id,
      supplier: suppliers.get(row.supplier_id) ?? "Unknown supplier", effectiveDate: row.effective_date,
      importedAt: row.imported_at, productCount: row.summary?.rows_imported ?? 0, revision: row.revision })),
    suppliers: supplierRows.map(row => ({ supplierId: row.supplier_id, supplier: row.name })),
    selectedImport: selectedImport ? { importId: selectedImport.import_id, supplierId: selectedImport.supplier_id,
      supplier: suppliers.get(selectedImport.supplier_id) ?? "Unknown supplier", effectiveDate: selectedImport.effective_date,
      importedAt: selectedImport.imported_at, productCount: selectedImport.summary?.rows_imported ?? 0,
      revision: selectedImport.revision } : null,
  });
}

async function fetchImportProductIds(supabase: ReturnType<typeof createServerSupabaseClient>, importId: string) {
  const ids: string[] = [];
  for (let from = 0; ; from += 1000) {
    const result = await supabase.from("wholesale_supplier_observations").select("supplier_product_id")
      .eq("import_id", importId).range(from, from + 999);
    if (result.error) throw new Error(result.error.message);
    ids.push(...(result.data ?? []).map(row => row.supplier_product_id));
    if ((result.data ?? []).length < 1000) break;
  }
  return unique(ids);
}

async function fetchOpportunitiesForProducts(
  supabase: ReturnType<typeof createServerSupabaseClient>, productIds: string[], statuses: string[],
) {
  const rows: any[] = [];
  for (let index = 0; index < productIds.length; index += 150) {
    const result = await supabase.from("wholesale_opportunities").select("*")
      .in("supplier_product_id", productIds.slice(index, index + 150)).in("opportunity_status", statuses);
    if (result.error) throw new Error(result.error.message);
    rows.push(...(result.data ?? []));
  }
  return rows.sort((left, right) => String(right.updated_at ?? "").localeCompare(String(left.updated_at ?? "")));
}

function dto(opportunity: any, product: any, evaluation: any, draft: any, candidate: any, matchState: any, suppliers: Map<string, string>, fulfillmentByAsin: Map<string, "fba" | "mf" | null>) {
  const target = number(evaluation?.target_units);
  const currentDraft = number(draft?.quantity) ?? 0;
  const exposureWithoutDraft = (number(evaluation?.fba_fulfillable_units) ?? 0) + (number(evaluation?.inbound_units) ?? 0);
  const purchaseCapacity = target === null ? null : Math.max(target - exposureWithoutDraft - currentDraft, 0);
  return {
    opportunityId: opportunity.opportunity_id, status: opportunity.opportunity_status,
    evaluationId: opportunity.current_evaluation_id, activeDecisionScope: opportunity.active_decision_scope,
    activeDecisionReason: opportunity.active_decision_reason,
    supplierProductId: opportunity.supplier_product_id, supplier: suppliers.get(product?.supplier_id) ?? "Unknown supplier",
    supplierTitle: product?.latest_observation?.raw_title ?? product?.raw_title ?? "", system: product?.latest_observation?.raw_system ?? product?.raw_system ?? "",
    rawIdentifier: product?.latest_observation?.raw_identifier ?? product?.raw_identifier ?? "", presentInLatestList: product?.present_in_latest_list ?? false,
    availabilityRaw: evaluation?.supplier_availability_raw ?? null,
    supplierCost: number(evaluation?.supplier_unit_cost), previousSupplierPrice: number(evaluation?.previous_supplier_price),
    supplierHistoricalLow: number(evaluation?.supplier_historical_low), supplierPriceChange30d: number(evaluation?.supplier_price_change_30d),
    supplierPriceChange90d: number(evaluation?.supplier_price_change_90d),
    asin: evaluation?.asin ?? null, amazonTitle: evaluation?.source_evidence_json?.amazon_title ?? null,
    amazonPlatform: evaluation?.source_evidence_json?.amazon_platform ?? null,
    imageUrl: evaluation?.source_evidence_json?.image_url ?? null,
    matchSources: candidate?.match_sources ?? [], priorAccountSale: candidate?.prior_account_sale ?? false,
    selectionSource: matchState?.selection_source ?? null, rankingRationale: candidate?.ranking_rationale ?? {},
    compatibilityStatus: candidate?.compatibility_status ?? null,
    compatibilityReasonCodes: candidate?.compatibility_reason_codes ?? [],
    evaluationRequested: opportunity.evaluation_requested ?? false,
    eligibilityStatus: evaluation?.eligibility_status ?? null, evaluatedAt: evaluation?.evaluated_at ?? null,
    currentBuyBox: number(evaluation?.current_buy_box_price), keepaAvg30: number(evaluation?.keepa_avg30_price),
    currentPriceSource: evaluation?.source_evidence_json?.current_price_source ?? (number(evaluation?.current_buy_box_price) !== null ? "buy_box" : "no_data"),
    currentPriceLabel: evaluation?.source_evidence_json?.current_price_label ?? (number(evaluation?.current_buy_box_price) !== null ? "Buy Box" : "No Data"),
    currentPriceIsBuyBox: evaluation?.source_evidence_json?.current_price_is_buy_box ?? (number(evaluation?.current_buy_box_price) !== null),
    currentBuyBoxFulfillment: evaluation?.source_evidence_json?.current_price_fulfillment ??
      (number(evaluation?.current_buy_box_price) !== null ? fulfillmentForAsin(fulfillmentByAsin, evaluation?.asin) : null),
    keepaAvg90: number(evaluation?.keepa_avg90_price), keepaVelocity90: number(evaluation?.keepa_sales_rank_drops90),
    currentFees: number(evaluation?.current_total_amazon_fees), avg90Fees: number(evaluation?.avg90_total_amazon_fees),
    inboundAllowance: number(evaluation?.inbound_allowance), returnAllowance: number(evaluation?.return_allowance),
    storageAllowance: number(evaluation?.storage_allowance), allowanceStatus: evaluation?.allowance_status ?? null,
    currentProfit: number(evaluation?.current_true_profit), currentRoi: number(evaluation?.current_true_roi),
    avg90Profit: number(evaluation?.avg90_true_profit), avg90Roi: number(evaluation?.avg90_true_roi),
    qualificationBasis: evaluation?.qualification_basis ?? "incomplete",
    roiFloor: number(evaluation?.current_roi_floor_price), avg90RoiFloor: number(evaluation?.avg90_roi_floor_price),
    priceHeadroom: number(evaluation?.current_price_headroom),
    expectedMonthlySales: number(evaluation?.expected_monthly_sales), fbaUnits: number(evaluation?.fba_fulfillable_units) ?? 0,
    inboundUnits: number(evaluation?.inbound_units) ?? 0, draftUnits: currentDraft, targetUnits: target,
    purchaseCapacity, offerCount: number(evaluation?.offer_count_current), fbaSellerCount: number(evaluation?.fba_seller_count),
    riskSignals: evaluation?.risk_signals_json ?? {}, incompleteReasons: evaluation?.incomplete_reasons ?? [],
    draft: draft ? { id: draft.order_candidate_id, quantity: draft.quantity, extendedCost: number(draft.extended_supplier_cost), revision: draft.revision } : null,
  };
}

async function groupCounts(supabase: ReturnType<typeof createServerSupabaseClient>) {
  const entries = await Promise.all(Object.entries(STATUS_GROUPS).map(async ([key, statuses]) => {
    const { count } = await supabase.from("wholesale_opportunities").select("opportunity_id", { count: "exact", head: true }).in("opportunity_status", statuses);
    return [key, count ?? 0] as const;
  }));
  return Object.fromEntries(entries);
}
function unique(values: Array<string | null | undefined>) { return Array.from(new Set(values.filter(Boolean) as string[])); }
function number(value: unknown) { const parsed = Number(value); return value === null || value === undefined || value === "" || !Number.isFinite(parsed) ? null : parsed; }
function json(body: unknown, status = 200) { const response = NextResponse.json(body, { status }); response.headers.set("Cache-Control", "no-store"); return response; }
