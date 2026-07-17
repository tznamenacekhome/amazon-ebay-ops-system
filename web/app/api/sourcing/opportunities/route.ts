import { NextRequest, NextResponse } from "next/server";
import { supabase, toNumber } from "../_supabase";

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
    raw_ebay_json: unknown;
  } | null;
};

type KeepaSnapshotRow = {
  asin: string | null;
  buy_box_price_current_cents: number | null;
  buy_box_price_avg90_cents: number | null;
  new_fba_price_current_cents: number | null;
  new_price_current_cents: number | null;
  raw_keepa_json: unknown;
};

type KeepaPriceContext = {
  avg90Price: number | null;
  avg90Label: string | null;
  currentPrice: number | null;
  currentPriceLabel: string | null;
  imageUrl: string | null;
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
  const sourceMode = searchParams.get("sourceMode") ?? "all";
  const queryText = (searchParams.get("q") ?? "").trim();
  const limit = Math.min(toNumber(searchParams.get("limit"), 100), 250);
  const queryLimit = Math.min(Math.max(limit * 5, 500), 1000);
  const latestRunIds = runId ? [] : await fetchLatestSourcingRunIds(sourceMode);
  const latestBatches = await fetchLatestSourcingBatches(runId, latestRunIds);
  const latestBatch = latestBatches[0] ?? null;
  const batchOpportunityIds = latestBatches.length ? await fetchBatchOpportunityIds(latestBatches.map((batch) => batch.batch_id)) : null;
  if (!runId && latestRunIds.length === 0) {
    return jsonNoStore({
      refreshedAt: new Date().toISOString(),
      summary: { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 },
      opportunities: [],
      batch: null,
    });
  }
  if (latestBatch && batchOpportunityIds?.length === 0) {
    return jsonNoStore({
      refreshedAt: new Date().toISOString(),
      summary: { total: 0, buyNow: 0, bestOffer: 0, auction: 0, multiUnit: 0 },
      opportunities: [],
      batch: latestBatch,
    });
  }

  const { data, error } = batchOpportunityIds
    ? await fetchBatchOpportunities(batchOpportunityIds, status, type)
    : await fetchRunOpportunities({ runId, latestRunIds, status, type, queryLimit });
  if (error) return jsonNoStore({ error: error.message }, { status: 500 });

  const rows = (data ?? []) as OpportunityRow[];
  const keepaByAsin = await fetchKeepaPriceContextByAsin(rows.map((row) => row.asin));
  const amazonImageByAsin = await fetchAmazonImageFallbackByAsin(rows.map((row) => row.asin), keepaByAsin);
  const lastSaleByAsin = await fetchLastSaleContextByAsin(rows.map((row) => row.asin));

  const mappedRows = rows
    .map((row) => {
      const rawEbay = row.sourcing_ebay_candidates?.raw_ebay_json;
      const shippingQuoteStatus = getShippingQuoteStatus(
        rawEbay,
        row.sourcing_ebay_candidates?.shipping_cost ?? null,
      );
      const originalCurrency = getOriginalCurrency(rawEbay);
      const targetSalePrice = row.target_sale_price ?? row.sourcing_seed_asins?.target_sale_price ?? null;
      const lastSale = lastSaleByAsin.get(row.asin.toUpperCase()) ?? null;
      const landedCost = row.sourcing_ebay_candidates?.landed_cost ?? null;
      const conservativeProfit = conservativeDisplayedProfit(targetSalePrice, landedCost, row.profit);
      return {
        opportunityId: row.opportunity_id,
        runId: row.sourcing_run_id,
        asin: row.asin,
        amazonTitle: row.sourcing_seed_asins?.amazon_title ?? "",
        amazonImageUrl: row.sourcing_seed_asins?.amazon_image_url ?? amazonImageByAsin.get(row.asin.toUpperCase()) ?? null,
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
        targetSalePrice,
        lastSalePrice: lastSale?.salePrice ?? null,
        keepaAvg90Price: keepaByAsin.get(row.asin)?.avg90Price ?? null,
        keepaAvg90Label: keepaByAsin.get(row.asin)?.avg90Label ?? null,
        keepaCurrentPrice: keepaByAsin.get(row.asin)?.currentPrice ?? null,
        keepaCurrentPriceLabel: keepaByAsin.get(row.asin)?.currentPriceLabel ?? null,
        currentInventoryUnits: row.sourcing_seed_asins?.current_inventory_units ?? null,
        monthlyVelocity: row.sourcing_seed_asins?.monthly_velocity ?? null,
        monthsOfSupply: row.sourcing_seed_asins?.months_of_supply ?? null,
        inventoryNeedLevel: row.sourcing_seed_asins?.inventory_need_level ?? null,
        lastSoldAt: lastSale?.soldAt ?? null,
        unitsSold90d: lastSale?.unitsSold90d ?? 0,
        unitsSold120d: lastSale?.unitsSold120d ?? 0,
        unitsSold365d: lastSale?.unitsSold365d ?? 0,
        salesCountSource: lastSale?.salesCountSource ?? null,
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
        createdAt: row.created_at,
      };
    })
    .filter((row) => {
      if (sourceMode !== "all" && row.sourceMode !== sourceMode) return false;
      if (!queryText) return true;
      const haystack = `${row.asin} ${row.amazonTitle} ${row.ebayTitle}`.toLowerCase();
      return haystack.includes(queryText.toLowerCase());
    });

  const opportunities = groupByAsinPriority(dedupeExactEbayListings(mappedRows)).slice(0, limit);

  return jsonNoStore({
    refreshedAt: new Date().toISOString(),
    summary: {
      total: opportunities.length,
      buyNow: opportunities.filter((row) => row.opportunityType === "buy_now").length,
      bestOffer: opportunities.filter((row) => row.opportunityType === "best_offer").length,
      auction: opportunities.filter((row) => row.opportunityType === "auction").length,
      multiUnit: opportunities.filter((row) => row.opportunityType === "multi_unit").length,
    },
    opportunities,
    batch: latestBatch,
  });
}

