import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

const HEALTHY_MAX_AGE_DAYS = 59;
const WATCH_MAX_AGE_DAYS = 89;
const REPRICE_MAX_AGE_DAYS = 179;
const STALE_KEEPA_DAYS = 30;

type AmazonAgeBucket =
  | "0-90"
  | "91-180"
  | "181-270"
  | "271-365"
  | "365+";

type RecommendationTier =
  | "Healthy"
  | "Watch"
  | "Reprice"
  | "Liquidate"
  | "Remove / eBay"
  | "Needs Data";

type InventoryRow = {
  seller_sku: string | null;
  marketplace_id: string | null;
  asin: string | null;
  fnsku: string | null;
  product_name: string | null;
  condition: string | null;
  total_quantity: number | null;
  fulfillable_quantity: number | null;
  inbound_working_quantity: number | null;
  inbound_shipped_quantity: number | null;
  inbound_receiving_quantity: number | null;
  reserved_quantity: number | null;
  researching_quantity: number | null;
  unfulfillable_quantity: number | null;
  captured_at: string | null;
};

type AmazonSkuRow = {
  amazon_sku_id: string;
  seller_sku: string;
  marketplace_id: string;
  asin: string | null;
  product_name: string | null;
  condition: string | null;
  fulfillment_channel: string | null;
  listing_status: string | null;
  item_status: string | null;
  currency: string | null;
  listing_price: number | null;
  landed_price: number | null;
};

type ListingSnapshotRow = {
  seller_sku: string;
  marketplace_id: string;
  asin: string | null;
  product_name: string | null;
  condition: string | null;
  listing_status: string | null;
  item_status: string | null;
  fulfillment_channel: string | null;
  issue_count: number | null;
  issue_severity: string | null;
  issues_json: unknown;
  captured_at: string | null;
};

type InventoryPlanningRow = {
  seller_sku: string;
  marketplace_id: string;
  asin: string | null;
  snapshot_date: string | null;
  available_quantity: number | null;
  pending_removal_quantity: number | null;
  inv_age_0_to_90_days: number | null;
  inv_age_91_to_180_days: number | null;
  inv_age_181_to_270_days: number | null;
  inv_age_271_to_365_days: number | null;
  inv_age_365_plus_days: number | null;
  estimated_storage_cost_next_month: number | null;
  estimated_ltsf_next_charge: number | null;
  recommended_action: string | null;
  healthy_inventory_level: number | null;
  sales_shipped_last_7_days: number | null;
  sales_shipped_last_30_days: number | null;
  sales_shipped_last_60_days: number | null;
  sales_shipped_last_90_days: number | null;
  alert: string | null;
  captured_at: string | null;
};

type InventoryLabRow = {
  seller_sku: string | null;
  asin: string | null;
  title: string | null;
  active_cost_per_unit: number | null;
  active_supplier: string | null;
  active_date_purchased: string | null;
  list_price: number | null;
  condition: string | null;
  match_status: string | null;
};

type KeepaRow = {
  asin: string;
  captured_at: string | null;
  title: string | null;
  buy_box_price_current_cents: number | null;
  buy_box_price_avg30_cents: number | null;
  buy_box_price_avg90_cents: number | null;
  new_price_current_cents: number | null;
  new_fba_price_current_cents: number | null;
  sales_rank_current: number | null;
  sales_rank_avg30: number | null;
  sales_rank_avg90: number | null;
  sales_rank_avg180: number | null;
  sales_rank_drops30: number | null;
  sales_rank_drops90: number | null;
  sales_rank_drops180: number | null;
  offer_count_current: number | null;
  review_count_current: number | null;
  rating_current: number | null;
};

type InventoryPositionRow = {
  asin: string | null;
  seller_sku: string | null;
  quantity: number | null;
  unit_cost: number | null;
  total_cost: number | null;
  effective_at: string | null;
  inventory_state: string | null;
  physical_location: string | null;
  marketplace_intent: string | null;
  listing_channel: string | null;
};

