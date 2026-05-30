"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, HelpCircle, RefreshCw, XCircle } from "lucide-react";

type HealthStatus = "ok" | "delayed" | "failed" | "unknown";

type HealthJob = {
  id: string;
  name: string;
  command: string;
  status: HealthStatus;
  lastRunAt: string | null;
  hoursSinceLastRun: number | null;
  expectedEveryHours: number;
  criticalAfterHours: number;
  source: string;
  stats: Array<{ label: string; value: string }>;
  message: string | null;
};

type HealthData = {
  generatedAt: string;
  summary: {
    total: number;
    ok: number;
    delayed: number;
    failed: number;
    unknown: number;
  };
  jobs: HealthJob[];
};

const STATUS_RANK: Record<HealthStatus, number> = {
  failed: 0,
  delayed: 1,
  unknown: 2,
  ok: 3,
};

export default function SystemHealthPage() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHealth();
  }, []);

  const jobs = useMemo(() => {
    return [...(data?.jobs ?? [])].sort((a, b) => {
      const statusSort = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (statusSort !== 0) return statusSort;
      return (b.hoursSinceLastRun ?? -1) - (a.hoursSinceLastRun ?? -1);
    });
  }, [data]);

  async function loadHealth() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/system-health", { cache: "no-store" });
      if (!response.ok) throw new Error(`Failed to load system health: ${response.status}`);
      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system health.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System Health</h1>
          <p className="mt-1 text-sm text-slate-600">
            Scheduled sync visibility with Pacific-time run history and operational result signals.
          </p>
        </div>

        <button
          onClick={loadHealth}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
          type="button"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <Summary label="Jobs" value={formatNumber(data?.summary.total)} tone="neutral" />
        <Summary label="Healthy" value={formatNumber(data?.summary.ok)} tone="ok" />
        <Summary label="Delayed" value={formatNumber(data?.summary.delayed)} tone="delayed" />
        <Summary label="Failed" value={formatNumber(data?.summary.failed)} tone="failed" />
        <Summary label="Unknown" value={formatNumber(data?.summary.unknown)} tone="unknown" />
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <div>
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">Sync Jobs</div>
            <h2 className="mt-1 text-lg font-semibold">Scheduler Health</h2>
          </div>
          <div className="text-xs text-slate-500">
            Refreshed {data?.generatedAt ? formatPacificDateTime(data.generatedAt) : "--"}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Sync Job</th>
                <th className="px-3 py-2">Last Run Pacific</th>
                <th className="px-3 py-2 text-right">Age</th>
                <th className="px-3 py-2">Expected</th>
                <th className="px-3 py-2">Result Stats</th>
                <th className="px-3 py-2">Signal</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={7}>
                    Loading sync health...
                  </td>
                </tr>
              ) : jobs.length ? (
                jobs.map((job) => (
                  <tr key={job.id} className="border-t border-slate-100 align-top">
                    <td className="px-3 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium text-slate-900">{job.name}</div>
                      <div className="mt-1 font-mono text-xs text-slate-500">{job.command}</div>
                      {job.message && <div className="mt-2 text-xs text-red-700">{job.message}</div>}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">{formatPacificDateTime(job.lastRunAt)}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-right">{formatAge(job.hoursSinceLastRun)}</td>
                    <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                      every {job.expectedEveryHours}h
                      <div className="text-xs text-slate-500">critical after {job.criticalAfterHours}h</div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-2">
                        {job.stats.length ? (
                          job.stats.map((stat) => (
                            <span
                              key={`${job.id}-${stat.label}`}
                              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs"
                            >
                              <span className="text-slate-500">{stat.label}</span>
                              <span className="font-medium text-slate-900">{stat.value}</span>
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-500">--</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-slate-500">{job.source}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={7}>
                    No sync jobs found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Summary({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "ok" | "delayed" | "failed" | "unknown";
}) {
  const toneClass = {
    neutral: "border-slate-200 bg-white text-slate-900",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
    delayed: "border-amber-200 bg-amber-50 text-amber-900",
    failed: "border-red-200 bg-red-50 text-red-900",
    unknown: "border-slate-200 bg-slate-50 text-slate-700",
  }[tone];

  return (
    <div className={`rounded-lg border p-3 shadow-sm ${toneClass}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: HealthStatus }) {
  const config = {
    ok: {
      label: "Healthy",
      icon: CheckCircle2,
      className: "border-emerald-200 bg-emerald-50 text-emerald-800",
    },
    delayed: {
      label: "Delayed",
      icon: Clock3,
      className: "border-amber-200 bg-amber-50 text-amber-800",
    },
    failed: {
      label: "Failed",
      icon: XCircle,
      className: "border-red-200 bg-red-50 text-red-800",
    },
    unknown: {
      label: "Unknown",
      icon: HelpCircle,
      className: "border-slate-200 bg-slate-50 text-slate-700",
    },
  }[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${config.className}`}>
      <Icon className="h-3.5 w-3.5" />
      {config.label}
    </span>
  );
}

function formatPacificDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function formatAge(hours?: number | null) {
  if (hours === null || hours === undefined || Number.isNaN(Number(hours))) return "--";
  if (hours < 1) return "<1h";
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US");
}
