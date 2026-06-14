import { NextResponse } from "next/server";
import {
  DashboardPurchaseRow,
  STALE_TRACKING_LOOKBACK_DAYS,
  STALE_TRACKING_ORDER_AGE_DAYS,
  ageDays,
  fetchDashboardPurchaseRows,
  fetchOpenOrderProblemCases,
  hasSellPrice,
  hasValidAsin,
  normalizeStatus,
  reportableRows,
  sumCost,
  sumUnits,
  todayDateString,
  weekEndDateString,
} from "../_summary";

type AgingBucket = {
  label: string;
  rows: number;
  units: number;
};

export async function GET() {
  const [purchaseRows, problemCases] = await Promise.all([
    fetchDashboardPurchaseRows(),
    fetchOpenOrderProblemCases(),
  ]);
  const rows = reportableRows(purchaseRows);
  const today = todayDateString();
  const weekEnd = weekEndDateString();
  const receivingRows = rows.filter((row) =>
    ["delivered", "shipped_no_tracking"].includes(normalizeStatus(row.current_status)),
  );
  const arrivingTodayRows = rows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    const eta = dateOnly(row.estimated_delivery_date);
    return ["in_transit", "out_for_delivery", "available_for_pickup"].includes(status) && eta === today;
  });
  const arrivingWeekRows = rows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    const eta = dateOnly(row.estimated_delivery_date);
    return (
      ["in_transit", "out_for_delivery", "available_for_pickup"].includes(status) &&
      Boolean(eta) &&
      eta >= today &&
      eta <= weekEnd
    );
  });
  const noTrackingRows = rows.filter((row) =>
    ["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"].includes(normalizeStatus(row.current_status)),
  );
  const fbaReadyRows = rows.filter(isFbaReady);
  const fbaBlockedRows = rows.filter(isFbaBlocked);
  const activeRows = rows.filter((row) => !["listed", "cancelled", "return_opened"].includes(normalizeStatus(row.current_status)));
  const purchaseCleanup = {
    missingAsin: activeRows.filter((row) => !hasValidAsin(row.asin)).length,
    missingSellPrice: activeRows.filter((row) => !hasSellPrice(row)).length,
    missingAmazonTitle: activeRows.filter((row) => hasValidAsin(row.asin) && !row.amazon_title).length,
    missingSystem: activeRows.filter((row) => !row.system).length,
  };

  return NextResponse.json({
    refreshedAt: new Date().toISOString(),
    receiving: {
      deliveredNotReceived: receivingRows.length,
      deliveredNotReceivedUnits: sumUnits(receivingRows),
      shippedWithNoTracking: noTrackingRows.length,
      arrivingToday: arrivingTodayRows.length,
      arrivingThisWeek: arrivingWeekRows.length,
      oldestDeliveredNotReceivedDays: maxAge(receivingRows, (row) => row.delivered_date ?? row.order_date),
      href: "/receiving",
    },
    fbaPrep: {
      readyRows: fbaReadyRows.length,
      readyUnits: sumUnits(fbaReadyRows),
      distinctAsins: new Set(fbaReadyRows.map((row) => row.asin).filter(Boolean)).size,
      estimatedCostReady: sumCost(fbaReadyRows),
      blockedRows: fbaBlockedRows.length,
      blockedUnits: sumUnits(fbaBlockedRows),
      oldestReceivedNotListedDays: maxAge([...fbaReadyRows, ...fbaBlockedRows], (row) => row.received_date ?? row.order_date),
      href: "/fba",
    },
    purchaseCleanup: {
      ...purchaseCleanup,
      href: "/?tab=missing-data",
    },
    orderProblems: {
      lateDeliveryCandidates: problemCases.filter((row) => row.problem_type === "late_delivery_candidate").length,
      staleTrackingCandidates: problemCases.filter((row) => row.problem_type === "stale_tracking_candidate").length,
      carrierExceptions: problemCases.filter((row) => row.problem_type === "carrier_exception_candidate").length,
      returnPending: problemCases.filter((row) => row.workflow_state === "return_needed" || row.workflow_state === "return_pending").length,
      returnOpened: problemCases.filter((row) => row.workflow_state === "return_opened").length,
      refundPending: problemCases.filter((row) => row.workflow_state === "refund_pending").length,
      replacementFollowUp: problemCases.filter((row) =>
        ["replacement_pending", "replacement_shipped", "escalation_available"].includes(String(row.workflow_state ?? "")),
      ).length,
      href: "/?tab=order-problems",
    },
    workflowAging: {
      purchaseToDelivered: agingBuckets(
        rows.filter((row) =>
          [
            "no_tracking",
            "shipped_no_tracking",
            "awaiting_carrier_scan",
            "in_transit",
            "available_for_pickup",
            "out_for_delivery",
          ].includes(normalizeStatus(row.current_status)),
        ),
        (row) => row.order_date,
      ),
      deliveredToReceived: agingBuckets(receivingRows, (row) => row.delivered_date ?? row.order_date),
      receivedToListed: agingBuckets([...fbaReadyRows, ...fbaBlockedRows], (row) => row.received_date ?? row.order_date),
    },
    attentionRows: [
      ...staleTrackingRows(activeRows).map((row) => attentionRow(row, "Tracking stale or missing", row.order_date)),
      ...receivingRows.map((row) => attentionRow(row, "Delivered not received", row.delivered_date ?? row.order_date)),
      ...fbaBlockedRows.map((row) => attentionRow(row, "FBA prep blocked", row.received_date ?? row.order_date)),
    ]
      .sort((left, right) => (right.ageDays ?? -1) - (left.ageDays ?? -1))
      .slice(0, 10),
  });
}

