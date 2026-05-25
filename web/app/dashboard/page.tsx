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

      <section className="mb-4 grid gap-3 md:grid-cols-3">
        <MetricCard
          label="Total Units"
          value={loading ? "--" : formatNumber(data?.totals.units)}
        />
        <MetricCard
          label="Total Cost"
          value={loading ? "--" : formatMoney(data?.totals.cost)}
        />
        <MetricCard
          label="Months"
          value={loading ? "--" : formatNumber(data?.months.length)}
        />
      </section>

      <section className="mb-4 grid gap-3 lg:grid-cols-4">
        <OperationalPanel
          title="Purchase Completeness"
          rows={[
            ["Active units", formatNumber(data?.operations.purchaseCompleteness.active_units)],
            ["Needs review units", formatNumber(data?.operations.purchaseCompleteness.needs_review_units)],
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
        <OperationalPanel
          title="Inventory State"
          rows={[
            ["Purchased not received", formatNumber(data?.operations.inventoryState.purchased_not_received_units)],
            ["Received", formatNumber(data?.operations.inventoryState.received_units)],
            ["Listed", formatNumber(data?.operations.inventoryState.listed_units)],
            ["Return/cancel", formatNumber(data?.operations.inventoryState.return_or_cancel_units)],
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
            <h2 className="mt-1 text-lg font-semibold">Attention Counts</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <InlineMetric
              label="Past ETA"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.overdue_units)}
            />
            <InlineMetric
              label="Tracking Stale"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.aged_no_tracking_units)}
            />
            <InlineMetric
              label="Exceptions"
              value={loading ? "--" : formatNumber(data?.operations.exceptions.exception_units)}
            />
          </div>
        </div>
      </section>

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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

      <section className="mb-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
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
    </main>
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

function InlineMetric({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold">{value || "--"}</div>
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