type AdvisorRow = {
  asin: string | null;
  seller_sku: string;
  title: string;
  condition: string | null;
  fba_sellable_quantity: number;
  inbound_quantity: number;
  reserved_quantity: number;
  unsellable_quantity: number;
  total_quantity: number;
  listing_status: string | null;
  listing_issue_status: string;
  listing_issue_count: number;
  cost_basis: number | null;
  cost_source: string | null;
  oldest_known_purchase_date: string | null;
  inventory_age_days: number | null;
  amazon_age_bucket: AmazonAgeBucket | null;
  amazon_age_source: "Amazon Inventory Planning" | "InventoryLab/MBOP fallback" | "Missing";
  inv_age_0_to_90_days: number;
  inv_age_91_to_180_days: number;
  inv_age_181_to_270_days: number;
  inv_age_271_to_365_days: number;
  inv_age_365_plus_days: number;
  planning_snapshot_date: string | null;
  planning_recommended_action: string | null;
  planning_alert: string | null;
  sales_shipped_last_30_days: number | null;
  sales_shipped_last_90_days: number | null;
  current_list_price: number | null;
  keepa_buy_box_price: number | null;
  keepa_buy_box_avg30: number | null;
  keepa_buy_box_avg90: number | null;
  keepa_sales_rank_current: number | null;
  keepa_sales_rank_avg90: number | null;
  keepa_sales_rank_drops30: number | null;
  keepa_sales_rank_drops90: number | null;
  offer_count: number | null;
  review_count: number | null;
  rating: number | null;
  keepa_captured_at: string | null;
  has_keepa_data: boolean;
  estimated_capital_tied_up: number | null;
  recommendation_tier: RecommendationTier;
  recommended_manual_action: string;
  reason: string;
};

export async function GET() {
  try {
    const [
      inventoryRows,
      skuRows,
      listingRows,
      planningRows,
      inventoryLabRows,
      keepaRows,
      positionRows,
    ] = await Promise.all([
        fetchAll<InventoryRow>(
          "vw_latest_amazon_fba_inventory_snapshot",
          "seller_sku,marketplace_id,asin,fnsku,product_name,condition,total_quantity," +
            "fulfillable_quantity,inbound_working_quantity,inbound_shipped_quantity," +
            "inbound_receiving_quantity,reserved_quantity,researching_quantity," +
            "unfulfillable_quantity,captured_at"
        ),
        fetchAll<AmazonSkuRow>(
          "amazon_skus",
          "amazon_sku_id,seller_sku,marketplace_id,asin,product_name,condition," +
            "fulfillment_channel,listing_status,item_status,currency,listing_price,landed_price"
        ),
        fetchAll<ListingSnapshotRow>(
          "vw_latest_amazon_listing_snapshot",
          "seller_sku,marketplace_id,asin,product_name,condition,listing_status,item_status," +
            "fulfillment_channel,issue_count,issue_severity,issues_json,captured_at"
        ),
        fetchAll<InventoryPlanningRow>(
          "vw_latest_amazon_inventory_planning_snapshot",
          "seller_sku,marketplace_id,asin,snapshot_date,available_quantity,pending_removal_quantity," +
            "inv_age_0_to_90_days,inv_age_91_to_180_days,inv_age_181_to_270_days," +
            "inv_age_271_to_365_days,inv_age_365_plus_days,estimated_storage_cost_next_month," +
            "estimated_ltsf_next_charge,recommended_action,healthy_inventory_level," +
            "sales_shipped_last_7_days,sales_shipped_last_30_days,sales_shipped_last_60_days," +
            "sales_shipped_last_90_days,alert,captured_at"
        ),
        fetchAll<InventoryLabRow>(
          "inventorylab_active_inventory_backfill",
          "seller_sku,asin,title,active_cost_per_unit,active_supplier,active_date_purchased," +
            "list_price,condition,match_status"
        ),
        fetchAll<KeepaRow>(
          "vw_latest_keepa_product_snapshot",
          "asin,captured_at,title,buy_box_price_current_cents,buy_box_price_avg30_cents," +
            "buy_box_price_avg90_cents,new_price_current_cents,new_fba_price_current_cents," +
            "sales_rank_current,sales_rank_avg30,sales_rank_avg90,sales_rank_avg180," +
            "sales_rank_drops30,sales_rank_drops90,sales_rank_drops180,offer_count_current," +
            "review_count_current,rating_current"
        ),
        fetchAll<InventoryPositionRow>(
          "inventory_positions",
          "asin,seller_sku,quantity,unit_cost,total_cost,effective_at,inventory_state," +
            "physical_location,marketplace_intent,listing_channel"
        ),
      ]);

    const rows = buildAdvisorRows(
      inventoryRows,
      keyBySku(skuRows),
      keyBySku(listingRows),
      keyBySku(planningRows),
      keyBySellerSku(inventoryLabRows),
      keyByAsin(keepaRows),
      aggregatePositions(positionRows)
    );

    return NextResponse.json({
      generated_at: new Date().toISOString(),
      thresholds: {
        healthy_max_age_days: HEALTHY_MAX_AGE_DAYS,
        watch_max_age_days: WATCH_MAX_AGE_DAYS,
        reprice_max_age_days: REPRICE_MAX_AGE_DAYS,
        stale_keepa_days: STALE_KEEPA_DAYS,
      },
      summary: summarizeRows(rows),
      rows,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to build repricing recommendations",
      },
      { status: 500 }
    );
  }
}

