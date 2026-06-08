import { NextRequest, NextResponse } from "next/server";
import {
  dateDaysAgo,
  fetchSalesOrdersSince,
  fetchSalesProfitabilityRows,
  latestTimestamp,
  supabase,
  toNumber,
} from "../_summary";

const SELLER_CENTRAL_FEEDBACK_URL = "https://sellercentral.amazon.com/feedback-manager/index.html";
const SELLER_CENTRAL_ACCOUNT_HEALTH_URL = "https://sellercentral.amazon.com/performance/dashboard";

export async function GET(request: NextRequest) {
  const [orders, profitRows, fbaInventory, listingRows, planningRows, repricing, accountHealth, feedbackSummary, lowRatingFeedback] = await Promise.all([
    fetchSalesOrdersSince("2025-01-01T00:00:00.000Z"),
    fetchSalesProfitabilityRows(),
    fetchLatestFbaInventory(),
    fetchLatestListingRows(),
    fetchLatestPlanningRows(),
    fetchRepricingSummary(request),
    fetchAccountHealthSnapshots(),
    fetchLatestFeedbackSummary(),
    fetchLowRatingFeedbackItems(),
  ]);
  const last30 = dateDaysAgo(30);
  const last7 = dateDaysAgo(7);
  const orderDateById = new Map(orders.map((order) => [order.amazon_order_id, order.purchase_date]));
  const profit30 = profitRows.filter((row) => (orderDateById.get(String(row.amazon_order_id ?? "")) ?? "") >= last30);
  const profit7 = profitRows.filter((row) => (orderDateById.get(String(row.amazon_order_id ?? "")) ?? "") >= last7);
  const completed30 = profit30.filter((row) => String(row.data_status ?? "") === "complete");
  const fbaUnitsByAsin = new Map<string, number>();
  for (const row of fbaInventory) {
    const asin = String(row.asin ?? "").toUpperCase();
    if (asin) fbaUnitsByAsin.set(asin, (fbaUnitsByAsin.get(asin) ?? 0) + toNumber(row.fulfillable_quantity));
  }

  return NextResponse.json({
    refreshedAt: newest([
      latestOrderTimestamp(orders),
      latestProfitTimestamp(profitRows),
      latestInventoryTimestamp(fbaInventory),
      latestListingTimestamp(listingRows),
    ]),
    freshness: {
      salesUpdatedAt: latestOrderTimestamp(orders),
      inventoryUpdatedAt: latestInventoryTimestamp(fbaInventory),
      listingUpdatedAt: latestListingTimestamp(listingRows),
      planningUpdatedAt: latestPlanningTimestamp(planningRows),
      accountHealthUpdatedAt: accountHealth[0]?.captured_at ?? null,
      feedbackUpdatedAt: feedbackSummary?.captured_at ?? null,
      informedUpdatedAt: await latestTimestamp("informed_listing_snapshots", "imported_at"),
      keepaUpdatedAt: await latestTimestamp("keepa_product_snapshots", "captured_at"),
      oldestRequiredInputAt: oldest([latestOrderTimestamp(orders), latestProfitTimestamp(profitRows), latestInventoryTimestamp(fbaInventory)]),
    },
    sellerAccount: {
      accountHealthScore: accountHealth[0]?.account_health_score ?? null,
      accountHealthUpdatedAt: accountHealth[0]?.captured_at ?? null,
      accountHealthUrl: SELLER_CENTRAL_ACCOUNT_HEALTH_URL,
      accountHealthChanges: accountHealthChanges(accountHealth),
      feedbackStarRating: feedbackSummary?.star_rating ?? null,
      feedbackRatingCount: feedbackSummary?.rating_count ?? null,
      feedbackUpdatedAt: feedbackSummary?.captured_at ?? null,
      feedbackUrl: SELLER_CENTRAL_FEEDBACK_URL,
      lowRatingFeedbackCount: lowRatingFeedback.length,
      lowRatingFeedback,
    },
    salesSummary: {
      unitsSold7d: sumQuantity(profit7),
      unitsSold30d: sumQuantity(profit30),
      revenue30d: sumField(profit30, "sale_price"),
      grossProfit30d: sumField(completed30, "net_profit") + sumField(completed30, "amazon_fees_excluding_fulfillment") + sumField(completed30, "fulfillment_cost"),
      netProfit30d: sumField(completed30, "net_profit"),
      roi30d: weightedRoi(completed30),
      missingCogsCount: profit30.filter((row) => String(row.data_status ?? "").includes("missing_cogs") || row.cogs === null).length,
      missingFeesCount: profit30.filter((row) => String(row.data_status ?? "").includes("missing_fees")).length,
      pendingFeesCount: profit30.filter((row) => String(row.data_status ?? "").includes("pending")).length,
    },
    inventorySummary: {
      activeSkus: fbaInventory.filter((row) => toNumber(row.total_quantity) > 0).length,
      sellableUnits: sumRows(fbaInventory, "fulfillable_quantity"),
      reservedUnits: sumRows(fbaInventory, "reserved_quantity"),
      inboundUnits: sumRows(fbaInventory, "inbound_working_quantity") + sumRows(fbaInventory, "inbound_shipped_quantity") + sumRows(fbaInventory, "inbound_receiving_quantity"),
      unfulfillableUnits: sumRows(fbaInventory, "unfulfillable_quantity"),
      strandedOrSuppressedCount: listingRows.filter((row) => toNumber(row.issue_count) > 0 || !String(row.item_status ?? "").includes("BUYABLE")).length,
      unsellableCount: fbaInventory.filter((row) => toNumber(row.unfulfillable_quantity) > 0).length,
    },
    listingHealth: [
      issue("high", "Suppressed / non-buyable", listingRows.filter((row) => !String(row.item_status ?? "").includes("BUYABLE")).length, null, null, "/inventory-reconciliation"),
      issue("medium", "Listing issue count", listingRows.filter((row) => toNumber(row.issue_count) > 0).length, null, null, "/inventory-reconciliation"),
      issue("high", "Unsellable", fbaInventory.filter((row) => toNumber(row.unfulfillable_quantity) > 0).length, sumRows(fbaInventory, "unfulfillable_quantity"), null, "/inventory-reconciliation"),
      issue("medium", "Missing COGS", profit30.filter((row) => row.cogs === null).length, null, null, "/sales-orders?dataStatus=missing_cogs"),
      issue("medium", "Missing fees", profit30.filter((row) => String(row.data_status ?? "").includes("missing_fees")).length, null, null, "/sales-orders?dataStatus=missing_fees"),
    ].filter((row) => row.count > 0),
    repricingSummary: {
      pricingRows: toNumber(repricing?.summary?.by_tier?.Reprice),
      pricingCapital: toNumber(repricing?.summary?.not_snoozed_estimated_capital_tied_up),
      liquidateRows: toNumber(repricing?.summary?.by_tier?.Liquidate),
      liquidateCapital: 0,
      removeOrEbayRows: toNumber(repricing?.summary?.by_tier?.["Remove / eBay"]),
      missingDataRows: toNumber(repricing?.summary?.by_tier?.["Needs Data"]),
      snoozedRows: toNumber(repricing?.summary?.snoozed_rows),
    },
    topSellers: topSellers(profit30, fbaUnitsByAsin),
    staleInventory: (repricing?.rows ?? []).slice(0, 10).map((row: Record<string, unknown>) => ({
      asin: String(row.asin ?? ""),
      sellerSku: String(row.seller_sku ?? ""),
      title: String(row.product_name ?? row.title ?? "Untitled"),
      units: toNumber(row.total_quantity),
      value: toNumber(row.estimated_capital_tied_up),
      ageBucket: String(row.amazon_age_bucket ?? ""),
      currentVelocity: toNumber(row.sales_shipped_last_30_days),
      recommendation: String(row.recommendation_tier ?? ""),
      drilldownUrl: "/repricing",
    })),
  });
}

