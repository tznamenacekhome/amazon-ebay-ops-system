import { NextResponse } from "next/server";
import { createServerSupabaseClient, isCloudDeployment, requireAdminApiToken } from "../../../../_server";
import { runSchedulerCommandTask } from "../../../../_awsScheduler";
import { currentPriceContext } from "../../../_keepa";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ productId: string }> };
type ActionBody = { action?: string; marketplaceId?: string; asin?: string | null };

export async function GET(request: Request, context: Context) {
  const { productId } = await context.params;
  const marketplaceId = new URL(request.url).searchParams.get("marketplaceId")?.trim();
  if (!marketplaceId) return json({ error: "marketplaceId is required." }, 400);
  const supabase = createServerSupabaseClient();
  const [productResult, stateResult, candidateResult, searchResult] = await Promise.all([
    supabase.from("vw_wholesale_supplier_products").select("*").eq("supplier_product_id", productId).maybeSingle(),
    supabase.from("wholesale_match_states").select("*").eq("supplier_product_id", productId).eq("marketplace_id", marketplaceId).maybeSingle(),
    supabase.from("wholesale_amazon_candidates").select("*").eq("supplier_product_id", productId).eq("marketplace_id", marketplaceId).order("rank_position").order("asin"),
    supabase.from("wholesale_catalog_searches").select("query_type,query_value,query_context,candidate_asins,searched_at")
      .eq("supplier_product_id", productId).eq("marketplace_id", marketplaceId).order("searched_at", { ascending: false }),
  ]);
  const error = productResult.error || stateResult.error || candidateResult.error || searchResult.error;
  if (error) return json({ error: error.message }, 500);
  if (!productResult.data) return json({ error: "Wholesale product not found." }, 404);
  const candidates = candidateResult.data ?? [];
  const asins = Array.from(new Set(candidates.map(row => row.asin).filter(Boolean)));
  const [catalogResult, keepaResult] = await Promise.all([
    asins.length ? supabase.from("amazon_catalog_item_identity_snapshots").select("*").in("asin", asins) : Promise.resolve({ data: [], error: null }),
    asins.length ? supabase.from("keepa_product_snapshots")
      .select("asin,title,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,raw_keepa_json,sales_rank_drops90,captured_at")
      .eq("domain_id", 1).in("asin", asins).order("captured_at", { ascending: false }) : Promise.resolve({ data: [], error: null }),
  ]);
  const evidenceError = catalogResult.error || keepaResult.error;
  if (evidenceError) return json({ error: evidenceError.message }, 500);
  const catalogs = new Map((catalogResult.data ?? []).map(row => [row.asin, row]));
  const keepa = new Map<string, any>();
  for (const row of keepaResult.data ?? []) if (!keepa.has(row.asin)) keepa.set(row.asin, row);
  return json({
    product: productResult.data,
    matchState: stateResult.data,
    candidates: candidates.map(candidate => candidateDto(candidate, catalogs.get(candidate.asin), keepa.get(candidate.asin),
      productResult.data, (searchResult.data ?? []).filter(search => (search.candidate_asins ?? []).includes(candidate.asin)))),
  });
}

export async function POST(request: Request, context: Context) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;
  const { productId } = await context.params;
  const body = (await request.json().catch(() => ({}))) as ActionBody;
  const marketplaceId = body.marketplaceId?.trim();
  if (!marketplaceId) return json({ error: "marketplaceId is required." }, 400);
  const supabase = createServerSupabaseClient();
  const action = body.action?.trim();
  let result;
  if (action === "select_candidate") {
    const asin = body.asin?.trim().toUpperCase();
    if (!asin) return json({ error: "asin is required." }, 400);
    result = await supabase.rpc("wholesale_set_manual_candidate", {
      p_supplier_product_id: productId, p_marketplace_id: marketplaceId,
      p_asin: asin, p_actor: "wholesale-api",
    });
  } else if (action === "clear_candidate") {
    result = await supabase.rpc("wholesale_set_manual_candidate", {
      p_supplier_product_id: productId, p_marketplace_id: marketplaceId,
      p_asin: null, p_actor: "wholesale-api",
    });
  } else if (action === "request_rematch") {
    result = await supabase.rpc("wholesale_request_rematch", {
      p_supplier_product_id: productId, p_marketplace_id: marketplaceId,
      p_actor: "wholesale-api",
    });
  } else {
    return json({ error: "Unsupported action." }, 400);
  }
  if (result.error) return json({ error: result.error.message }, 409);
  let taskArn: string | null = null;
  if (action === "select_candidate" && isCloudDeployment()) {
    try {
      const task = await runSchedulerCommandTask({
        command: ["python", "integrations/wholesale_evaluate_opportunities.py", "--product-id", productId, "--marketplace-id", marketplaceId, "--limit", "1"],
        source: "mbop-web-wholesale-evaluation", job: "wholesale-evaluation",
        clientToken: `wholesale-${productId.replaceAll("-", "").slice(0, 20)}-${Date.now()}`.slice(0, 64),
      });
      taskArn = task.taskArn ?? null;
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "Candidate selected, but evaluation could not be started.", matchState: result.data }, 502);
    }
  }
  return json({ matchState: result.data, evaluation: action === "select_candidate" ? "requested" : null, taskArn });
}

