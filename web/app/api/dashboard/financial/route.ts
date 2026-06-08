import { NextResponse } from "next/server";
import {
  dateDaysAgo,
  fetchSalesOrdersSince,
  fetchSalesProfitabilityRows,
  latestTimestamp,
  supabase,
  toNumber,
} from "../_summary";

const SELLER_CENTRAL_PAYMENTS_URL = "https://sellercentral.amazon.com/payments/dashboard/index.html";

type CashSnapshot = {
  captured_at: string | null;
  balance_currency?: number | null;
  total_amazon_cash?: number | null;
  available_to_withdraw?: number | null;
  in_transit_to_bank?: number | null;
  deferred_or_reserved_cash?: number | null;
  raw_financial_event_groups_json?: {
    inTransitBreakdown?: {
      unmatchedCompletedTransferCash?: number | null;
      ynabMatchedCompletedTransferCash?: number | null;
      processingTransferCash?: number | null;
      unmatchedCompletedTransferGroupIds?: string[] | null;
      ynabMatchedCompletedTransfers?: unknown[] | null;
    };
  } | null;
};

type ProfitRowWithDate = Awaited<ReturnType<typeof fetchSalesProfitabilityRows>>[number] & {
  soldAt: string | null;
};

export async function GET() {
  const [orders, profitRows, ynabCash, amazonCash, salesUpdatedAt] = await Promise.all([
    fetchSalesOrdersSince("2025-01-01T00:00:00.000Z"),
    fetchSalesProfitabilityRows(),
    fetchLatestYnabBusinessCash(),
    fetchLatestAmazonCash(),
    latestTimestamp("amazon_sales_profitability", "updated_at"),
  ]);

  const orderDateById = new Map(orders.map((order) => [order.amazon_order_id, order.purchase_date]));
  const profitWithDates = profitRows.map((row) => ({
    ...row,
    soldAt: orderDateById.get(String(row.amazon_order_id ?? "")) ?? null,
  }));
  const now = new Date();
  const periods = [
    summarizePeriod("7d", "Last 7 Days", profitWithDates, dateDaysAgo(7)),
    summarizePeriod("30d", "Last 30 Days", profitWithDates, dateDaysAgo(30)),
    summarizePeriod("90d", "Last 90 Days", profitWithDates, dateDaysAgo(90)),
    summarizePeriod("mtd", "Month To Date", profitWithDates, `${now.toISOString().slice(0, 7)}-01T00:00:00.000Z`),
    summarizePeriod("ytd", "Year To Date", profitWithDates, `${now.getUTCFullYear()}-01-01T00:00:00.000Z`),
  ];
  const activePeriod = periods.find((period) => period.period === "30d") ?? periods[0];
  const amazonBreakdown = amazonCash?.raw_financial_event_groups_json?.inTransitBreakdown ?? {};
  const ynabBusinessCash = toNumber(ynabCash?.balance_currency);
  const amazonAvailable = toNumber(amazonCash?.available_to_withdraw);
  const amazonInTransit = toNumber(amazonCash?.in_transit_to_bank);
  const amazonDeferred = toNumber(amazonCash?.deferred_or_reserved_cash);

  return NextResponse.json({
    refreshedAt: latest([ynabCash?.captured_at, amazonCash?.captured_at, salesUpdatedAt]) ?? new Date().toISOString(),
    freshness: {
      ynabCashUpdatedAt: ynabCash?.captured_at ?? null,
      amazonCashUpdatedAt: amazonCash?.captured_at ?? null,
      profitabilityUpdatedAt: salesUpdatedAt,
    },
    summary: {
      grossSales30d: activePeriod.grossSales,
      netProfit30d: activePeriod.netProfit,
      roi30d: activePeriod.roi,
      averageProfitPerUnit30d: activePeriod.averageProfitPerUnit,
      ynabBusinessCash,
      amazonCash: toNumber(amazonCash?.total_amazon_cash),
      amazonFundsAvailable: amazonAvailable,
      sellerCentralPaymentsUrl: SELLER_CENTRAL_PAYMENTS_URL,
      totalAvailableBusinessCash: ynabBusinessCash + amazonAvailable + amazonInTransit,
    },
    profitability: periods,
    cashPosition: [
      {
        id: "ynab-business",
        label: "YNAB Business Cash",
        value: ynabBusinessCash,
        detail: "Budget category balance",
      },
      {
        id: "amazon-available",
        label: "Amazon Funds Available",
        value: amazonAvailable,
        detail: "Seller Central Payments Dashboard Funds Available",
        href: SELLER_CENTRAL_PAYMENTS_URL,
        external: true,
      },
      {
        id: "amazon-in-transit",
        label: "Amazon To Bank In Transit",
        value: amazonInTransit,
        detail: "Processing fund transfers",
      },
      {
        id: "amazon-deferred",
        label: "Deferred / Reserved Amazon Cash",
        value: amazonDeferred,
        detail: "Deferred, reserved, or not yet withdrawable",
      },
      {
        id: "total-available",
        label: "Total Available Business Cash",
        value: ynabBusinessCash + amazonAvailable + amazonInTransit,
        detail: "YNAB cash plus withdrawable/in-transit Amazon cash",
      },
    ],
    payoutReconciliation: {
      inTransitToBank: amazonInTransit,
      completedPayoutsMatchedToYnab: toNumber(amazonBreakdown.ynabMatchedCompletedTransferCash),
      completedPayoutsNotMatchedToYnab: toNumber(amazonBreakdown.unmatchedCompletedTransferCash),
      unmatchedCompletedTransferCount: Array.isArray(amazonBreakdown.unmatchedCompletedTransferGroupIds)
        ? amazonBreakdown.unmatchedCompletedTransferGroupIds.length
        : 0,
      matchedCompletedTransferCount: Array.isArray(amazonBreakdown.ynabMatchedCompletedTransfers)
        ? amazonBreakdown.ynabMatchedCompletedTransfers.length
        : 0,
    },
    dataCompleteness: summarizeCompleteness(profitWithDates),
    scheduleC: {
      status: "placeholder",
      note: "Schedule C export categories are reserved for the future tax-reporting phase.",
    },
  });
}

