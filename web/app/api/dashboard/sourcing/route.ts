import { NextResponse } from "next/server";
import {
  dateDaysAgo,
  fetchDashboardPurchaseRows,
  fetchInventoryPositions,
  fetchSalesOrdersSince,
  fetchSalesProfitabilityRows,
  latestTimestamp,
  toNumber,
} from "../_summary";

export async function GET() {
  const [orders, profitRows, positions, purchases, keepaUpdatedAt, informedUpdatedAt] = await Promise.all([
    fetchSalesOrdersSince("2025-01-01T00:00:00.000Z"),
    fetchSalesProfitabilityRows(),
    fetchInventoryPositions(),
    fetchDashboardPurchaseRows(),
    latestTimestamp("keepa_product_snapshots", "captured_at"),
    latestTimestamp("informed_listing_snapshots", "imported_at"),
  ]);
  const orderDateById = new Map(orders.map((order) => [order.amazon_order_id, order.purchase_date]));
  const soldRows = profitRows.map((row) => ({ ...row, soldAt: orderDateById.get(String(row.amazon_order_id ?? "")) ?? null }));
  const currentAmazonUnits = unitsByAsin(positions.filter((row) => String(row.inventory_state ?? "").startsWith("amazon_fba")));
  const preAmazonUnits = unitsByAsin(positions.filter((row) => !String(row.inventory_state ?? "").startsWith("amazon_fba")));
  const purchaseHistory = purchaseStats(purchases);
  const candidates = buildCandidates(soldRows, currentAmazonUnits, preAmazonUnits, purchaseHistory);

  return NextResponse.json({
    refreshedAt: newest([latestTimestampFromRows(profitRows), latestTimestampFromInventory(positions), keepaUpdatedAt, informedUpdatedAt]),
    freshness: {
      salesUpdatedAt: latestTimestampFromRows(profitRows),
      inventoryUpdatedAt: latestTimestampFromInventory(positions),
      keepaUpdatedAt,
      informedUpdatedAt,
      oldestRequiredInputAt: oldest([latestTimestampFromRows(profitRows), latestTimestampFromInventory(positions)]),
    },
    summary: {
      replenishmentCandidates: candidates.length,
      outOfStockRecentSellers: candidates.filter((row) => row.currentAmazonUnits <= 0 && row.unitsSold90d > 0).length,
      lowStockHighRoi: candidates.filter((row) => row.currentAmazonUnits <= 2 && toNumber(row.averageRoi90d) >= 0.5).length,
      highProfitRepeatBuys: candidates.filter((row) => row.timesPurchased >= 2 && toNumber(row.averageProfit90d) >= 8).length,
      researchQueueValue: candidates.reduce((sum, row) => sum + toNumber(row.suggestedMaxBuyCost), 0),
    },
    candidates: candidates.slice(0, 25),
    recentlyOutOfStock: candidates.filter((row) => row.currentAmazonUnits <= 0 && row.currentMbopPreAmazonUnits <= 0).slice(0, 10),
    repeatWinners: candidates.filter((row) => row.timesPurchased >= 2).slice(0, 10).map((row) => ({
      asin: row.asin,
      title: row.title,
      system: row.system,
      totalUnitsSold: row.unitsSold90d,
      totalProfit: toNumber(row.averageProfit90d) * row.unitsSold90d,
      averageRoi: row.averageRoi90d,
      timesPurchased: row.timesPurchased,
      reason: row.reason,
    })),
  });
}

