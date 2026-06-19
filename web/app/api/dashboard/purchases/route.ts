import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";

const supabase = createServerSupabaseClient();

const STALE_TRACKING_ORDER_AGE_DAYS = 14;
const STALE_TRACKING_LOOKBACK_DAYS = 90;
const BUSINESS_VALUE_HISTORY_START_DATE = "2026-05-30";

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

type InventoryPositionSummaryRow = {
  inventory_state: string;
  physical_location: string;
  marketplace_intent: string;
  listing_channel: string;
  operational_status: string;
  condition_disposition: string;
  reconciliation_status: string;
  needs_reconciliation: boolean;
  position_count: number | null;
  unit_count: number | null;
  total_cost: number | null;
};

type InventoryPositionValueRow = {
  inventory_state: string | null;
  asin: string | null;
  total_cost: number | null;
};

type OpenReconciliationItemRow = {
  inventory_reconciliation_event_item_id: string;
  severity: "info" | "warning" | "critical";
  issue_type: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  mbop_quantity: number | null;
  amazon_total_quantity: number | null;
  amazon_fulfillable_quantity: number | null;
  amazon_inbound_quantity: number | null;
  amazon_reserved_quantity: number | null;
  amazon_unsellable_quantity: number | null;
};

type ReconciliationEventRow = {
  inventory_reconciliation_event_id: string;
  reconciliation_type: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  matched_count: number | null;
  mismatch_count: number | null;
  missing_internal_count: number | null;
  missing_external_count: number | null;
  needs_review_count: number | null;
};

type InventoryLocationValueRow = {
  location: string;
  units: number;
  total_cost: number;
};

type BusinessInventoryValueSummary = {
  amazon_inventory_value: number;
  pre_amazon_inventory_value: number;
  amazon_cash_balance: number | null;
  amazon_cash_in_transit: number | null;
  cash_on_hand: number | null;
  total_business_value: number;
  amazon_cash_source: string;
  amazon_cash_in_transit_source: string;
  cash_on_hand_source: string;
};

type BusinessValueHistoryRow = {
  snapshot_date: string;
  total_business_value: number;
  amazon_inventory_value: number;
  pre_amazon_inventory_value: number;
  amazon_cash_balance: number;
  amazon_cash_in_transit: number;
  cash_on_hand: number;
};

type InventoryLabValuationSummary = {
  units: number;
  total_value: number;
  source: string;
} | null;

type YnabCashBalanceSummary = {
  balance: number;
  source: string;
} | null;

type AmazonFinanceBalanceSummary = {
  total_amazon_cash: number | null;
  available_to_withdraw: number | null;
  in_transit_to_bank: number | null;
  deferred_or_reserved_cash: number | null;
  source: string;
} | null;

