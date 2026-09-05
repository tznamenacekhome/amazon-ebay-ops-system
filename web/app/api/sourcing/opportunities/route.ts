import { NextRequest, NextResponse } from "next/server";
import { supabase, toNumber } from "../_supabase";
import { buildDiagnosticComparison } from "../diagnosticComparison";

type OpportunityRow = {
  opportunity_id: string;
  sourcing_run_id: string;
  asin: string;
  opportunity_type: string | null;
  status: string | null;
  target_sale_price: number | null;
  profit: number | null;
  roi_percent: number | null;
  max_profitable_landed_cost: number | null;
  max_offer_price: number | null;
  required_offer_percent_of_ask: number | null;
  max_bid: number | null;
  total_profit_opportunity: number | null;
  score: number | null;
  ai_flags: string[] | null;
  matching_diagnostics_json: unknown;
  created_at: string | null;
  sourcing_seed_asins?: {
    asin: string | null;
    amazon_title: string | null;
    amazon_image_url: string | null;
    seller_sku: string | null;
    source_mode: string | null;
    target_sale_price: number | null;
    current_inventory_units: number | null;
    monthly_velocity: number | null;
    months_of_supply: number | null;
    inventory_need_level: string | null;
    last_sold_at: string | null;
    units_sold_90d: number | null;
  } | null;
  sourcing_ebay_candidates?: {
    ebay_item_id: string | null;
    ebay_legacy_item_id: string | null;
    ebay_item_web_url: string | null;
    ebay_title: string | null;
    ebay_image_url: string | null;
    seller_username: string | null;
    item_location_country: string | null;
    condition: string | null;
    buying_options: string[] | null;
    price: number | null;
    shipping_cost: number | null;
    landed_cost: number | null;
    available_quantity: number | null;
    auction_end_time: string | null;
    bid_count: number | null;
    best_offer_enabled: boolean | null;
    listing_status: string | null;
    raw_ebay_json: unknown;
  } | null;
};

type KeepaSnapshotRow = {
  asin: string | null;
  title: string | null;
  buy_box_price_current_cents: number | null;
  buy_box_price_avg90_cents: number | null;
  new_fba_price_current_cents: number | null;
  new_price_current_cents: number | null;
  raw_keepa_json: unknown;
};

type AmazonSkuListingRow = {
  asin: string | null;
  fulfillment_channel: string | null;
  listing_status: string | null;
  item_status: string | null;
  listing_price: number | null;
  landed_price: number | null;
  total_quantity: number | null;
  fulfillable_quantity: number | null;
  inbound_working_quantity: number | null;
  inbound_shipped_quantity: number | null;
  inbound_receiving_quantity: number | null;
  reserved_quantity: number | null;
  unfulfillable_quantity: number | null;
  updated_at: string | null;
};

type KeepaPriceContext = {
  amazonTitle: string | null;
  avg90Price: number | null;
  avg90Label: string | null;
  currentPrice: number | null;
  currentPriceLabel: string | null;
  currentPriceSource: "buy_box" | "fba" | "mf" | "used_only" | "no_data" | null;
  currentPriceFulfillment: "fba" | "mf" | null;
  currentPriceIsBuyBox: boolean;
  imageUrl: string | null;
};

type MyListingContext = {
  price: number | null;
  quantity: number;
  pipelineQuantity: number;
  purchasedQuantity: number;
  receivedQuantity: number;
  outboundQuantity: number;
  fulfillment: "fba" | "mf" | null;
};

type PurchasePipelineContext = {
  purchasedQuantity: number;
  receivedQuantity: number;
  outboundQuantity: number;
};

type PurchasePipelineRow = {
  item_id: string | null;
  asin: string | null;
  quantity: number | null;
  current_status: string | null;
  marketplace: string | null;
  exclude_from_purchase_reporting?: boolean | null;
};

type FbaShipmentPipelineRow = {
  item_id: string | null;
  quantity: number | null;
  included: boolean | null;
  outbound_remaining_quantity: number | null;
  received_quantity: number | null;
  available_quantity: number | null;
  fba_shipments:
    | {
        shipment_code: string | null;
        workflow_status: string | null;
        amazon_status_normalized: string | null;
      }
    | Array<{
        shipment_code: string | null;
        workflow_status: string | null;
        amazon_status_normalized: string | null;
      }>
    | null;
};

type LastSaleContext = {
  salePrice: number | null;
  soldAt: string | null;
  unitsSold90d: number;
  unitsSold120d: number;
  unitsSold365d: number;
  salesCountSource: "amazon_orders";
};

type AmazonProfitabilitySaleRow = {
  amazon_order_id: string | null;
  asin: string | null;
  quantity: number | null;
  sale_price: number | null;
};

type AmazonOrderDateRow = {
  amazon_order_id: string | null;
  purchase_date: string | null;
  order_status?: string | null;
};

type AmazonSalesOrderItemRow = {
  amazon_order_id: string | null;
  asin: string | null;
  quantity_ordered: number | null;
  quantity_shipped: number | null;
  item_price_amount: number | null;
};

type ShippingQuoteStatus = "known_paid" | "known_free" | "unknown_no_cost" | "unknown_no_options";

type SourcingBatchRow = {
  batch_id: string;
  sourcing_run_id: string;
  batch_sequence: number | null;
  status: string | null;
  requested_opportunity_count: number | null;
  qualifying_opportunity_count: number | null;
  cumulative_qualifying_count: number | null;
  seeds_searched: number | null;
  cumulative_seeds_searched: number | null;
  seeds_remaining: number | null;
  api_call_count: number | null;
  stop_reason: string | null;
  funnel_json: unknown;
  started_at: string | null;
  completed_at: string | null;
};

type PresentationMetadata = {
  firstPresentedAt: string | null;
  lastPresentedAt: string | null;
  originatingRunId: string | null;
  latestPresentedRunId: string | null;
  originatingCycleId: string | null;
  latestPresentedCycleId: string | null;
  isNewThisRun: boolean;
  presentationCount: number;
};

type OpportunityScope = "all_open" | "new_this_run" | "prior_unreviewed" | "closest_excluded";
type ClosestExcludedContext = {
  presentationByOpportunityId: Map<string, PresentationMetadata>;
  actionedOpportunityIds: Set<string>;
  presentedListingKeys: Set<string>;
};

type ExclusionReasonSeverity =
  | "hard_block"
  | "probable_non_match"
  | "review_threshold"
  | "score_threshold"
  | "profitability"
  | "availability"
  | "seller_rule"
  | "duplicate_history"
  | "unsupported_platform"
  | "item_location"
  | "other_eligibility_gate";

type ExclusionReasonSummary = {
  code: string;
  label: string;
  summary: string;
  source: string;
  severity: ExclusionReasonSeverity;
  category: string;
  diagnosticKeys: string[];
};

type ExclusionReason = ExclusionReasonSummary & {
  eligible?: boolean;
  finalRecommendation: string | null;
  finalStatus: string | null;
  secondaryReasons: ExclusionReasonSummary[];
  supportingSignals: string[];
};

type DecisionTraceRow = {
  stage: string;
  diagnosticKey: string;
  result: string;
  summary: string;
  reasonCode?: string;
};

type SalesVelocitySuppressionRow = {
  asin: string | null;
  velocity_at_dismissal: number | null;
  current_velocity: number | null;
  required_velocity: number | null;
  metric_window_days: number | null;
  last_evaluated_at: string | null;
  reactivated_at: string | null;
  status: string | null;
};

export async function GET(request: NextRequest) {
  try {
    return await getOpportunities(request);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Failed to load sourcing opportunities.";
    console.error("Sourcing opportunities API failed", error);
    return jsonNoStore({ error: message }, { status: 500 });
  }
}

