import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

const HEALTHY_MAX_AGE_DAYS = 59;
const WATCH_MAX_AGE_DAYS = 89;
const REPRICE_MAX_AGE_DAYS = 179;
const STALE_KEEPA_DAYS = 30;
const REPRICE_DISCOUNT_PCT = 0.03;
const LIQUIDATE_DISCOUNT_PCT = 0.08;
const MIN_MARGIN_ABOVE_COST_PCT = 0.1;

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

type AdvisorBucket =
  | "Pricing"
  | "Inventory / Listing Issue"
  | "Missing Data";

type SalesVelocitySignal =
  | "Strong"
  | "Moving"
  | "Slow"
  | "No recent sales"
  | "Unknown";

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
  reserved_customer_order_quantity: number | null;
  reserved_fc_transfer_quantity: number | null;
  reserved_fc_processing_quantity: number | null;
  future_supply_buyable_quantity: number | null;
  reserved_future_supply_quantity: number | null;
  researching_quantity: number | null;
  unfulfillable_quantity: number | null;
  unfulfillable_customer_damaged_quantity: number | null;
  unfulfillable_warehouse_damaged_quantity: number | null;
  unfulfillable_distributor_damaged_quantity: number | null;
  unfulfillable_carrier_damaged_quantity: number | null;
  unfulfillable_defective_quantity: number | null;
  unfulfillable_expired_quantity: number | null;
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

type InformedListingRow = {
  asin: string | null;
  seller_sku: string | null;
  marketplace: string | null;
  fulfillment_channel: string | null;
  repricing_enabled: boolean | null;
  assigned_rule_name: string | null;
  current_price: number | null;
  min_price: number | null;
  max_price: number | null;
  buy_box_price: number | null;
  buy_box_status: string | null;
  buy_box_winner: boolean | null;
  competition_offer_count: number | null;
  quantity: number | null;
  listing_status: string | null;
  report_generated_at: string | null;
  imported_at: string | null;
};

type InformedRuleOverrideRow = {
  informed_rule_id: string | null;
  friendly_name: string | null;
  active: boolean | null;
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
  raw_keepa_json: unknown;
};

type CompetitionOffer = {
  seller_id: string | null;
  seller_name: string | null;
  fulfillment: "FBA" | "MFN" | "Unknown";
  landed_price: number | null;
  item_price: number | null;
  shipping_price: number | null;
  stock_quantity: number | null;
  condition: string | null;
  is_buy_box_winner: boolean;
  is_amazon: boolean;
  is_prime: boolean | null;
  last_seen: string | null;
};

