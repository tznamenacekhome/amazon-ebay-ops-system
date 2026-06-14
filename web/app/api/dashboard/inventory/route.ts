import { NextResponse } from "next/server";
import {
  ageDays,
  fetchInventoryPositions,
  fetchOpenReconciliationItems,
  latestTimestamp,
  toNumber,
} from "../_summary";

const LOCATION_GROUPS = [
  { key: "amazon_fba", label: "Amazon FBA", states: ["amazon_fba_sellable", "amazon_fba_reserved", "amazon_fba_unsellable_damaged", "amazon_fba_stranded"], href: "/inventory-reconciliation" },
  { key: "outbound_to_amazon", label: "Outbound to Amazon", states: ["outbound_to_amazon", "amazon_fba_inbound_receiving"], href: "/fba" },
  { key: "received", label: "Received / Ready for FBA", states: ["received_unassigned", "received_assigned_amazon_not_sent"], href: "/fba" },
  { key: "ordered_not_received", label: "Ordered not received", states: ["purchased_not_shipped", "shipped_not_delivered", "delivered_not_received"], href: "/" },
  { key: "return_pending", label: "Return pending", states: ["return_pending", "return_opened", "cancelled_refund_follow_up"], href: "/?tab=order-problems" },
];

export async function GET() {
  const [positions, findings, amazonInventoryUpdatedAt, valuationUpdatedAt, reconciliationUpdatedAt] = await Promise.all([
    fetchInventoryPositions(),
    fetchOpenReconciliationItems(500),
    latestTimestamp("amazon_fba_inventory_snapshots", "captured_at"),
    latestTimestamp("inventorylab_inventory_valuation_snapshots", "imported_at"),
    latestTimestamp("inventory_reconciliation_events", "completed_at"),
  ]);
  const totalUnits = positions.reduce((total, row) => total + toNumber(row.quantity), 0);
  const totalInventoryValue = positions.reduce((total, row) => total + rowValue(row), 0);
  const byLocation = LOCATION_GROUPS.map((group) => {
    const rows = positions.filter((row) => group.states.includes(String(row.inventory_state ?? "")));
    const value = rows.reduce((total, row) => total + rowValue(row), 0);
    return {
      locationKey: group.key,
      label: group.label,
      units: rows.reduce((total, row) => total + toNumber(row.quantity), 0),
      value,
      percentOfTotal: totalInventoryValue ? (value / totalInventoryValue) * 100 : 0,
      drilldownUrl: group.href,
    };
  });
  const groupedValue = byLocation.reduce((total, row) => total + row.value, 0);
  const groupedUnits = byLocation.reduce((total, row) => total + row.units, 0);
  byLocation.push({
    locationKey: "other",
    label: "Other / unknown",
    units: Math.max(totalUnits - groupedUnits, 0),
    value: Math.max(totalInventoryValue - groupedValue, 0),
    percentOfTotal: totalInventoryValue ? ((totalInventoryValue - groupedValue) / totalInventoryValue) * 100 : 0,
    drilldownUrl: "/inventory-reconciliation",
  });

  const ageBuckets = buildAgeBuckets(positions, totalInventoryValue);
  const concentration = buildConcentration(positions).slice(0, 10);
  const summaryByKey = new Map(byLocation.map((row) => [row.locationKey, row]));
  const risk = {
    over90DaysValue: ageBuckets.filter((row) => ["91-180", "181-365", "365+"].includes(row.bucket)).reduce((sum, row) => sum + row.value, 0),
    over180DaysValue: ageBuckets.filter((row) => ["181-365", "365+"].includes(row.bucket)).reduce((sum, row) => sum + row.value, 0),
    over365DaysValue: ageBuckets.find((row) => row.bucket === "365+")?.value ?? 0,
    unknownAgeValue: ageBuckets.find((row) => row.bucket === "unknown")?.value ?? 0,
  };

  return NextResponse.json({
    refreshedAt: newest([amazonInventoryUpdatedAt, reconciliationUpdatedAt, latestUpdatedAt(positions)]),
    freshness: {
      inventoryPositionsUpdatedAt: latestUpdatedAt(positions),
      amazonInventoryUpdatedAt,
      inventoryValuationUpdatedAt: valuationUpdatedAt,
      reconciliationUpdatedAt,
      oldestRequiredInputAt: oldest([latestUpdatedAt(positions), amazonInventoryUpdatedAt, reconciliationUpdatedAt]),
    },
    summary: {
      totalUnits,
      totalInventoryValue,
      amazonFbaSellableUnits: unitsFor(positions, ["amazon_fba_sellable"]),
      amazonFbaValue: summaryByKey.get("amazon_fba")?.value ?? 0,
      outboundToAmazonUnits: summaryByKey.get("outbound_to_amazon")?.units ?? 0,
      outboundToAmazonValue: summaryByKey.get("outbound_to_amazon")?.value ?? 0,
      receivedUnits: summaryByKey.get("received")?.units ?? 0,
      receivedValue: summaryByKey.get("received")?.value ?? 0,
      orderedNotReceivedUnits: summaryByKey.get("ordered_not_received")?.units ?? 0,
      orderedNotReceivedValue: summaryByKey.get("ordered_not_received")?.value ?? 0,
      returnPendingUnits: summaryByKey.get("return_pending")?.units ?? 0,
      returnPendingValue: summaryByKey.get("return_pending")?.value ?? 0,
    },
    byLocation,
    ageBuckets,
    capitalAtRisk: risk,
    concentration,
    attention: [
      attention("high", "Open reconciliation findings", findings.length, null, "Inventory reconciliation has open findings.", "/inventory-reconciliation"),
      attention("high", "Unsellable Amazon units", findings.filter((row) => String(row.issue_type ?? "").includes("unsellable")).length, null, "Amazon reports unsellable or damaged inventory.", "/inventory-reconciliation"),
      attention("medium", "Inventory over 180 days", 0, risk.over180DaysValue, "Capital is tied up in aged inventory.", "/repricing"),
      attention("medium", "Unknown age inventory", 0, risk.unknownAgeValue, "Age context is missing for some inventory positions.", "/inventory-reconciliation"),
      attention("medium", "Return pending value", summaryByKey.get("return_pending")?.units ?? 0, summaryByKey.get("return_pending")?.value ?? 0, "Problem inventory may need refund follow-up.", "/?tab=order-problems"),
    ].filter((row) => row.count > 0 || toNumber(row.valueAtRisk) > 0).slice(0, 8),
  });
}