const OPPORTUNITY_SELECT = `
  *,
  sourcing_seed_asins (
    amazon_title,
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
  if (!runId) query = query.in("sourcing_run_id", latestRunIds);

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
      .select("asin,buy_box_price_current_cents,buy_box_price_avg90_cents,new_fba_price_current_cents,new_price_current_cents,raw_keepa_json")
      .in("asin", chunk);
    if (error) throw new Error(`Keepa snapshots: ${error.message}`);

    for (const row of (data ?? []) as KeepaSnapshotRow[]) {
      const asin = row.asin?.toUpperCase();
      if (asin) {
        const buyBoxCurrent = centsToDollars(row.buy_box_price_current_cents);
        const lowFbaCurrent = centsToDollars(row.new_fba_price_current_cents);
        const newCurrent = centsToDollars(row.new_price_current_cents);
        const buyBoxAvg90 = centsToDollars(row.buy_box_price_avg90_cents);
        const newAvg90 = keepaStatsCentsToDollars(row.raw_keepa_json, "avg90", 1);
        byAsin.set(asin, {
          avg90Price: buyBoxAvg90 ?? newAvg90,
          avg90Label: buyBoxAvg90 !== null ? "Buy Box avg" : newAvg90 !== null ? "New avg" : null,
          currentPrice: buyBoxCurrent ?? lowFbaCurrent ?? newCurrent,
          currentPriceLabel:
            buyBoxCurrent !== null
              ? "Buy Box"
              : lowFbaCurrent !== null
                ? "Low FBA New"
                : newCurrent !== null
                  ? "New Current"
                  : null,
          imageUrl: keepaImageUrl(row.raw_keepa_json),
        });
      }
    }
  }

  return byAsin;
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
  return typeof value === "number" ? value / 100 : null;
}

function keepaStatsCentsToDollars(rawKeepa: unknown, statsKey: "avg90" | "current", index: number) {
  if (!rawKeepa || typeof rawKeepa !== "object") return null;
  const stats = (rawKeepa as { stats?: unknown }).stats;
  if (!stats || typeof stats !== "object") return null;
  const values = (stats as Record<string, unknown>)[statsKey];
  if (!Array.isArray(values)) return null;
  const cents = values[index];
  return typeof cents === "number" && cents >= 0 ? cents / 100 : null;
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
