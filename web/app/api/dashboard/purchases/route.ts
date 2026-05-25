import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

type DashboardPurchaseRow = {
  item_id: string | null;
  purchase_id?: string | null;
  order_date: string | null;
  supplier_order_id?: string | null;
  title?: string | null;
  amazon_title?: string | null;
  system?: string | null;
  asin?: string | null;
  sell_price?: number | null;
  target_price?: number | null;
  quantity: number | null;
  unit_cost: number | null;
  current_status: string | null;
  estimated_delivery_date?: string | null;
  delivered_date?: string | null;
  received_date?: string | null;
  exclude_from_purchase_reporting?: boolean;
  marketplace?: "Amazon" | "eBay" | null;
};

type MonthAggregate = {
  year: number;
  month: number;
  monthLabel: string;
  units: number;
  cost: number;
};

type StatusAggregate = {
  status: string;
  label: string;
  units: number;
};

type AgingBucket = {
  label: string;
  count: number;
  units: number;
};

type AttentionRow = {
  item_id: string | null;
  order_id: string | null;
  title: string;
  status: string;
  age_days: number | null;
  issue: string;
};

export async function GET() {
  const rows = await fetchPurchaseRows();
  const rowsWithExclusions = await hydrateReportingExclusions(rows);
  const monthly = aggregateByMonth(rowsWithExclusions);
  const years = aggregateByYear(monthly);
  const statusBreakdown = aggregateByStatus(rowsWithExclusions);
  const operations = aggregateOperations(rowsWithExclusions);
  const totals = monthly.reduce(
    (accumulator, month) => ({
      units: accumulator.units + month.units,
      cost: accumulator.cost + month.cost,
    }),
    { units: 0, cost: 0 }
  );

  return NextResponse.json({
    totals,
    years,
    months: monthly,
    statusBreakdown,
    operations,
  });
}

async function fetchPurchaseRows() {
  const rows: DashboardPurchaseRow[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select("*")
      .range(offset, offset + pageSize - 1);

    if (error) {
      throw new Error(error.message);
    }

    rows.push(...((data ?? []) as DashboardPurchaseRow[]));

    if ((data ?? []).length < pageSize) {
      return rows;
    }

    offset += pageSize;
  }
}

async function hydrateReportingExclusions(rows: DashboardPurchaseRow[]) {
  const itemIds = rows
    .map((row) => row.item_id)
    .filter((itemId): itemId is string => typeof itemId === "string");

  if (itemIds.length === 0) {
    return rows;
  }

  const itemMetaById = new Map<
    string,
    {
      exclude_from_purchase_reporting?: boolean | null;
      amazon_title?: string | null;
      marketplace?: "Amazon" | "eBay" | null;
      received_date?: string | null;
    }
  >();
  const chunkSize = 100;

  for (let index = 0; index < itemIds.length; index += chunkSize) {
    const chunk = itemIds.slice(index, index + chunkSize);
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,exclude_from_purchase_reporting,amazon_title,marketplace,received_date")
      .in("item_id", chunk);

    if (error) {
      console.warn("Dashboard reporting exclusion lookup failed", error.message);
      return rows;
    }

    for (const item of data ?? []) {
      itemMetaById.set(item.item_id, item);
    }
  }

  return rows.map((row) => ({
    ...row,
    amazon_title:
      typeof row.item_id === "string"
        ? itemMetaById.get(row.item_id)?.amazon_title ?? row.amazon_title ?? null
        : row.amazon_title ?? null,
    marketplace:
      typeof row.item_id === "string"
        ? itemMetaById.get(row.item_id)?.marketplace ?? row.marketplace ?? null
        : row.marketplace ?? null,
    received_date:
      typeof row.item_id === "string"
        ? itemMetaById.get(row.item_id)?.received_date ?? row.received_date ?? null
        : row.received_date ?? null,
    exclude_from_purchase_reporting:
      typeof row.item_id === "string"
        ? !!itemMetaById.get(row.item_id)?.exclude_from_purchase_reporting
        : !!row.exclude_from_purchase_reporting,
  }));
}