async function fetchLatestYnabBusinessCash() {
  const { data, error } = await supabase
    .from("vw_latest_ynab_category_balance_snapshot")
    .select("captured_at,balance_currency")
    .eq("category_name", "Business")
    .limit(1);
  if (error) {
    console.warn("Dashboard YNAB cash lookup failed", error.message);
    return null;
  }
  return ((data ?? []) as unknown as CashSnapshot[])[0] ?? null;
}

async function fetchLatestAmazonCash() {
  const { data, error } = await supabase
    .from("vw_latest_amazon_finance_balance_snapshot")
    .select(
      "captured_at,total_amazon_cash,available_to_withdraw,in_transit_to_bank,deferred_or_reserved_cash,raw_financial_event_groups_json",
    )
    .limit(1);
  if (error) {
    console.warn("Dashboard Amazon cash lookup failed", error.message);
    return null;
  }
  return ((data ?? []) as unknown as CashSnapshot[])[0] ?? null;
}

function summarizePeriod(period: string, label: string, rows: ProfitRowWithDate[], startIso: string) {
  const periodRows = rows.filter((row) => (row.soldAt ?? "") >= startIso);
  const completeRows = periodRows.filter((row) => normalizeDataStatus(row.data_status) === "complete");
  const units = sumQuantity(completeRows);
  const grossSales = sumField(completeRows, "sale_price");
  const amazonFees = Math.abs(sumField(completeRows, "amazon_fees_excluding_fulfillment"));
  const fulfillmentCosts = Math.abs(sumField(completeRows, "fulfillment_cost"));
  const cogs = sumField(completeRows, "cogs");
  const netProfit = sumField(completeRows, "net_profit");
  return {
    period,
    label,
    grossSales,
    amazonFees,
    fulfillmentCosts,
    shippingLabels: 0,
    cogs,
    grossProfit: grossSales - amazonFees - cogs,
    netProfit,
    roi: cogs ? netProfit / cogs : null,
    averageProfitPerUnit: units ? netProfit / units : null,
    units,
    completeRows: completeRows.length,
    excludedRows: periodRows.length - completeRows.length,
  };
}

function summarizeCompleteness(rows: ProfitRowWithDate[]) {
  const recentRows = rows.filter((row) => (row.soldAt ?? "") >= dateDaysAgo(90) && normalizeDataStatus(row.data_status) !== "cancelled");
  const missingCogs = recentRows.filter((row) => normalizeDataStatus(row.data_status) === "missing_cogs" || toNumber(row.cogs) <= 0);
  const missingFees = recentRows.filter((row) => normalizeDataStatus(row.data_status) === "missing_fees");
  const pendingFees = recentRows.filter((row) => normalizeDataStatus(row.data_status).includes("pending"));
  const missingFulfillmentCost = recentRows.filter(
    (row) => normalizeDataStatus(row.data_status) === "missing_fulfillment_cost" || toNumber(row.fulfillment_cost) === 0,
  );
  return [
    completenessRow("missing-cogs", "Missing COGS", missingCogs),
    completenessRow("missing-fees", "Missing Amazon Fees", missingFees),
    completenessRow("pending-fees", "Pending Fees", pendingFees),
    completenessRow("missing-fulfillment", "Missing Fulfillment Cost", missingFulfillmentCost),
  ];
}

function completenessRow(id: string, label: string, rows: ProfitRowWithDate[]) {
  return {
    id,
    label,
    count: rows.length,
    amountAtRisk: rows.reduce((sum, row) => sum + toNumber(row.sale_price), 0),
    drilldownUrl: "/sales-orders",
  };
}

function normalizeDataStatus(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function sumQuantity(rows: Array<{ quantity: number | null }>) {
  return rows.reduce((sum, row) => sum + toNumber(row.quantity), 0);
}

function sumField<T extends Record<string, unknown>>(rows: T[], field: keyof T) {
  return rows.reduce((sum, row) => sum + toNumber(row[field]), 0);
}

function latest(values: Array<string | null | undefined>) {
  return values.filter(Boolean).sort().at(-1) ?? null;
}