async function fetchLatestFbaInventory() {
  const { data, error } = await supabase.from("vw_latest_amazon_fba_inventory_snapshot").select("*");
  if (error) return [];
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

async function fetchLatestListingRows() {
  const { data, error } = await supabase.from("vw_latest_amazon_listing_snapshot").select("*");
  if (error) return [];
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

async function fetchLatestPlanningRows() {
  const { data, error } = await supabase.from("vw_latest_amazon_inventory_planning_snapshot").select("*");
  if (error) return [];
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

async function fetchRepricingSummary(request: NextRequest) {
  try {
    const response = await fetch(new URL("/api/amazon/repricing-advisor", request.url), { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

async function fetchAccountHealthSnapshots() {
  const { data, error } = await supabase
    .from("amazon_account_health_snapshots")
    .select("captured_at,account_health_score,source,notes")
    .order("captured_at", { ascending: false })
    .limit(100);
  if (error) {
    console.warn("Amazon dashboard account health lookup failed", error.message);
    return [] as Array<Record<string, unknown>>;
  }
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

async function fetchLatestFeedbackSummary() {
  const { data, error } = await supabase
    .from("amazon_seller_feedback_snapshots")
    .select("captured_at,star_rating,rating_count,source")
    .order("captured_at", { ascending: false })
    .limit(1);
  if (error) {
    console.warn("Amazon dashboard feedback summary lookup failed", error.message);
    return null;
  }
  return ((data ?? []) as unknown as Array<Record<string, unknown>>)[0] ?? null;
}

async function fetchLowRatingFeedbackItems() {
  const { data, error } = await supabase
    .from("amazon_seller_feedback_items")
    .select("feedback_date,rating,amazon_order_id,comment")
    .gte("rating", 1)
    .lte("rating", 3)
    .order("feedback_date", { ascending: false, nullsFirst: false })
    .order("created_at", { ascending: false })
    .limit(10);
  if (error) {
    console.warn("Amazon dashboard low-rating feedback lookup failed", error.message);
    return [] as Array<Record<string, unknown>>;
  }
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

function accountHealthChanges(rows: Array<Record<string, unknown>>) {
  const chronological = [...rows].reverse();
  const changes: Array<{ date: string; value: number; previousValue: number | null; change: number | null; notes: string | null }> = [];
  let previousValue: number | null = null;

  for (const row of chronological) {
    const value = Number(row.account_health_score);
    if (!Number.isFinite(value)) continue;
    if (previousValue === null || value !== previousValue) {
      changes.push({
        date: String(row.captured_at ?? ""),
        value,
        previousValue,
        change: previousValue === null ? null : value - previousValue,
        notes: String(row.notes ?? "") || null,
      });
    }
    previousValue = value;
  }

  return changes.reverse().slice(0, 10);
}

function topSellers(rows: Awaited<ReturnType<typeof fetchSalesProfitabilityRows>>, fbaUnitsByAsin: Map<string, number>) {
  const byAsin = new Map<string, { asin: string; sellerSku: string | null; title: string; unitsSold30d: number; revenue30d: number; netProfit30d: number; roiNumerator: number; roiDenominator: number; currentFbaUnits: number; drilldownUrl: string }>();
  for (const row of rows) {
    const asin = String(row.asin ?? "").toUpperCase();
    if (!asin) continue;
    const current = byAsin.get(asin) ?? { asin, sellerSku: row.seller_sku, title: row.title ?? "Untitled", unitsSold30d: 0, revenue30d: 0, netProfit30d: 0, roiNumerator: 0, roiDenominator: 0, currentFbaUnits: fbaUnitsByAsin.get(asin) ?? 0, drilldownUrl: `/sales-orders?search=${asin}` };
    current.unitsSold30d += toNumber(row.quantity);
    current.revenue30d += toNumber(row.sale_price);
    current.netProfit30d += toNumber(row.net_profit);
    if (row.roi !== null && row.cogs) {
      current.roiNumerator += toNumber(row.roi) * toNumber(row.cogs);
      current.roiDenominator += toNumber(row.cogs);
    }
    byAsin.set(asin, current);
  }
  return [...byAsin.values()].sort((left, right) => right.netProfit30d - left.netProfit30d).slice(0, 10).map((row) => ({ ...row, roi30d: row.roiDenominator ? row.roiNumerator / row.roiDenominator : null }));
}

function sumQuantity(rows: Array<{ quantity: number | null }>) { return rows.reduce((sum, row) => sum + toNumber(row.quantity), 0); }
function sumField(rows: Array<Record<string, unknown>>, field: string) { return rows.reduce((sum, row) => sum + toNumber(row[field]), 0); }
function sumRows(rows: Array<Record<string, unknown>>, field: string) { return rows.reduce((sum, row) => sum + toNumber(row[field]), 0); }
function weightedRoi(rows: Array<{ roi: number | null; cogs: number | null }>) {
  const denominator = rows.reduce((sum, row) => sum + toNumber(row.cogs), 0);
  if (!denominator) return null;
  return rows.reduce((sum, row) => sum + toNumber(row.roi) * toNumber(row.cogs), 0) / denominator;
}
function issue(severity: "high" | "medium" | "low", issueType: string, count: number, units: number | null, value: number | null, drilldownUrl: string) { return { severity, issueType, count, units, value, drilldownUrl }; }
function latestOrderTimestamp(rows: Array<{ updated_at: string | null }>) { return newest(rows.map((row) => row.updated_at)); }
function latestProfitTimestamp(rows: Array<{ updated_at: string | null; calculated_at: string | null }>) { return newest(rows.map((row) => row.updated_at ?? row.calculated_at)); }
function latestInventoryTimestamp(rows: Array<Record<string, unknown>>) { return newest(rows.map((row) => String(row.captured_at ?? ""))); }
function latestListingTimestamp(rows: Array<Record<string, unknown>>) { return newest(rows.map((row) => String(row.captured_at ?? ""))); }
function latestPlanningTimestamp(rows: Array<Record<string, unknown>>) { return newest(rows.map((row) => String(row.captured_at ?? ""))); }
function newest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort().at(-1) ?? null; }
function oldest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort()[0] ?? null; }