function aggregateByMonth(rows: DashboardPurchaseRow[]) {
  const aggregates = new Map<string, MonthAggregate>();

  for (const row of rows) {
    if (isExcludedStatus(row.current_status)) continue;
    if (row.exclude_from_purchase_reporting) continue;
    if (!row.order_date) continue;

    const dateMatch = row.order_date.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!dateMatch) continue;

    const year = Number(dateMatch[1]);
    const month = Number(dateMatch[2]);
    const key = `${year}-${String(month).padStart(2, "0")}`;
    const quantity = Number(row.quantity ?? 0);
    const unitCost = Number(row.unit_cost ?? 0);
    const existing = aggregates.get(key) ?? {
      year,
      month,
      monthLabel: monthName(month),
      units: 0,
      cost: 0,
    };

    existing.units += Number.isFinite(quantity) ? quantity : 0;
    existing.cost += Number.isFinite(unitCost) ? unitCost * quantity : 0;

    aggregates.set(key, existing);
  }

  return [...aggregates.values()].sort((left, right) => {
    if (left.year !== right.year) return right.year - left.year;
    return right.month - left.month;
  });
}

function aggregateByYear(months: MonthAggregate[]) {
  const years = new Map<
    number,
    { year: number; units: number; cost: number; months: MonthAggregate[] }
  >();

  for (const month of months) {
    const existing = years.get(month.year) ?? {
      year: month.year,
      units: 0,
      cost: 0,
      months: [],
    };

    existing.units += month.units;
    existing.cost += month.cost;
    existing.months.push(month);

    years.set(month.year, existing);
  }

  return [...years.values()].sort((left, right) => right.year - left.year);
}

function aggregateByStatus(rows: DashboardPurchaseRow[]) {
  const aggregates = new Map<string, StatusAggregate>();

  for (const row of rows) {
    if (row.exclude_from_purchase_reporting) continue;

    const status = normalizeStatus(row.current_status) || "unknown";
    const quantity = Number(row.quantity ?? 0);
    const existing = aggregates.get(status) ?? {
      status,
      label: statusLabel(status),
      units: 0,
    };

    existing.units += Number.isFinite(quantity) ? quantity : 0;
    aggregates.set(status, existing);
  }

  return [...aggregates.values()].sort((left, right) => {
    const leftIndex = STATUS_ORDER.indexOf(left.status);
    const rightIndex = STATUS_ORDER.indexOf(right.status);

    if (leftIndex !== -1 || rightIndex !== -1) {
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    }

    return left.label.localeCompare(right.label);
  });
}

