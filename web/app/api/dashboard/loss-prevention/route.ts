import { NextResponse } from "next/server";
import {
  ageDays,
  fetchDashboardPurchaseRows,
  fetchOpenOrderProblemCases,
  fetchOpenReconciliationItems,
  latestTimestamp,
  monthKey,
  supabase,
  toNumber,
} from "../_summary";

export async function GET() {
  const [cases, purchaseRows, findings, trackingUpdatedAt, salesUpdatedAt, fbaRows] = await Promise.all([
    fetchOpenOrderProblemCases(),
    fetchDashboardPurchaseRows(),
    fetchOpenReconciliationItems(500),
    latestTimestamp("inbound_shipments", "last_tracking_sync"),
    latestTimestamp("amazon_sales_profitability", "updated_at"),
    fetchLatestFbaInventory(),
  ]);
  const valueByItem = new Map(purchaseRows.map((row) => [row.item_id, toNumber(row.unit_cost) * toNumber(row.quantity)]));
  const titleByItem = new Map(purchaseRows.map((row) => [row.item_id, row.amazon_title || row.title || "Untitled"]));
  const enriched = cases.map((row) => ({
    ...row,
    valueAtRisk: toNumber(row.expected_refund_amount) || (valueByItem.get(row.purchase_item_id ?? "") ?? 0),
    title: titleByItem.get(row.purchase_item_id ?? "") ?? "Order problem",
  }));
  const amazonUnsellableUnits = fbaRows.reduce((sum, row) => sum + toNumber(row.unfulfillable_quantity), 0);
  const amazonDiscrepancyCount = findings.length;

  return NextResponse.json({
    refreshedAt: newest([latest(cases.map((row) => row.updated_at)), trackingUpdatedAt, latest(findings.map((row) => String(row.created_at ?? row.first_seen_at ?? "")))]),
    freshness: {
      orderProblemsUpdatedAt: latest(cases.map((row) => row.updated_at)),
      trackingUpdatedAt,
      reconciliationUpdatedAt: latest(findings.map((row) => String(row.created_at ?? row.first_seen_at ?? ""))),
      salesUpdatedAt,
      oldestRequiredInputAt: oldest([latest(cases.map((row) => row.updated_at)), trackingUpdatedAt, salesUpdatedAt]),
    },
    summary: {
      openProblemCases: cases.length,
      estimatedValueAtRisk: enriched.reduce((sum, row) => sum + row.valueAtRisk, 0),
      refundPendingValue: sumRisk(enriched.filter((row) => row.workflow_state === "refund_pending")),
      returnPendingCount: enriched.filter((row) => ["return_needed", "return_pending"].includes(String(row.workflow_state ?? ""))).length,
      lateShipmentCount: enriched.filter((row) => ["late_delivery_candidate", "stale_tracking_candidate"].includes(String(row.problem_type ?? ""))).length,
      carrierExceptionCount: enriched.filter((row) => row.problem_type === "carrier_exception_candidate").length,
      amazonUnsellableUnits,
      amazonDiscrepancyCount,
    },
    byRiskType: [
      risk("Return pending", enriched.filter((row) => ["return_needed", "return_pending"].includes(String(row.workflow_state ?? ""))), "/?tab=order-problems&stage=return_needed"),
      risk("Refund pending", enriched.filter((row) => row.workflow_state === "refund_pending"), "/?tab=order-problems&stage=refund_pending"),
      risk("Late delivery", enriched.filter((row) => row.problem_type === "late_delivery_candidate"), "/?tab=order-problems&type=late_delivery_candidate"),
      risk("Stale/no tracking", enriched.filter((row) => row.problem_type === "stale_tracking_candidate"), "/?tab=order-problems&type=stale_tracking_candidate"),
      risk("Carrier exception", enriched.filter((row) => row.problem_type === "carrier_exception_candidate"), "/?tab=order-problems&type=carrier_exception_candidate"),
      risk("Cancelled awaiting refund", enriched.filter((row) => row.problem_type === "cancelled_refund_followup"), "/?tab=order-problems&stage=refund_pending"),
      { riskType: "Amazon discrepancy", count: amazonDiscrepancyCount, valueAtRisk: null, oldestAgeDays: null, drilldownUrl: "/inventory-reconciliation" },
    ].filter((row) => row.count > 0),
    urgentCases: enriched
      .sort((left, right) => priorityScore(right) - priorityScore(left))
      .slice(0, 10)
      .map((row) => ({
        severity: priorityScore(row) > 90 ? "high" : priorityScore(row) > 40 ? "medium" : "low",
        caseId: row.problem_case_id,
        orderNumber: row.supplier_order_id,
        title: row.title,
        status: row.problem_type,
        stage: row.workflow_state,
        ageDays: ageDays(row.first_detected_at),
        valueAtRisk: row.valueAtRisk,
        nextAction: row.next_action,
        actionDueDate: row.next_action_due_at ?? row.refund_due_at,
        drilldownUrl: "/?tab=order-problems",
      })),
    lossTrend: await lossTrend(),
  });
}