async function fetchAll<T>(table: string, select: string): Promise<T[]> {
  const rows: T[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from(table)
      .select(select)
      .range(offset, offset + pageSize - 1);

    if (error) throw new Error(`${table}: ${error.message}`);

    rows.push(...((data ?? []) as T[]));
    if (!data || data.length < pageSize) return rows;
    offset += pageSize;
  }
}

function buildAdvisorRows(
  inventoryRows: InventoryRow[],
  skuByKey: Map<string, AmazonSkuRow>,
  listingByKey: Map<string, ListingSnapshotRow>,
  planningByKey: Map<string, InventoryPlanningRow>,
  inventoryLabBySku: Map<string, InventoryLabRow>,
  keepaByAsin: Map<string, KeepaRow>,
  positionBySku: Map<string, { unit_cost: number | null; oldest_date: string | null }>
): AdvisorRow[] {
  return inventoryRows
    .map((inventory) => {
      const sellerSku = cleanText(inventory.seller_sku);
      const marketplaceId = cleanText(inventory.marketplace_id);
      if (!sellerSku || !marketplaceId) return null;

      const key = skuKey(sellerSku, marketplaceId);
      const sku = skuByKey.get(key);
      const listing = listingByKey.get(key);
      const planning = planningByKey.get(key);
      const inventoryLab = inventoryLabBySku.get(sellerSku);
      const asin = normalizeAsin(
        inventory.asin ?? sku?.asin ?? listing?.asin ?? planning?.asin ?? inventoryLab?.asin
      );
      const keepa = asin ? keepaByAsin.get(asin) : undefined;
      const position = positionBySku.get(sellerSku);

      const fbaSellableQuantity = toNumber(inventory.fulfillable_quantity, 0);
      const inboundQuantity =
        toNumber(inventory.inbound_working_quantity, 0) +
        toNumber(inventory.inbound_shipped_quantity, 0) +
        toNumber(inventory.inbound_receiving_quantity, 0);
      const reservedQuantity = toNumber(inventory.reserved_quantity, 0);
      const unsellableQuantity = toNumber(inventory.unfulfillable_quantity, 0);
      const componentQuantity =
        fbaSellableQuantity + inboundQuantity + reservedQuantity + unsellableQuantity;
      const totalQuantity =
        componentQuantity > 0 ? componentQuantity : toNumber(inventory.total_quantity, 0);

      if (totalQuantity <= 0) return null;

      const costBasis =
        toOptionalNumber(inventoryLab?.active_cost_per_unit) ??
        position?.unit_cost ??
        null;
      const costSource =
        toOptionalNumber(inventoryLab?.active_cost_per_unit) !== null
          ? "InventoryLab"
          : position?.unit_cost !== null && position?.unit_cost !== undefined
            ? "MBOP inventory projection"
            : null;
      const oldestKnownPurchaseDate =
        dateOnly(inventoryLab?.active_date_purchased) ?? dateOnly(position?.oldest_date) ?? null;
      const inventoryAgeDays = oldestKnownPurchaseDate
        ? daysBetween(oldestKnownPurchaseDate, todayDateOnly())
        : null;
      const ageSignal = planningAgeSignal(planning);
      const amazonAgeSource = ageSignal
        ? "Amazon Inventory Planning"
        : inventoryAgeDays !== null
          ? "InventoryLab/MBOP fallback"
          : "Missing";
      const currentListPrice =
        toOptionalNumber(sku?.listing_price) ??
        toOptionalNumber(sku?.landed_price) ??
        toOptionalNumber(inventoryLab?.list_price) ??
        null;
      const keepaBuyBoxPrice = centsToDollars(keepa?.buy_box_price_current_cents);
      const listingStatus = cleanText(listing?.listing_status ?? sku?.listing_status);
      const listingIssueCount = toNumber(listing?.issue_count, 0);
      const listingIssueStatus = listingIssueSummary(listingStatus, listingIssueCount, listing);
      const capitalTiedUp =
        costBasis !== null ? roundMoney(costBasis * totalQuantity) : null;

      const recommendation = recommend({
        asin,
        ageDays: inventoryAgeDays,
        costBasis,
        currentListPrice,
        keepa,
        keepaBuyBoxPrice,
        amazonAgeBucket: ageSignal?.bucket ?? null,
        listingStatus,
        listingIssueCount,
        unsellableQuantity,
      });

      return {
        asin,
        seller_sku: sellerSku,
        title:
          cleanText(inventory.product_name) ??
          cleanText(listing?.product_name) ??
          cleanText(sku?.product_name) ??
          cleanText(inventoryLab?.title) ??
          cleanText(keepa?.title) ??
          "Untitled Amazon item",
        condition:
          cleanText(inventory.condition) ??
          cleanText(listing?.condition) ??
          cleanText(sku?.condition) ??
          cleanText(inventoryLab?.condition),
        fba_sellable_quantity: fbaSellableQuantity,
        inbound_quantity: inboundQuantity,
        reserved_quantity: reservedQuantity,
        unsellable_quantity: unsellableQuantity,
        total_quantity: totalQuantity,
        listing_status: listingStatus,
        listing_issue_status: listingIssueStatus,
        listing_issue_count: listingIssueCount,
        cost_basis: costBasis,
        cost_source: costSource,
        oldest_known_purchase_date: oldestKnownPurchaseDate,
        inventory_age_days: inventoryAgeDays,
        amazon_age_bucket: ageSignal?.bucket ?? null,
        amazon_age_source: amazonAgeSource,
        inv_age_0_to_90_days: toNumber(planning?.inv_age_0_to_90_days, 0),
        inv_age_91_to_180_days: toNumber(planning?.inv_age_91_to_180_days, 0),
        inv_age_181_to_270_days: toNumber(planning?.inv_age_181_to_270_days, 0),
        inv_age_271_to_365_days: toNumber(planning?.inv_age_271_to_365_days, 0),
        inv_age_365_plus_days: toNumber(planning?.inv_age_365_plus_days, 0),
        planning_snapshot_date: dateOnly(planning?.snapshot_date) ?? dateOnly(planning?.captured_at),
        planning_recommended_action: cleanText(planning?.recommended_action),
        planning_alert: cleanText(planning?.alert),
        sales_shipped_last_30_days: toOptionalNumber(planning?.sales_shipped_last_30_days),
        sales_shipped_last_90_days: toOptionalNumber(planning?.sales_shipped_last_90_days),
        current_list_price: currentListPrice,
        keepa_buy_box_price: keepaBuyBoxPrice,
        keepa_buy_box_avg30: centsToDollars(keepa?.buy_box_price_avg30_cents),
        keepa_buy_box_avg90: centsToDollars(keepa?.buy_box_price_avg90_cents),
        keepa_sales_rank_current: toOptionalNumber(keepa?.sales_rank_current),
        keepa_sales_rank_avg90: toOptionalNumber(keepa?.sales_rank_avg90),
        keepa_sales_rank_drops30: toOptionalNumber(keepa?.sales_rank_drops30),
        keepa_sales_rank_drops90: toOptionalNumber(keepa?.sales_rank_drops90),
        offer_count: toOptionalNumber(keepa?.offer_count_current),
        review_count: toOptionalNumber(keepa?.review_count_current),
        rating: toOptionalNumber(keepa?.rating_current),
        keepa_captured_at: keepa?.captured_at ?? null,
        has_keepa_data: !!keepa,
        estimated_capital_tied_up: capitalTiedUp,
        recommendation_tier: recommendation.tier,
        recommended_manual_action: recommendation.action,
        reason: recommendation.reason,
      };
    })
    .filter((row): row is AdvisorRow => !!row)
    .sort((left, right) => {
      const tierDifference = tierSort(left.recommendation_tier) - tierSort(right.recommendation_tier);
      if (tierDifference !== 0) return tierDifference;
      const ageDifference = bucketSort(right.amazon_age_bucket) - bucketSort(left.amazon_age_bucket);
      if (ageDifference !== 0) return ageDifference;
      return (right.inventory_age_days ?? -1) - (left.inventory_age_days ?? -1);
    });
}