async function getOpportunities(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "open";
  const type = searchParams.get("type") ?? "all";
  const runId = searchParams.get("runId");
  const scope = parseScope(searchParams.get("scope"), runId);
  const sourceMode = searchParams.get("sourceMode") ?? "all";
  const inventoryFilter = parseInventoryFilter(searchParams.get("inventoryFilter"));
  const queryText = (searchParams.get("q") ?? "").trim();
  const limit = Math.min(toNumber(searchParams.get("limit"), 100), 250);
  const queryLimit = Math.min(Math.max(limit * 20, 1000), 5000);
  const latestRunIds = runId ? [] : await fetchLatestSourcingRunIds(sourceMode);
  const latestBatches = await fetchLatestSourcingBatches(runId, latestRunIds);
  const latestBatch = latestBatches[0] ?? null;
  const latestBatchOpportunityIds = latestBatch ? await fetchBatchOpportunityIds([latestBatch.batch_id]) : null;
  if ((scope === "new_this_run" || scope === "prior_unreviewed") && !latestBatch) {
    return jsonNoStore({
      refreshedAt: new Date().toISOString(),
      scope,
      summary: emptySummary(),
      opportunities: [],
      batch: null,
    });
  }
  if ((scope === "new_this_run" || scope === "prior_unreviewed") && latestBatch && latestBatchOpportunityIds?.length === 0) {
    return jsonNoStore({
      refreshedAt: new Date().toISOString(),
      scope,
      summary: emptySummary(),
      opportunities: [],
      batch: latestBatch,
    });
  }

  const requestedStatus = status === "sales_velocity_suppressed" ? "all" : status;
  const { data, error } = scope === "new_this_run" && latestBatchOpportunityIds
    ? await fetchBatchOpportunities(latestBatchOpportunityIds, requestedStatus, type)
    : await fetchRunOpportunities({
        runId,
        latestRunIds,
        status: scope === "closest_excluded" ? "all" : requestedStatus,
        type,
        queryLimit,
      });
  if (error) return jsonNoStore({ error: error.message }, { status: 500 });

  const activeSuppressionByAsin = await fetchActiveSalesVelocitySuppressions();
  let rows = (data ?? []) as OpportunityRow[];
  if (status === "sales_velocity_suppressed") {
    rows = rows.filter((row) => activeSuppressionByAsin.has(row.asin?.toUpperCase()));
  } else if (status === "open" && scope !== "closest_excluded") {
    rows = rows.filter((row) => !activeSuppressionByAsin.has(row.asin?.toUpperCase()));
  }
  const closestExcludedContext = scope === "closest_excluded"
    ? await buildClosestExcludedContext(rows)
    : null;
  const qualifyingClosestExcludedRows = scope === "closest_excluded"
    ? rows.filter((row) => isClosestExcludedCandidate(row, closestExcludedContext))
    : [];
  const eligibleRows = scope === "closest_excluded"
    ? qualifyingClosestExcludedRows
    : rows.filter(isPresentationEligibleOpportunity);
  const presentationByOpportunityId = scope === "closest_excluded"
    ? new Map<string, PresentationMetadata>()
    : await fetchPresentationMetadataByOpportunityId(
        eligibleRows.map((row) => row.opportunity_id),
        new Set(latestBatchOpportunityIds ?? []),
      );
  const keepaByAsin = await fetchKeepaPriceContextByAsin(eligibleRows.map((row) => row.asin));
  const myListingByAsin = await fetchMyListingContextByAsin(eligibleRows.map((row) => row.asin));
  const amazonImageByAsin = await fetchAmazonImageFallbackByAsin(eligibleRows.map((row) => row.asin), keepaByAsin);
  const lastSaleByAsin = await fetchLastSaleContextByAsin(eligibleRows.map((row) => row.asin));

  const mappedRows = eligibleRows
    .map((row) => {
      const presentation = presentationByOpportunityId.get(row.opportunity_id) ?? emptyPresentationMetadata();
      const rawEbay = row.sourcing_ebay_candidates?.raw_ebay_json;
      const shippingQuoteStatus = getShippingQuoteStatus(
        rawEbay,
        row.sourcing_ebay_candidates?.shipping_cost ?? null,
      );
      const originalCurrency = getOriginalCurrency(rawEbay);
      const targetSalePrice = row.target_sale_price ?? row.sourcing_seed_asins?.target_sale_price ?? null;
      const asinKey = row.asin.toUpperCase();
      const keepaContext = keepaByAsin.get(asinKey) ?? null;
      const seedAsin = row.sourcing_seed_asins?.asin?.toUpperCase() ?? asinKey;
      const amazonTitle = asinKey === seedAsin
        ? row.sourcing_seed_asins?.amazon_title ?? keepaContext?.amazonTitle ?? ""
        : keepaContext?.amazonTitle ?? row.sourcing_seed_asins?.amazon_title ?? "";
      const lastSale = lastSaleByAsin.get(row.asin.toUpperCase()) ?? null;
      const myListing = myListingByAsin.get(row.asin.toUpperCase()) ?? null;
      const landedCost = row.sourcing_ebay_candidates?.landed_cost ?? null;
      const conservativeProfit = conservativeDisplayedProfit(targetSalePrice, landedCost, row.profit);
      const exclusionReason = scope === "closest_excluded" ? closestExcludedReason(row) : null;
      const decisionTrace = scope === "closest_excluded" ? persistedDecisionTrace(row.matching_diagnostics_json) : [];
      const velocitySuppression = activeSuppressionByAsin.get(row.asin.toUpperCase()) ?? null;
      return {
        opportunityId: row.opportunity_id,
        runId: row.sourcing_run_id,
        asin: row.asin,
        amazonTitle,
        amazonImageUrl: (asinKey === seedAsin ? row.sourcing_seed_asins?.amazon_image_url : null) ?? amazonImageByAsin.get(row.asin.toUpperCase()) ?? null,
        sellerSku: row.sourcing_seed_asins?.seller_sku ?? null,
        sourceMode: row.sourcing_seed_asins?.source_mode ?? null,
        amazonUrl: `https://www.amazon.com/dp/${row.asin}`,
        ebayItemId: row.sourcing_ebay_candidates?.ebay_item_id ?? null,
        ebayLegacyItemId:
          row.sourcing_ebay_candidates?.ebay_legacy_item_id ??
          legacyEbayItemId(row.sourcing_ebay_candidates?.ebay_item_id),
        ebayUrl: row.sourcing_ebay_candidates?.ebay_item_web_url ?? null,
        ebayTitle: row.sourcing_ebay_candidates?.ebay_title ?? "",
        ebayImageUrl: row.sourcing_ebay_candidates?.ebay_image_url ?? null,
        sellerUsername: row.sourcing_ebay_candidates?.seller_username ?? null,
        itemLocationCountry: row.sourcing_ebay_candidates?.item_location_country ?? null,
        conditionName: row.sourcing_ebay_candidates?.condition ?? null,
        buyingOptions: row.sourcing_ebay_candidates?.buying_options ?? [],
        itemPrice: row.sourcing_ebay_candidates?.price ?? null,
        shippingPrice: row.sourcing_ebay_candidates?.shipping_cost ?? null,
        landedCost,
        originalCurrency,
        originalItemPrice: getOriginalItemPrice(rawEbay),
        originalShippingPrice: getOriginalShippingPrice(rawEbay),
        shippingQuoteStatus,
        shippingQuoteLabel: getShippingQuoteLabel(shippingQuoteStatus),
        quantityAvailable: row.sourcing_ebay_candidates?.available_quantity ?? null,
        auctionEndAt: row.sourcing_ebay_candidates?.auction_end_time ?? null,
        bidCount: row.sourcing_ebay_candidates?.bid_count ?? null,
        bestOfferEnabled: row.sourcing_ebay_candidates?.best_offer_enabled ?? false,
        listingStatus: row.sourcing_ebay_candidates?.listing_status ?? null,
        targetSalePrice,
        lastSalePrice: lastSale?.salePrice ?? null,
        keepaAvg90Price: keepaByAsin.get(row.asin)?.avg90Price ?? null,
        keepaAvg90Label: keepaByAsin.get(row.asin)?.avg90Label ?? null,
        keepaCurrentPrice: keepaByAsin.get(row.asin)?.currentPrice ?? null,
        keepaCurrentPriceLabel: keepaByAsin.get(row.asin)?.currentPriceLabel ?? null,
        keepaCurrentPriceSource: keepaByAsin.get(row.asin)?.currentPriceSource ?? "no_data",
        keepaCurrentPriceFulfillment: keepaByAsin.get(row.asin)?.currentPriceFulfillment ?? null,
        keepaCurrentPriceIsBuyBox: keepaByAsin.get(row.asin)?.currentPriceIsBuyBox ?? false,
        myPrice: myListing?.price ?? null,
        myQuantity: myListing?.quantity ?? 0,
        myPipelineQuantity: myListing?.pipelineQuantity ?? 0,
        myPurchasedQuantity: myListing?.purchasedQuantity ?? 0,
        myReceivedQuantity: myListing?.receivedQuantity ?? 0,
        myOutboundQuantity: myListing?.outboundQuantity ?? 0,
        myPriceFulfillment: myListing?.fulfillment ?? null,
        currentInventoryUnits: row.sourcing_seed_asins?.current_inventory_units ?? null,
        monthlyVelocity: row.sourcing_seed_asins?.monthly_velocity ?? null,
        monthsOfSupply: row.sourcing_seed_asins?.months_of_supply ?? null,
        inventoryNeedLevel: row.sourcing_seed_asins?.inventory_need_level ?? null,
        lastSoldAt: lastSale?.soldAt ?? null,
        unitsSold90d: lastSale?.unitsSold90d ?? 0,
        unitsSold120d: lastSale?.unitsSold120d ?? 0,
        unitsSold365d: lastSale?.unitsSold365d ?? 0,
        salesCountSource: lastSale?.salesCountSource ?? null,
        salesVelocitySuppression: velocitySuppression ? {
          velocityAtDismissal: velocitySuppression.velocity_at_dismissal ?? null,
          currentVelocity: velocitySuppression.current_velocity ?? null,
          requiredVelocity: velocitySuppression.required_velocity ?? null,
          metricWindowDays: velocitySuppression.metric_window_days ?? null,
          lastEvaluatedAt: velocitySuppression.last_evaluated_at ?? null,
          reactivatedAt: velocitySuppression.reactivated_at ?? null,
          releaseEligible: (velocitySuppression.current_velocity ?? 0) >= (velocitySuppression.required_velocity ?? Number.POSITIVE_INFINITY),
        } : null,
        opportunityType: row.opportunity_type,
        status: row.status,
        estimatedProfit: conservativeProfit.profit,
        estimatedRoiPercent: conservativeProfit.roiPercent ?? row.roi_percent,
        maxProfitableLandedCost: row.max_profitable_landed_cost,
        suggestedOfferPrice: row.max_offer_price,
        requiredOfferPercentOfAsk: row.required_offer_percent_of_ask,
        suggestedMaxBid: row.max_bid,
        quantityMultiplier: row.sourcing_ebay_candidates?.available_quantity ?? null,
        totalProfitOpportunity: row.total_profit_opportunity,
        score: row.score,
        aiFlags: mergeFlags(row.ai_flags, diagnosticFlags(row.matching_diagnostics_json)),
        matchingDiagnostics: row.matching_diagnostics_json ?? null,
        diagnosticComparison: buildDiagnosticComparison({
          opportunity: row as unknown as Record<string, unknown>,
          seed: (row.sourcing_seed_asins ?? {}) as unknown as Record<string, unknown>,
          candidate: (row.sourcing_ebay_candidates ?? {}) as unknown as Record<string, unknown>,
          diagnostics: row.matching_diagnostics_json,
        }),
        exclusionReason,
        decisionTrace,
        nearMissRank: scope === "closest_excluded" ? closestExcludedRank(row) : null,
        createdAt: row.created_at,
        firstPresentedAt: presentation.firstPresentedAt,
        lastPresentedAt: presentation.lastPresentedAt,
        originatingRunId: presentation.originatingRunId,
        latestPresentedRunId: presentation.latestPresentedRunId,
        originatingCycleId: presentation.originatingCycleId,
        latestPresentedCycleId: presentation.latestPresentedCycleId,
        isNewThisRun: presentation.isNewThisRun,
        presentationCount: presentation.presentationCount,
      };
    })
    .filter((row) => {
      if (scope === "prior_unreviewed" && row.isNewThisRun) return false;
      if (row.status === "open" && row.listingStatus === "ended") return false;
      if (sourceMode !== "all" && row.sourceMode !== sourceMode) return false;
      if (inventoryFilter === "exclude_in_stock" && row.myQuantity > 0) return false;
      if (inventoryFilter === "only_in_stock" && row.myQuantity <= 0) return false;
      if (!queryText) return true;
      const haystack = `${row.asin} ${row.amazonTitle} ${row.ebayTitle}`.toLowerCase();
      return haystack.includes(queryText.toLowerCase());
    });

  const sortedRows = scope === "closest_excluded"
    ? dedupeExactEbayListings(mappedRows).sort((left, right) => (right.nearMissRank ?? 0) - (left.nearMissRank ?? 0))
    : groupByAsinPriority(dedupeExactEbayListings(mappedRows));
  const opportunities = sortedRows.slice(0, limit);

  return jsonNoStore({
    refreshedAt: new Date().toISOString(),
    scope,
    summary: summarizeMappedRows(sortedRows, opportunities.length),
    opportunities,
    batch: latestBatch,
  });
}

const OPPORTUNITY_SELECT = `
  *,
  sourcing_seed_asins (
    amazon_title,
    asin,
    amazon_image_url,
    seller_sku,
    source_mode,
    target_sale_price,
    current_inventory_units,
    monthly_velocity,
    months_of_supply,
    inventory_need_level,
    last_sold_at,
    units_sold_90d
  ),
  sourcing_ebay_candidates (
    ebay_item_id,
    ebay_legacy_item_id,
    ebay_item_web_url,
    ebay_title,
    ebay_image_url,
    seller_username,
    item_location_country,
    condition,
    buying_options,
    price,
    shipping_cost,
    landed_cost,
    available_quantity,
    auction_end_time,
    bid_count,
    best_offer_enabled,
    listing_status,
    raw_ebay_json
  )
`;