async function fetchLatestFbaInventory() {
  const { data, error } = await supabase.from("vw_latest_amazon_fba_inventory_snapshot").select("unfulfillable_quantity");
  if (error) return [];
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

async function lossTrend() {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select("problem_type,workflow_state,actual_refund_amount,created_at,closed_at")
    .order("created_at", { ascending: false })
    .limit(1000);
  if (error) return [];
  const byMonth = new Map<string, { yearMonth: string; refundsReceived: number; closedNoRefundValue: number; returnCount: number; cancelledCount: number; problemCaseCount: number }>();
  for (const row of (data ?? []) as unknown as Array<Record<string, unknown>>) {
    const key = monthKey(String(row.created_at ?? row.closed_at ?? ""));
    if (!key) continue;
    const current = byMonth.get(key) ?? { yearMonth: key, refundsReceived: 0, closedNoRefundValue: 0, returnCount: 0, cancelledCount: 0, problemCaseCount: 0 };
    current.problemCaseCount += 1;
    if (String(row.workflow_state ?? "").includes("refund")) current.refundsReceived += toNumber(row.actual_refund_amount);
    if (String(row.workflow_state ?? "") === "closed_no_refund") current.closedNoRefundValue += 0;
    if (String(row.problem_type ?? "").includes("return") || String(row.workflow_state ?? "").includes("return")) current.returnCount += 1;
    if (String(row.problem_type ?? "").includes("cancel")) current.cancelledCount += 1;
    byMonth.set(key, current);
  }
  return [...byMonth.values()].sort((left, right) => right.yearMonth.localeCompare(left.yearMonth)).slice(0, 12).reverse();
}

function risk(riskType: string, rows: Array<{ valueAtRisk: number; first_detected_at?: string | null }>, drilldownUrl: string) {
  return {
    riskType,
    count: rows.length,
    valueAtRisk: sumRisk(rows),
    oldestAgeDays: rows.reduce<number | null>((max, row) => {
      const age = ageDays(row.first_detected_at);
      return age === null ? max : max === null ? age : Math.max(max, age);
    }, null),
    drilldownUrl,
  };
}
function sumRisk(rows: Array<{ valueAtRisk: number }>) { return rows.reduce((sum, row) => sum + row.valueAtRisk, 0); }
function priorityScore(row: { valueAtRisk: number; next_action_due_at?: string | null; refund_due_at?: string | null; first_detected_at?: string | null; problem_type?: string | null; workflow_state?: string | null }) {
  const due = Date.parse(String(row.next_action_due_at ?? row.refund_due_at ?? ""));
  const overdueBoost = Number.isNaN(due) ? 0 : due < Date.now() ? 50 : 10;
  const age = ageDays(row.first_detected_at) ?? 0;
  const typeBoost = ["carrier_exception_candidate", "refund_pending"].includes(String(row.problem_type ?? row.workflow_state ?? "")) ? 25 : 0;
  return overdueBoost + age + Math.min(row.valueAtRisk, 100) + typeBoost;
}
function latest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort().at(-1) ?? null; }
function newest(values: Array<string | null | undefined>) { return latest(values); }
function oldest(values: Array<string | null | undefined>) { return values.filter(Boolean).sort()[0] ?? null; }