function buildCandidates(rows: Array<Record<string, unknown> & { soldAt: string | null }>, amazonUnits: Map<string, number>, preAmazonUnits: Map<string, number>, purchases: Map<string, { timesPurchased: number; lastPurchaseCost: number | null; system: string | null }>) {
  const last30 = dateDaysAgo(30);
  const last90 = dateDaysAgo(90);
  const byAsin = new Map<string, { asin: string; sellerSku: string | null; title: string; unitsSold30d: number; unitsSold90d: number; revenue90d: number; profit90d: number; roiNumerator: number; roiDenominator: number; lastSoldDate: string | null }>();
  for (const row of rows) {
    const asin = String(row.asin ?? "").toUpperCase();
    if (!asin || (row.soldAt ?? "") < last90) continue;
    const current = byAsin.get(asin) ?? { asin, sellerSku: String(row.seller_sku ?? "") || null, title: String(row.title ?? "Untitled"), unitsSold30d: 0, unitsSold90d: 0, revenue90d: 0, profit90d: 0, roiNumerator: 0, roiDenominator: 0, lastSoldDate: null };
    const quantity = toNumber(row.quantity);
    if ((row.soldAt ?? "") >= last30) current.unitsSold30d += quantity;
    current.unitsSold90d += quantity;
    current.revenue90d += toNumber(row.sale_price);
    current.profit90d += toNumber(row.net_profit);
    if (row.roi !== null && row.cogs) {
      current.roiNumerator += toNumber(row.roi) * toNumber(row.cogs);
      current.roiDenominator += toNumber(row.cogs);
    }
    if (!current.lastSoldDate || (row.soldAt ?? "") > current.lastSoldDate) current.lastSoldDate = row.soldAt;
    byAsin.set(asin, current);
  }
  return [...byAsin.values()].map((row) => {
    const currentAmazonUnits = amazonUnits.get(row.asin) ?? 0;
    const currentMbopPreAmazonUnits = preAmazonUnits.get(row.asin) ?? 0;
    const averageProfit90d = row.unitsSold90d ? row.profit90d / row.unitsSold90d : null;
    const averageRoi90d = row.roiDenominator ? row.roiNumerator / row.roiDenominator : null;
    const purchase = purchases.get(row.asin);
    const score = scoreCandidate(row.unitsSold30d, row.unitsSold90d, currentAmazonUnits + currentMbopPreAmazonUnits, averageProfit90d, averageRoi90d, purchase?.timesPurchased ?? 0);
    return {
      priority: score >= 80 ? "high" : score >= 50 ? "medium" : "low",
      score,
      asin: row.asin,
      sellerSku: row.sellerSku,
      title: row.title,
      system: purchase?.system ?? null,
      unitsSold30d: row.unitsSold30d,
      unitsSold90d: row.unitsSold90d,
      currentAmazonUnits,
      currentMbopPreAmazonUnits,
      averageSalePrice90d: row.unitsSold90d ? row.revenue90d / row.unitsSold90d : null,
      averageProfit90d,
      averageRoi90d,
      lastPurchaseCost: purchase?.lastPurchaseCost ?? null,
      suggestedMaxBuyCost: suggestedMaxBuyCost(row.unitsSold90d ? row.revenue90d / row.unitsSold90d : null, averageProfit90d),
      reason: reason(row.unitsSold30d, row.unitsSold90d, currentAmazonUnits + currentMbopPreAmazonUnits, averageProfit90d, averageRoi90d),
      amazonUrl: `https://www.amazon.com/dp/${row.asin}`,
      keepaUrl: `https://keepa.com/#!product/1-${row.asin}`,
      ebaySearchUrl: `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent([row.title, purchase?.system].filter(Boolean).join(" "))}`,
      lastSoldDate: row.lastSoldDate,
      timesPurchased: purchase?.timesPurchased ?? 0,
    };
  }).filter((row) => row.score > 25).sort((left, right) => right.score - left.score);
}

function unitsByAsin(rows: Awaited<ReturnType<typeof fetchInventoryPositions>>) {
  const output = new Map<string, number>();
  for (const row of rows) {
    const asin = String(row.asin ?? "").toUpperCase();
    if (asin) output.set(asin, (output.get(asin) ?? 0) + toNumber(row.quantity));
  }
  return output;
}
function purchaseStats(rows: Awaited<ReturnType<typeof fetchDashboardPurchaseRows>>) {
  const output = new Map<string, { timesPurchased: number; lastPurchaseCost: number | null; system: string | null }>();
  for (const row of rows) {
    const asin = String(row.asin ?? "").toUpperCase();
    if (!asin) continue;
    const current = output.get(asin) ?? { timesPurchased: 0, lastPurchaseCost: null, system: row.system ?? null };
    current.timesPurchased += 1;
    current.lastPurchaseCost = toNumber(row.unit_cost) || current.lastPurchaseCost;
    current.system = current.system ?? row.system ?? null;
    output.set(asin, current);
  }
  return output;
}
function scoreCandidate(sold30: number, sold90: number, currentUnits: number, profit: number | null, roi: number | null, timesPurchased: number) {
  return Math.round(Math.min(100, sold30 * 15 + sold90 * 4 + Math.max(0, 6 - currentUnits) * 8 + toNumber(profit) * 2 + toNumber(roi) * 20 + Math.min(timesPurchased, 5) * 4));
}
function suggestedMaxBuyCost(avgSale: number | null, avgProfit: number | null) { return avgSale && avgProfit ? Math.max(avgSale - avgProfit * 0.75, 0) : null; }
function reason(sold30: number, sold90: number, currentUnits: number, profit: number | null, roi: number | null) {
  return `${sold90} sold in 90d, ${sold30} in 30d; ${currentUnits} current unit(s); avg profit ${money(profit)}; ROI ${roi === null ? "--" : `${Math.round(roi * 100)}%`}.`;
}
function money(value: number | null) { return value === null ? "--" : `$${value.toFixed(2)}`; }
function latestTimestampFromRows(rows: Array<{ updated_at: string | null; calculated_at?: string | null }>) { return newest(rows.map((row) => row.updated_at ?? row.calculated_at)); }
function latestTimestampFromInventory(rows: Array<{ updated_at: string | null }>) { return newest(rows.map((row) => row.updated_at)); }
function newest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort().at(-1) ?? null; }
function oldest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort()[0] ?? null; }