function isFbaReady(row: DashboardPurchaseRow) {
  return (
    normalizeStatus(row.current_status) === "received" &&
    row.marketplace !== "eBay" &&
    hasValidAsin(row.asin) &&
    hasSellPrice(row) &&
    Boolean(row.amazon_title)
  );
}

function isFbaBlocked(row: DashboardPurchaseRow) {
  return (
    normalizeStatus(row.current_status) === "received" &&
    row.marketplace !== "eBay" &&
    (!hasValidAsin(row.asin) || !hasSellPrice(row) || !row.amazon_title)
  );
}

function staleTrackingRows(rows: DashboardPurchaseRow[]) {
  return rows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    const orderAge = ageDays(row.order_date);
    return (
      ["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"].includes(status) &&
      orderAge !== null &&
      orderAge >= STALE_TRACKING_ORDER_AGE_DAYS &&
      orderAge <= STALE_TRACKING_LOOKBACK_DAYS
    );
  });
}

function agingBuckets(rows: DashboardPurchaseRow[], dateSelector: (row: DashboardPurchaseRow) => string | null | undefined): AgingBucket[] {
  const buckets = [
    { label: "0-3 days", max: 3, rows: 0, units: 0 },
    { label: "4-7 days", max: 7, rows: 0, units: 0 },
    { label: "8-14 days", max: 14, rows: 0, units: 0 },
    { label: "15+ days", max: Number.POSITIVE_INFINITY, rows: 0, units: 0 },
  ];

  for (const row of rows) {
    const age = ageDays(dateSelector(row));
    if (age === null) continue;
    const bucket = buckets.find((candidate) => age <= candidate.max) ?? buckets.at(-1)!;
    bucket.rows += 1;
    bucket.units += Number(row.quantity ?? 0);
  }

  return buckets.map(({ label, rows: rowCount, units }) => ({ label, rows: rowCount, units }));
}

function maxAge(rows: DashboardPurchaseRow[], dateSelector: (row: DashboardPurchaseRow) => string | null | undefined) {
  return rows.reduce<number | null>((max, row) => {
    const age = ageDays(dateSelector(row));
    if (age === null) return max;
    return max === null ? age : Math.max(max, age);
  }, null);
}

function attentionRow(row: DashboardPurchaseRow, issue: string, date: string | null | undefined) {
  return {
    itemId: row.item_id,
    orderId: row.supplier_order_id,
    title: row.amazon_title || row.title || "Untitled item",
    status: normalizeStatus(row.current_status) || "unknown",
    issue,
    ageDays: ageDays(date),
  };
}

function dateOnly(value: string | null | undefined) {
  return String(value || "").slice(0, 10);
}
