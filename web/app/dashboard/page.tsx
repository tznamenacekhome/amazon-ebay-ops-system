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