function candidateDto(candidate: any, catalog: any, keepa: any, product: any, searches: any[]) {
  const attributes = catalog?.relevant_attributes_json ?? {};
  const amazonIdentifiers = catalogIdentifiers(catalog?.raw_catalog_json);
  const current = currentPriceContext(keepa);
  return {
    ...candidate,
    title: attributes.title ?? keepa?.title ?? null,
    image_url: firstImage(catalog?.raw_catalog_json),
    platform: catalog?.normalized_platform ?? null,
    edition: catalog?.normalized_edition ?? null,
    region: catalog?.normalized_region ?? null,
    format: catalog?.normalized_format ?? null,
    product_type: catalog?.product_type ?? null,
    current_buy_box: current.price,
    current_price_source: current.source,
    current_price_label: current.label,
    current_buy_box_fulfillment: current.fulfillment,
    current_price_is_buy_box: current.isBuyBox,
    keepa_avg90: cents(keepa?.buy_box_price_avg90_cents),
    evidence_captured_at: keepa?.captured_at ?? catalog?.fetched_at ?? null,
    match_evidence: searches.map(search => search.query_type === "identifier" ? {
      type: "identifier", label: `Matched by ${identifierLabel(search.query_context?.identifier_type ?? product?.identifier_type)}`,
      supplier_identifier: search.query_context?.supplier_identifier ?? product?.normalized_identifier ?? product?.raw_identifier ?? null,
      amazon_identifiers: amazonIdentifiers,
    } : {
      type: search.query_type === "title" ? "title" : "title_platform",
      label: search.query_type === "title" ? "Matched by Title" : "Matched by Title + Platform",
      title_terms: search.query_context?.title_terms ?? product?.raw_title ?? null,
      platform_term: search.query_context?.platform_term ?? product?.raw_system ?? null,
      variant_label: searchVariantLabel(search.query_context?.search_variant),
      query: search.query_value,
      amazon_title: attributes.title ?? keepa?.title ?? null,
      amazon_platform: catalog?.normalized_platform ?? attributes.platform ?? null,
    }),
  };
}

function searchVariantLabel(value: unknown) {
  const labels: Record<string, string> = {
    shared_cleaned_title_platform: "Shared cleaned title + platform",
    core_title_platform: "Core title + platform",
    core_title_fallback: "Core title fallback",
  };
  return labels[String(value ?? "")] ?? "Legacy title search";
}

function identifierLabel(value: unknown) {
  const normalized = String(value ?? "identifier").toUpperCase().replace("UPC_A", "UPC");
  return normalized === "EAN" || normalized === "UPC" ? normalized : "Identifier";
}

function catalogIdentifiers(payload: any) {
  const values = new Set<string>();
  for (const group of payload?.identifiers ?? []) for (const identifier of group?.identifiers ?? []) {
    const value = String(identifier?.identifier ?? identifier?.value ?? "").replace(/\D/g, "");
    if (value) values.add(value);
  }
  for (const identifier of payload?.attributes?.externally_assigned_product_identifier ?? []) {
    const value = String(identifier?.value ?? "").replace(/\D/g, "");
    if (value) values.add(value);
  }
  return Array.from(values);
}

function firstImage(payload: any) {
  for (const group of payload?.images ?? []) for (const image of group?.images ?? []) if (image?.link) return image.link;
  return null;
}

function cents(value: unknown) {
  const parsed = Number(value);
  return value === null || value === undefined || !Number.isFinite(parsed) || parsed < 0 ? null : parsed / 100;
}

function json(body: unknown, status = 200) {
  const response = NextResponse.json(body, { status });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