function buildAgeBuckets(rows: Awaited<ReturnType<typeof fetchInventoryPositions>>, totalValue: number) {
  const buckets = ["0-30", "31-60", "61-90", "91-180", "181-365", "365+", "unknown"] as const;
  const output = new Map(buckets.map((bucket) => [bucket, { bucket, units: 0, value: 0, percentOfValue: 0, drilldownUrl: bucket === "181-365" || bucket === "365+" ? "/repricing" : "/inventory-reconciliation" }]));
  for (const row of rows) {
    const age = ageDays(row.effective_at ?? row.updated_at);
    const bucket = age === null ? "unknown" : age <= 30 ? "0-30" : age <= 60 ? "31-60" : age <= 90 ? "61-90" : age <= 180 ? "91-180" : age <= 365 ? "181-365" : "365+";
    const current = output.get(bucket)!;
    current.units += toNumber(row.quantity);
    current.value += rowValue(row);
  }
  return [...output.values()].map((row) => ({ ...row, percentOfValue: totalValue ? (row.value / totalValue) * 100 : 0 }));
}

function buildConcentration(rows: Awaited<ReturnType<typeof fetchInventoryPositions>>) {
  const byKey = new Map<string, { asin: string | null; sellerSku: string | null; title: string; system: string | null; units: number; value: number; locations: Set<string>; drilldownUrl: string }>();
  for (const row of rows) {
    const key = row.asin || row.seller_sku || row.title || row.inventory_position_id;
    const current = byKey.get(key) ?? { asin: row.asin, sellerSku: row.seller_sku, title: row.title ?? "Untitled", system: row.system, units: 0, value: 0, locations: new Set<string>(), drilldownUrl: row.asin ? `/repricing?search=${encodeURIComponent(row.asin)}` : "/inventory-reconciliation" };
    current.units += toNumber(row.quantity);
    current.value += rowValue(row);
    if (row.inventory_state) current.locations.add(inventoryStateLabel(row.inventory_state));
    byKey.set(key, current);
  }
  return [...byKey.values()].sort((left, right) => right.value - left.value).map((row) => ({ ...row, locationSummary: [...row.locations].slice(0, 3).join(", ") || "--" }));
}

function rowValue(row: { total_cost: number | null; unit_cost: number | null; quantity: number | null }) {
  return toNumber(row.total_cost) || toNumber(row.unit_cost) * toNumber(row.quantity);
}

function unitsFor(rows: Awaited<ReturnType<typeof fetchInventoryPositions>>, states: string[]) {
  return rows.filter((row) => states.includes(String(row.inventory_state ?? ""))).reduce((total, row) => total + toNumber(row.quantity), 0);
}

function attention(severity: "high" | "medium" | "low", label: string, count: number, valueAtRisk: number | null, reason: string, drilldownUrl: string) {
  return { severity, label, count, valueAtRisk, reason, drilldownUrl };
}

function latestUpdatedAt(rows: Array<{ updated_at: string | null }>) {
  return newest(rows.map((row) => row.updated_at));
}

function newest(values: Array<string | null | undefined>) {
  return values.filter(Boolean).sort().at(-1) ?? null;
}

function oldest(values: Array<string | null | undefined>) {
  return values.filter(Boolean).sort()[0] ?? null;
}

function inventoryStateLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
