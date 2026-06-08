import { NextResponse } from "next/server";
import {
  dateDaysAgo,
  fetchBusinessValueHistory,
  fetchDashboardPurchaseRows,
  fetchSalesOrdersSince,
  fetchSalesProfitabilityRows,
  median,
  monthKey,
  percentChange,
  reportableRows,
  sumCost,
  sumUnits,
  toNumber,
} from "../_summary";

export async function GET() {
  const [orders, profitRows, purchases, valueHistory] = await Promise.all([
    fetchSalesOrdersSince("2025-01-01T00:00:00.000Z"),
    fetchSalesProfitabilityRows(),
    fetchDashboardPurchaseRows(),
    fetchBusinessValueHistory(400),
  ]);
  const orderDateById = new Map(orders.map((order) => [order.amazon_order_id, order.purchase_date]));
  const now = new Date();
  const mtdKey = now.toISOString().slice(0, 7);
  const last30 = dateDaysAgo(30);
  const last90 = dateDaysAgo(90);
  const ytd = `${now.getUTCFullYear()}-01-01T00:00:00.000Z`;
  const profitWithDates = profitRows.map((row) => ({ ...row, soldAt: orderDateById.get(String(row.amazon_order_id ?? "")) ?? null }));
  const last30Rows = profitWithDates.filter((row) => (row.soldAt ?? "") >= last30);
  const last90Rows = profitWithDates.filter((row) => (row.soldAt ?? "") >= last90);
  const mtdRows = profitWithDates.filter((row) => monthKey(row.soldAt) === mtdKey);
  const ytdRows = profitWithDates.filter((row) => (row.soldAt ?? "") >= ytd);
  const reportablePurchases = reportableRows(purchases);
  const purchasedLast30 = reportablePurchases.filter((row) => `${row.order_date ?? ""}T00:00:00.000Z` >= last30);
  const currentValue = valueHistory.at(-1)?.total_business_value ?? null;
  const prior30Value = valueHistory.find((row) => row.snapshot_date >= dateDaysAgo(60).slice(0, 10) && row.snapshot_date <= dateDaysAgo(30).slice(0, 10))?.total_business_value ?? null;
  const monthlyTrends = buildMonthlyTrends(profitWithDates, reportablePurchases, valueHistory);

  return NextResponse.json({
    refreshedAt: newest([valueHistory.at(-1)?.snapshot_date, latest(profitRows.map((row) => row.updated_at)), latest(purchases.map((row) => row.order_date))]),
    freshness: {
      salesUpdatedAt: latest(profitRows.map((row) => row.updated_at)),
      purchasesUpdatedAt: latest(purchases.map((row) => row.order_date)),
      businessValueUpdatedAt: valueHistory.at(-1)?.snapshot_date ?? null,
      oldestRequiredInputAt: oldest([latest(profitRows.map((row) => row.updated_at)), valueHistory.at(-1)?.snapshot_date]),
    },
    summary: {
      revenueMtd: sumRevenue(mtdRows),
      revenueLast30d: sumRevenue(last30Rows),
      revenueYtd: sumRevenue(ytdRows),
      profitMtd: sumProfit(mtdRows),
      profitLast30d: sumProfit(last30Rows),
      profitYtd: sumProfit(ytdRows),
      roiLast90d: weightedRoi(last90Rows),
      businessValueCurrent: currentValue,
      businessValueChange30d: currentValue !== null ? currentValue - (prior30Value ?? currentValue) : null,
      unitsPurchasedLast30d: sumUnits(purchasedLast30),
      unitsSoldLast30d: sumQuantity(last30Rows),
    },
    monthlyTrends,
    efficiency: {
      averageBuyCostLast90d: averageBuyCost(reportablePurchases.filter((row) => `${row.order_date ?? ""}T00:00:00.000Z` >= last90)),
      averageProfitPerUnitLast90d: perUnitProfit(last90Rows),
      averageRoiLast90d: weightedRoi(last90Rows),
      purchaseToReceivedMedianDays: median(reportablePurchases.filter((row) => row.order_date && row.received_date).map((row) => diffDays(row.order_date!, row.received_date!))),
      receivedToListedMedianDays: null,
      purchaseToSoldMedianDays: null,
    },
    growthSignals: [
      signal("Revenue last 30 days", sumRevenue(last30Rows), previousWindowRevenue(profitWithDates, 30), "Revenue trend compared with the prior 30-day window."),
      signal("Profit last 30 days", sumProfit(last30Rows), previousWindowProfit(profitWithDates, 30), "Profit trend compared with the prior 30-day window."),
      signal("Units purchased vs sold", sumUnits(purchasedLast30), sumQuantity(last30Rows), "Purchasing below sales may shrink inventory; above sales may build inventory."),
      signal("Business value", currentValue ?? 0, prior30Value, "Business value movement across recent snapshots."),
    ],
  });
}