type CompetitionSummary = {
  source: "Keepa offers" | "Keepa summary" | "Missing";
  note: string;
  condition_filter: string | null;
  offer_count: number | null;
  fba_offer_count: number;
  mfn_offer_count: number;
  lowest_fba_price: number | null;
  lowest_mfn_price: number | null;
  buy_box_seller_id: string | null;
  buy_box_price: number | null;
  total_observed_stock: number | null;
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
  reserved_customer_order_quantity: number;
  reserved_fc_transfer_quantity: number;
  reserved_fc_processing_quantity: number;
  future_supply_buyable_quantity: number;
  reserved_future_supply_quantity: number;
  inventory_detail_status: string;
  unsellable_quantity: number;
  unfulfillable_customer_damaged_quantity: number;
  unfulfillable_warehouse_damaged_quantity: number;
  unfulfillable_distributor_damaged_quantity: number;
  unfulfillable_carrier_damaged_quantity: number;
  unfulfillable_defective_quantity: number;
  unfulfillable_expired_quantity: number;
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
  sales_velocity_signal: SalesVelocitySignal;
  informed_rule_name: string | null;
  informed_rule_id: string | null;
  informed_current_price: number | null;
  informed_min_price: number | null;
  informed_max_price: number | null;
  informed_buy_box_price: number | null;
  informed_buy_box_status: string | null;
  informed_repricing_enabled: boolean | null;
  informed_missing_data: boolean;
  informed_price_gap_to_buy_box_pct: number | null;
  informed_min_price_gap_to_buy_box_pct: number | null;
  informed_repricing_note: string;
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
  competition_summary: CompetitionSummary;
  competition_offers: CompetitionOffer[];
  estimated_capital_tied_up: number | null;
  advisor_bucket: AdvisorBucket;
  recommended_target_price: number | null;
  target_price_basis: string | null;
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
      informedRows,
      informedRuleOverrides,
      inventoryLabRows,
      keepaRows,
      positionRows,
    ] = await Promise.all([
        fetchAll<InventoryRow>(
          "vw_latest_amazon_fba_inventory_snapshot",
          "seller_sku,marketplace_id,asin,fnsku,product_name,condition,total_quantity," +
            "fulfillable_quantity,inbound_working_quantity,inbound_shipped_quantity," +
            "inbound_receiving_quantity,reserved_quantity,researching_quantity," +
            "unfulfillable_quantity,reserved_customer_order_quantity,reserved_fc_transfer_quantity," +
            "reserved_fc_processing_quantity,future_supply_buyable_quantity,reserved_future_supply_quantity," +
            "unfulfillable_customer_damaged_quantity,unfulfillable_warehouse_damaged_quantity," +
            "unfulfillable_distributor_damaged_quantity,unfulfillable_carrier_damaged_quantity," +
            "unfulfillable_defective_quantity,unfulfillable_expired_quantity,captured_at"
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
        fetchAll<InformedListingRow>(
          "vw_latest_informed_listing_snapshot",
          "asin,seller_sku,marketplace,fulfillment_channel,repricing_enabled,assigned_rule_name," +
            "current_price,min_price,max_price,buy_box_price,buy_box_status,buy_box_winner," +
            "competition_offer_count,quantity,listing_status,report_generated_at,imported_at"
        ),
        fetchAll<InformedRuleOverrideRow>(
          "informed_rule_name_overrides",
          "informed_rule_id,friendly_name,active"
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
            "review_count_current,rating_current,raw_keepa_json"
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
      keyBySellerSku(informedRows),
      keyByInformedRuleId(informedRuleOverrides),
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
  informedBySku: Map<string, InformedListingRow>,
  informedRuleNameById: Map<string, string>,
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
      const informed = informedBySku.get(sellerSku);
      const informedRuleId = cleanText(informed?.assigned_rule_name);
      const informedRuleName = informedRuleId
        ? (informedRuleNameById.get(informedRuleId) ?? informedRuleId)
        : null;
      const inventoryLab = inventoryLabBySku.get(sellerSku);
      const itemCondition =
        cleanText(inventory.condition) ??
        cleanText(listing?.condition) ??
        cleanText(sku?.condition) ??
        cleanText(inventoryLab?.condition);
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
      const reservedCustomerOrderQuantity = toNumber(inventory.reserved_customer_order_quantity, 0);
      const reservedFcTransferQuantity = toNumber(inventory.reserved_fc_transfer_quantity, 0);
      const reservedFcProcessingQuantity = toNumber(inventory.reserved_fc_processing_quantity, 0);
      const futureSupplyBuyableQuantity = toNumber(inventory.future_supply_buyable_quantity, 0);
      const reservedFutureSupplyQuantity = toNumber(inventory.reserved_future_supply_quantity, 0);
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
        toOptionalNumber(informed?.current_price) ??
        toOptionalNumber(sku?.listing_price) ??
        toOptionalNumber(sku?.landed_price) ??
        toOptionalNumber(inventoryLab?.list_price) ??
        null;
      const keepaBuyBoxPrice = centsToDollars(keepa?.buy_box_price_current_cents);
      const competition = buildCompetitionContext(keepa, keepaBuyBoxPrice, itemCondition);
      const informedBuyBoxPrice = toOptionalNumber(informed?.buy_box_price);
      const marketReferencePrice =
        informedBuyBoxPrice ??
        keepaBuyBoxPrice ??
        centsToDollars(keepa?.buy_box_price_avg90_cents) ??
        centsToDollars(keepa?.new_price_current_cents);
      const listingStatus = cleanText(listing?.listing_status ?? sku?.listing_status);
      const rawListingIssueCount = toNumber(listing?.issue_count, 0);
      const actionableListingStatus = listingStatusNeedsAction(listingStatus);
      const listingIssueCount = actionableListingStatus ? rawListingIssueCount : 0;
      const listingIssueStatus = listingIssueSummary(listingStatus, listingIssueCount, listing);
      const capitalTiedUp =
        costBasis !== null ? roundMoney(costBasis * totalQuantity) : null;
      const sales30 = toOptionalNumber(planning?.sales_shipped_last_30_days);
      const sales90 = toOptionalNumber(planning?.sales_shipped_last_90_days);
      const velocitySignal = salesVelocitySignal(sales30, sales90, totalQuantity);
      const informedNote = informedRepricingNote({
        informed,
        tierAgeBucket: ageSignal?.bucket ?? null,
        ageDays: inventoryAgeDays,
        currentPrice: toOptionalNumber(informed?.current_price),
        minPrice: toOptionalNumber(informed?.min_price),
        buyBoxPrice: informedBuyBoxPrice ?? keepaBuyBoxPrice,
      });

      const recommendation = recommend({
        asin,
        ageDays: inventoryAgeDays,
        costBasis,
        currentListPrice,
        keepa,
        keepaBuyBoxPrice,
        informed,
        informedBuyBoxPrice,
        marketReferencePrice,
        salesVelocitySignal: velocitySignal,
        informedNote,
        amazonAgeBucket: ageSignal?.bucket ?? null,
        listingStatus,
        unsellableQuantity,
      });

      const actionableIssue =
        recommendation.tier === "Remove / eBay" ||
        recommendation.tier === "Reprice" ||
        recommendation.tier === "Liquidate" ||
        recommendation.tier === "Needs Data";
      if (!actionableIssue) return null;

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
          itemCondition,
        fba_sellable_quantity: fbaSellableQuantity,
        inbound_quantity: inboundQuantity,
        reserved_quantity: reservedQuantity,
        reserved_customer_order_quantity: reservedCustomerOrderQuantity,
        reserved_fc_transfer_quantity: reservedFcTransferQuantity,
        reserved_fc_processing_quantity: reservedFcProcessingQuantity,
        future_supply_buyable_quantity: futureSupplyBuyableQuantity,
        reserved_future_supply_quantity: reservedFutureSupplyQuantity,
        inventory_detail_status: inventoryDetailStatus({
          fbaSellableQuantity,
          inboundQuantity,
          reservedCustomerOrderQuantity,
          reservedFcTransferQuantity,
          reservedFcProcessingQuantity,
          futureSupplyBuyableQuantity,
          reservedFutureSupplyQuantity,
          unsellableQuantity,
        }),
        unsellable_quantity: unsellableQuantity,
        unfulfillable_customer_damaged_quantity: toNumber(
          inventory.unfulfillable_customer_damaged_quantity,
          0
        ),
        unfulfillable_warehouse_damaged_quantity: toNumber(
          inventory.unfulfillable_warehouse_damaged_quantity,
          0
        ),
        unfulfillable_distributor_damaged_quantity: toNumber(
          inventory.unfulfillable_distributor_damaged_quantity,
          0
        ),
        unfulfillable_carrier_damaged_quantity: toNumber(
          inventory.unfulfillable_carrier_damaged_quantity,
          0
        ),
        unfulfillable_defective_quantity: toNumber(inventory.unfulfillable_defective_quantity, 0),
        unfulfillable_expired_quantity: toNumber(inventory.unfulfillable_expired_quantity, 0),
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
        sales_shipped_last_30_days: sales30,
        sales_shipped_last_90_days: sales90,
        sales_velocity_signal: velocitySignal,
        informed_rule_name: informedRuleName,
        informed_rule_id: informedRuleId,
        informed_current_price: toOptionalNumber(informed?.current_price),
        informed_min_price: toOptionalNumber(informed?.min_price),
        informed_max_price: toOptionalNumber(informed?.max_price),
        informed_buy_box_price: informedBuyBoxPrice,
        informed_buy_box_status: cleanText(informed?.buy_box_status),
        informed_repricing_enabled: informed?.repricing_enabled ?? null,
        informed_missing_data: !informed,
        informed_price_gap_to_buy_box_pct: priceGapPct(
          toOptionalNumber(informed?.current_price),
          informedBuyBoxPrice ?? keepaBuyBoxPrice
        ),
        informed_min_price_gap_to_buy_box_pct: priceGapPct(
          toOptionalNumber(informed?.min_price),
          informedBuyBoxPrice ?? keepaBuyBoxPrice
        ),
        informed_repricing_note: informedNote,
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
        competition_summary: competition.summary,
        competition_offers: competition.offers,
        estimated_capital_tied_up: capitalTiedUp,
        advisor_bucket: recommendation.bucket,
        recommended_target_price: recommendation.targetPrice,
        target_price_basis: recommendation.targetPriceBasis,
        recommendation_tier: recommendation.tier,
        recommended_manual_action: recommendation.action,
        reason: recommendation.reason,
      };
    })
    .filter((row): row is AdvisorRow => !!row)
    .sort((left, right) => {
      const capitalDifference =
        (right.estimated_capital_tied_up ?? -1) - (left.estimated_capital_tied_up ?? -1);
      if (capitalDifference !== 0) return capitalDifference;
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
  informed?: InformedListingRow;
  informedBuyBoxPrice: number | null;
  marketReferencePrice: number | null;
  salesVelocitySignal: SalesVelocitySignal;
  informedNote: string;
  amazonAgeBucket?: AmazonAgeBucket | null;
  listingStatus: string | null;
  unsellableQuantity: number;
}): {
  tier: RecommendationTier;
  bucket: AdvisorBucket;
  targetPrice: number | null;
  targetPriceBasis: string | null;
  action: string;
  reason: string;
} {
  if (!input.asin) {
    return needsData("Missing ASIN; cannot connect Amazon, Keepa, and cost context.");
  }

  const actionableListingStatus = listingStatusNeedsAction(input.listingStatus);
  if (input.unsellableQuantity > 0 || actionableListingStatus) {
    return {
      tier: "Remove / eBay",
      bucket: "Inventory / Listing Issue",
      targetPrice: null,
      targetPriceBasis: null,
      action: "Review suppression, removal, or eBay transfer.",
      reason:
        input.unsellableQuantity > 0
          ? "Unsellable quantity detected; repricing alone may not fix this inventory."
          : "Amazon listing status is not buyable/discoverable; repricing alone may not fix this inventory.",
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
  if (!input.informed) {
    return needsData("Informed snapshot missing; import the latest Informed listing report before manual repricing.");
  }

  if (input.amazonAgeBucket) {
    if (input.amazonAgeBucket === "365+" || input.amazonAgeBucket === "271-365" || input.amazonAgeBucket === "181-270") {
      const target = targetPriceRecommendation({
        tier: "Liquidate",
        costBasis: input.costBasis,
        marketReferencePrice: input.marketReferencePrice,
        salesVelocitySignal: input.salesVelocitySignal,
      });
      return {
        tier: "Liquidate",
        bucket: "Pricing",
        targetPrice: target.price,
        targetPriceBasis: target.basis,
        action: "Review and lower the Informed target/floor manually if margin is acceptable.",
        reason: withInformedNote(
          `${input.amazonAgeBucket} Amazon planning age bucket with active FBA inventory; use a controlled markdown before considering removal.`,
          velocityReason(input.salesVelocitySignal),
          input.informedNote
        ),
      };
    }

    if (input.amazonAgeBucket === "91-180") {
      const buyBoxBelowList =
        input.currentListPrice !== null &&
        input.keepaBuyBoxPrice !== null &&
        input.keepaBuyBoxPrice < input.currentListPrice;
      const target = targetPriceRecommendation({
        tier: "Reprice",
        costBasis: input.costBasis,
        marketReferencePrice: input.marketReferencePrice,
        salesVelocitySignal: input.salesVelocitySignal,
      });
      return {
        tier: "Reprice",
        bucket: "Pricing",
        targetPrice: target.price,
        targetPriceBasis: target.basis,
        action: "Review Informed.co target/floor manually.",
        reason: withInformedNote(
          buyBoxBelowList
            ? "Amazon planning shows 91-180 day inventory and Buy Box is below current/list price; review repricer floor."
            : "Amazon planning shows 91-180 day sellable FBA inventory; consider a controlled price reduction.",
          velocityReason(input.salesVelocitySignal),
          input.informedNote
        ),
      };
    }

    return {
      tier: "Watch",
      bucket: "Pricing",
      targetPrice: null,
      targetPriceBasis: null,
      action: "Monitor sales velocity and Buy Box position.",
      reason: withInformedNote(
        "Amazon planning places this inventory in the 0-90 day bucket; exact 60-day split is unavailable from this report.",
        velocityReason(input.salesVelocitySignal),
        input.informedNote
      ),
    };
  }

  if ((input.ageDays ?? 0) <= HEALTHY_MAX_AGE_DAYS) {
    return {
      tier: "Healthy",
      bucket: "Pricing",
      targetPrice: null,
      targetPriceBasis: null,
      action: "No repricing action needed.",
      reason: withInformedNote(
        "Inventory is under 60 days old and no major Amazon listing issue is visible.",
        input.informedNote
      ),
    };
  }
  if ((input.ageDays ?? 0) <= WATCH_MAX_AGE_DAYS) {
    return {
      tier: "Watch",
      bucket: "Pricing",
      targetPrice: null,
      targetPriceBasis: null,
      action: "Monitor sales velocity and Buy Box position.",
      reason: withInformedNote("60-89 days old; watch before forcing price down.", input.informedNote),
    };
  }
  if ((input.ageDays ?? 0) <= REPRICE_MAX_AGE_DAYS) {
    const buyBoxBelowList =
      input.currentListPrice !== null &&
      input.keepaBuyBoxPrice !== null &&
      input.keepaBuyBoxPrice < input.currentListPrice;
    const target = targetPriceRecommendation({
      tier: "Reprice",
      costBasis: input.costBasis,
      marketReferencePrice: input.marketReferencePrice,
      salesVelocitySignal: input.salesVelocitySignal,
    });
    return {
      tier: "Reprice",
      bucket: "Pricing",
      targetPrice: target.price,
      targetPriceBasis: target.basis,
      action: "Review Informed.co target/floor manually.",
      reason: withInformedNote(
        buyBoxBelowList
          ? "90+ days old and Buy Box is below current/list price; review repricer floor."
          : "90+ days old with sellable FBA quantity; consider a controlled price reduction.",
        velocityReason(input.salesVelocitySignal),
        input.informedNote
      ),
    };
  }

  const target = targetPriceRecommendation({
    tier: "Liquidate",
    costBasis: input.costBasis,
    marketReferencePrice: input.marketReferencePrice,
    salesVelocitySignal: input.salesVelocitySignal,
  });
  return {
    tier: "Liquidate",
    bucket: "Pricing",
    targetPrice: target.price,
    targetPriceBasis: target.basis,
    action: "Review and lower the Informed target/floor manually if margin is acceptable.",
    reason: withInformedNote(
      "180+ days old with active Amazon inventory; recover capital even if margin compresses.",
      velocityReason(input.salesVelocitySignal),
      input.informedNote
    ),
  };
}

function buildCompetitionContext(
  keepa?: KeepaRow,
  fallbackBuyBoxPrice?: number | null,
  listingCondition?: string | null
): { summary: CompetitionSummary; offers: CompetitionOffer[] } {
  const conditionFilter = conditionGroup(listingCondition);
  if (!keepa) {
    return {
      summary: {
        source: "Missing",
        note: "Keepa snapshot missing; run targeted Keepa sync before reviewing competitors.",
        condition_filter: conditionFilter,
        offer_count: null,
        fba_offer_count: 0,
        mfn_offer_count: 0,
        lowest_fba_price: null,
        lowest_mfn_price: null,
        buy_box_seller_id: null,
        buy_box_price: fallbackBuyBoxPrice ?? null,
        total_observed_stock: null,
      },
      offers: [],
    };
  }

  const rawProduct = firstKeepaProduct(keepa.raw_keepa_json);
  const stats = isRecord(rawProduct?.stats) ? rawProduct.stats : null;
  const offersRaw = Array.isArray(rawProduct?.offers) ? rawProduct.offers : [];
  const buyBoxSellerId =
    cleanText(lastValue(stats?.buyBoxSellerId)) ??
    cleanText(lastValue(rawProduct?.buyBoxSellerIdHistory)) ??
    cleanText(rawProduct?.buyBoxSellerId);
  const buyBoxPrice =
    centsToDollars(lastNumeric(stats?.buyBoxPrice)) ??
    centsToDollars(lastNumeric(rawProduct?.buyBoxPriceHistory)) ??
    fallbackBuyBoxPrice ??
    null;

  const offers = offersRaw
    .map((offer) => parseKeepaOffer(offer, buyBoxSellerId, buyBoxPrice))
    .filter((offer): offer is CompetitionOffer => offer !== null)
    .filter((offer) => sameConditionGroup(offer.condition, conditionFilter))
    .sort((left, right) => {
      if (left.is_buy_box_winner !== right.is_buy_box_winner) {
        return left.is_buy_box_winner ? -1 : 1;
      }
      return (left.landed_price ?? Number.MAX_SAFE_INTEGER) - (right.landed_price ?? Number.MAX_SAFE_INTEGER);
    })
    .slice(0, 25);

  const fbaPrices = offers
    .filter((offer) => offer.fulfillment === "FBA" && offer.landed_price !== null)
    .map((offer) => offer.landed_price as number);
  const mfnPrices = offers
    .filter((offer) => offer.fulfillment === "MFN" && offer.landed_price !== null)
    .map((offer) => offer.landed_price as number);
  const stockValues = offers
    .map((offer) => offer.stock_quantity)
    .filter((stock): stock is number => stock !== null);

  if (!offers.length) {
    return {
      summary: {
        source: "Keepa summary",
        note:
          "Latest Keepa snapshot has summary data but no offer-level rows; run a targeted Keepa sync with offers for this ASIN.",
        condition_filter: conditionFilter,
        offer_count: toOptionalNumber(keepa.offer_count_current),
        fba_offer_count: 0,
        mfn_offer_count: 0,
        lowest_fba_price: null,
        lowest_mfn_price: null,
        buy_box_seller_id: buyBoxSellerId,
        buy_box_price: buyBoxPrice,
        total_observed_stock: null,
      },
      offers: [],
    };
  }

  return {
    summary: {
      source: "Keepa offers",
      note:
        "Offer rows come from the latest stored Keepa payload and are filtered to the same condition as your listing when condition is known. Seller stock is Keepa-estimated when available and may be capped or incomplete.",
      condition_filter: conditionFilter,
      offer_count: offers.length,
      fba_offer_count: offers.filter((offer) => offer.fulfillment === "FBA").length,
      mfn_offer_count: offers.filter((offer) => offer.fulfillment === "MFN").length,
      lowest_fba_price: fbaPrices.length ? roundMoney(Math.min(...fbaPrices)) : null,
      lowest_mfn_price: mfnPrices.length ? roundMoney(Math.min(...mfnPrices)) : null,
      buy_box_seller_id: buyBoxSellerId,
      buy_box_price: buyBoxPrice,
      total_observed_stock: stockValues.length
        ? stockValues.reduce((total, stock) => total + stock, 0)
        : null,
    },
    offers,
  };
}

function firstKeepaProduct(raw: unknown): Record<string, unknown> | null {
  const root = isRecord(raw) ? raw : null;
  const products = root && Array.isArray(root.products) ? root.products : null;
  if (products?.[0] && isRecord(products[0])) return products[0];
  if (root && Array.isArray(root.offers)) return root;
  return null;
}

function parseKeepaOffer(
  offer: unknown,
  buyBoxSellerId: string | null,
  buyBoxPrice: number | null
): CompetitionOffer | null {
  if (!isRecord(offer)) return null;

  const sellerId =
    cleanText(offer.sellerId) ??
    cleanText(offer.seller_id) ??
    cleanText(lastValue(offer.sellerIdHistory));
  const itemPrice =
    centsToDollars(firstNumber(offer.price, offer.current, offer.lastPrice, offer.offerPrice)) ??
    centsToDollars(firstOfferCsvPrice(offer.offerCSV));
  const shippingPrice = centsToDollars(firstNumber(offer.shipping, offer.shippingPrice));
  const landedPrice =
    centsToDollars(firstNumber(offer.landedPrice, offer.totalPrice)) ??
    (itemPrice !== null ? roundMoney(itemPrice + (shippingPrice ?? 0)) : null);
  const fulfillment = offerFulfillment(offer);
  const stockQuantity = firstNumber(
    offer.stock,
    offer.stockQuantity,
    offer.quantity,
    lastNumeric(offer.stockCSV)
  );
  const lastSeen = keepaMinutesToIso(firstNumber(offer.lastSeen, lastNumeric(offer.lastSeenHistory)));
  const condition = keepaConditionName(firstNumber(offer.condition, offer.conditionCode));

  if (!sellerId && landedPrice === null && stockQuantity === null) return null;

  return {
    seller_id: sellerId,
    seller_name: cleanText(offer.sellerName) ?? cleanText(offer.seller),
    fulfillment,
    landed_price: landedPrice,
    item_price: itemPrice,
    shipping_price: shippingPrice,
    stock_quantity: stockQuantity,
    condition,
    is_buy_box_winner:
      sellerId !== null && buyBoxSellerId !== null
        ? sellerId === buyBoxSellerId
        : buyBoxPrice !== null && landedPrice !== null && Math.abs(landedPrice - buyBoxPrice) < 0.01,
    is_amazon:
      sellerId === "ATVPDKIKX0DER" ||
      String(cleanText(offer.sellerName) ?? "").toLowerCase() === "amazon",
    is_prime: toOptionalBoolean(offer.isPrime ?? offer.prime),
    last_seen: lastSeen,
  };
}

function offerFulfillment(offer: Record<string, unknown>): "FBA" | "MFN" | "Unknown" {
  const isFba = toOptionalBoolean(offer.isFBA ?? offer.fba ?? offer.isFulfilledByAmazon);
  if (isFba === true) return "FBA";
  if (isFba === false) return "MFN";

  const text = cleanText(offer.fulfillmentChannel ?? offer.fulfillment);
  if (!text) return "Unknown";
  if (text.toUpperCase().includes("AMAZON") || text.toUpperCase() === "FBA") return "FBA";
  if (text.toUpperCase().includes("MERCHANT") || text.toUpperCase() === "MFN") return "MFN";
  return "Unknown";
}

function firstOfferCsvPrice(value: unknown) {
  if (!Array.isArray(value)) return null;
  for (let index = value.length - 1; index >= 0; index -= 1) {
    const price = Number(value[index]);
    if (Number.isFinite(price) && price > 0) return price;
  }
  return null;
}

function firstNumber(...values: unknown[]) {
  for (const value of values) {
    const number = toOptionalNumber(value);
    if (number !== null) return number;
  }
  return null;
}

function lastNumeric(value: unknown) {
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      const number = toOptionalNumber(value[index]);
      if (number !== null) return number;
    }
    return null;
  }
  return toOptionalNumber(value);
}

function lastValue(value: unknown) {
  if (Array.isArray(value)) {
    for (let index = value.length - 1; index >= 0; index -= 1) {
      if (value[index] !== null && value[index] !== undefined && value[index] !== "") {
        return value[index];
      }
    }
    return null;
  }
  return value ?? null;
}

function keepaMinutesToIso(value: number | null) {
  if (value === null || value <= 0) return null;
  const keepaEpoch = Date.UTC(2011, 0, 1, 0, 0, 0);
  return new Date(keepaEpoch + value * 60_000).toISOString();
}

function keepaConditionName(value: number | null) {
  if (value === null) return null;
  const labels: Record<number, string> = {
    1: "New",
    2: "Used - Like New",
    3: "Used - Very Good",
    4: "Used - Good",
    5: "Used - Acceptable",
    6: "Refurbished",
    7: "Collectible - Like New",
    8: "Collectible - Very Good",
    9: "Collectible - Good",
    10: "Collectible - Acceptable",
  };
  return labels[value] ?? `Condition ${value}`;
}

function conditionGroup(value?: string | null) {
  const text = cleanText(value)?.toLowerCase();
  if (!text) return null;
  if (text.includes("used")) return "used";
  if (text.includes("collectible")) return "collectible";
  if (text.includes("refurbished") || text.includes("renewed")) return "refurbished";
  if (text.includes("acceptable") || text.includes("good") || text.includes("like new")) {
    return "used";
  }
  if (text.includes("new")) return "new";
  return null;
}

function sameConditionGroup(offerCondition: string | null, targetConditionGroup: string | null) {
  if (!targetConditionGroup) return true;
  const offerGroup = conditionGroup(offerCondition);
  return offerGroup === targetConditionGroup;
}

function needsData(reason: string) {
  return {
    tier: "Needs Data" as const,
    bucket: "Missing Data" as const,
    targetPrice: null,
    targetPriceBasis: null,
    action: "Fill missing data or run targeted sync before repricing.",
    reason,
  };
}

function targetPriceRecommendation(input: {
  tier: "Reprice" | "Liquidate";
  costBasis: number | null;
  marketReferencePrice: number | null;
  salesVelocitySignal: SalesVelocitySignal;
}) {
  if (input.costBasis === null || input.marketReferencePrice === null) {
    return { price: null, basis: null };
  }

  const discount = targetDiscountPct(input.tier, input.salesVelocitySignal);
  const marketTarget = input.marketReferencePrice * (1 - discount);
  const floor = input.costBasis * (1 + MIN_MARGIN_ABOVE_COST_PCT);
  const target = Math.max(marketTarget, floor);

  return {
    price: roundMoney(target),
    basis:
      target === floor
        ? `Cost + ${Math.round(MIN_MARGIN_ABOVE_COST_PCT * 100)}% floor`
        : `${Math.round(discount * 100)}% below Buy Box/reference (${input.salesVelocitySignal})`,
  };
}

function targetDiscountPct(tier: "Reprice" | "Liquidate", signal: SalesVelocitySignal) {
  if (tier === "Reprice") {
    if (signal === "Strong") return 0.01;
    if (signal === "Moving") return 0.02;
    if (signal === "No recent sales") return 0.05;
    return REPRICE_DISCOUNT_PCT;
  }

  if (signal === "Strong") return 0.04;
  if (signal === "Moving") return 0.06;
  if (signal === "No recent sales") return 0.12;
  return LIQUIDATE_DISCOUNT_PCT;
}

function velocityReason(signal: SalesVelocitySignal) {
  if (signal === "Strong") {
    return "Recent Amazon sales are strong, so use a smaller markdown and check Buy Box/floor behavior first.";
  }
  if (signal === "Moving") {
    return "Recent Amazon sales are moving, so use a moderate markdown rather than a liquidation cut.";
  }
  if (signal === "Slow") {
    return "Recent Amazon sales are slow, so a firmer markdown may be justified.";
  }
  if (signal === "No recent sales") {
    return "No recent Amazon sales are visible in the planning data, so prioritize this for price review.";
  }
  return "Amazon sales velocity is unknown, so treat the target as a first-pass recommendation.";
}

function withInformedNote(reason: string, ...notes: string[]) {
  const usableNotes = notes.filter(
    (note) => note && note !== "Informed data present; no obvious repricing blocker."
  );
  if (!usableNotes.length) return reason;
  return `${reason} ${usableNotes.join(" ")}`;
}

function salesVelocitySignal(
  sales30: number | null,
  sales90: number | null,
  totalQuantity: number
): SalesVelocitySignal {
  if (sales30 === null && sales90 === null) return "Unknown";
  const last30 = sales30 ?? 0;
  const last90 = sales90 ?? 0;
  if (last30 <= 0 && last90 <= 0) return "No recent sales";

  const meaningfulUnitCount = Math.max(1, totalQuantity);
  if (last30 >= Math.max(2, Math.ceil(meaningfulUnitCount * 0.5)) || last90 >= meaningfulUnitCount * 2) {
    return "Strong";
  }
  if (last30 > 0 || last90 >= Math.max(2, Math.ceil(meaningfulUnitCount * 0.5))) {
    return "Moving";
  }
  return "Slow";
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
    by_bucket: rows.reduce(
      (counts, row) => {
        counts[row.advisor_bucket] += 1;
        return counts;
      },
      {
        Pricing: 0,
        "Inventory / Listing Issue": 0,
        "Missing Data": 0,
      } as Record<AdvisorBucket, number>
    ),
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

function informedRepricingNote(input: {
  informed?: InformedListingRow;
  tierAgeBucket: AmazonAgeBucket | null;
  ageDays: number | null;
  currentPrice: number | null;
  minPrice: number | null;
  buyBoxPrice: number | null;
}) {
  if (!input.informed) {
    return "Missing Informed listing snapshot; import Informed report before making floor/rule decisions.";
  }

  const stale =
    input.tierAgeBucket !== null && input.tierAgeBucket !== "0-90"
      ? true
      : (input.ageDays ?? 0) >= 90;
  const notes: string[] = [];

  if (!input.informed.assigned_rule_name) {
    notes.push("Informed rule is missing; review rule assignment manually.");
  }
  if (stale && input.informed.repricing_enabled === false) {
    notes.push("Repricing is disabled for stale inventory; review Informed managed status.");
  }
  if (
    stale &&
    input.currentPrice !== null &&
    input.buyBoxPrice !== null &&
    input.currentPrice > input.buyBoxPrice
  ) {
    notes.push("Current Informed price is above Buy Box; review manual price or repricer behavior.");
  }
  if (
    stale &&
    input.minPrice !== null &&
    input.buyBoxPrice !== null &&
    input.minPrice > input.buyBoxPrice
  ) {
    notes.push("Informed min price is above Buy Box; floor may be blocking sell-through.");
  }

  return notes.length ? notes.join(" ") : "Informed data present; no obvious repricing blocker.";
}

function inventoryDetailStatus(input: {
  fbaSellableQuantity: number;
  inboundQuantity: number;
  reservedCustomerOrderQuantity: number;
  reservedFcTransferQuantity: number;
  reservedFcProcessingQuantity: number;
  futureSupplyBuyableQuantity: number;
  reservedFutureSupplyQuantity: number;
  unsellableQuantity: number;
}) {
  const parts: string[] = [];
  if (input.fbaSellableQuantity > 0) parts.push(`Sellable ${input.fbaSellableQuantity}`);
  if (input.inboundQuantity > 0) parts.push(`Inbound ${input.inboundQuantity}`);
  if (input.reservedCustomerOrderQuantity > 0) {
    parts.push(`Customer order ${input.reservedCustomerOrderQuantity}`);
  }
  if (input.reservedFcTransferQuantity > 0) {
    parts.push(`FC transfer ${input.reservedFcTransferQuantity}`);
  }
  if (input.reservedFcProcessingQuantity > 0) {
    parts.push(`FC processing ${input.reservedFcProcessingQuantity}`);
  }
  if (input.futureSupplyBuyableQuantity > 0) {
    parts.push(`Future buyable ${input.futureSupplyBuyableQuantity}`);
  }
  if (input.reservedFutureSupplyQuantity > 0) {
    parts.push(`Reserved future ${input.reservedFutureSupplyQuantity}`);
  }
  if (input.unsellableQuantity > 0) parts.push(`Unsellable ${input.unsellableQuantity}`);
  return parts.length ? parts.join(" / ") : "No active FBA quantity";
}

function priceGapPct(price: number | null, referencePrice: number | null) {
  if (price === null || referencePrice === null || referencePrice <= 0) return null;
  return Math.round(((price - referencePrice) / referencePrice) * 10000) / 100;
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

function keyByInformedRuleId(rows: InformedRuleOverrideRow[]) {
  const map = new Map<string, string>();
  for (const row of rows) {
    if (row.active === false) continue;
    const id = cleanText(row.informed_rule_id);
    const name = cleanText(row.friendly_name);
    if (id && name) map.set(id, name);
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
  if (listingStatusNeedsAction(listingStatus)) return listingStatus;
  return "None";
}

function listingStatusNeedsAction(listingStatus: string | null) {
  if (!listingStatus) return false;
  const statuses = listingStatus
    .split(",")
    .map((part) => part.trim().toUpperCase())
    .filter(Boolean);
  if (!statuses.length) return false;
  return statuses.some((status) =>
    ["SUPPRESSED", "INACTIVE", "INCOMPLETE", "NOT_BUYABLE"].includes(status)
  );
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

function toOptionalBoolean(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value === 1 ? true : value === 0 ? false : null;
  const text = String(value).trim().toLowerCase();
  if (["true", "yes", "y", "1"].includes(text)) return true;
  if (["false", "no", "n", "0"].includes(text)) return false;
  return null;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
