import { NextResponse } from "next/server";
import {
  fetchDashboardPurchaseRows,
  fetchOpenOrderProblemCases,
  hasSellPrice,
  hasValidAsin,
  normalizeStatus,
  reportableRows,
  sumCost,
  sumUnits,
} from "../_summary";

export async function GET() {
  const [purchaseRows, problemCases] = await Promise.all([
    fetchDashboardPurchaseRows(),
    fetchOpenOrderProblemCases(),
  ]);
  const rows = reportableRows(purchaseRows);
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
  const preAmazonRows = rows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    return !["listed", "cancelled", "return_opened"].includes(status);
  });

  return NextResponse.json({
    refreshedAt: new Date().toISOString(),
    metrics: {
      preAmazonInventoryValue: sumCost(preAmazonRows),
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
        detail: "Open MBOP episodes and active eBay returns",
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
    warnings: [
      "Dashboard split MVP tabs are live. Some drill-downs still open base workflow routes until those pages support exact dashboard filters.",
    ],
  });
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