export async function GET() {
  const rows = await fetchPurchaseRows();
  const rowsWithExclusions = await hydrateReportingExclusions(rows);
  const monthly = aggregateByMonth(rowsWithExclusions);
  const years = aggregateByYear(monthly);
  const statusBreakdown = aggregateByStatus(rowsWithExclusions);
  const operations = aggregateOperations(rowsWithExclusions);
  const inventoryVisibility = await fetchInventoryVisibility();
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
    inventoryVisibility,
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

  const itemMetaById = new Map<string, PurchaseItemMetadata>();
  const metadataRows = await fetchPurchaseItemMetadata();

  if (!metadataRows) {
    return rows;
  }

  const wantedItemIds = new Set(itemIds);
  for (const item of metadataRows) {
    if (wantedItemIds.has(item.item_id)) {
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

type PurchaseItemMetadata = {
  item_id: string;
  exclude_from_purchase_reporting?: boolean | null;
  amazon_title?: string | null;
  marketplace?: "Amazon" | "eBay" | null;
  received_date?: string | null;
};

async function fetchPurchaseItemMetadata() {
  const rows: PurchaseItemMetadata[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const result = await retrySupabaseQuery(() =>
      supabase
        .from("purchase_items")
        .select("item_id,exclude_from_purchase_reporting,amazon_title,marketplace,received_date")
        .range(offset, offset + pageSize - 1),
    );

    if (result.error) {
      console.warn("Dashboard reporting exclusion lookup failed", result.error.message);
      return null;
    }

    rows.push(...((result.data ?? []) as PurchaseItemMetadata[]));
    if ((result.data ?? []).length < pageSize) {
      return rows;
    }

    offset += pageSize;
  }
}

async function retrySupabaseQuery<T>(query: () => PromiseLike<{ data: T[] | null; error: { message: string } | null }>) {
  const maxAttempts = 3;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const result = await query();
    if (!result.error || attempt === maxAttempts) return result;
    await sleep(200 * attempt);
  }

  return query();
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
      orderAgeDays >= STALE_TRACKING_ORDER_AGE_DAYS &&
      orderAgeDays <= STALE_TRACKING_LOOKBACK_DAYS
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

async function fetchInventoryVisibility() {
  const [
    summaryRows,
    openItems,
    latestEvent,
    inventoryLabValuation,
    ynabCashBalance,
    amazonFinanceBalance,
    businessValueHistory,
    inventoryValueRows,
  ] =
    await Promise.all([
    fetchInventoryPositionSummary(),
    fetchOpenReconciliationItems(),
    fetchLatestReconciliationEvent(),
    fetchInventoryLabValuationSummary(),
    fetchYnabCashBalanceSummary(),
    fetchAmazonFinanceBalanceSummary(),
    fetchBusinessValueHistory(),
    fetchInventoryPositionValueRows(),
  ]);

  const unitsByState = new Map<string, number>();
  const costByState = new Map<string, number>();
  const unitsByLocation = new Map<string, number>();
  const unitsByIntent = new Map<string, number>();
  const purchasePreListedStates = [
    "purchased_not_shipped",
    "shipped_not_delivered",
    "delivered_not_received",
    "received_unassigned",
    "received_assigned_amazon_not_sent",
    "transferred_to_ebay",
    "return_pending",
  ];
  const amazonFbaCurrentStates = [
    "amazon_fba_sellable",
    "amazon_fba_inbound_receiving",
    "amazon_fba_reserved",
    "amazon_fba_unsellable_damaged",
    "amazon_fba_stranded",
  ];

  for (const row of summaryRows) {
    const units = Number(row.unit_count ?? 0);
    const cost = Number(row.total_cost ?? 0);

    unitsByState.set(row.inventory_state, (unitsByState.get(row.inventory_state) ?? 0) + units);
    costByState.set(row.inventory_state, (costByState.get(row.inventory_state) ?? 0) + cost);
    unitsByLocation.set(
      row.physical_location,
      (unitsByLocation.get(row.physical_location) ?? 0) + units
    );
    unitsByIntent.set(
      row.marketplace_intent,
      (unitsByIntent.get(row.marketplace_intent) ?? 0) + units
    );
  }

  const reconciliationBySeverity = {
    critical: openItems.filter((item) => item.severity === "critical").length,
    warning: openItems.filter((item) => item.severity === "warning").length,
    info: openItems.filter((item) => item.severity === "info").length,
  };

  return {
    metrics: {
      canonical_inventory_units:
        sumStates(unitsByState, purchasePreListedStates) +
        sumStates(unitsByState, amazonFbaCurrentStates),
      purchase_pre_listed_inventory_units: sumStates(unitsByState, purchasePreListedStates),
      amazon_fba_current_units: sumStates(unitsByState, amazonFbaCurrentStates),
      purchased_inventory_units: sumStates(unitsByState, purchasePreListedStates),
      delivered_not_received_units: unitsByState.get("delivered_not_received") ?? 0,
      received_not_listed_units: sumStates(unitsByState, [
        "received_unassigned",
        "received_assigned_amazon_not_sent",
      ]),
      assigned_to_amazon_not_sent_units:
        unitsByState.get("received_assigned_amazon_not_sent") ?? 0,
      outbound_to_amazon_units: unitsByState.get("outbound_to_amazon") ?? 0,
      amazon_active_sellable_units: unitsByState.get("amazon_fba_sellable") ?? 0,
      amazon_inbound_units: unitsByState.get("amazon_fba_inbound_receiving") ?? 0,
      amazon_reserved_units: unitsByState.get("amazon_fba_reserved") ?? 0,
      amazon_unsellable_units: unitsByState.get("amazon_fba_unsellable_damaged") ?? 0,
      ebay_active_units: sumStates(unitsByState, [
        "home_ebay_resale_listed",
        "home_ebay_personal_listed",
      ]),
      assigned_to_ebay_units: unitsByState.get("transferred_to_ebay") ?? 0,
      return_or_cancel_units: sumStates(unitsByState, [
        "return_pending",
        "return_opened",
        "cancelled_refund_follow_up",
      ]),
      inventory_needing_reconciliation_units: summaryRows
        .filter((row) => row.needs_reconciliation)
        .reduce((total, row) => total + Number(row.unit_count ?? 0), 0),
      open_reconciliation_findings: openItems.length,
      estimated_mbop_cost_basis:
        sumStates(costByState, purchasePreListedStates) +
        (inventoryLabValuation?.total_value ?? sumStates(costByState, amazonFbaCurrentStates)),
    },
    locationValueSummary: buildLocationValueSummary(
      unitsByState,
      costByState,
      inventoryLabValuation
    ),
    businessInventoryValue: buildBusinessInventoryValueSummary(
      costByState,
      inventoryValueRows,
      inventoryLabValuation,
      ynabCashBalance,
      amazonFinanceBalance
    ),
    businessValueHistory,
    unitsByState: Array.from(unitsByState.entries())
      .map(([state, units]) => ({ state, label: inventoryStateLabel(state), units }))
      .sort((left, right) => right.units - left.units),
    unitsByLocation: Array.from(unitsByLocation.entries())
      .map(([location, units]) => ({ location, label: inventoryDimensionLabel(location), units }))
      .sort((left, right) => right.units - left.units),
    unitsByIntent: Array.from(unitsByIntent.entries())
      .map(([intent, units]) => ({ intent, label: inventoryDimensionLabel(intent), units }))
      .sort((left, right) => right.units - left.units),
    reconciliationBySeverity,
    latestReconciliation: latestEvent,
    openFindings: openItems.slice(0, 15).map((item) => ({
      id: item.inventory_reconciliation_event_item_id,
      severity: item.severity,
      issue_type: item.issue_type,
      issue_label: reconciliationIssueLabel(item.issue_type),
      asin: item.asin,
      seller_sku: item.seller_sku,
      title: item.title,
      mbop_quantity: item.mbop_quantity,
      amazon_total_quantity: item.amazon_total_quantity,
      amazon_fulfillable_quantity: item.amazon_fulfillable_quantity,
      amazon_inbound_quantity: item.amazon_inbound_quantity,
      amazon_reserved_quantity: item.amazon_reserved_quantity,
      amazon_unsellable_quantity: item.amazon_unsellable_quantity,
    })),
  };
}

function buildLocationValueSummary(
  unitsByState: Map<string, number>,
  costByState: Map<string, number>,
  _inventoryLabValuation: InventoryLabValuationSummary
): InventoryLocationValueRow[] {
  const rows = [
    {
      location: "At Amazon FBA",
      states: [
        "amazon_fba_sellable",
        "amazon_fba_reserved",
        "amazon_fba_unsellable_damaged",
        "amazon_fba_stranded",
      ],
    },
    {
      location: "On the way to Amazon FBA",
      states: ["outbound_to_amazon", "amazon_fba_inbound_receiving"],
    },
    {
      location: "Received",
      states: ["received_unassigned", "received_assigned_amazon_not_sent"],
    },
    {
      location: "Ordered and not received yet",
      states: ["purchased_not_shipped", "shipped_not_delivered", "delivered_not_received"],
    },
  ].map((row) => {
    const units = sumStates(unitsByState, row.states);
    const totalCost = sumStates(costByState, row.states);

    return {
      location: row.location,
      units,
      total_cost: totalCost,
    };
  });

  rows.push({
    location: "Total",
    units: rows.reduce((total, row) => total + row.units, 0),
    total_cost: rows.reduce((total, row) => total + row.total_cost, 0),
  });

  return rows;
}

function buildBusinessInventoryValueSummary(
  costByState: Map<string, number>,
  inventoryValueRows: InventoryPositionValueRow[],
  _inventoryLabValuation: InventoryLabValuationSummary,
  ynabCashBalance: YnabCashBalanceSummary,
  amazonFinanceBalance: AmazonFinanceBalanceSummary
): BusinessInventoryValueSummary {
  const amazonAtFbaValue = sumStates(costByState, [
    "amazon_fba_sellable",
    "amazon_fba_reserved",
    "amazon_fba_unsellable_damaged",
    "amazon_fba_stranded",
  ]);
  const amazonOutboundValue = calculateAmazonOutboundValue(inventoryValueRows);
  const amazonInventoryValue = amazonAtFbaValue + amazonOutboundValue;
  const preAmazonInventoryValue = sumStates(costByState, [
    "purchased_not_shipped",
    "shipped_not_delivered",
    "delivered_not_received",
    "received_unassigned",
    "received_assigned_amazon_not_sent",
  ]);
  const amazonCashBalance = amazonFinanceBalance?.total_amazon_cash ?? null;
  const amazonCashInTransit = amazonFinanceBalance?.in_transit_to_bank ?? null;
  const cashOnHand = ynabCashBalance?.balance ?? null;
  const totalBusinessValue =
    amazonInventoryValue +
    preAmazonInventoryValue +
    (amazonCashBalance ?? 0) +
    (amazonCashInTransit ?? 0) +
    (cashOnHand ?? 0);

  return {
    amazon_inventory_value: amazonInventoryValue,
    pre_amazon_inventory_value: preAmazonInventoryValue,
    amazon_cash_balance: amazonCashBalance,
    amazon_cash_in_transit: amazonCashInTransit,
    cash_on_hand: cashOnHand,
    total_business_value: totalBusinessValue,
    amazon_cash_source: amazonFinanceBalance
      ? `${amazonFinanceBalance.source}; available/API open ${formatCurrencyNumber(
          amazonFinanceBalance.available_to_withdraw
        )}; deferred ${formatCurrencyNumber(amazonFinanceBalance.deferred_or_reserved_cash)}`
      : "Amazon Finance snapshot missing",
    amazon_cash_in_transit_source: amazonFinanceBalance
      ? "Amazon Finance Processing transfers plus completed payouts not yet matched to YNAB Business deposits"
      : "Amazon Finance snapshot missing",
    cash_on_hand_source: ynabCashBalance?.source ?? "YNAB Business category snapshot missing",
  };
}

function calculateAmazonOutboundValue(rows: InventoryPositionValueRow[]) {
  let outboundCost = 0;
  const outboundAsins = new Set<string>();
  const amazonInboundByAsin = new Map<string, number>();

  for (const row of rows) {
    const state = row.inventory_state || "";
    const asin = (row.asin || "").trim().toUpperCase();
    const cost = Number(row.total_cost ?? 0);

    if (state === "outbound_to_amazon") {
      outboundCost += cost;
      if (asin) outboundAsins.add(asin);
    } else if (state === "amazon_fba_inbound_receiving" && asin) {
      amazonInboundByAsin.set(asin, (amazonInboundByAsin.get(asin) ?? 0) + cost);
    }
  }

  let uncoveredAmazonInboundCost = 0;
  for (const [asin, cost] of amazonInboundByAsin.entries()) {
    if (!outboundAsins.has(asin)) {
      uncoveredAmazonInboundCost += cost;
    }
  }

  return outboundCost + uncoveredAmazonInboundCost;
}

async function fetchInventoryLabValuationSummary(): Promise<InventoryLabValuationSummary> {
  const { data, error } = await supabase
    .from("vw_latest_inventorylab_inventory_valuation")
    .select("source_file,on_hand_quantity,total_value");

  if (error) {
    console.warn("InventoryLab valuation lookup failed", error.message);
    return null;
  }

  const rows = data ?? [];
  const totalValue = rows.reduce((total, row) => total + Number(row.total_value ?? 0), 0);
  const units = rows.reduce((total, row) => total + Number(row.on_hand_quantity ?? 0), 0);
  const source = rows[0]?.source_file ?? "latest InventoryLab valuation";

  if (!rows.length || totalValue <= 0) {
    return null;
  }

  return {
    units,
    total_value: totalValue,
    source,
  };
}

async function fetchYnabCashBalanceSummary(): Promise<YnabCashBalanceSummary> {
  const { data, error } = await supabase
    .from("vw_latest_ynab_category_balance_snapshot")
    .select("plan_name,category_group_name,category_name,balance_currency,balance_formatted")
    .ilike("category_name", "Business")
    .limit(1);

  if (error) {
    console.warn("YNAB cash balance lookup failed", error.message);
    return null;
  }

  const row = ((data ?? [])[0] ?? null) as unknown as
    | {
        plan_name: string | null;
        category_group_name: string | null;
        category_name: string | null;
        balance_currency: unknown;
        balance_formatted: string | null;
      }
    | null;
  if (!row) {
    return null;
  }

  const balance = Number(row.balance_currency ?? 0);
  if (!Number.isFinite(balance)) {
    return null;
  }

  return {
    balance,
    source: `YNAB ${row.plan_name ?? "plan"} / ${row.category_group_name ?? "category group"} / ${
      row.category_name ?? "category"
    }${row.balance_formatted ? ` (${row.balance_formatted})` : ""}`,
  };
}

async function fetchAmazonFinanceBalanceSummary(): Promise<AmazonFinanceBalanceSummary> {
  const { data, error } = await supabase
    .from("vw_latest_amazon_finance_balance_snapshot")
    .select(
      "currency,total_amazon_cash,available_to_withdraw,in_transit_to_bank," +
        "deferred_or_reserved_cash,captured_at"
    )
    .limit(1);

  if (error) {
    console.warn("Amazon finance balance lookup failed", error.message);
    return null;
  }

  const row = ((data ?? [])[0] ?? null) as unknown as
    | {
        total_amazon_cash: unknown;
        available_to_withdraw: unknown;
        in_transit_to_bank: unknown;
        deferred_or_reserved_cash: unknown;
        captured_at: string | null;
      }
    | null;
  if (!row) {
    return null;
  }

  return {
    total_amazon_cash: nullableNumber(row.total_amazon_cash),
    available_to_withdraw: nullableNumber(row.available_to_withdraw),
    in_transit_to_bank: nullableNumber(row.in_transit_to_bank),
    deferred_or_reserved_cash: nullableNumber(row.deferred_or_reserved_cash),
    source: `Amazon Finance snapshot ${row.captured_at ?? ""}`.trim(),
  };
}

async function fetchBusinessValueHistory(): Promise<BusinessValueHistoryRow[]> {
  const { data, error } = await supabase
    .from("business_value_snapshots")
    .select(
      "snapshot_date,total_business_value,amazon_inventory_value,pre_amazon_inventory_value," +
        "amazon_cash_balance,amazon_cash_in_transit,cash_on_hand"
    )
    .gte("snapshot_date", BUSINESS_VALUE_HISTORY_START_DATE)
    .order("snapshot_date", { ascending: true })
    .limit(365);

  if (error) {
    console.warn("Business value history lookup failed", error.message);
    return [];
  }

  const rows = (data ?? []) as unknown as Array<{
    snapshot_date: string;
    total_business_value: unknown;
    amazon_inventory_value: unknown;
    pre_amazon_inventory_value: unknown;
    amazon_cash_balance: unknown;
    amazon_cash_in_transit: unknown;
    cash_on_hand: unknown;
  }>;

  return rows.map((row) => ({
    snapshot_date: row.snapshot_date,
    total_business_value: Number(row.total_business_value ?? 0),
    amazon_inventory_value: Number(row.amazon_inventory_value ?? 0),
    pre_amazon_inventory_value: Number(row.pre_amazon_inventory_value ?? 0),
    amazon_cash_balance: Number(row.amazon_cash_balance ?? 0),
    amazon_cash_in_transit: Number(row.amazon_cash_in_transit ?? 0),
    cash_on_hand: Number(row.cash_on_hand ?? 0),
  }));
}

function nullableNumber(value: unknown) {
  if (value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatCurrencyNumber(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "--";
  return `$${value.toFixed(2)}`;
}

async function fetchInventoryPositionSummary() {
  const { data, error } = await supabase
    .from("vw_inventory_position_summary")
    .select("*");

  if (error) {
    console.warn("Inventory position summary lookup failed", error.message);
    return [] as InventoryPositionSummaryRow[];
  }

  return (data ?? []) as InventoryPositionSummaryRow[];
}

async function fetchInventoryPositionValueRows() {
  const rows: InventoryPositionValueRow[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("inventory_positions")
      .select("inventory_state,asin,total_cost")
      .range(offset, offset + pageSize - 1);

    if (error) {
      console.warn("Inventory position value lookup failed", error.message);
      return [] as InventoryPositionValueRow[];
    }

    rows.push(...((data ?? []) as InventoryPositionValueRow[]));
    if ((data ?? []).length < pageSize) return rows;
    offset += pageSize;
  }
}

async function fetchOpenReconciliationItems() {
  const { data, error } = await supabase
    .from("vw_open_inventory_reconciliation_items")
    .select(
      "inventory_reconciliation_event_item_id,severity,issue_type,asin,seller_sku,title," +
        "mbop_quantity,amazon_total_quantity,amazon_fulfillable_quantity," +
        "amazon_inbound_quantity,amazon_reserved_quantity,amazon_unsellable_quantity"
    )
    .order("severity", { ascending: true })
    .limit(50);

  if (error) {
    console.warn("Open inventory reconciliation lookup failed", error.message);
    return [] as OpenReconciliationItemRow[];
  }

  return (data ?? []) as unknown as OpenReconciliationItemRow[];
}

async function fetchLatestReconciliationEvent() {
  const { data, error } = await supabase
    .from("inventory_reconciliation_events")
    .select(
      "inventory_reconciliation_event_id,reconciliation_type,status,started_at,completed_at," +
        "matched_count,mismatch_count,missing_internal_count,missing_external_count,needs_review_count"
    )
    .order("started_at", { ascending: false })
    .limit(1);

  if (error) {
    console.warn("Latest inventory reconciliation lookup failed", error.message);
    return null;
  }

  return ((data ?? [])[0] ?? null) as unknown as ReconciliationEventRow | null;
}

function sumStates(values: Map<string, number>, states: string[]) {
  return states.reduce((total, state) => total + (values.get(state) ?? 0), 0);
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

function inventoryStateLabel(state: string) {
  const labels: Record<string, string> = {
    purchased_not_shipped: "Purchased, Not Shipped",
    shipped_not_delivered: "Shipped, Not Delivered",
    delivered_not_received: "Delivered, Not Received",
    received_unassigned: "Received, Unassigned",
    received_assigned_amazon_not_sent: "Ready For Amazon",
    home_amazon_mfn_listed: "Home, Amazon MFN Listed",
    outbound_to_amazon: "Outbound To Amazon",
    amazon_fba_inbound_receiving: "Amazon FBA Inbound",
    amazon_fba_sellable: "Amazon FBA Sellable",
    amazon_fba_reserved: "Amazon FBA Reserved",
    amazon_fba_unsellable_damaged: "Amazon FBA Unsellable",
    amazon_fba_stranded: "Amazon FBA Stranded",
    removed_from_amazon_home: "Removed From Amazon",
    transferred_to_ebay: "Assigned To eBay",
    home_ebay_resale_listed: "eBay Resale Listed",
    home_ebay_personal_listed: "eBay Personal Listed",
    sold_amazon: "Sold On Amazon",
    sold_ebay: "Sold On eBay",
    return_pending: "Return Pending",
    return_opened: "Return Opened",
    cancelled_refund_follow_up: "Cancelled / Refund Follow-Up",
    disposed_donated_lost: "Disposed / Donated / Lost",
  };

  return labels[state] ?? inventoryDimensionLabel(state);
}

function reconciliationIssueLabel(issueType: string) {
  const labels: Record<string, string> = {
    quantity_mismatch: "Quantity Mismatch",
    mbop_missing_from_amazon: "MBOP Missing From Amazon",
    amazon_unknown_to_mbop: "Amazon Unknown To MBOP",
    amazon_inbound_discrepancy: "Amazon Inbound Discrepancy",
    amazon_unsellable: "Amazon Unsellable",
    amazon_reserved: "Amazon Reserved",
    amazon_stranded_or_suppressed: "Amazon Stranded Or Suppressed",
    amazon_removed_needs_home_state: "Amazon Removed, Needs Home State",
    ebay_unknown_to_mbop: "eBay Unknown To MBOP",
    ebay_transfer_missing: "eBay Transfer Missing",
    marketplace_intent_mismatch: "Marketplace Intent Mismatch",
    listing_channel_mismatch: "Listing Channel Mismatch",
    condition_disposition_mismatch: "Condition / Disposition Mismatch",
    sku_mapping_missing: "SKU Mapping Missing",
    asin_mapping_missing: "ASIN Mapping Missing",
    cost_basis_missing: "Cost Basis Missing",
    needs_operator_review: "Needs Operator Review",
  };

  return labels[issueType] ?? inventoryDimensionLabel(issueType);
}

function inventoryDimensionLabel(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