function recommend(input: {
  asin: string | null;
  ageDays: number | null;
  costBasis: number | null;
  currentListPrice: number | null;
  keepa?: KeepaRow;
  keepaBuyBoxPrice: number | null;
  amazonAgeBucket?: AmazonAgeBucket | null;
  listingStatus: string | null;
  listingIssueCount: number;
  unsellableQuantity: number;
}): { tier: RecommendationTier; action: string; reason: string } {
  if (!input.asin) {
    return needsData("Missing ASIN; cannot connect Amazon, Keepa, and cost context.");
  }

  const buyable = listingStatusIsBuyable(input.listingStatus);
  if (
    input.unsellableQuantity > 0 ||
    input.listingIssueCount > 0 ||
    (input.listingStatus !== null && !buyable)
  ) {
    return {
      tier: "Remove / eBay",
      action: "Review listing issue, removal, or eBay transfer.",
      reason: "Unsellable quantity or Amazon listing issue detected; repricing alone may not fix this inventory.",
    };
  }

  if (input.costBasis === null) {
    return needsData("Missing cost basis; cannot calculate a safe liquidation floor.");
  }
  if (!input.amazonAgeBucket && input.ageDays === null) {
    return needsData("Missing Amazon planning age bucket and fallback date context; cannot assess aged inventory.");
  }
  if (input.currentListPrice === null && input.keepaBuyBoxPrice === null) {
    return needsData("Missing pricing context; run pricing sync or targeted Keepa sync before repricing.");
  }
  if (!input.keepa) {
    return needsData("Keepa snapshot missing; run targeted Keepa sync before repricing decision.");
  }

  if (input.amazonAgeBucket) {
    if (input.amazonAgeBucket === "365+" || input.amazonAgeBucket === "271-365" || input.amazonAgeBucket === "181-270") {
      return {
        tier: "Liquidate",
        action: "Consider liquidation pricing or alternate channel move.",
        reason: `${input.amazonAgeBucket} Amazon planning age bucket with active FBA inventory; recover capital even if margin compresses.`,
      };
    }

    if (input.amazonAgeBucket === "91-180") {
      const buyBoxBelowList =
        input.currentListPrice !== null &&
        input.keepaBuyBoxPrice !== null &&
        input.keepaBuyBoxPrice < input.currentListPrice;
      return {
        tier: "Reprice",
        action: "Review Informed.co floor and current listing price manually.",
        reason: buyBoxBelowList
          ? "Amazon planning shows 91-180 day inventory and Keepa Buy Box is below current/list price; review repricer floor."
          : "Amazon planning shows 91-180 day sellable FBA inventory; consider a controlled price reduction.",
      };
    }

    return {
      tier: "Watch",
      action: "Monitor sales velocity and Buy Box position.",
      reason: "Amazon planning places this inventory in the 0-90 day bucket; exact 60-day split is unavailable from this report.",
    };
  }

  if ((input.ageDays ?? 0) <= HEALTHY_MAX_AGE_DAYS) {
    return {
      tier: "Healthy",
      action: "No repricing action needed.",
      reason: "Inventory is under 60 days old and no major Amazon listing issue is visible.",
    };
  }
  if ((input.ageDays ?? 0) <= WATCH_MAX_AGE_DAYS) {
    return {
      tier: "Watch",
      action: "Monitor sales velocity and Buy Box position.",
      reason: "60-89 days old; watch before forcing price down.",
    };
  }
  if ((input.ageDays ?? 0) <= REPRICE_MAX_AGE_DAYS) {
    const buyBoxBelowList =
      input.currentListPrice !== null &&
      input.keepaBuyBoxPrice !== null &&
      input.keepaBuyBoxPrice < input.currentListPrice;
    return {
      tier: "Reprice",
      action: "Review Informed.co floor and current listing price manually.",
      reason: buyBoxBelowList
        ? "90+ days old and Keepa Buy Box is below current/list price; review repricer floor."
        : "90+ days old with sellable FBA quantity; consider a controlled price reduction.",
    };
  }

  return {
    tier: "Liquidate",
    action: "Consider liquidation pricing or alternate channel move.",
    reason: "180+ days old with active Amazon inventory; recover capital even if margin compresses.",
  };
}