type OpportunityQueryResult = {
  data: OpportunityRow[] | null;
  error: { message: string } | null;
};

async function fetchRunOpportunities({
  runId,
  latestRunIds,
  status,
  type,
  queryLimit,
}: {
  runId: string | null;
  latestRunIds: string[];
  status: string;
  type: string;
  queryLimit: number;
}): Promise<OpportunityQueryResult> {
  let query = supabase
    .from("sourcing_opportunities")
    .select(OPPORTUNITY_SELECT)
    .order("score", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(queryLimit);

  if (status !== "all") query = query.eq("status", status);
  if (type !== "all") query = query.eq("opportunity_type", type);
  if (runId) query = query.eq("sourcing_run_id", runId);
  if (!runId && status !== "open" && latestRunIds.length) query = query.in("sourcing_run_id", latestRunIds);

  const { data, error } = await query;
  return { data: (data ?? null) as OpportunityRow[] | null, error };
}

async function fetchBatchOpportunities(
  opportunityIds: string[],
  status: string,
  type: string,
): Promise<OpportunityQueryResult> {
  const rows: OpportunityRow[] = [];
  for (let index = 0; index < opportunityIds.length; index += 75) {
    const chunk = opportunityIds.slice(index, index + 75);
    let query = supabase
      .from("sourcing_opportunities")
      .select(OPPORTUNITY_SELECT)
      .in("opportunity_id", chunk)
      .order("score", { ascending: false })
      .order("created_at", { ascending: false });

    if (status !== "all") query = query.eq("status", status);
    if (type !== "all") query = query.eq("opportunity_type", type);

    const { data, error } = await query;
    if (error) return { data: null, error };
    rows.push(...((data ?? []) as OpportunityRow[]));
  }

  rows.sort((left, right) => {
    const scoreDelta = (right.score ?? Number.NEGATIVE_INFINITY) - (left.score ?? Number.NEGATIVE_INFINITY);
    if (scoreDelta !== 0) return scoreDelta;
    return (right.created_at ?? "").localeCompare(left.created_at ?? "");
  });

  return { data: rows, error: null };
}

async function fetchLatestSourcingBatches(runId: string | null, latestRunIds: string[]) {
  const runIds = runId ? [runId] : latestRunIds;
  if (!runIds.length) return [];
  const { data, error } = await supabase
    .from("sourcing_opportunity_batches")
    .select(
      "batch_id,sourcing_run_id,batch_sequence,status,requested_opportunity_count,qualifying_opportunity_count,cumulative_qualifying_count,seeds_searched,cumulative_seeds_searched,seeds_remaining,api_call_count,stop_reason,funnel_json,started_at,completed_at",
    )
    .in("sourcing_run_id", runIds)
    .eq("status", "completed")
    .order("completed_at", { ascending: false })
    .limit(runId ? 1 : runIds.length);
  if (error) {
    if (isMissingBatchTableError(error.message)) return [];
    throw new Error(`Latest sourcing batch: ${error.message}`);
  }
  const rows = (data ?? []) as SourcingBatchRow[];
  if (runId) return rows;
  const selected: SourcingBatchRow[] = [];
  const seenRunIds = new Set<string>();
  for (const row of rows) {
    if (seenRunIds.has(row.sourcing_run_id)) continue;
    seenRunIds.add(row.sourcing_run_id);
    selected.push(row);
  }
  return selected;
}

async function fetchBatchOpportunityIds(batchIds: string[]) {
  const { data, error } = await supabase
    .from("sourcing_opportunity_batch_items")
    .select("opportunity_id")
    .in("batch_id", batchIds)
    .order("presented_at", { ascending: true });
  if (error) {
    if (isMissingBatchTableError(error.message)) return null;
    throw new Error(`Sourcing batch items: ${error.message}`);
  }
  return (data ?? []).map((row) => row.opportunity_id).filter(Boolean) as string[];
}

async function fetchPresentationMetadataByOpportunityId(opportunityIds: string[], latestBatchOpportunityIds: Set<string>) {
  const uniqueIds = [...new Set(opportunityIds.filter(Boolean))];
  const byOpportunityId = new Map<string, PresentationMetadata>();
  if (!uniqueIds.length) return byOpportunityId;

  const items: Array<{ opportunity_id: string | null; sourcing_run_id: string | null; presented_at: string | null }> = [];
  for (let index = 0; index < uniqueIds.length; index += 100) {
    const chunk = uniqueIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("sourcing_opportunity_batch_items")
      .select("opportunity_id,sourcing_run_id,presented_at")
      .in("opportunity_id", chunk)
      .order("presented_at", { ascending: true });
    if (error) {
      if (isMissingBatchTableError(error.message)) return byOpportunityId;
      throw new Error(`Sourcing presentation metadata: ${error.message}`);
    }
    items.push(...((data ?? []) as Array<{ opportunity_id: string | null; sourcing_run_id: string | null; presented_at: string | null }>));
  }

  const runIds = [...new Set(items.map((item) => item.sourcing_run_id).filter(Boolean))] as string[];
  const cycleByRunId = await fetchCycleIdsByRunId(runIds);

  for (const item of items) {
    if (!item.opportunity_id) continue;
    const current = byOpportunityId.get(item.opportunity_id) ?? emptyPresentationMetadata();
    const presentedAt = item.presented_at ?? null;
    const runId = item.sourcing_run_id ?? null;
    const cycleId = runId ? cycleByRunId.get(runId) ?? null : null;
    current.presentationCount += 1;
    current.isNewThisRun = current.isNewThisRun || latestBatchOpportunityIds.has(item.opportunity_id);
    if (!current.firstPresentedAt || (presentedAt && presentedAt < current.firstPresentedAt)) {
      current.firstPresentedAt = presentedAt;
      current.originatingRunId = runId;
      current.originatingCycleId = cycleId;
    }
    if (!current.lastPresentedAt || (presentedAt && presentedAt > current.lastPresentedAt)) {
      current.lastPresentedAt = presentedAt;
      current.latestPresentedRunId = runId;
      current.latestPresentedCycleId = cycleId;
    }
    byOpportunityId.set(item.opportunity_id, current);
  }

  return byOpportunityId;
}

async function fetchCycleIdsByRunId(runIds: string[]) {
  const byRunId = new Map<string, string | null>();
  for (let index = 0; index < runIds.length; index += 100) {
    const chunk = runIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("sourcing_runs")
      .select("sourcing_run_id,coverage_cycle_id")
      .in("sourcing_run_id", chunk);
    if (error) throw new Error(`Sourcing run cycle metadata: ${error.message}`);
    for (const row of (data ?? []) as Array<{ sourcing_run_id: string | null; coverage_cycle_id: string | null }>) {
      if (row.sourcing_run_id) byRunId.set(row.sourcing_run_id, row.coverage_cycle_id ?? null);
    }
  }
  return byRunId;
}

function emptyPresentationMetadata(): PresentationMetadata {
  return {
    firstPresentedAt: null,
    lastPresentedAt: null,
    originatingRunId: null,
    latestPresentedRunId: null,
    originatingCycleId: null,
    latestPresentedCycleId: null,
    isNewThisRun: false,
    presentationCount: 0,
  };
}

function parseScope(value: string | null, runId: string | null): OpportunityScope {
  if (runId) return "new_this_run";
  if (value === "new_this_run" || value === "prior_unreviewed" || value === "closest_excluded") return value;
  return "all_open";
}

function parseInventoryFilter(value: string | null) {
  if (value === "exclude_in_stock" || value === "only_in_stock") return value;
  return "all";
}

function emptySummary() {
  return { total: 0, returned: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 };
}

function summarizeMappedRows(rows: Array<{ opportunityType: string | null }>, returned: number) {
  return {
    total: rows.length,
    returned,
    buyNow: rows.filter((row) => row.opportunityType === "buy_now").length,
    bestOffer: rows.filter((row) => row.opportunityType === "best_offer").length,
    auction: rows.filter((row) => row.opportunityType === "auction").length,
    multiUnit: rows.filter((row) => row.opportunityType === "multi_unit").length,
  };
}

function isPresentationEligibleOpportunity(row: OpportunityRow) {
  if (row.status !== "open") return true;
  if (hasBlockedDiagnostic(row.matching_diagnostics_json)) return false;
  return !(row.ai_flags ?? []).some((flag) => String(flag).startsWith("Blocked:"));
}

function isClosestExcludedCandidate(row: OpportunityRow, context: ClosestExcludedContext | null) {
  if (isActionedOrPresentedStatus(row.status)) {
    return false;
  }
  if (!row.matching_diagnostics_json || !isRecord(row.matching_diagnostics_json)) return false;
  if (isObviousLowValueExclusion(row)) return false;
  if (context) {
    const presentation = context.presentationByOpportunityId.get(row.opportunity_id);
    if ((presentation?.presentationCount ?? 0) > 0) return false;
    if (context.actionedOpportunityIds.has(row.opportunity_id)) return false;
    const listingKey = opportunityListingKey(row);
    if (listingKey && context.presentedListingKeys.has(listingKey)) return false;
  }
  return !isPresentationEligibleOpportunity(row) || row.status === "rejected";
}

function isActionedOrPresentedStatus(status: string | null | undefined) {
  return [
    "watching",
    "purchased",
    "purchased_pending_match",
    "dismissed",
    "matched_to_purchase",
    "completed",
    "confirmed_valid_match",
    "confirmed_exclusion",
    "roi_snoozed",
    "inventory_snoozed",
  ].includes(String(status ?? "").toLowerCase());
}

async function buildClosestExcludedContext(rows: OpportunityRow[]): Promise<ClosestExcludedContext> {
  const opportunityIds = rows.map((row) => row.opportunity_id).filter(Boolean);
  const presentationByOpportunityId = await fetchPresentationMetadataByOpportunityId(opportunityIds, new Set());
  const actionedOpportunityIds = await fetchActionedOpportunityIds(opportunityIds);
  const presentedListingKeys = await fetchPresentedListingKeys(rows);
  return { presentationByOpportunityId, actionedOpportunityIds, presentedListingKeys };
}

async function fetchActionedOpportunityIds(opportunityIds: string[]) {
  const uniqueIds = [...new Set(opportunityIds.filter(Boolean))];
  const ids = new Set<string>();
  for (let index = 0; index < uniqueIds.length; index += 100) {
    const chunk = uniqueIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("sourcing_actions")
      .select("opportunity_id,action_type")
      .in("opportunity_id", chunk);
    if (error) throw new Error(`Sourcing action history: ${error.message}`);
    for (const row of (data ?? []) as Array<{ opportunity_id: string | null; action_type: string | null }>) {
      if (!row.opportunity_id) continue;
      if (isOperatorActionType(row.action_type)) ids.add(row.opportunity_id);
    }
  }
  return ids;
}

async function fetchActiveSalesVelocitySuppressions() {
  const byAsin = new Map<string, SalesVelocitySuppressionRow>();
  const { data, error } = await supabase
    .from("sourcing_sales_velocity_suppressions")
    .select("asin,velocity_at_dismissal,current_velocity,required_velocity,metric_window_days,last_evaluated_at,reactivated_at,status")
    .eq("status", "active");
  if (error) {
    if (isMissingSalesVelocitySuppressionTableError(error.message)) return byAsin;
    throw new Error(`Sales velocity suppressions: ${error.message}`);
  }
  for (const row of (data ?? []) as SalesVelocitySuppressionRow[]) {
    const asin = row.asin?.toUpperCase();
    if (asin) byAsin.set(asin, row);
  }
  return byAsin;
}

function isMissingSalesVelocitySuppressionTableError(message: string) {
  return message.includes("sourcing_sales_velocity_suppressions") && (
    message.includes("does not exist") ||
    message.includes("PGRST205") ||
    message.includes("42P01")
  );
}

function isOperatorActionType(actionType: string | null | undefined) {
  return [
    "watch",
    "purchased",
    "dismiss",
    "block_asin",
    "mark_valid_match",
    "confirm_exclusion",
    "seller_listing_mismatch",
    "inventory_snoozed",
  ].includes(String(actionType ?? "").toLowerCase());
}

async function fetchPresentedListingKeys(candidateRows: OpportunityRow[]) {
  const candidateKeys = new Set(candidateRows.map(opportunityListingKey).filter(Boolean) as string[]);
  const asins = [...new Set(candidateRows.map((row) => row.asin?.toUpperCase()).filter(Boolean))];
  const relatedRows: OpportunityRow[] = [];
  if (!candidateKeys.size || !asins.length) return new Set<string>();

  for (let index = 0; index < asins.length; index += 75) {
    const chunk = asins.slice(index, index + 75);
    const { data, error } = await supabase
      .from("sourcing_opportunities")
      .select(`
        opportunity_id,
        sourcing_run_id,
        asin,
        status,
        score,
        matching_diagnostics_json,
        created_at,
        sourcing_ebay_candidates (
          ebay_item_id,
          ebay_legacy_item_id,
          ebay_item_web_url,
          ebay_title,
          ebay_image_url,
          seller_username,
          item_location_country,
          condition,
          buying_options,
          price,
          shipping_cost,
          landed_cost,
          available_quantity,
          auction_end_time,
          bid_count,
          best_offer_enabled,
          listing_status,
          raw_ebay_json
        )
      `)
      .in("asin", chunk)
      .limit(5000);
    if (error) throw new Error(`Presented listing identity lookup: ${error.message}`);
    relatedRows.push(...((data ?? []) as unknown as OpportunityRow[]).filter((row) => {
      const key = opportunityListingKey(row);
      return key ? candidateKeys.has(key) : false;
    }));
  }

  const presentedIds = await fetchPresentedOpportunityIds(relatedRows.map((row) => row.opportunity_id));
  const presentedKeys = new Set<string>();
  for (const row of relatedRows) {
    if (!presentedIds.has(row.opportunity_id)) continue;
    const key = opportunityListingKey(row);
    if (key) presentedKeys.add(key);
  }
  return presentedKeys;
}

async function fetchPresentedOpportunityIds(opportunityIds: string[]) {
  const uniqueIds = [...new Set(opportunityIds.filter(Boolean))];
  const ids = new Set<string>();
  for (let index = 0; index < uniqueIds.length; index += 100) {
    const chunk = uniqueIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("sourcing_opportunity_batch_items")
      .select("opportunity_id")
      .in("opportunity_id", chunk);
    if (error) {
      if (isMissingBatchTableError(error.message)) return ids;
      throw new Error(`Presented opportunity lookup: ${error.message}`);
    }
    for (const row of (data ?? []) as Array<{ opportunity_id: string | null }>) {
      if (row.opportunity_id) ids.add(row.opportunity_id);
    }
  }
  return ids;
}

function opportunityListingKey(row: Pick<OpportunityRow, "asin" | "sourcing_ebay_candidates">) {
  const asin = row.asin?.trim().toUpperCase();
  if (!asin) return null;
  const candidate = row.sourcing_ebay_candidates;
  const legacyId = legacyEbayItemId(candidate?.ebay_legacy_item_id) ?? legacyEbayItemId(candidate?.ebay_item_id);
  if (legacyId) return `${asin}|legacy:${legacyId}`;
  const itemId = normalizeKeyPart(candidate?.ebay_item_id);
  if (itemId) return `${asin}|item:${itemId}`;
  const url = normalizeEbayUrl(candidate?.ebay_item_web_url);
  return url ? `${asin}|url:${url}` : null;
}

function isObviousLowValueExclusion(row: OpportunityRow) {
  const diagnostics = isRecord(row.matching_diagnostics_json) ? row.matching_diagnostics_json : {};
  const flags = [...(row.ai_flags ?? []), ...diagnosticFlags(diagnostics)].map((flag) => flag.toLowerCase());
  const joined = flags.join(" ");
  if (joined.includes("historical non_match") || joined.includes("no longer available")) return true;
  if (joined.includes("non-video-game category") && closestExcludedRank(row) < 35) return true;
  return false;
}

const EXCLUSION_REASON_RULES: Array<{
  code: string;
  label: string;
  summary: string;
  source: string;
  severity: ExclusionReasonSeverity;
  category: string;
  diagnosticKeys: string[];
  patterns: string[];
}> = [
  {
    code: "historical_exact_negative",
    label: "Historical Exact Negative",
    summary: "Stored matching intelligence says this exact listing/title was previously rejected.",
    source: "matching_intelligence",
    severity: "duplicate_history",
    category: "duplicate/history rule",
    diagnosticKeys: ["confidence_summary", "hard_blocks", "warnings"],
    patterns: ["historical non_match", "historical condition_problem", "exact historical"],
  },
  {
    code: "game_name_conflict",
    label: "Different Game Name",
    summary: "eBay Game Name or title evidence identifies a different game.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["game_name", "core_game_identity", "full_title", "hard_blocks"],
    patterns: ["game name"],
  },
  {
    code: "numeric_installment_mismatch",
    label: "Numeric Installment Mismatch",
    summary: "Stored diagnostics found a conflicting installment, sequel, or identity number.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["installment_number", "hard_blocks"],
    patterns: ["numeric", "identity number", "installment", "sequel"],
  },
  {
    code: "wrong_platform",
    label: "Wrong Platform",
    summary: "Amazon and eBay platform/system evidence does not match.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["platform_system", "hard_blocks"],
    patterns: ["platform mismatch", "wrong platform"],
  },
  {
    code: "unsupported_platform",
    label: "Unsupported Platform",
    summary: "The Amazon seed platform is not supported for sourcing presentation.",
    source: "matching_diagnostics",
    severity: "unsupported_platform",
    category: "unsupported platform",
    diagnosticKeys: ["platform_system", "hard_blocks"],
    patterns: ["unsupported sourcing platform", "unsupported platform"],
  },
  {
    code: "edition_version_conflict",
    label: "Edition/version conflict",
    summary: "Edition, version, or bundle wording conflicts with the Amazon product.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["edition_version", "package_bundle_contents", "hard_blocks"],
    patterns: ["edition", "version"],
  },
  {
    code: "digital_or_service_listing",
    label: "Digital or service listing",
    summary: "The listing appears to be digital delivery, DLC, an account, or a service.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["digital_physical", "hard_blocks"],
    patterns: ["digital", "download", "dlc", "account", "service"],
  },
  {
    code: "accessory_not_game",
    label: "Accessory / not a game",
    summary: "Category or title evidence indicates an accessory, merchandise, or non-game item.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["category", "format_type", "hard_blocks"],
    patterns: ["non-video-game", "not a game", "not-game", "accessory", "category"],
  },
  {
    code: "incomplete_product",
    label: "Incomplete product",
    summary: "The listing appears incomplete, disc-only, case-only, or missing expected contents.",
    source: "matching_diagnostics",
    severity: "hard_block",
    category: "hard block",
    diagnosticKeys: ["completeness", "package_bundle_contents", "hard_blocks"],
    patterns: ["incomplete", "disc only", "case only", "missing manual", "missing contents"],
  },
  {
    code: "region_or_location",
    label: "Region or location conflict",
    summary: "Stored diagnostics found region, North American, item-location, or pickup-only conflict.",
    source: "matching_diagnostics",
    severity: "item_location",
    category: "item location",
    diagnosticKeys: ["region", "item_location", "hard_blocks"],
    patterns: ["region", "north american", "non-north", "item location", "pickup"],
  },
  {
    code: "unavailable_listing",
    label: "Unavailable listing",
    summary: "Availability evidence says the eBay listing is ended, sold out, or unavailable.",
    source: "availability",
    severity: "availability",
    category: "availability",
    diagnosticKeys: ["opportunity_context", "hard_blocks"],
    patterns: ["no longer available", "unavailable", "ended", "sold out"],
  },
  {
    code: "seller_policy",
    label: "Seller avoid/watch policy",
    summary: "Seller intelligence warning reduced or blocked presentation.",
    source: "seller_intelligence",
    severity: "seller_rule",
    category: "seller rule",
    diagnosticKeys: ["warnings", "confidence_summary"],
    patterns: ["seller"],
  },
  {
    code: "probable_non_match",
    label: "Probable non-match",
    summary: "Final diagnostics classify the candidate as a probable non-match.",
    source: "matching_diagnostics",
    severity: "probable_non_match",
    category: "probable non-match",
    diagnosticKeys: ["final_recommendation", "confidence_summary"],
    patterns: ["probable non-match"],
  },
];

function closestExcludedReason(row: OpportunityRow): ExclusionReason {
  const diagnostics = isRecord(row.matching_diagnostics_json) ? row.matching_diagnostics_json : {};
  const persisted = persistedExclusionReason(diagnostics);
  if (persisted) return persisted;
  const staticRules = isRecord(diagnostics.static_rules) ? diagnostics.static_rules : {};
  const hardBlocks = stringArray(staticRules.hard_blocks ?? diagnostics.hard_blocks);
  const warnings = stringArray(staticRules.warnings ?? diagnostics.warnings ?? diagnostics.flags);
  const flags = [...(row.ai_flags ?? []), ...diagnosticFlags(diagnostics)];
  const finalRecommendation = String(diagnostics.recommendation ?? staticRules.recommendation ?? "") || null;
  const signalText = [
    ...hardBlocks,
    ...warnings,
    ...flags.filter((flag) => flag.startsWith("Blocked:")),
    finalRecommendation,
  ].filter((value): value is string => Boolean(value));
  const supportingSignals = [
    ...hardBlocks,
    ...warnings,
    ...flags,
    finalRecommendation,
  ].filter((value): value is string => Boolean(value));
  const signalHaystack = signalText.join(" | ").toLowerCase();
  const matches = EXCLUSION_REASON_RULES
    .filter((rule) => rule.patterns.some((pattern) => signalHaystack.includes(pattern)))
    .map((rule) => ({
      code: rule.code,
      label: rule.label,
      summary: rule.summary,
      source: rule.source,
      severity: rule.severity,
      category: rule.category,
      diagnosticKeys: rule.diagnosticKeys,
    }));

  const primary = matches[0] ?? closestExcludedFallbackReason(row, finalRecommendation, hardBlocks.length > 0);
  return {
    ...primary,
    eligible: false,
    finalRecommendation,
    finalStatus: row.status ?? null,
    secondaryReasons: matches.filter((reason) => reason.code !== primary.code),
    supportingSignals: [...new Set(supportingSignals)].slice(0, 8),
  };
}

function persistedExclusionReason(diagnostics: Record<string, unknown>): ExclusionReason | null {
  const decision = isRecord(diagnostics.presentationDecision) ? diagnostics.presentationDecision : null;
  const primary = decision && isRecord(decision.primaryReason) ? decision.primaryReason : null;
  if (!decision || !primary) return null;
  const secondaryReasons = Array.isArray(decision.secondaryReasons)
    ? decision.secondaryReasons.filter(isRecord).map((reason) => exclusionSummary(reason))
    : [];
  const traceSignals = persistedDecisionTrace(diagnostics)
    .filter((row) => row.result === "fail" || row.result === "warning")
    .map((row) => row.summary)
    .filter(Boolean);
  return {
    ...exclusionSummary(primary),
    eligible: typeof decision.eligible === "boolean" ? decision.eligible : undefined,
    finalRecommendation: stringOrNull(decision.finalRecommendation),
    finalStatus: stringOrNull(decision.finalStatus),
    secondaryReasons,
    supportingSignals: [...new Set(traceSignals)].slice(0, 8),
  };
}

function exclusionSummary(value: Record<string, unknown>): ExclusionReasonSummary {
  return {
    code: String(value.code ?? "unknown"),
    label: String(value.label ?? "Unknown - inspect diagnostics"),
    summary: String(value.summary ?? "No backend exclusion reason was returned."),
    source: String(value.source ?? "unknown"),
    severity: exclusionSeverity(value.severity),
    category: String(value.category ?? value.severity ?? "other_eligibility_gate"),
    diagnosticKeys: stringArray(value.diagnosticKeys),
  };
}

function exclusionSeverity(value: unknown): ExclusionReasonSeverity {
  const text = String(value ?? "");
  const allowed: ExclusionReasonSeverity[] = [
    "hard_block",
    "probable_non_match",
    "review_threshold",
    "score_threshold",
    "profitability",
    "availability",
    "seller_rule",
    "duplicate_history",
    "unsupported_platform",
    "item_location",
    "other_eligibility_gate",
  ];
  return allowed.includes(text as ExclusionReasonSeverity) ? text as ExclusionReasonSeverity : "other_eligibility_gate";
}

function persistedDecisionTrace(value: unknown): DecisionTraceRow[] {
  if (!isRecord(value) || !Array.isArray(value.decisionTrace)) return [];
  return value.decisionTrace.filter(isRecord).map((row) => ({
    stage: String(row.stage ?? ""),
    diagnosticKey: String(row.diagnosticKey ?? ""),
    result: String(row.result ?? "unknown"),
    summary: String(row.summary ?? ""),
    reasonCode: row.reasonCode ? String(row.reasonCode) : undefined,
  })).filter((row) => row.stage && row.summary);
}

function closestExcludedFallbackReason(
  row: OpportunityRow,
  finalRecommendation: string | null,
  hasHardBlock: boolean,
): ExclusionReasonSummary {
  if (hasHardBlock) {
    return {
      code: "other_hard_block",
      label: "Other hard block",
      summary: "Stored diagnostics contain a hard block that is not yet mapped to a named reason.",
      source: "matching_diagnostics",
      severity: "hard_block",
      category: "hard block",
      diagnosticKeys: ["hard_blocks", "final_recommendation"],
    };
  }
  if ((row.profit ?? 0) <= 0 && row.profit !== null) {
    return {
      code: "profitability",
      label: "Rejected by profitability",
      summary: "Stored opportunity profit is at or below zero.",
      source: "profitability",
      severity: "profitability",
      category: "profitability",
      diagnosticKeys: ["opportunity_context", "confidence_summary"],
    };
  }
  if (String(finalRecommendation ?? "").toLowerCase().includes("review")) {
    return {
      code: "review_threshold",
      label: "Review threshold",
      summary: "Final recommendation required review and did not enter presentation.",
      source: "presentation_gate",
      severity: "review_threshold",
      category: "review threshold",
      diagnosticKeys: ["final_recommendation", "confidence_summary"],
    };
  }
  if (String(row.status ?? "").toLowerCase() === "rejected") {
    return {
      code: "status_rejected_without_block",
      label: "Rejected before presentation",
      summary: "Status is rejected, but stored diagnostics do not include a mapped exclusion rule.",
      source: "opportunity_status",
      severity: "other_eligibility_gate",
      category: "other eligibility gate",
      diagnosticKeys: ["final_recommendation", "confidence_summary", "opportunity_context"],
    };
  }
  return {
    code: "unknown",
    label: "Unknown - inspect diagnostics",
    summary: "No stored exclusion reason could be derived from diagnostics or eligibility fields.",
    source: "unknown",
    severity: "other_eligibility_gate",
    category: "other eligibility gate",
    diagnosticKeys: ["final_recommendation", "confidence_summary"],
  };
}

function closestExcludedRank(row: OpportunityRow) {
  const diagnostics = isRecord(row.matching_diagnostics_json) ? row.matching_diagnostics_json : {};
  const staticRules = isRecord(diagnostics.static_rules) ? diagnostics.static_rules : {};
  const titleOverlap = isRecord(staticRules.title_overlap ?? diagnostics.title_overlap) ? (staticRules.title_overlap ?? diagnostics.title_overlap) as Record<string, unknown> : {};
  const platformRule = isRecord(staticRules.platform_rule ?? diagnostics.platform_rule) ? (staticRules.platform_rule ?? diagnostics.platform_rule) as Record<string, unknown> : {};
  const category = isRecord(staticRules.category ?? diagnostics.category) ? (staticRules.category ?? diagnostics.category) as Record<string, unknown> : {};
  let rank = row.score ?? 0;
  const sharedTokens = Array.isArray(titleOverlap.shared_title_tokens) ? titleOverlap.shared_title_tokens.length : 0;
  rank += Math.min(sharedTokens * 6, 30);
  if (String(platformRule.result ?? "").toLowerCase().includes("match")) rank += 15;
  if (!String(category.result ?? "").toLowerCase().includes("non")) rank += 5;
  if (String(diagnostics.recommendation ?? staticRules.recommendation ?? "") === "Review") rank += 8;
  if (hasBlockedDiagnostic(row.matching_diagnostics_json)) rank -= 20;
  return Math.round(rank * 10) / 10;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter(Boolean) : [];
}

function stringOrNull(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function hasBlockedDiagnostic(value: unknown): boolean {
  if (!isRecord(value)) return false;
  if (String(value.recommendation ?? "") === "Blocked") return true;
  if (hasValues(value.hard_blocks)) return true;
  if (hasBlockedFlags(value.flags)) return true;
  const staticRules = value.static_rules;
  if (isRecord(staticRules)) {
    if (String(staticRules.recommendation ?? "") === "Blocked") return true;
    if (hasValues(staticRules.hard_blocks)) return true;
    if (hasBlockedFlags(staticRules.flags)) return true;
  }
  return false;
}

function hasValues(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0;
}

function hasBlockedFlags(value: unknown): boolean {
  return Array.isArray(value) && value.some((flag) => String(flag).startsWith("Blocked:"));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isMissingBatchTableError(message: string) {
  return message.includes("sourcing_opportunity_batches") || message.includes("sourcing_opportunity_batch_items");
}

async function fetchLatestSourcingRunIds(sourceMode: string) {
  const priorityModes = new Set(["1_recently_sold", "2_purchased_not_sent", "3_catalog_remaining"]);
  const wantedModes = sourceMode === "all"
    ? ["daily_catalog_sourcing", "recent_sales", "full_listings"]
    : priorityModes.has(sourceMode)
      ? ["daily_catalog_sourcing"]
      : [sourceMode];
  const { data, error } = await supabase
    .from("sourcing_runs")
    .select("sourcing_run_id,run_type,started_at")
    .eq("status", "completed")
    .in("run_type", wantedModes)
    .order("started_at", { ascending: false })
    .limit(20);
  if (error) throw new Error(`Latest sourcing runs: ${error.message}`);

  const runIds: string[] = [];
  const seenModes = new Set<string>();
  for (const row of (data ?? []) as Array<{ sourcing_run_id: string | null; run_type: string | null }>) {
    const mode = row.run_type ?? "";
    if (!mode || seenModes.has(mode) || !row.sourcing_run_id) continue;
    seenModes.add(mode);
    runIds.push(row.sourcing_run_id);
  }
  return runIds;
}

function jsonNoStore(body: unknown, init?: ResponseInit) {
  const response = NextResponse.json(body, init);
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, proxy-revalidate");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");
  return response;
}

function conservativeDisplayedProfit(
  salePrice: number | null,
  landedCost: number | null,
  storedProfit: number | null,
) {
  if (salePrice === null || landedCost === null || storedProfit === null || landedCost <= 0) {
    return { profit: storedProfit, roiPercent: null };
  }
  const impliedFees = salePrice - landedCost - storedProfit;
  if (impliedFees >= 1) {
    return { profit: storedProfit, roiPercent: null };
  }
  const conservativeFees = salePrice * 0.22 + 4;
  const profit = roundMoney(salePrice - conservativeFees - landedCost);
  return {
    profit,
    roiPercent: roundPercent((profit / landedCost) * 100),
  };
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function roundPercent(value: number) {
  return Math.round(value * 10) / 10;
}

function groupByAsinPriority<T extends { asin: string }>(rows: T[]) {
  const grouped = new Map<string, T[]>();
  const asinOrder: string[] = [];
  for (const row of rows) {
    const key = row.asin || "";
    if (!grouped.has(key)) {
      grouped.set(key, []);
      asinOrder.push(key);
    }
    grouped.get(key)?.push(row);
  }
  return asinOrder.flatMap((asin) => grouped.get(asin) ?? []);
}

function dedupeExactEbayListings<
  T extends {
    ebayItemId: string | null;
    ebayLegacyItemId: string | null;
    ebayUrl: string | null;
    score: number | null;
    status: string | null;
    createdAt: string | null;
  },
>(rows: T[]) {
  const keyedRows = new Map<string, T>();
  const unkeyedRows: T[] = [];

  for (const row of rows) {
    const key = ebayListingDedupeKey(row);
    if (!key) {
      unkeyedRows.push(row);
      continue;
    }

    const current = keyedRows.get(key);
    if (!current || isBetterOpportunityRow(row, current)) {
      keyedRows.set(key, row);
    }
  }

  return [...keyedRows.values(), ...unkeyedRows].sort(compareOpportunityRows);
}

function ebayListingDedupeKey(row: {
  ebayItemId: string | null;
  ebayLegacyItemId: string | null;
  ebayUrl: string | null;
}) {
  const legacyId = row.ebayLegacyItemId ?? legacyEbayItemId(row.ebayItemId);
  if (legacyId) return `legacy:${legacyId}`;

  const itemId = normalizeKeyPart(row.ebayItemId);
  if (itemId) return `item:${itemId}`;

  const url = normalizeEbayUrl(row.ebayUrl);
  return url ? `url:${url}` : null;
}

function legacyEbayItemId(value: string | null | undefined) {
  const trimmed = normalizeKeyPart(value);
  if (!trimmed) return null;
  if (/^\d+$/.test(trimmed)) return trimmed;
  if (trimmed.startsWith("v1|")) return trimmed.split("|")[1] || null;
  return null;
}

function normalizeEbayUrl(value: string | null | undefined) {
  const trimmed = normalizeKeyPart(value);
  return trimmed ? trimmed.replace(/[?#].*$/, "") : null;
}

function normalizeKeyPart(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed ? trimmed.toLowerCase() : null;
}

function isBetterOpportunityRow<T extends { score: number | null; status: string | null; createdAt: string | null }>(
  candidate: T,
  current: T,
) {
  return compareOpportunityRows(candidate, current) < 0;
}

function compareOpportunityRows<T extends { score: number | null; status: string | null; createdAt: string | null }>(
  left: T,
  right: T,
) {
  const statusDelta = statusRank(right.status) - statusRank(left.status);
  if (statusDelta !== 0) return statusDelta;

  const scoreDelta = (right.score ?? Number.NEGATIVE_INFINITY) - (left.score ?? Number.NEGATIVE_INFINITY);
  if (scoreDelta !== 0) return scoreDelta;

  return (right.createdAt ?? "").localeCompare(left.createdAt ?? "");
}

function statusRank(status: string | null) {
  if (status === "open") return 4;
  if (status === "watching") return 3;
  if (status === "purchased_pending_match") return 2;
  if (status === "roi_snoozed") return 1;
  if (status === "inventory_snoozed") return 1;
  return 0;
}

function mergeFlags(primary: string[] | null, secondary: string[]) {
  const output: string[] = [];
  for (const value of [...(primary ?? []), ...secondary]) {
    const text = String(value ?? "").trim();
    if (text && !output.includes(text)) output.push(text);
  }
  return output;
}

function diagnosticFlags(value: unknown) {
  if (!value || typeof value !== "object") return [];
  const flags = (value as { flags?: unknown }).flags;
  if (Array.isArray(flags)) return flags.map(String);
  const staticRules = (value as { static_rules?: unknown }).static_rules;
  if (staticRules && typeof staticRules === "object") {
    const staticFlags = (staticRules as { flags?: unknown }).flags;
    if (Array.isArray(staticFlags)) return staticFlags.map(String);
  }
  return [];
}

function getShippingQuoteStatus(rawEbay: unknown, storedShippingCost?: number | null): ShippingQuoteStatus {
  if (storedShippingCost !== null && storedShippingCost !== undefined) {
    return Number(storedShippingCost) === 0 ? "known_free" : "known_paid";
  }

  if (!rawEbay || typeof rawEbay !== "object") return "unknown_no_options";
  const shippingOptions = (rawEbay as { shippingOptions?: unknown }).shippingOptions;
  if (!Array.isArray(shippingOptions) || shippingOptions.length === 0) return "unknown_no_options";

  let foundOptionWithoutCost = false;
  for (const option of shippingOptions) {
    if (!option || typeof option !== "object") continue;
    const shippingCost = (option as { shippingCost?: unknown }).shippingCost;
    if (!shippingCost || typeof shippingCost !== "object") {
      foundOptionWithoutCost = true;
      continue;
    }
    const value = (shippingCost as { value?: unknown }).value;
    if (value !== null && value !== undefined && value !== "") {
      return Number(value) === 0 ? "known_free" : "known_paid";
    }
    foundOptionWithoutCost = true;
  }

  return foundOptionWithoutCost ? "unknown_no_cost" : "unknown_no_options";
}

function getOriginalCurrency(rawEbay: unknown) {
  if (!rawEbay || typeof rawEbay !== "object") return null;
  const price = (rawEbay as { price?: { convertedFromCurrency?: unknown } }).price;
  if (typeof price?.convertedFromCurrency === "string") return price.convertedFromCurrency;
  const currentBidPrice = (rawEbay as { currentBidPrice?: { convertedFromCurrency?: unknown } }).currentBidPrice;
  if (typeof currentBidPrice?.convertedFromCurrency === "string") return currentBidPrice.convertedFromCurrency;
  const shipping = firstShippingOptionWithCost(rawEbay);
  const cost = shipping?.shippingCost;
  return typeof cost?.convertedFromCurrency === "string" ? cost.convertedFromCurrency : null;
}

function getOriginalItemPrice(rawEbay: unknown) {
  if (!rawEbay || typeof rawEbay !== "object") return null;
  const price = (rawEbay as { price?: { convertedFromValue?: unknown } }).price;
  const priceValue = toNullableNumber(price?.convertedFromValue);
  if (priceValue !== null) return priceValue;
  const currentBidPrice = (rawEbay as { currentBidPrice?: { convertedFromValue?: unknown } }).currentBidPrice;
  return toNullableNumber(currentBidPrice?.convertedFromValue);
}

function getOriginalShippingPrice(rawEbay: unknown) {
  const shipping = firstShippingOptionWithCost(rawEbay);
  return toNullableNumber(shipping?.shippingCost?.convertedFromValue);
}

function firstShippingOptionWithCost(rawEbay: unknown) {
  if (!rawEbay || typeof rawEbay !== "object") return null;
  const shippingOptions = (rawEbay as { shippingOptions?: unknown }).shippingOptions;
  if (!Array.isArray(shippingOptions)) return null;
  for (const option of shippingOptions) {
    if (!option || typeof option !== "object") continue;
    const shippingCost = (option as { shippingCost?: unknown }).shippingCost;
    if (shippingCost && typeof shippingCost === "object" && "value" in shippingCost) {
      return option as { shippingCost?: { convertedFromValue?: unknown; convertedFromCurrency?: unknown } };
    }
  }
  return null;
}

function toNullableNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function getShippingQuoteLabel(status: ShippingQuoteStatus) {
  if (status === "known_free") return "Free shipping";
  if (status === "known_paid") return "Shipping";
  if (status === "unknown_no_cost") return "Shipping unknown";
  return "No ZIP quote";
}

async function fetchKeepaPriceContextByAsin(asins: string[]) {
  const uniqueAsins = [...new Set(asins.map((asin) => asin?.toUpperCase()).filter(Boolean))];
  const byAsin = new Map<string, KeepaPriceContext>();

  for (let index = 0; index < uniqueAsins.length; index += 100) {
    const chunk = uniqueAsins.slice(index, index + 100);
    const { data, error } = await supabase
      .from("vw_latest_keepa_product_snapshot")
      .select("asin,title,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,raw_keepa_json")
      .in("asin", chunk);
    if (error) throw new Error(`Keepa snapshots: ${error.message}`);

    for (const row of (data ?? []) as KeepaSnapshotRow[]) {
      const asin = row.asin?.toUpperCase();
      if (asin) {
        const buyBoxCurrent = centsToDollars(row.buy_box_price_current_cents);
        const lowFbaCurrent = centsToDollars(row.new_fba_price_current_cents);
        const lowFbmCurrent = keepaStatsCentsToDollars(row.raw_keepa_json, "current", 7);
        const buyBoxAvg90 = centsToDollars(row.buy_box_price_avg90_cents);
        const newAvg90 = keepaStatsCentsToDollars(row.raw_keepa_json, "avg90", 1);
        const current = keepaCurrentPriceContext({
          hasOfferData: hasKeepaOfferData(row.raw_keepa_json),
          buyBoxCurrent,
          buyBoxIsUsed: keepaBoolean(row.raw_keepa_json, "buyBoxIsUsed"),
          buyBoxIsFba: keepaBoolean(row.raw_keepa_json, "buyBoxIsFBA"),
          lowFbaCurrent,
          lowFbmCurrent,
          usedCurrent: keepaStatsCentsToDollars(row.raw_keepa_json, "current", 2),
        });
        byAsin.set(asin, {
          amazonTitle: row.title ?? null,
          avg90Price: buyBoxAvg90 ?? newAvg90,
          avg90Label: buyBoxAvg90 !== null ? "Buy Box avg" : newAvg90 !== null ? "New avg" : null,
          currentPrice: current.price,
          currentPriceLabel: current.label,
          currentPriceSource: current.source,
          currentPriceFulfillment: current.fulfillment,
          currentPriceIsBuyBox: current.isBuyBox,
          imageUrl: keepaImageUrl(row.raw_keepa_json),
        });
      }
    }
  }

  return byAsin;
}

async function fetchMyListingContextByAsin(asins: string[]) {
  const uniqueAsins = [...new Set(asins.map((asin) => asin?.toUpperCase()).filter(Boolean))];
  const inventoryQuantityByAsin = await fetchLatestFbaInventoryQuantityByAsin(uniqueAsins);
  const pipelineQuantityByAsin = await fetchPipelineQuantityByAsin(uniqueAsins);
  const byAsin = new Map<string, MyListingContext>();

  for (const [asin, pipeline] of pipelineQuantityByAsin.entries()) {
    byAsin.set(asin, {
      price: null,
      quantity: 0,
      pipelineQuantity: pipelineQuantity(pipeline),
      purchasedQuantity: pipeline.purchasedQuantity,
      receivedQuantity: pipeline.receivedQuantity,
      outboundQuantity: pipeline.outboundQuantity,
      fulfillment: null,
    });
  }

  for (let index = 0; index < uniqueAsins.length; index += 200) {
    const chunk = uniqueAsins.slice(index, index + 200);
    const { data, error } = await supabase
      .from("amazon_skus")
      .select(
        [
          "asin",
          "fulfillment_channel",
          "listing_status",
          "item_status",
          "listing_price",
          "landed_price",
          "updated_at",
        ].join(",")
      )
      .in("asin", chunk);

    if (error) throw new Error(`Amazon SKU listings: ${error.message}`);

    for (const row of (data ?? []) as unknown as AmazonSkuListingRow[]) {
      const asin = row.asin?.toUpperCase();
      if (!asin || isInactiveListing(row)) continue;

      const quantity = inventoryQuantityByAsin.get(asin) ?? listingQuantity(row);
      const price = toNumber(row.landed_price) ?? toNumber(row.listing_price);
      if (quantity <= 0 && price === null) continue;

      const fulfillment = fulfillmentKind(row.fulfillment_channel);
      const existing = byAsin.get(asin);
      if (!existing) {
        byAsin.set(asin, {
          price,
          quantity,
          pipelineQuantity: 0,
          purchasedQuantity: 0,
          receivedQuantity: 0,
          outboundQuantity: 0,
          fulfillment,
        });
        continue;
      }

      existing.quantity = Math.max(existing.quantity, quantity);
      if (
        price !== null &&
        (existing.price === null ||
          price < existing.price ||
          (Math.abs(price - existing.price) < 0.01 &&
            existing.fulfillment !== "fba" &&
            fulfillment === "fba"))
      ) {
        existing.price = price;
        existing.fulfillment = fulfillment;
      }
    }
  }

  return byAsin;
}

async function fetchPipelineQuantityByAsin(asins: string[]) {
  const byAsin = new Map<string, PurchasePipelineContext>();
  const asinByListedItemId = new Map<string, string>();

  for (let index = 0; index < asins.length; index += 200) {
    const chunk = asins.slice(index, index + 200);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,asin,quantity,current_status,marketplace,exclude_from_purchase_reporting")
      .in("asin", chunk);

    if (error) throw new Error(`Purchase pipeline quantities: ${error.message}`);

    for (const row of (data ?? []) as unknown as PurchasePipelineRow[]) {
      const asin = row.asin?.toUpperCase();
      const itemId = row.item_id;
      if (!asin || !itemId || isExcludedPipelinePurchase(row)) continue;

      const quantity = purchaseItemQuantity(row.quantity);
      const status = normalizedStatus(row.current_status);
      if (PURCHASED_NOT_RECEIVED_STATUSES.has(status)) {
        addPipelineQuantity(byAsin, asin, "purchasedQuantity", quantity);
      } else if (status === "received") {
        addPipelineQuantity(byAsin, asin, "receivedQuantity", quantity);
      } else if (status === "listed") {
        asinByListedItemId.set(itemId, asin);
      }
    }
  }

  const listedItemIds = [...asinByListedItemId.keys()];
  for (let index = 0; index < listedItemIds.length; index += 200) {
    const chunk = listedItemIds.slice(index, index + 200);
    const { data, error } = await supabase
      .from("fba_shipment_items")
      .select(
        [
          "item_id",
          "quantity",
          "included",
          "outbound_remaining_quantity",
          "received_quantity",
          "available_quantity",
          "fba_shipments(shipment_code,workflow_status,amazon_status_normalized)",
        ].join(",")
      )
      .in("item_id", chunk);

    if (error) throw new Error(`FBA outbound pipeline quantities: ${error.message}`);

    for (const row of (data ?? []) as unknown as FbaShipmentPipelineRow[]) {
      const itemId = row.item_id;
      const asin = itemId ? asinByListedItemId.get(itemId) : null;
      if (!asin || row.included === false || !isActiveOutboundShipment(row.fba_shipments)) continue;

      const quantity = outboundPipelineQuantity(row);
      if (quantity > 0) addPipelineQuantity(byAsin, asin, "outboundQuantity", quantity);
    }
  }

  return byAsin;
}

async function fetchLatestFbaInventoryQuantityByAsin(asins: string[]) {
  const quantityByAsin = new Map<string, number>();
  const latest = await supabase
    .from("amazon_fba_inventory_snapshots")
    .select("captured_at")
    .order("captured_at", { ascending: false })
    .limit(1);

  if (latest.error) throw new Error(`FBA inventory latest snapshot: ${latest.error.message}`);

  const capturedAt = latest.data?.[0]?.captured_at;
  if (!capturedAt) return quantityByAsin;

  for (let index = 0; index < asins.length; index += 200) {
    const chunk = asins.slice(index, index + 200);
    const { data, error } = await supabase
      .from("amazon_fba_inventory_snapshots")
      .select(
        [
          "asin",
          "total_quantity",
          "fulfillable_quantity",
          "inbound_working_quantity",
          "inbound_shipped_quantity",
          "inbound_receiving_quantity",
          "reserved_quantity",
          "unfulfillable_quantity",
        ].join(",")
      )
      .eq("captured_at", capturedAt)
      .in("asin", chunk);

    if (error) throw new Error(`FBA inventory quantities: ${error.message}`);

    for (const row of (data ?? []) as unknown as AmazonSkuListingRow[]) {
      const asin = row.asin?.toUpperCase();
      if (!asin) continue;
      quantityByAsin.set(asin, (quantityByAsin.get(asin) ?? 0) + inventoryQuantity(row));
    }
  }

  return quantityByAsin;
}

function keepaCurrentPriceContext(input: {
  hasOfferData: boolean;
  buyBoxCurrent: number | null;
  buyBoxIsUsed: boolean | null;
  buyBoxIsFba: boolean | null;
  lowFbaCurrent: number | null;
  lowFbmCurrent: number | null;
  usedCurrent: number | null;
}) {
  const buyBox = input.buyBoxIsUsed === true ? null : input.buyBoxCurrent;
  if (buyBox !== null) {
    return {
      price: buyBox,
      label: "Buy Box",
      source: "buy_box" as const,
      fulfillment:
        input.buyBoxIsFba === true ? ("fba" as const) : input.buyBoxIsFba === false ? ("mf" as const) : null,
      isBuyBox: true,
    };
  }
  if (input.lowFbaCurrent !== null) {
    return {
      price: input.lowFbaCurrent,
      label: "Low FBA New",
      source: "fba" as const,
      fulfillment: "fba" as const,
      isBuyBox: false,
    };
  }
  if (input.lowFbmCurrent !== null) {
    return {
      price: input.lowFbmCurrent,
      label: "Low MF New",
      source: "mf" as const,
      fulfillment: "mf" as const,
      isBuyBox: false,
    };
  }
  if (!input.hasOfferData) {
    return {
      price: null,
      label: "No Data",
      source: "no_data" as const,
      fulfillment: null,
      isBuyBox: false,
    };
  }
  return {
    price: null,
    label: input.usedCurrent !== null || input.buyBoxIsUsed === true ? "Used Only" : "No Data",
    source: input.usedCurrent !== null || input.buyBoxIsUsed === true ? ("used_only" as const) : ("no_data" as const),
    fulfillment: null,
    isBuyBox: false,
  };
}

function hasKeepaOfferData(rawKeepa: unknown) {
  if (!rawKeepa || typeof rawKeepa !== "object") return false;
  const record = rawKeepa as Record<string, unknown>;
  const offers = record.offers;
  const stats = record.stats && typeof record.stats === "object" ? (record.stats as Record<string, unknown>) : {};
  return Boolean(
    (Array.isArray(offers) && offers.length > 0) ||
      hasKeepaOfferValue(stats.buyBoxSellerId) ||
      hasKeepaOfferValue(stats.sellerIdsLowestFBA) ||
      hasKeepaOfferValue(stats.sellerIdsLowestFBM),
  );
}

function hasKeepaOfferValue(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasKeepaOfferValue);
  if (typeof value === "string") return value.trim() !== "" && value !== "-1";
  if (typeof value === "number") return Number.isFinite(value) && value > 0;
  return false;
}

const PURCHASED_NOT_RECEIVED_STATUSES = new Set([
  "ordered",
  "no_tracking",
  "shipped_no_tracking",
  "awaiting_carrier_scan",
  "in_transit",
  "delivered",
]);

const EXCLUDED_PIPELINE_STATUSES = new Set([
  "cancelled",
  "return_opened",
  "return_pending",
]);

const CLOSED_OUTBOUND_SHIPMENT_STATUSES = new Set([
  "cancelled",
  "canceled",
  "closed",
  "deleted",
  "voided",
  "abandoned",
]);

function addPipelineQuantity(
  byAsin: Map<string, PurchasePipelineContext>,
  asin: string,
  key: keyof PurchasePipelineContext,
  quantity: number,
) {
  const current = byAsin.get(asin) ?? emptyPurchasePipelineContext();
  current[key] += quantity;
  byAsin.set(asin, current);
}

function emptyPurchasePipelineContext(): PurchasePipelineContext {
  return {
    purchasedQuantity: 0,
    receivedQuantity: 0,
    outboundQuantity: 0,
  };
}

function pipelineQuantity(context: PurchasePipelineContext) {
  return context.purchasedQuantity + context.receivedQuantity + context.outboundQuantity;
}

function purchaseItemQuantity(value: number | string | null | undefined) {
  const quantity = toNumber(value);
  return Math.max(1, Math.floor(quantity ?? 1));
}

function normalizedStatus(value: string | null | undefined) {
  return String(value ?? "").trim().toLowerCase();
}

function isExcludedPipelinePurchase(row: PurchasePipelineRow) {
  if (row.exclude_from_purchase_reporting === true) return true;
  if (EXCLUDED_PIPELINE_STATUSES.has(normalizedStatus(row.current_status))) return true;
  return String(row.marketplace ?? "").trim().toLowerCase() === "ebay";
}

function isActiveOutboundShipment(value: FbaShipmentPipelineRow["fba_shipments"]) {
  const shipment = Array.isArray(value) ? value[0] : value;
  const shipmentCode = String(shipment?.shipment_code ?? "").trim().toLowerCase();
  if (!shipmentCode || shipmentCode === "legacy_listed_no_shipment_id") return false;

  const statuses = [shipment?.workflow_status, shipment?.amazon_status_normalized]
    .map(normalizedStatus)
    .filter(Boolean);
  return !statuses.some((status) => CLOSED_OUTBOUND_SHIPMENT_STATUSES.has(status));
}

function outboundPipelineQuantity(row: FbaShipmentPipelineRow) {
  const outboundRemaining = toNumber(row.outbound_remaining_quantity);
  if (outboundRemaining !== null) return Math.max(0, Math.floor(outboundRemaining));

  const quantity = Math.max(0, Math.floor(toNumber(row.quantity) ?? 0));
  const received = Math.max(0, Math.floor(toNumber(row.received_quantity) ?? 0));
  const available = Math.max(0, Math.floor(toNumber(row.available_quantity) ?? 0));
  return Math.max(0, quantity - received - available);
}

function listingQuantity(row: AmazonSkuListingRow) {
  const fulfillable = toNumber(row.fulfillable_quantity);
  if (fulfillable !== null) return Math.max(0, Math.floor(fulfillable));
  const total = toNumber(row.total_quantity);
  return total === null ? 0 : Math.max(0, Math.floor(total));
}

function inventoryQuantity(row: {
  total_quantity?: number | string | null;
  fulfillable_quantity?: number | string | null;
  inbound_working_quantity?: number | string | null;
  inbound_shipped_quantity?: number | string | null;
  inbound_receiving_quantity?: number | string | null;
  reserved_quantity?: number | string | null;
  unfulfillable_quantity?: number | string | null;
}) {
  const total = toNumber(row.total_quantity);
  if (total !== null) return Math.max(0, Math.floor(total));

  return [
    row.fulfillable_quantity,
    row.inbound_working_quantity,
    row.inbound_shipped_quantity,
    row.inbound_receiving_quantity,
    row.reserved_quantity,
    row.unfulfillable_quantity,
  ].reduce<number>((sum, value) => sum + Math.max(0, Math.floor(toNumber(value) ?? 0)), 0);
}

function fulfillmentKind(value: string | null) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (["amazon", "amazon_na", "afn", "fba"].includes(normalized)) return "fba" as const;
  if (["merchant", "merchant_na", "mfn", "mf"].includes(normalized)) return "mf" as const;
  return null;
}

function isInactiveListing(row: AmazonSkuListingRow) {
  const status = [row.listing_status, row.item_status]
    .map((value) => String(value ?? "").trim().toLowerCase())
    .filter(Boolean);
  return status.some((value) =>
    ["inactive", "deleted", "closed", "suppressed", "incomplete"].includes(value)
  );
}

function keepaBoolean(rawKeepa: unknown, key: string) {
  if (!rawKeepa || typeof rawKeepa !== "object") return null;
  const stats = (rawKeepa as { stats?: unknown }).stats;
  if (!stats || typeof stats !== "object") return null;
  const value = (stats as Record<string, unknown>)[key];
  if (typeof value === "boolean") return value;
  return null;
}

async function fetchAmazonImageFallbackByAsin(asins: string[], keepaByAsin: Map<string, KeepaPriceContext>) {
  const uniqueAsins = [...new Set(asins.map((asin) => asin?.toUpperCase()).filter(Boolean))];
  const byAsin = new Map<string, string>();

  for (let index = 0; index < uniqueAsins.length; index += 100) {
    const chunk = uniqueAsins.slice(index, index + 100);
    const { data, error } = await supabase
      .from("vw_latest_amazon_listing_snapshot")
      .select("asin,raw_listing_json")
      .in("asin", chunk);
    if (error) throw new Error(`Amazon listing images: ${error.message}`);

    for (const row of (data ?? []) as Array<{ asin: string | null; raw_listing_json: unknown }>) {
      const asin = row.asin?.toUpperCase();
      const imageUrl = listingImageUrl(row.raw_listing_json);
      if (asin && imageUrl) byAsin.set(asin, imageUrl);
    }
  }

  for (const asin of uniqueAsins) {
    const keepaImage = keepaByAsin.get(asin)?.imageUrl;
    if (!byAsin.has(asin) && keepaImage) byAsin.set(asin, keepaImage);
    if (!byAsin.has(asin)) byAsin.set(asin, amazonAsinImageUrl(asin));
  }

  return byAsin;
}

async function fetchLastSaleContextByAsin(asins: string[]) {
  const uniqueAsins = [...new Set(asins.map((asin) => asin?.toUpperCase()).filter(Boolean))];
  const byAsin = new Map<string, LastSaleContext>();
  const orderItemRows: AmazonSalesOrderItemRow[] = [];

  for (let index = 0; index < uniqueAsins.length; index += 100) {
    const chunk = uniqueAsins.slice(index, index + 100);
    const { data, error } = await supabase
      .from("amazon_sales_order_items")
      .select("amazon_order_id,asin,quantity_ordered,quantity_shipped,item_price_amount")
      .in("asin", chunk)
      .not("amazon_order_id", "is", null);
    if (error) throw new Error(`Amazon sales order items: ${error.message}`);
    orderItemRows.push(...((data ?? []) as AmazonSalesOrderItemRow[]));
  }

  const orderIds = [...new Set(orderItemRows.map((row) => row.amazon_order_id).filter(Boolean))] as string[];
  const orderById = await fetchAmazonOrderContextById(orderIds);
  const priceByAsinOrder = await fetchProfitabilityUnitPriceByAsinOrder(uniqueAsins);
  const cutoff90 = soldSinceIso(90);
  const cutoff120 = soldSinceIso(120);
  const cutoff365 = soldSinceIso(365);

  for (const row of orderItemRows) {
    const asin = row.asin?.toUpperCase();
    const order = row.amazon_order_id ? orderById.get(row.amazon_order_id) ?? null : null;
    const soldAt = order?.purchase_date ?? null;
    if (!asin || !soldAt || isCancelledAmazonOrder(order?.order_status ?? null)) continue;

    const quantity = salesUnitQuantity(row.quantity_ordered, row.quantity_shipped);
    const current = byAsin.get(asin) ?? {
      salePrice: null,
      soldAt: null,
      unitsSold90d: 0,
      unitsSold120d: 0,
      unitsSold365d: 0,
      salesCountSource: "amazon_orders" as const,
    };
    if (soldAt >= cutoff90) current.unitsSold90d += quantity;
    if (soldAt >= cutoff120) current.unitsSold120d += quantity;
    if (soldAt >= cutoff365) current.unitsSold365d += quantity;

    const profitPrice = row.amazon_order_id ? priceByAsinOrder.get(`${asin}|${row.amazon_order_id}`) ?? null : null;
    const itemPrice = unitSalePrice(row.item_price_amount, quantity);
    const salePrice = profitPrice ?? itemPrice;
    if (!current.soldAt || soldAt > current.soldAt) {
      current.soldAt = soldAt;
      current.salePrice = salePrice;
    } else if (soldAt === current.soldAt && current.salePrice === null && salePrice !== null) {
      current.salePrice = salePrice;
    }
    byAsin.set(asin, current);
  }

  return byAsin;
}

async function fetchProfitabilityUnitPriceByAsinOrder(asins: string[]) {
  const saleRows: AmazonProfitabilitySaleRow[] = [];

  for (let index = 0; index < asins.length; index += 100) {
    const chunk = asins.slice(index, index + 100);
    const { data, error } = await supabase
      .from("amazon_sales_profitability")
      .select("amazon_order_id,asin,quantity,sale_price")
      .in("asin", chunk)
      .not("sale_price", "is", null);
    if (error) throw new Error(`Amazon last sale profitability: ${error.message}`);
    saleRows.push(...((data ?? []) as AmazonProfitabilitySaleRow[]));
  }

  const byAsinOrder = new Map<string, number>();
  for (const row of saleRows) {
    const asin = row.asin?.toUpperCase();
    const salePrice = unitSalePrice(row.sale_price, row.quantity);
    if (asin && row.amazon_order_id && salePrice !== null) {
      byAsinOrder.set(`${asin}|${row.amazon_order_id}`, salePrice);
    }
  }
  return byAsinOrder;
}

async function fetchAmazonOrderContextById(orderIds: string[]) {
  const byId = new Map<string, { purchase_date: string | null; order_status: string | null }>();
  for (let index = 0; index < orderIds.length; index += 100) {
    const chunk = orderIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from("amazon_sales_orders")
      .select("amazon_order_id,purchase_date,order_status")
      .in("amazon_order_id", chunk);
    if (error) throw new Error(`Amazon last sale order dates: ${error.message}`);
    for (const row of (data ?? []) as AmazonOrderDateRow[]) {
      if (row.amazon_order_id) {
        byId.set(row.amazon_order_id, {
          purchase_date: row.purchase_date ?? null,
          order_status: row.order_status ?? null,
        });
      }
    }
  }
  return byId;
}

function salesUnitQuantity(quantityOrdered: number | null | undefined, quantityShipped: number | null | undefined) {
  const ordered = typeof quantityOrdered === "number" && quantityOrdered > 0 ? quantityOrdered : null;
  const shipped = typeof quantityShipped === "number" && quantityShipped > 0 ? quantityShipped : null;
  return ordered ?? shipped ?? 1;
}

function isCancelledAmazonOrder(status: string | null) {
  return status?.toLowerCase() === "canceled" || status?.toLowerCase() === "cancelled";
}

function soldSinceIso(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString();
}

function unitSalePrice(salePrice: number | null | undefined, quantity: number | null | undefined) {
  if (typeof salePrice !== "number" || salePrice <= 0) return null;
  const divisor = typeof quantity === "number" && quantity > 0 ? quantity : 1;
  return Math.round((salePrice / divisor) * 100) / 100;
}

function centsToDollars(value: number | null | undefined) {
  return typeof value === "number" && value > 0 ? value / 100 : null;
}

function keepaStatsCentsToDollars(rawKeepa: unknown, statsKey: "avg90" | "current", index: number) {
  if (!rawKeepa || typeof rawKeepa !== "object") return null;
  const stats = (rawKeepa as { stats?: unknown }).stats;
  if (!stats || typeof stats !== "object") return null;
  const values = (stats as Record<string, unknown>)[statsKey];
  if (!Array.isArray(values)) return null;
  const cents = values[index];
  return typeof cents === "number" && cents > 0 ? cents / 100 : null;
}

function listingImageUrl(rawListing: unknown) {
  if (!rawListing || typeof rawListing !== "object") return null;
  const summaries = (rawListing as { summaries?: unknown }).summaries;
  if (!Array.isArray(summaries)) return null;

  for (const summary of summaries) {
    if (!summary || typeof summary !== "object") continue;
    const mainImage = (summary as { mainImage?: unknown }).mainImage;
    if (!mainImage || typeof mainImage !== "object") continue;
    const link = (mainImage as { link?: unknown }).link;
    if (typeof link === "string" && link.trim()) return link.trim();
  }
  return null;
}

function keepaImageUrl(rawKeepa: unknown) {
  if (!rawKeepa || typeof rawKeepa !== "object") return null;
  const images = (rawKeepa as { images?: unknown }).images;
  if (Array.isArray(images)) {
    for (const image of images) {
      if (!image || typeof image !== "object") continue;
      const imageName = firstString((image as Record<string, unknown>).l, (image as Record<string, unknown>).m, (image as Record<string, unknown>).s);
      if (imageName) return amazonImageHostUrl(imageName);
    }
  }

  const imagesCsv = (rawKeepa as { imagesCSV?: unknown }).imagesCSV;
  if (typeof imagesCsv !== "string") return null;
  const imageName = imagesCsv.split(",")[0]?.trim();
  return imageName ? amazonImageHostUrl(imageName) : null;
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function amazonImageHostUrl(imageName: string) {
  if (/^https?:\/\//i.test(imageName)) return imageName;
  return `https://images-na.ssl-images-amazon.com/images/I/${imageName}`;
}

function amazonAsinImageUrl(asin: string) {
  return `https://images-na.ssl-images-amazon.com/images/P/${asin}.01._SL160_.jpg`;
}