function aggregateOperations(rows: DashboardPurchaseRow[]) {
  const reportableRows = rows.filter((row) => !row.exclude_from_purchase_reporting);
  const activeRows = reportableRows.filter(
    (row) => !["listed", "cancelled", "return_opened"].includes(normalizeStatus(row.current_status))
  );
  const receivingRows = reportableRows.filter((row) =>
    ["delivered", "shipped_no_tracking"].includes(normalizeStatus(row.current_status))
  );
  const fbaRows = reportableRows.filter(
    (row) =>
      normalizeStatus(row.current_status) === "received" &&
      row.marketplace !== "eBay" &&
      hasValidAsin(row.asin)
  );
  const fbaBlockedRows = reportableRows.filter(
    (row) =>
      normalizeStatus(row.current_status) === "received" &&
      row.marketplace !== "eBay" &&
      (!hasValidAsin(row.asin) || !hasSellPrice(row) || !row.amazon_title)
  );
  const needsReviewRows = activeRows.filter(needsReview);
  const overdueRows = activeRows.filter(isOverdue);
  const noTrackingAgedRows = activeRows.filter((row) => {
    const status = normalizeStatus(row.current_status);
    const orderAgeDays = ageDays(row.order_date);

    return (
      ["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"].includes(status) &&
      orderAgeDays !== null &&
      orderAgeDays >= 7 &&
      orderAgeDays <= 90
    );
  });
  const exceptionRows = reportableRows.filter((row) =>
    ["exception", "return_pending"].includes(normalizeStatus(row.current_status))
  );

  return {
    purchaseCompleteness: {
      active_rows: activeRows.length,
      active_units: sumUnits(activeRows),
      needs_review_rows: needsReviewRows.length,
      needs_review_units: sumUnits(needsReviewRows),
      missing_asin_rows: activeRows.filter((row) => !hasValidAsin(row.asin)).length,
      missing_sell_price_rows: activeRows.filter((row) => !hasSellPrice(row)).length,
      missing_system_rows: activeRows.filter((row) => !row.system).length,
      missing_amazon_title_rows: activeRows.filter(
        (row) => hasValidAsin(row.asin) && !row.amazon_title
      ).length,
    },
    receivingBacklog: {
      rows: receivingRows.length,
      units: sumUnits(receivingRows),
      oldest_age_days: maxAge(receivingRows, backlogStartDate),
      aging: agingBuckets(receivingRows, backlogStartDate),
    },
    shipmentPrepBacklog: {
      rows: fbaRows.length,
      units: sumUnits(fbaRows),
      total_cost: sumCost(fbaRows),
      oldest_age_days: maxAge(fbaRows, fbaStartDate),
      blocked_rows: fbaBlockedRows.length,
      blocked_units: sumUnits(fbaBlockedRows),
      aging: agingBuckets(fbaRows, fbaStartDate),
    },
    inventoryState: {
      purchased_not_received_units: sumUnits(
        reportableRows.filter((row) =>
          [
            "no_tracking",
            "shipped_no_tracking",
            "awaiting_carrier_scan",
            "in_transit",
            "available_for_pickup",
            "out_for_delivery",
            "delivered",
            "exception",
          ].includes(normalizeStatus(row.current_status))
        )
      ),
      received_units: sumUnits(
        reportableRows.filter((row) => normalizeStatus(row.current_status) === "received")
      ),
      listed_units: sumUnits(
        reportableRows.filter((row) => normalizeStatus(row.current_status) === "listed")
      ),
      return_or_cancel_units: sumUnits(
        reportableRows.filter((row) =>
          ["return_pending", "return_opened", "cancelled"].includes(
            normalizeStatus(row.current_status)
          )
        )
      ),
    },
    exceptions: {
      overdue_rows: overdueRows.length,
      overdue_units: sumUnits(overdueRows),
      aged_no_tracking_rows: noTrackingAgedRows.length,
      aged_no_tracking_units: sumUnits(noTrackingAgedRows),
      exception_rows: exceptionRows.length,
      exception_units: sumUnits(exceptionRows),
      top_attention: [
        ...overdueRows.map((row) => attentionRow(row, "Past ETA", etaAge(row))),
        ...noTrackingAgedRows.map((row) =>
          attentionRow(row, "Tracking stale or missing", ageDays(row.order_date))
        ),
        ...exceptionRows.map((row) =>
          attentionRow(row, statusLabel(normalizeStatus(row.current_status)), ageDays(row.order_date))
        ),
        ...needsReviewRows.map((row) =>
          attentionRow(row, reviewIssue(row), ageDays(row.order_date))
        ),
      ]
        .sort((left, right) => (right.age_days ?? -1) - (left.age_days ?? -1))
        .slice(0, 15),
    },
  };
}

function needsReview(row: DashboardPurchaseRow) {
  const status = normalizeStatus(row.current_status);
  if (["cancelled", "return_opened", "return_pending", "listed"].includes(status)) {
    return false;
  }

  return (
    !hasValidAsin(row.asin) ||
    !hasSellPrice(row) ||
    !row.system ||
    (hasValidAsin(row.asin) && !row.amazon_title)
  );
}

function reviewIssue(row: DashboardPurchaseRow) {
  if (!hasValidAsin(row.asin)) return "Missing ASIN";
  if (!hasSellPrice(row)) return "Missing sell price";
  if (!row.system) return "Missing system";
  if (!row.amazon_title) return "Missing Amazon title";
  return "Needs review";
}

function hasValidAsin(value?: string | null) {
  const asin = (value || "").trim().toUpperCase();
  return !!asin && asin !== "N/A";
}

function hasSellPrice(row: DashboardPurchaseRow) {
  return row.sell_price !== null && row.sell_price !== undefined
    ? Number(row.sell_price) > 0
    : row.target_price !== null && row.target_price !== undefined
      ? Number(row.target_price) > 0
      : false;
}

function isOverdue(row: DashboardPurchaseRow) {
  const status = normalizeStatus(row.current_status);
  if (["delivered", "received", "listed", "cancelled", "return_opened"].includes(status)) {
    return false;
  }

  const eta = parseDate(row.estimated_delivery_date);
  if (!eta) return false;

  return daysBetween(eta, today()) > 0;
}

function backlogStartDate(row: DashboardPurchaseRow) {
  return row.delivered_date ?? row.estimated_delivery_date ?? row.order_date ?? null;
}