function needsData(reason: string) {
  return {
    tier: "Needs Data" as const,
    action: "Fill missing data or run targeted sync before repricing.",
    reason,
  };
}

function summarizeRows(rows: AdvisorRow[]) {
  const byTier = Object.fromEntries(
    (["Healthy", "Watch", "Reprice", "Liquidate", "Remove / eBay", "Needs Data"] as RecommendationTier[]).map(
      (tier) => [tier, 0]
    )
  ) as Record<RecommendationTier, number>;

  let totalCapital = 0;
  let agedCapital90 = 0;
  let agedCapital180 = 0;
  let rowsNeedingData = 0;
  let unsellableOrSuppressed = 0;

  for (const row of rows) {
    byTier[row.recommendation_tier] += 1;
    const capital = row.estimated_capital_tied_up ?? 0;
    const costBasis = row.cost_basis ?? 0;
    const aged90Units =
      row.inv_age_91_to_180_days +
      row.inv_age_181_to_270_days +
      row.inv_age_271_to_365_days +
      row.inv_age_365_plus_days;
    const aged180Units =
      row.inv_age_181_to_270_days +
      row.inv_age_271_to_365_days +
      row.inv_age_365_plus_days;
    totalCapital += capital;
    if (row.amazon_age_bucket) {
      agedCapital90 += costBasis * aged90Units;
      agedCapital180 += costBasis * aged180Units;
    } else {
      if ((row.inventory_age_days ?? 0) >= 90) agedCapital90 += capital;
      if ((row.inventory_age_days ?? 0) >= 180) agedCapital180 += capital;
    }
    if (row.recommendation_tier === "Needs Data") rowsNeedingData += 1;
    if (row.unsellable_quantity > 0 || row.listing_issue_count > 0) {
      unsellableOrSuppressed += 1;
    }
  }

  return {
    total_rows: rows.length,
    total_units: rows.reduce((total, row) => total + row.total_quantity, 0),
    total_estimated_capital_tied_up: roundMoney(totalCapital),
    aged_capital_over_90_days: roundMoney(agedCapital90),
    aged_capital_over_180_days: roundMoney(agedCapital180),
    rows_needing_data: rowsNeedingData,
    unsellable_or_suppressed_rows: unsellableOrSuppressed,
    by_tier: byTier,
  };
}

