import { NextRequest, NextResponse } from "next/server";
import { supabase, toNumber } from "../_supabase";

type OpportunityRow = {
  opportunity_id: string;
  sourcing_run_id: string;
  asin: string;
  opportunity_type: string | null;
  status: string | null;
  profit: number | null;
  roi_percent: number | null;
  max_profitable_landed_cost: number | null;
  max_offer_price: number | null;
  required_offer_percent_of_ask: number | null;
  max_bid: number | null;
  total_profit_opportunity: number | null;
  score: number | null;
  ai_flags: string[] | null;
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
  } | null;
  sourcing_ebay_candidates?: {
    ebay_item_id: string | null;
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
};

type ShippingQuoteStatus = "known_paid" | "known_free" | "unknown_no_cost" | "unknown_no_options";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status") ?? "open";
  const type = searchParams.get("type") ?? "all";
  const runId = searchParams.get("runId");
  const sourceMode = searchParams.get("sourceMode") ?? "all";
  const queryText = (searchParams.get("q") ?? "").trim();
  const limit = Math.min(toNumber(searchParams.get("limit"), 100), 250);
  const queryLimit = sourceMode === "all" ? limit : 500;

  let query = supabase
    .from("sourcing_opportunities")
    .select(
      `
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
        last_sold_at
      ),
      sourcing_ebay_candidates (
        ebay_item_id,
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
    `,
    )
    .order("score", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(queryLimit);

  if (status !== "all") query = query.eq("status", status);
  if (type !== "all") query = query.eq("opportunity_type", type);
  if (runId) query = query.eq("sourcing_run_id", runId);
  const { data, error } = await query;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const rows = (data ?? []) as OpportunityRow[];
  const keepaByAsin = await fetchKeepaPriceContextByAsin(rows.map((row) => row.asin));

  const opportunities = rows.map((row) => {
    const shippingQuoteStatus = getShippingQuoteStatus(row.sourcing_ebay_candidates?.raw_ebay_json);
    return {
    opportunityId: row.opportunity_id,
    runId: row.sourcing_run_id,
    asin: row.asin,
    amazonTitle: row.sourcing_seed_asins?.amazon_title ?? "",
    amazonImageUrl: row.sourcing_seed_asins?.amazon_image_url ?? null,
    sellerSku: row.sourcing_seed_asins?.seller_sku ?? null,
    sourceMode: row.sourcing_seed_asins?.source_mode ?? null,
    amazonUrl: `https://www.amazon.com/dp/${row.asin}`,
    ebayItemId: row.sourcing_ebay_candidates?.ebay_item_id ?? null,
    ebayUrl: row.sourcing_ebay_candidates?.ebay_item_web_url ?? null,
    ebayTitle: row.sourcing_ebay_candidates?.ebay_title ?? "",
    ebayImageUrl: row.sourcing_ebay_candidates?.ebay_image_url ?? null,
    sellerUsername: row.sourcing_ebay_candidates?.seller_username ?? null,
    itemLocationCountry: row.sourcing_ebay_candidates?.item_location_country ?? null,
    conditionName: row.sourcing_ebay_candidates?.condition ?? null,
    buyingOptions: row.sourcing_ebay_candidates?.buying_options ?? [],
    itemPrice: row.sourcing_ebay_candidates?.price ?? null,
    shippingPrice: row.sourcing_ebay_candidates?.shipping_cost ?? null,
    landedCost: row.sourcing_ebay_candidates?.landed_cost ?? null,
    shippingQuoteStatus,
    shippingQuoteLabel: getShippingQuoteLabel(shippingQuoteStatus),
    quantityAvailable: row.sourcing_ebay_candidates?.available_quantity ?? null,
    auctionEndAt: row.sourcing_ebay_candidates?.auction_end_time ?? null,
    bidCount: row.sourcing_ebay_candidates?.bid_count ?? null,
    bestOfferEnabled: row.sourcing_ebay_candidates?.best_offer_enabled ?? false,
    targetSalePrice: row.sourcing_seed_asins?.target_sale_price ?? null,
    lastSalePrice: row.sourcing_seed_asins?.last_sold_at ? row.sourcing_seed_asins?.target_sale_price ?? null : null,
    keepaAvg90Price: keepaByAsin.get(row.asin)?.avg90Price ?? null,
    keepaAvg90Label: keepaByAsin.get(row.asin)?.avg90Label ?? null,
    keepaCurrentPrice: keepaByAsin.get(row.asin)?.currentPrice ?? null,
    keepaCurrentPriceLabel: keepaByAsin.get(row.asin)?.currentPriceLabel ?? null,
    currentInventoryUnits: row.sourcing_seed_asins?.current_inventory_units ?? null,
    monthlyVelocity: row.sourcing_seed_asins?.monthly_velocity ?? null,
    monthsOfSupply: row.sourcing_seed_asins?.months_of_supply ?? null,
    inventoryNeedLevel: row.sourcing_seed_asins?.inventory_need_level ?? null,
    lastSoldAt: row.sourcing_seed_asins?.last_sold_at ?? null,
    opportunityType: row.opportunity_type,
    status: row.status,
    estimatedProfit: row.profit,
    estimatedRoiPercent: row.roi_percent,
    maxProfitableLandedCost: row.max_profitable_landed_cost,
    suggestedOfferPrice: row.max_offer_price,
    requiredOfferPercentOfAsk: row.required_offer_percent_of_ask,
    suggestedMaxBid: row.max_bid,
    quantityMultiplier: row.sourcing_ebay_candidates?.available_quantity ?? null,
    totalProfitOpportunity: row.total_profit_opportunity,
    score: row.score,
    aiFlags: row.ai_flags ?? [],
    createdAt: row.created_at,
  };
  }).filter((row) => {
    if (sourceMode !== "all" && row.sourceMode !== sourceMode) return false;
    if (!queryText) return true;
    const haystack = `${row.asin} ${row.amazonTitle} ${row.ebayTitle}`.toLowerCase();
    return haystack.includes(queryText.toLowerCase());
  }).slice(0, limit);

  return NextResponse.json({
    refreshedAt: new Date().toISOString(),
    summary: {
      total: opportunities.length,
      buyNow: opportunities.filter((row) => row.opportunityType === "buy_now").length,
      bestOffer: opportunities.filter((row) => row.opportunityType === "best_offer").length,
      auction: opportunities.filter((row) => row.opportunityType === "auction").length,
      multiUnit: opportunities.filter((row) => row.opportunityType === "multi_unit").length,
    },
    opportunities,
  });
}

function getShippingQuoteStatus(rawEbay: unknown): ShippingQuoteStatus {
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
        });
      }
    }
  }

  return byAsin;
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