function fbaStartDate(row: DashboardPurchaseRow) {
  return row.received_date ?? row.delivered_date ?? row.order_date ?? null;
}

function etaAge(row: DashboardPurchaseRow) {
  const eta = parseDate(row.estimated_delivery_date);
  return eta ? daysBetween(eta, today()) : null;
}

function ageDays(value?: string | null) {
  const parsed = parseDate(value);
  return parsed ? daysBetween(parsed, today()) : null;
}

function maxAge(rows: DashboardPurchaseRow[], dateGetter: (row: DashboardPurchaseRow) => string | null) {
  const ages = rows
    .map((row) => ageDays(dateGetter(row)))
    .filter((age): age is number => typeof age === "number");

  return ages.length ? Math.max(...ages) : null;
}

function agingBuckets(
  rows: DashboardPurchaseRow[],
  dateGetter: (row: DashboardPurchaseRow) => string | null
): AgingBucket[] {
  const buckets = [
    { label: "0-2 days", min: 0, max: 2, count: 0, units: 0 },
    { label: "3-7 days", min: 3, max: 7, count: 0, units: 0 },
    { label: "8-14 days", min: 8, max: 14, count: 0, units: 0 },
    { label: "15+ days", min: 15, max: Infinity, count: 0, units: 0 },
    { label: "No date", min: null, max: null, count: 0, units: 0 },
  ];

  for (const row of rows) {
    const age = ageDays(dateGetter(row));
    const bucket =
      age === null
        ? buckets[buckets.length - 1]
        : buckets.find((candidate) => age >= candidate.min! && age <= candidate.max!)!;

    bucket.count += 1;
    bucket.units += unitQuantity(row);
  }

  return buckets.map(({ label, count, units }) => ({ label, count, units }));
}

function attentionRow(
  row: DashboardPurchaseRow,
  issue: string,
  age: number | null
): AttentionRow {
  return {
    item_id: row.item_id,
    order_id: row.supplier_order_id ?? null,
    title: row.amazon_title || row.title || "Untitled item",
    status: statusLabel(normalizeStatus(row.current_status) || "unknown"),
    age_days: age,
    issue,
  };
}

function sumUnits(rows: DashboardPurchaseRow[]) {
  return rows.reduce((total, row) => total + unitQuantity(row), 0);
}

function sumCost(rows: DashboardPurchaseRow[]) {
  return rows.reduce((total, row) => {
    const quantity = unitQuantity(row);
    const unitCost = Number(row.unit_cost ?? 0);
    return total + (Number.isFinite(unitCost) ? unitCost * quantity : 0);
  }, 0);
}

function unitQuantity(row: DashboardPurchaseRow) {
  const quantity = Number(row.quantity ?? 0);
  return Number.isFinite(quantity) ? quantity : 0;
}

function parseDate(value?: string | null) {
  if (!value) return null;
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function today() {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

function daysBetween(start: Date, end: Date) {
  return Math.floor((end.getTime() - start.getTime()) / 86_400_000);
}

function normalizeStatus(value?: string | null) {
  return (value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function isExcludedStatus(value?: string | null) {
  return ["cancelled", "return_opened"].includes(normalizeStatus(value));
}

function monthName(month: number) {
  return new Date(Date.UTC(2026, month - 1, 1)).toLocaleString("en-US", {
    month: "short",
    timeZone: "UTC",
  });
}

const STATUS_ORDER = [
  "no_tracking",
  "ordered",
  "shipped_no_tracking",
  "awaiting_carrier_scan",
  "in_transit",
  "available_for_pickup",
  "out_for_delivery",
  "delivered",
  "received",
  "listed",
  "exception",
  "return_pending",
  "return_opened",
  "cancelled",
  "unknown",
];

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    no_tracking: "No Tracking",
    ordered: "Ordered",
    shipped_no_tracking: "Shipped (No Tracking)",
    awaiting_carrier_scan: "Awaiting Carrier Scan",
    in_transit: "In Transit",
    available_for_pickup: "Out for Pickup / Pickup Available",
    out_for_delivery: "Out for Delivery",
    delivered: "Delivered",
    received: "Received",
    listed: "Listed",
    exception: "Exception",
    return_pending: "Return Pending",
    return_opened: "Return Opened",
    cancelled: "Cancelled",
    unknown: "Unknown",
  };

  return labels[status] ?? status.replace(/_/g, " ");
}