function buildMonthlyTrends(profitRows: Array<Record<string, unknown> & { soldAt: string | null }>, purchases: Awaited<ReturnType<typeof fetchDashboardPurchaseRows>>, valueHistory: Awaited<ReturnType<typeof fetchBusinessValueHistory>>) {
  const months = new Map<string, { yearMonth: string; revenue: number; grossProfit: number; netProfit: number; unitsSold: number; unitsPurchased: number; inventorySpend: number; endingBusinessValue: number | null }>();
  for (const row of profitRows) {
    const key = monthKey(row.soldAt);
    if (!key) continue;
    const current = months.get(key) ?? baseMonth(key);
    current.revenue += toNumber(row.sale_price);
    current.netProfit += toNumber(row.net_profit);
    current.grossProfit += toNumber(row.net_profit) + toNumber(row.amazon_fees_excluding_fulfillment) + toNumber(row.fulfillment_cost);
    current.unitsSold += toNumber(row.quantity);
    months.set(key, current);
  }
  for (const row of purchases) {
    const key = monthKey(row.order_date);
    if (!key) continue;
    const current = months.get(key) ?? baseMonth(key);
    current.unitsPurchased += toNumber(row.quantity);
    current.inventorySpend += toNumber(row.quantity) * toNumber(row.unit_cost);
    months.set(key, current);
  }
  for (const row of valueHistory) {
    const key = monthKey(row.snapshot_date);
    if (!key) continue;
    const current = months.get(key) ?? baseMonth(key);
    current.endingBusinessValue = row.total_business_value;
    months.set(key, current);
  }
  return [...months.values()].sort((left, right) => right.yearMonth.localeCompare(left.yearMonth)).slice(0, 12).reverse();
}

function baseMonth(yearMonth: string) { return { yearMonth, revenue: 0, grossProfit: 0, netProfit: 0, unitsSold: 0, unitsPurchased: 0, inventorySpend: 0, endingBusinessValue: null }; }
function sumRevenue(rows: Array<{ sale_price: number | null }>) { return rows.reduce((sum, row) => sum + toNumber(row.sale_price), 0); }
function sumProfit(rows: Array<{ net_profit: number | null }>) { return rows.reduce((sum, row) => sum + toNumber(row.net_profit), 0); }
function sumQuantity(rows: Array<{ quantity: number | null }>) { return rows.reduce((sum, row) => sum + toNumber(row.quantity), 0); }
function weightedRoi(rows: Array<{ roi: number | null; cogs: number | null }>) {
  const denominator = rows.reduce((sum, row) => sum + toNumber(row.cogs), 0);
  return denominator ? rows.reduce((sum, row) => sum + toNumber(row.roi) * toNumber(row.cogs), 0) / denominator : null;
}
function averageBuyCost(rows: Awaited<ReturnType<typeof fetchDashboardPurchaseRows>>) {
  const units = sumUnits(rows);
  return units ? sumCost(rows) / units : null;
}
function perUnitProfit(rows: Array<{ net_profit: number | null; quantity: number | null }>) {
  const units = sumQuantity(rows);
  return units ? sumProfit(rows) / units : null;
}
function previousWindowRevenue(rows: Array<{ soldAt: string | null; sale_price: number | null }>, days: number) {
  const start = dateDaysAgo(days * 2);
  const end = dateDaysAgo(days);
  return sumRevenue(rows.filter((row) => (row.soldAt ?? "") >= start && (row.soldAt ?? "") < end));
}
function previousWindowProfit(rows: Array<{ soldAt: string | null; net_profit: number | null }>, days: number) {
  const start = dateDaysAgo(days * 2);
  const end = dateDaysAgo(days);
  return sumProfit(rows.filter((row) => (row.soldAt ?? "") >= start && (row.soldAt ?? "") < end));
}
function signal(label: string, currentValue: number, previousValue: number | null, interpretation: string) {
  const changePercent = percentChange(currentValue, previousValue);
  return { label, currentValue, previousValue, changePercent, direction: changePercent === null ? "unknown" : Math.abs(changePercent) < 1 ? "flat" : changePercent > 0 ? "up" : "down", interpretation };
}
function diffDays(start: string, end: string) { return Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000)); }
function latest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort().at(-1) ?? null; }
function newest(values: Array<string | null | undefined>) { return latest(values); }
function oldest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort()[0] ?? null; }
