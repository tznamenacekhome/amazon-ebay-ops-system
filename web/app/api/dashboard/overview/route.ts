import { NextResponse } from "next/server";
import {
  fetchBusinessValueHistory,
  fetchDashboardPurchaseRows,
  fetchOpenOrderProblemCases,
  hasSellPrice,
  hasValidAsin,
  normalizeStatus,
  reportableRows,
  sumCost,
  sumUnits,
  supabase,
  toNumber,
} from "../_summary";

const SELLER_CENTRAL_PAYMENTS_URL = "https://sellercentral.amazon.com/payments/dashboard/index.html";

export async function GET() {
  const [history, purchaseRows, problemCases, amazonCash] = await Promise.all([
    fetchBusinessValueHistory(30),
    fetchDashboardPurchaseRows(),
    fetchOpenOrderProblemCases(),
    fetchLatestAmazonCash(),
  ]);
  const rows = reportableRows(purchaseRows);
  const latestValue = history.at(-1) ?? null;
  const receivingRows = rows.filter((row) =>
    ["delivered", "shipped_no_tracking"].includes(normalizeStatus(row.current_status)),
  );
  const fbaReadyRows = rows.filter(
    (row) =>
      normalizeStatus(row.current_status) === "received" &&
      row.marketplace !== "eBay" &&
      hasValidAsin(row.asin) &&
      hasSellPrice(row) &&
      Boolean(row.amazon_title),
  );
  const purchaseCleanupRows = rows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    if (["listed", "cancelled", "return_opened"].includes(status)) return false;
    return !hasValidAsin(row.asin) || !hasSellPrice(row) || !row.system || !row.amazon_title;
  });

  return NextResponse.json({
    refreshedAt: latestValue?.snapshot_date ?? new Date().toISOString(),
    metrics: {
      totalBusinessValue: latestValue?.total_business_value ?? null,
      amazonInventoryValue: latestValue?.amazon_inventory_value ?? null,
      preAmazonInventoryValue: latestValue?.pre_amazon_inventory_value ?? null,
      amazonCash: latestValue?.amazon_cash_balance ?? null,
      amazonFundsAvailable: toNumber(amazonCash?.available_to_withdraw),
      sellerCentralPaymentsUrl: SELLER_CENTRAL_PAYMENTS_URL,
      amazonToBankInTransit: latestValue?.amazon_cash_in_transit ?? null,
      ynabBusinessCash: latestValue?.cash_on_hand ?? null,
    },
    attention: [
      {
        label: "Receiving Backlog",
        value: sumUnits(receivingRows),
        detail: `${receivingRows.length} row(s) delivered or shipped without tracking`,
        severity: severityFor(sumUnits(receivingRows), 0, 10),
        href: "/receiving",
      },
      {
        label: "FBA Prep Backlog",
        value: sumUnits(fbaReadyRows),
        detail: `${fbaReadyRows.length} ready row(s), ${formatMoney(sumCost(fbaReadyRows))} cost basis`,
        severity: severityFor(sumUnits(fbaReadyRows), 0, 40),
        href: "/fba",
      },
      {
        label: "Open Order Problems",
        value: problemCases.length,
        detail: "Open derived/manual/eBay return problem cases",
        severity: severityFor(problemCases.length, 0, 8),
        href: "/?tab=order-problems",
      },
      {
        label: "Purchase Missing Data",
        value: purchaseCleanupRows.length,
        detail: "Rows missing ASIN, sell price, Amazon title, or system",
        severity: severityFor(purchaseCleanupRows.length, 0, 25),
        href: "/?tab=missing-data",
      },
      {
        label: "Repricing Action Items",
        value: null,
        detail: "Lightweight repricing summary endpoint pending",
        severity: "unknown",
        href: "/repricing",
      },
      {
        label: "Reconciliation Findings",
        value: null,
        detail: "Inventory dashboard phase will add summary counts",
        severity: "unknown",
        href: "/inventory-reconciliation",
      },
    ],
    trend: history.map((row) => ({
      date: row.snapshot_date,
      value: row.total_business_value,
    })),
    warnings: [
      "Dashboard split MVP tabs are live. Some drill-downs still open base workflow routes until those pages support exact dashboard filters.",
    ],
  });
}

async function fetchLatestAmazonCash() {
  const { data, error } = await supabase
    .from("vw_latest_amazon_finance_balance_snapshot")
    .select("available_to_withdraw")
    .limit(1);
  if (error) {
    console.warn("Dashboard Amazon funds available lookup failed", error.message);
    return null;
  }
  return ((data ?? []) as unknown as Array<{ available_to_withdraw?: number | null }>)[0] ?? null;
}

function severityFor(value: number, warningAt: number, urgentAt: number) {
  if (value > urgentAt) return "red";
  if (value > warningAt) return "yellow";
  return "green";
}

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}
