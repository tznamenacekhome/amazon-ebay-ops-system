"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, RefreshCw } from "lucide-react";

type MonthAggregate = {
  year: number;
  month: number;
  monthLabel: string;
  units: number;
  cost: number;
};

type YearAggregate = {
  year: number;
  units: number;
  cost: number;
  months: MonthAggregate[];
};

type StatusAggregate = {
  status: string;
  label: string;
  units: number;
};

type DashboardData = {
  totals: {
    units: number;
    cost: number;
  };
  years: YearAggregate[];
  months: MonthAggregate[];
  statusBreakdown: StatusAggregate[];
  inventoryVisibility: InventoryVisibility;
  operations: {
    purchaseCompleteness: {
      active_rows: number;
      active_units: number;
      needs_review_rows: number;
      needs_review_units: number;
      missing_asin_rows: number;
      missing_sell_price_rows: number;
      missing_system_rows: number;
      missing_amazon_title_rows: number;
    };
    receivingBacklog: BacklogSummary;
    shipmentPrepBacklog: BacklogSummary & {
      total_cost: number;
      blocked_rows: number;
      blocked_units: number;
    };
    inventoryState: {
      purchased_not_received_units: number;
      received_units: number;
      listed_units: number;
      return_or_cancel_units: number;
    };
    exceptions: {
      overdue_rows: number;
      overdue_units: number;
      aged_no_tracking_rows: number;
      aged_no_tracking_units: number;
      exception_rows: number;
      exception_units: number;
      top_attention: AttentionRow[];
    };
  };
};