function planningAgeSignal(row?: InventoryPlanningRow) {
  if (!row) return null;

  const buckets: Array<{ bucket: AmazonAgeBucket; units: number; sort: number }> = [
    { bucket: "365+", units: toNumber(row.inv_age_365_plus_days, 0), sort: 5 },
    { bucket: "271-365", units: toNumber(row.inv_age_271_to_365_days, 0), sort: 4 },
    { bucket: "181-270", units: toNumber(row.inv_age_181_to_270_days, 0), sort: 3 },
    { bucket: "91-180", units: toNumber(row.inv_age_91_to_180_days, 0), sort: 2 },
    { bucket: "0-90", units: toNumber(row.inv_age_0_to_90_days, 0), sort: 1 },
  ];

  return buckets.find((bucket) => bucket.units > 0) ?? null;
}

function aggregatePositions(rows: InventoryPositionRow[]) {
  const bySku = new Map<string, { unit_cost: number | null; oldest_date: string | null }>();

  for (const row of rows) {
    const sku = cleanText(row.seller_sku);
    if (!sku || row.marketplace_intent !== "amazon_fba" || row.physical_location !== "amazon_fba") {
      continue;
    }

    const current = bySku.get(sku) ?? { unit_cost: null, oldest_date: null };
    const unitCost = toOptionalNumber(row.unit_cost);
    if (current.unit_cost === null && unitCost !== null) {
      current.unit_cost = unitCost;
    }

    const date = dateOnly(row.effective_at);
    if (date && (!current.oldest_date || date < current.oldest_date)) {
      current.oldest_date = date;
    }

    bySku.set(sku, current);
  }

  return bySku;
}

function keyBySku<T extends { seller_sku: string | null; marketplace_id?: string | null }>(rows: T[]) {
  const map = new Map<string, T>();
  for (const row of rows) {
    const sellerSku = cleanText(row.seller_sku);
    const marketplaceId = cleanText(row.marketplace_id) ?? "";
    if (sellerSku) map.set(skuKey(sellerSku, marketplaceId), row);
  }
  return map;
}

function keyBySellerSku<T extends { seller_sku: string | null }>(rows: T[]) {
  const map = new Map<string, T>();
  for (const row of rows) {
    const sellerSku = cleanText(row.seller_sku);
    if (sellerSku) map.set(sellerSku, row);
  }
  return map;
}

function keyByAsin<T extends { asin: string | null }>(rows: T[]) {
  const map = new Map<string, T>();
  for (const row of rows) {
    const asin = normalizeAsin(row.asin);
    if (asin) map.set(asin, row);
  }
  return map;
}

function skuKey(sellerSku: string, marketplaceId: string) {
  return `${sellerSku}::${marketplaceId}`;
}

function listingIssueSummary(
  listingStatus: string | null,
  issueCount: number,
  listing?: ListingSnapshotRow
) {
  if (issueCount > 0) {
    return `${issueCount} issue${issueCount === 1 ? "" : "s"}${
      listing?.issue_severity ? ` (${listing.issue_severity})` : ""
    }`;
  }
  if (!listingStatus) return "Unknown";
  if (!listingStatusIsBuyable(listingStatus)) return listingStatus;
  return "None";
}

function listingStatusIsBuyable(listingStatus: string | null) {
  if (!listingStatus) return false;
  return listingStatus
    .split(",")
    .map((part) => part.trim().toUpperCase())
    .includes("BUYABLE");
}

function tierSort(tier: RecommendationTier) {
  const order: Record<RecommendationTier, number> = {
    "Remove / eBay": 0,
    Liquidate: 1,
    Reprice: 2,
    "Needs Data": 3,
    Watch: 4,
    Healthy: 5,
  };
  return order[tier];
}

function bucketSort(bucket: AmazonAgeBucket | null) {
  const order: Record<AmazonAgeBucket, number> = {
    "0-90": 1,
    "91-180": 2,
    "181-270": 3,
    "271-365": 4,
    "365+": 5,
  };
  return bucket ? order[bucket] : 0;
}

function centsToDollars(value?: number | null) {
  const cents = toOptionalNumber(value);
  return cents === null ? null : roundMoney(cents / 100);
}

function toNumber(value: unknown, defaultValue: number) {
  const number = Number(value);
  return Number.isFinite(number) ? number : defaultValue;
}

function toOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function cleanText(value: unknown) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function normalizeAsin(value: unknown) {
  const text = cleanText(value)?.toUpperCase();
  return text && text.length === 10 ? text : null;
}

function dateOnly(value?: string | null) {
  if (!value) return null;
  const match = value.match(/^\d{4}-\d{2}-\d{2}/);
  if (!match) return null;
  const date = match[0];
  const year = Number(date.slice(0, 4));
  return year >= 2000 ? date : null;
}

function todayDateOnly() {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00Z`).getTime();
  const end = new Date(`${endDate}T00:00:00Z`).getTime();
  return Math.floor((end - start) / 86_400_000);
}