type InventoryVisibility = {
  metrics: {
    canonical_inventory_units: number;
    purchase_pre_listed_inventory_units: number;
    amazon_fba_current_units: number;
    purchased_inventory_units: number;
    delivered_not_received_units: number;
    received_not_listed_units: number;
    assigned_to_amazon_not_sent_units: number;
    outbound_to_amazon_units: number;
    amazon_active_sellable_units: number;
    amazon_inbound_units: number;
    amazon_reserved_units: number;
    amazon_unsellable_units: number;
    ebay_active_units: number;
    assigned_to_ebay_units: number;
    return_or_cancel_units: number;
    inventory_needing_reconciliation_units: number;
    open_reconciliation_findings: number;
    estimated_mbop_cost_basis: number;
  };
  locationValueSummary: Array<{
    location: string;
    units: number;
    total_cost: number;
  }>;
  businessInventoryValue: {
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
  businessValueHistory: Array<{
    snapshot_date: string;
    total_business_value: number;
    amazon_inventory_value: number;
    pre_amazon_inventory_value: number;
    amazon_cash_balance: number;
    amazon_cash_in_transit: number;
    cash_on_hand: number;
  }>;
  unitsByState: Array<{ state: string; label: string; units: number }>;
  unitsByLocation: Array<{ location: string; label: string; units: number }>;
  unitsByIntent: Array<{ intent: string; label: string; units: number }>;
  reconciliationBySeverity: {
    critical: number;
    warning: number;
    info: number;
  };
  latestReconciliation: {
    reconciliation_type: string;
    status: string;
    started_at: string;
    completed_at: string | null;
    matched_count: number | null;
    mismatch_count: number | null;
    missing_internal_count: number | null;
    missing_external_count: number | null;
    needs_review_count: number | null;
  } | null;
  openFindings: InventoryFinding[];
};

type InventoryFinding = {
  id: string;
  severity: "info" | "warning" | "critical";
  issue_type: string;
  issue_label: string;
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

type BacklogSummary = {
  rows: number;
  units: number;
  oldest_age_days: number | null;
  aging: AgingBucket[];
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

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showBusinessValueHistory, setShowBusinessValueHistory] = useState(false);

  useEffect(() => {
    loadDashboard();
  }, []);

  const maxMonthlyCost = useMemo(() => {
    return Math.max(...(data?.months ?? []).map((month) => month.cost), 1);
  }, [data]);

  async function loadDashboard() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/dashboard/purchases", {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Failed to load dashboard: ${response.status}`);
      }

      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-slate-600">
            MBOP purchase completeness and cost overview
          </p>
        </div>

        <button
          onClick={loadDashboard}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
          type="button"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3">
          <div>
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Inventory Visibility
            </div>
            <h2 className="mt-1 text-lg font-semibold">
              Inventory Value And Location
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Current business inventory value by where the units physically are or where cash is held.
            </p>
          </div>
        </div>

        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <InlineMetric
            label="Canonical Units"
            value={loading ? "--" : formatNumber(data?.inventoryVisibility.metrics.canonical_inventory_units)}
            detail="Amazon FBA inventory plus MBOP purchase inventory before Listed."
          />
          <InlineMetric
            label="Amazon FBA Sellable"
            value={loading ? "--" : formatNumber(data?.inventoryVisibility.metrics.amazon_active_sellable_units)}
            detail="Units Amazon reports as fulfillable/sellable in the latest FBA inventory snapshot."
          />
          <InlineMetric
            label="MBOP Cost Basis"
            value={loading ? "--" : formatMoney(data?.inventoryVisibility.metrics.estimated_mbop_cost_basis)}
            detail="Backend rollup using InventoryLab opening value plus MBOP costs."
          />
        </div>

        <div className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(420px,0.9fr)]">
          <LocationValueTable
            rows={data?.inventoryVisibility.locationValueSummary ?? []}
            loading={loading}
          />
          <BusinessInventoryValuePanel
            value={data?.inventoryVisibility.businessInventoryValue}
            history={data?.inventoryVisibility.businessValueHistory ?? []}
            loading={loading}
            onOpenHistory={() => setShowBusinessValueHistory(true)}
          />
        </div>

        <div className="hidden">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
            <InventoryMiniTable
              title="State Counts"
              rows={(data?.inventoryVisibility.unitsByState ?? []).slice(0, 10)}
              loading={loading}
            />
            <OperationalPanel
              title="Channel / Exception Counts"
              rows={[
                ["Purchase pre-Listed", formatNumber(data?.inventoryVisibility.metrics.purchase_pre_listed_inventory_units)],
                ["Amazon FBA current", formatNumber(data?.inventoryVisibility.metrics.amazon_fba_current_units)],
                ["Delivered not received", formatNumber(data?.inventoryVisibility.metrics.delivered_not_received_units)],
                ["Received not listed", formatNumber(data?.inventoryVisibility.metrics.received_not_listed_units)],
                ["Outbound to Amazon", formatNumber(data?.inventoryVisibility.metrics.outbound_to_amazon_units)],
                ["Amazon inbound", formatNumber(data?.inventoryVisibility.metrics.amazon_inbound_units)],
                ["Amazon reserved", formatNumber(data?.inventoryVisibility.metrics.amazon_reserved_units)],
                ["Amazon unsellable", formatNumber(data?.inventoryVisibility.metrics.amazon_unsellable_units)],
                ["Assigned to eBay", formatNumber(data?.inventoryVisibility.metrics.assigned_to_ebay_units)],
                ["eBay active", formatNumber(data?.inventoryVisibility.metrics.ebay_active_units)],
                ["Return/cancel", formatNumber(data?.inventoryVisibility.metrics.return_or_cancel_units)],
              ]}
              loading={loading}
            />
          </div>

          <div className="overflow-hidden rounded-md border border-slate-200">
            <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
              <div className="text-sm font-semibold">Open Reconciliation Findings</div>
              <div className="text-xs text-slate-500">
                Critical {formatNumber(data?.inventoryVisibility.reconciliationBySeverity.critical)} · Warning{" "}
                {formatNumber(data?.inventoryVisibility.reconciliationBySeverity.warning)} · Info{" "}
                {formatNumber(data?.inventoryVisibility.reconciliationBySeverity.info)}
              </div>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Issue</th>
                  <th className="px-3 py-2">ASIN / SKU</th>
                  <th className="px-3 py-2">Title</th>
                  <th className="px-3 py-2 text-right">MBOP</th>
                  <th className="px-3 py-2 text-right">Amazon</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                      Loading inventory findings...
                    </td>
                  </tr>
                ) : data?.inventoryVisibility.openFindings.length ? (
                  data.inventoryVisibility.openFindings.map((finding) => (
                    <tr key={finding.id} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <div className="font-medium">{finding.issue_label}</div>
                        <div className="text-xs uppercase text-slate-500">{finding.severity}</div>
                      </td>
                      <td className="px-3 py-2">
                        <div>{finding.asin || "--"}</div>
                        <div className="text-xs text-slate-500">{finding.seller_sku || "--"}</div>
                      </td>
                      <td className="max-w-[420px] truncate px-3 py-2">{finding.title || "--"}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(finding.mbop_quantity)}</td>
                      <td className="px-3 py-2 text-right">{formatNumber(finding.amazon_total_quantity)}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                      No open reconciliation findings.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="mb-4 grid gap-3 lg:grid-cols-3">
        <OperationalPanel
          title="Purchase Completeness"
          rows={[
            ["Active units", formatNumber(data?.operations.purchaseCompleteness.active_units)],
            ["Missing data units", formatNumber(data?.operations.purchaseCompleteness.needs_review_units)],
            ["Missing ASIN rows", formatNumber(data?.operations.purchaseCompleteness.missing_asin_rows)],
            ["Missing sell price rows", formatNumber(data?.operations.purchaseCompleteness.missing_sell_price_rows)],
            ["Missing system rows", formatNumber(data?.operations.purchaseCompleteness.missing_system_rows)],
            ["Missing Amazon title rows", formatNumber(data?.operations.purchaseCompleteness.missing_amazon_title_rows)],
          ]}
          loading={loading}
        />
        <OperationalPanel
          title="Receiving Backlog"
          rows={[
            ["Rows", formatNumber(data?.operations.receivingBacklog.rows)],
            ["Units", formatNumber(data?.operations.receivingBacklog.units)],
            ["Oldest age", formatDays(data?.operations.receivingBacklog.oldest_age_days)],
          ]}
          loading={loading}
        />
        <OperationalPanel
          title="Shipment Prep Backlog"
          rows={[
            ["Rows", formatNumber(data?.operations.shipmentPrepBacklog.rows)],
            ["Units", formatNumber(data?.operations.shipmentPrepBacklog.units)],
            ["Total cost", formatMoney(data?.operations.shipmentPrepBacklog.total_cost)],
            ["Blocked rows", formatNumber(data?.operations.shipmentPrepBacklog.blocked_rows)],
            ["Oldest age", formatDays(data?.operations.shipmentPrepBacklog.oldest_age_days)],
          ]}
          loading={loading}
        />
      </section>

      <section className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3">
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Workflow Aging
            </div>
            <h2 className="mt-1 text-lg font-semibold">Backlog Buckets</h2>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <AgingTable
              title="Receiving"
              buckets={data?.operations.receivingBacklog.aging ?? []}
              loading={loading}
            />
            <AgingTable
              title="FBA Prep"
              buckets={data?.operations.shipmentPrepBacklog.aging ?? []}
              loading={loading}
            />
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3">
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Missing / Exception Visibility
            </div>
            <h2 className="mt-1 text-lg font-semibold">Order Problem Counts</h2>
            <p className="mt-1 text-sm text-slate-600">
              Past ETA means supplier delivery is late, tracking stale means no usable carrier progress after a week,
              and exceptions are carrier or return statuses that need operator follow-up.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <InlineMetric
              label="Past ETA"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.overdue_units)}
            />
            <InlineMetric
              label="Tracking stale/no tracking"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.aged_no_tracking_units)}
            />
            <InlineMetric
              label="Exceptions"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.exception_units)}
            />
          </div>
        </div>
      </section>

      <section className="hidden">
        <div className="mb-3">
          <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
            Item Status
          </div>
          <h2 className="mt-1 text-lg font-semibold">Operational Units</h2>
        </div>

        {loading ? (
          <div className="py-6 text-center text-sm text-slate-500">
            Loading status counts...
          </div>
        ) : data?.statusBreakdown.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            {data.statusBreakdown.map((status) => (
              <div
                key={status.status}
                className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
              >
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  {status.label}
                </div>
                <div className="mt-1 text-xl font-semibold">
                  {formatNumber(status.units)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-6 text-center text-sm text-slate-500">
            No status data found.
          </div>
        )}
      </section>

      <section className="hidden">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
            Operational Attention
          </div>
          <h2 className="mt-1 text-lg font-semibold">Oldest Missing Or Exception Rows</h2>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Issue</th>
              <th className="px-3 py-2">Order</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Age</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                  Loading attention rows...
                </td>
              </tr>
            ) : data?.operations.exceptions.top_attention.length ? (
              data.operations.exceptions.top_attention.map((row, index) => (
                <tr
                  key={`${row.item_id ?? row.order_id ?? "attention"}-${index}`}
                  className="border-t border-slate-100"
                >
                  <td className="px-3 py-2 font-medium">{row.issue}</td>
                  <td className="px-3 py-2 text-blue-700">{row.order_id || "--"}</td>
                  <td className="max-w-[520px] truncate px-3 py-2">{row.title}</td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2 text-right">{formatDays(row.age_days)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                  No attention rows found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(460px,0.9fr)]">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                <BarChart3 className="h-4 w-4" />
                Monthly Purchase Cost
              </div>
              <h2 className="mt-1 text-lg font-semibold">
                Returns Opened Excluded
              </h2>
            </div>
          </div>

          {loading ? (
            <div className="py-12 text-center text-sm text-slate-500">
              Loading dashboard...
            </div>
          ) : data?.months.length ? (
            <div className="space-y-3">
              {data.months.map((month) => (
                <div
                  key={`${month.year}-${month.month}`}
                  className="grid grid-cols-[86px_minmax(0,1fr)_110px] items-center gap-3"
                >
                  <div className="text-sm font-medium text-slate-700">
                    {month.monthLabel} {String(month.year).slice(2)}
                  </div>
                  <div className="h-8 overflow-hidden rounded-md bg-slate-100">
                    <div
                      className="flex h-full items-center justify-end rounded-md bg-blue-600 px-2 text-xs font-medium text-white"
                      style={{
                        width: `${Math.max((month.cost / maxMonthlyCost) * 100, 4)}%`,
                      }}
                    >
                      {formatNumber(month.units)}
                    </div>
                  </div>
                  <div className="text-right text-sm font-semibold">
                    {formatMoney(month.cost)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-12 text-center text-sm text-slate-500">
              No purchase data found.
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
              Pivot View
            </div>
            <h2 className="mt-1 text-lg font-semibold">Units And Cost</h2>
          </div>

          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2 text-right">Units</th>
                <th className="px-3 py-2 text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-6 text-center text-slate-500" colSpan={3}>
                    Loading...
                  </td>
                </tr>
              ) : (
                <>
                  {(data?.years ?? []).map((year) => (
                    <YearRows key={year.year} year={year} />
                  ))}
                  <tr className="border-t border-slate-300 bg-slate-100 font-semibold">
                    <td className="px-3 py-2">Grand Total</td>
                    <td className="px-3 py-2 text-right">
                      {formatNumber(data?.totals.units)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {formatMoney(data?.totals.cost)}
                    </td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {showBusinessValueHistory && (
        <BusinessValueHistoryModal
          rows={data?.inventoryVisibility.businessValueHistory ?? []}
          onClose={() => setShowBusinessValueHistory(false)}
        />
      )}
    </main>
  );
}

function LocationValueTable({
  rows,
  loading,
}: {
  rows: Array<{ location: string; units: number; total_cost: number }>;
  loading: boolean;
}) {
  return (
    <div className="overflow-hidden rounded-md border border-slate-200">
      <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="text-sm font-semibold">Inventory Value By Location</div>
        <div className="text-xs text-slate-500">Units and cost basis by operational location</div>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2 text-left">Location</th>
            <th className="px-3 py-2 text-right">Units</th>
            <th className="px-3 py-2 text-right">Total Cost</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className="px-3 py-6 text-center text-slate-500" colSpan={3}>
                Loading location values...
              </td>
            </tr>
          ) : rows.length ? (
            rows.map((row) => (
              <tr
                key={row.location}
                className={`border-t border-slate-100 ${
                  row.location === "Total" ? "bg-slate-100 font-semibold" : ""
                }`}
              >
                <td className="px-3 py-2">{row.location}</td>
                <td className="px-3 py-2 text-right">{formatNumber(row.units)}</td>
                <td className="px-3 py-2 text-right">{formatMoney(row.total_cost)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="px-3 py-6 text-center text-slate-500" colSpan={3}>
                No location value data found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function BusinessInventoryValuePanel({
  value,
  history,
  loading,
  onOpenHistory,
}: {
  value?: InventoryVisibility["businessInventoryValue"];
  history: InventoryVisibility["businessValueHistory"];
  loading: boolean;
  onOpenHistory: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 text-sm font-semibold">Business Inventory And Cash Value</h3>
      <div className="space-y-2">
        <ValueRow
          label="Inventory at or on way to Amazon"
          value={formatMoney(value?.amazon_inventory_value)}
          loading={loading}
        />
        <ValueRow
          label="Purchased, not shipped to Amazon"
          value={formatMoney(value?.pre_amazon_inventory_value)}
          loading={loading}
        />
        <ValueRow
          label="Cash balance at Amazon"
          value={formatMoney(value?.amazon_cash_balance)}
          detail={value?.amazon_cash_source}
          loading={loading}
        />
        <ValueRow
          label="Cash in transit from Amazon"
          value={formatMoney(value?.amazon_cash_in_transit)}
          detail={value?.amazon_cash_in_transit_source}
          loading={loading}
        />
        <ValueRow
          label="Cash on hand"
          value={formatMoney(value?.cash_on_hand)}
          detail={value?.cash_on_hand_source}
          loading={loading}
        />
        <ValueRow
          label="Total"
          value={formatMoney(value?.total_business_value)}
          loading={loading}
          emphasis
          onClick={history.length ? onOpenHistory : undefined}
        />
      </div>
    </div>
  );
}

function ValueRow({
  label,
  value,
  detail,
  loading,
  emphasis = false,
  onClick,
}: {
  label: string;
  value: string;
  detail?: string;
  loading: boolean;
  emphasis?: boolean;
  onClick?: () => void;
}) {
  const content = (
    <>
      <div>
        <div className={`text-sm ${emphasis ? "font-semibold text-slate-900" : "text-slate-600"}`}>
          {label}
        </div>
        {detail ? <div className="text-xs text-slate-500">{detail}</div> : null}
      </div>
      <div className={`text-right text-sm font-semibold ${emphasis ? "text-slate-950" : ""}`}>
        {loading ? "--" : value}
      </div>
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`flex w-full items-start justify-between gap-3 border-t pt-2 text-left hover:bg-slate-50 first:border-t-0 first:pt-0 ${
          emphasis ? "border-slate-300 cursor-pointer" : "border-slate-100"
        }`}
      >
        {content}
      </button>
    );
  }

  return (
    <div
      className={`flex items-start justify-between gap-3 border-t pt-2 first:border-t-0 first:pt-0 ${
        emphasis ? "border-slate-300" : "border-slate-100"
      }`}
    >
      {content}
    </div>
  );
}

function BusinessValueHistoryModal({
  rows,
  onClose,
}: {
  rows: InventoryVisibility["businessValueHistory"];
  onClose: () => void;
}) {
  const latest = rows[rows.length - 1];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4">
      <div className="w-full max-w-2xl rounded-lg border border-slate-200 bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-3">
          <div>
            <h3 className="text-base font-semibold">Business Value History</h3>
            <p className="text-xs text-slate-500">
              Daily total business value snapshots
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"
          >
            Close
          </button>
        </div>
        <div className="p-4">
          <BusinessValueLineChart rows={rows} />
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div className="rounded-md bg-slate-50 p-2">
              <div className="text-xs uppercase tracking-wide text-slate-500">Latest</div>
              <div className="font-semibold">{formatMoney(latest?.total_business_value)}</div>
            </div>
            <div className="rounded-md bg-slate-50 p-2">
              <div className="text-xs uppercase tracking-wide text-slate-500">Snapshots</div>
              <div className="font-semibold">{formatNumber(rows.length)}</div>
            </div>
          </div>
          <div className="mt-3 max-h-48 overflow-auto rounded-md border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2 text-left">Date</th>
                  <th className="px-3 py-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {rows
                  .slice()
                  .reverse()
                  .map((row) => (
                    <tr key={row.snapshot_date} className="border-t border-slate-100">
                      <td className="px-3 py-2">{row.snapshot_date}</td>
                      <td className="px-3 py-2 text-right font-medium">
                        {formatMoney(row.total_business_value)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function BusinessValueLineChart({
  rows,
}: {
  rows: InventoryVisibility["businessValueHistory"];
}) {
  const width = 620;
  const height = 220;
  const padding = 28;
  const values = rows.map((row) => row.total_business_value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const range = Math.max(max - min, 1);
  const points = rows.map((row, index) => {
    const x =
      rows.length === 1
        ? width / 2
        : padding + (index * (width - padding * 2)) / (rows.length - 1);
    const y = height - padding - ((row.total_business_value - min) / range) * (height - padding * 2);
    return { x, y };
  });
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  if (!rows.length) {
    return (
      <div className="flex h-56 items-center justify-center rounded-md border border-slate-200 text-sm text-slate-500">
        No business value snapshots found.
      </div>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Business value over time"
      className="h-56 w-full rounded-md border border-slate-200 bg-white"
    >
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#cbd5e1" />
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#cbd5e1" />
      <text x={padding} y={18} className="fill-slate-500 text-[11px]">
        {formatMoney(max)}
      </text>
      <text x={padding} y={height - 8} className="fill-slate-500 text-[11px]">
        {formatMoney(min)}
      </text>
      <path d={path} fill="none" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((point, index) => (
        <circle key={`${rows[index].snapshot_date}-${index}`} cx={point.x} cy={point.y} r="4" fill="#0f172a" />
      ))}
    </svg>
  );
}

function YearRows({ year }: { year: YearAggregate }) {
  return (
    <>
      <tr className="border-t border-slate-200 bg-slate-50 font-semibold">
        <td className="px-3 py-2">{year.year}</td>
        <td className="px-3 py-2 text-right">{formatNumber(year.units)}</td>
        <td className="px-3 py-2 text-right">{formatMoney(year.cost)}</td>
      </tr>
      {year.months.map((month) => (
        <tr key={`${month.year}-${month.month}`} className="border-t border-slate-100">
          <td className="px-3 py-2 pl-8">{month.monthLabel}</td>
          <td className="px-3 py-2 text-right">{formatNumber(month.units)}</td>
          <td className="px-3 py-2 text-right">{formatMoney(month.cost)}</td>
        </tr>
      ))}
    </>
  );
}

function MetricCard({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value || "--"}</div>
    </div>
  );
}

function InlineMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value?: string;
  detail?: string;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold">{value || "--"}</div>
      {detail ? <div className="mt-1 text-xs text-slate-500">{detail}</div> : null}
    </div>
  );
}

function OperationalPanel({
  title,
  rows,
  loading,
}: {
  title: string;
  rows: Array<[string, string]>;
  loading: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <div className="space-y-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-3">
            <span className="text-sm text-slate-600">{label}</span>
            <span className="text-sm font-semibold">{loading ? "--" : value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgingTable({
  title,
  buckets,
  loading,
}: {
  title: string;
  buckets: AgingBucket[];
  loading: boolean;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-1 text-left">Age</th>
            <th className="py-1 text-right">Rows</th>
            <th className="py-1 text-right">Units</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className="py-3 text-center text-slate-500" colSpan={3}>
                Loading...
              </td>
            </tr>
          ) : (
            buckets.map((bucket) => (
              <tr key={bucket.label} className="border-t border-slate-100">
                <td className="py-1">{bucket.label}</td>
                <td className="py-1 text-right">{formatNumber(bucket.count)}</td>
                <td className="py-1 text-right">{formatNumber(bucket.units)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function InventoryMiniTable({
  title,
  rows,
  loading,
}: {
  title: string;
  rows: Array<{ label: string; units: number }>;
  loading: boolean;
}) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-1 text-left">State</th>
            <th className="py-1 text-right">Units</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className="py-3 text-center text-slate-500" colSpan={2}>
                Loading...
              </td>
            </tr>
          ) : rows.length ? (
            rows.map((row) => (
              <tr key={row.label} className="border-t border-slate-100">
                <td className="py-1">{row.label}</td>
                <td className="py-1 text-right">{formatNumber(row.units)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="py-3 text-center text-slate-500" colSpan={2}>
                No inventory positions found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toLocaleString("en-US");
}

function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function formatDays(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return `${formatNumber(value)}d`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
