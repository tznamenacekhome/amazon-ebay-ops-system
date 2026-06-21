"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Clock3,
  Info,
  HelpCircle,
  PauseCircle,
  RefreshCw,
  RotateCw,
  ShieldAlert,
  X,
  XCircle,
} from "lucide-react";
import { DataFreshness } from "../DataFreshness";

type HealthStatus = "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";

type HealthJob = {
  id: string;
  name: string;
  command: string;
  group: string;
  primaryGroup: string;
  awsGroups: string[];
  blocking: boolean;
  enabled: boolean;
  status: HealthStatus;
  lastRunAt: string | null;
  hoursSinceLastRun: number | null;
  expectedEveryHours: number;
  criticalAfterHours: number;
  source: string;
  stats: Array<{ label: string; value: string }>;
  message: string | null;
};

type SchedulerRun = {
  runId: string;
  groupName: string;
  groupLabel?: string;
  status: "running" | "ok" | "degraded" | "failed" | "blocked" | "cancelled";
  startedAt: string | null;
  finishedAt: string | null;
  runtimeSeconds: number | null;
  triggerSource: string | null;
  ecsTaskArn: string | null;
  eventbridgeScheduleName: string | null;
  containerCpu: number | null;
  containerMemory: number | null;
  errorSummary: string | null;
  jobs?: SchedulerRunJob[];
  stats?: Array<{ label: string; value: string }>;
};

type SchedulerRunJob = {
  runId: string;
  jobName: string;
  groupName: string;
  command: string;
  status: "running" | "ok" | "skipped" | "failed" | "blocked";
  blocking: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  runtimeSeconds: number | null;
  errorSummary: string | null;
  rowsRead: number | null;
  rowsInserted: number | null;
  rowsUpdated: number | null;
  rowsDeleted: number | null;
  rowsSkipped: number | null;
  externalApiCalls: number | null;
  retryCount: number | null;
  rateLimitCount: number | null;
  logBytes: number | null;
};

type SchedulerGroup = {
  key: string;
  label: string;
  domain: string;
  cadence: string;
  schedule: string;
  scheduleNames: string[];
  expectedEveryHours: number;
  criticalAfterHours: number;
  description: string;
  features: string[];
  jobNames: string[];
  status: HealthStatus;
  lastRunAt: string | null;
  lastSuccessAt: string | null;
  hoursSinceLastRun: number | null;
  hoursSinceLastSuccess: number | null;
  latestRun: SchedulerRun | null;
  recentRuns: SchedulerRun[];
  jobs: Array<{
    name: string;
    status: HealthStatus;
    lastRunAt: string | null;
    runtimeSeconds: number | null;
    blocking: boolean;
    message: string | null;
  }>;
  stats: Array<{ label: string; value: string }>;
};

type HealthData = {
  generatedAt: string;
  summary: {
    total: number;
    ok: number;
    delayed: number;
    failed: number;
    running: number;
    blocked: number;
    unknown: number;
    skipped: number;
    groups?: number;
    healthyGroups?: number;
    delayedGroups?: number;
    failedGroups?: number;
    runningGroups?: number;
    blockedGroups?: number;
  };
  jobs: HealthJob[];
  schedulerGroups?: SchedulerGroup[];
  recentRuns?: SchedulerRun[];
};

const STATUS_RANK: Record<HealthStatus, number> = {
  failed: 0,
  blocked: 1,
  running: 2,
  delayed: 3,
  unknown: 4,
  skipped: 5,
  ok: 6,
};

const AWS_GROUP_ORDER = [
  "purchase-ingestion",
  "purchase-tracking",
  "returns-order-problems",
  "purchase-enrichment",
  "amazon-sales-recent",
  "finance-refresh",
  "business-value-finalizer",
  "fba-inventory-daily",
  "fba-shipments",
  "reconciliation",
  "repricing-catalog",
  "sourcing-catalog",
  "keepa-rolling-refresh",
  "fba-pricing",
];

export default function SystemHealthPage() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [freshnessKey, setFreshnessKey] = useState(0);
  const [selectedGroupKey, setSelectedGroupKey] = useState<string | null>(null);

  useEffect(() => {
    loadHealth();
  }, []);

  const jobs = useMemo(() => {
    return [...(data?.jobs ?? [])].sort((a, b) => {
      const groupSort = groupRank(a.primaryGroup) - groupRank(b.primaryGroup);
      if (groupSort !== 0) return groupSort;
      const statusSort = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (statusSort !== 0) return statusSort;
      return (b.hoursSinceLastRun ?? -1) - (a.hoursSinceLastRun ?? -1);
    });
  }, [data]);

  const schedulerGroups = useMemo(() => {
    return [...(data?.schedulerGroups ?? [])].sort((a, b) => {
      const statusSort = STATUS_RANK[a.status] - STATUS_RANK[b.status];
      if (statusSort !== 0) return statusSort;
      return groupRank(a.key) - groupRank(b.key);
    });
  }, [data]);

  const recentRuns = data?.recentRuns ?? [];
  const selectedGroup = schedulerGroups.find((group) => group.key === selectedGroupKey) ?? null;

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
      setFreshnessKey((current) => current + 1);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System Health</h1>
          <p className="mt-1 text-sm text-slate-600">
            Scheduler groups, latest run signals, blocking behavior, and stale-data checks.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="system-health" refreshKey={freshnessKey} />
          <button
            onClick={loadHealth}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="mb-4 grid gap-3 md:grid-cols-8">
        <Summary label="Jobs" value={formatNumber(data?.summary.total)} tone="neutral" />
        <Summary label="Healthy" value={formatNumber(data?.summary.ok)} tone="ok" />
        <Summary label="Running" value={formatNumber(data?.summary.running)} tone="running" />
        <Summary label="Delayed" value={formatNumber(data?.summary.delayed)} tone="delayed" />
        <Summary label="Failed" value={formatNumber(data?.summary.failed)} tone="failed" />
        <Summary label="Blocked" value={formatNumber(data?.summary.blocked)} tone="blocked" />
        <Summary label="Unknown" value={formatNumber(data?.summary.unknown)} tone="unknown" />
        <Summary label="Skipped" value={formatNumber(data?.summary.skipped)} tone="skipped" />
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-6">
        <Summary label="AWS Groups" value={formatNumber(data?.summary.groups)} tone="neutral" />
        <Summary label="Group Healthy" value={formatNumber(data?.summary.healthyGroups)} tone="ok" />
        <Summary label="Group Running" value={formatNumber(data?.summary.runningGroups)} tone="running" />
        <Summary label="Group Delayed" value={formatNumber(data?.summary.delayedGroups)} tone="delayed" />
        <Summary label="Group Failed" value={formatNumber(data?.summary.failedGroups)} tone="failed" />
        <Summary label="Group Blocked" value={formatNumber(data?.summary.blockedGroups)} tone="blocked" />
      </section>

      <section className="mb-4 grid gap-3 xl:grid-cols-2 2xl:grid-cols-3">
        {loading ? (
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
            Loading AWS scheduler groups...
          </div>
        ) : schedulerGroups.length ? (
          schedulerGroups.map((group) => (
            <SchedulerGroupPanel
              key={group.key}
              group={group}
              onOpen={() => setSelectedGroupKey(group.key)}
            />
          ))
        ) : (
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm">
            No scheduler group telemetry found.
          </div>
        )}
      </section>

      <section className="mb-4 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <div>
            <div className="text-sm font-medium uppercase tracking-wide text-slate-500">ECS Runs</div>
            <h2 className="mt-1 text-lg font-semibold">Recent Scheduler Runs</h2>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Group</th>
                <th className="px-3 py-2">Schedule</th>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">Runtime</th>
                <th className="px-3 py-2">Task</th>
              </tr>
            </thead>
            <tbody>
              {recentRuns.length ? (
                recentRuns.slice(0, 12).map((run) => (
                  <tr key={run.runId} className="border-t border-slate-100">
                    <td className="px-3 py-2"><StatusBadge status={runStatusToHealth(run.status)} /></td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-slate-900">{run.groupLabel ?? run.groupName}</div>
                      <div className="font-mono text-xs text-slate-500">{shortRunId(run.runId)}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">{run.eventbridgeScheduleName ?? run.triggerSource ?? "--"}</td>
                    <td className="whitespace-nowrap px-3 py-2">{formatPacificDateTime(run.startedAt)}</td>
                    <td className="whitespace-nowrap px-3 py-2">{formatDuration(run.runtimeSeconds)}</td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">{shortTaskArn(run.ecsTaskArn)}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-3 py-6 text-center text-slate-500" colSpan={6}>
                    No scheduler runs recorded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
          <table className="w-full min-w-[1280px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Sync Job</th>
                <th className="px-3 py-2">Group</th>
                <th className="px-3 py-2">Mode</th>
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
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={9}>
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
                    <td className="px-3 py-3 text-slate-700">
                      <div className="whitespace-nowrap font-medium">{formatGroupName(job.primaryGroup)}</div>
                      {job.awsGroups.length > 1 ? (
                        <div className="mt-1 text-xs text-slate-500">{job.awsGroups.map(formatGroupName).join(", ")}</div>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <ModeBadge blocking={job.blocking} enabled={job.enabled} />
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
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={9}>
                    No sync jobs found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedGroup ? (
        <SchedulerGroupDrawer group={selectedGroup} onClose={() => setSelectedGroupKey(null)} />
      ) : null}
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
  tone: "neutral" | "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";
}) {
  const toneClass = {
    neutral: "border-slate-200 bg-white text-slate-900",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
    running: "border-blue-200 bg-blue-50 text-blue-900",
    delayed: "border-amber-200 bg-amber-50 text-amber-900",
    failed: "border-red-200 bg-red-50 text-red-900",
    blocked: "border-orange-200 bg-orange-50 text-orange-900",
    unknown: "border-slate-200 bg-slate-50 text-slate-700",
    skipped: "border-slate-200 bg-white text-slate-500",
  }[tone];

  return (
    <div className={`rounded-lg border p-3 shadow-sm ${toneClass}`}>
      <div className="text-xs uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function SchedulerGroupPanel({ group, onOpen }: { group: SchedulerGroup; onOpen: () => void }) {
  const failed = group.jobs.filter((job) => job.status === "failed").length;
  const blocked = group.jobs.filter((job) => job.status === "blocked").length;
  const running = group.jobs.filter((job) => job.status === "running").length;
  const delayed = group.jobs.filter((job) => job.status === "delayed").length;
  const ok = group.jobs.filter((job) => job.status === "ok").length;

  return (
    <button
      className="rounded-lg border border-slate-200 bg-white p-3 text-left shadow-sm transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400"
      onClick={onOpen}
      type="button"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{group.domain}</div>
          <div className="mt-0.5 text-sm font-semibold text-slate-900">{group.label}</div>
          <div className="mt-0.5 text-xs text-slate-500">{group.cadence}</div>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={group.status} />
          <Info className="h-4 w-4 text-slate-400" />
        </div>
      </div>

      <p className="mt-2 text-xs leading-5 text-slate-600">{group.description}</p>

      <div className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Last Success</div>
          <div className="mt-0.5 text-slate-900">{formatPacificDateTime(group.lastSuccessAt)}</div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Last Attempt</div>
          <div className="mt-0.5 text-slate-900">{formatPacificDateTime(group.lastRunAt)}</div>
        </div>
        <div>
          <div className="font-semibold uppercase tracking-wide text-slate-500">Runtime</div>
          <div className="mt-0.5 text-slate-900">{formatDuration(group.latestRun?.runtimeSeconds ?? null)}</div>
        </div>
      </div>

      <div className="mt-3 text-xs text-slate-600">
        <span className="font-semibold text-slate-700">Schedule:</span> {group.schedule}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {group.scheduleNames.length ? (
          group.scheduleNames.map((name) => (
            <span key={name} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600">
              {name}
            </span>
          ))
        ) : (
          <span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-500">manual</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1 text-xs">
        <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-800">{ok} ok</span>
        <span className="rounded-md bg-blue-50 px-2 py-1 text-blue-800">{running} run</span>
        <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-800">{delayed} late</span>
        <span className="rounded-md bg-orange-50 px-2 py-1 text-orange-800">{blocked} blocked</span>
        <span className="rounded-md bg-red-50 px-2 py-1 text-red-800">{failed} fail</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {group.stats.map((stat) => (
          <span key={`${group.key}-${stat.label}`} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
            <span className="text-slate-500">{stat.label}</span>{" "}
            <span className="font-medium text-slate-900">{stat.value}</span>
          </span>
        ))}
      </div>

      <div className="mt-3 space-y-1">
        {group.jobs.map((job) => (
          <div key={`${group.key}-${job.name}`} className="flex items-center justify-between gap-2 rounded-md border border-slate-100 px-2 py-1.5 text-xs">
            <div className="min-w-0">
              <div className="truncate font-medium text-slate-800">{job.name}</div>
              <div className="text-slate-500">
                {formatPacificDateTime(job.lastRunAt)} · {formatDuration(job.runtimeSeconds)}
              </div>
            </div>
            <StatusBadge status={job.status} />
          </div>
        ))}
      </div>

      {group.latestRun?.errorSummary ? (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700">
          {group.latestRun.errorSummary}
        </div>
      ) : null}
    </button>
  );
}

function SchedulerGroupDrawer({ group, onClose }: { group: SchedulerGroup; onClose: () => void }) {
  const lastRuns = group.recentRuns.slice(0, 10);
  const successfulRuns = lastRuns.filter((run) => run.status === "ok").length;
  const latestStats = group.latestRun?.stats ?? [];

  return (
    <div className="fixed inset-0 z-50">
      <button
        aria-label="Close scheduler group details"
        className="absolute inset-0 cursor-default bg-slate-950/30"
        onClick={onClose}
        type="button"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-3xl flex-col border-l border-slate-200 bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{group.domain}</div>
            <h2 className="mt-1 text-xl font-semibold text-slate-950">{group.label}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={group.status} />
              <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600">{group.cadence}</span>
              <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600">
                Last 10: {successfulRuns}/{lastRuns.length} successful
              </span>
            </div>
          </div>
          <button
            className="rounded-md border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-800"
            onClick={onClose}
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <section className="grid gap-3 md:grid-cols-3">
            <MetricTile label="Last Success" value={formatPacificDateTime(group.lastSuccessAt)} />
            <MetricTile label="Last Attempt" value={formatPacificDateTime(group.lastRunAt)} />
            <MetricTile label="Latest Runtime" value={formatDuration(group.latestRun?.runtimeSeconds ?? null)} />
          </section>

          <section className="mt-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">What This Updates</h3>
            <p className="mt-2 text-sm leading-6 text-slate-700">{group.description}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {group.features.map((feature) => (
                <span key={feature} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">
                  {feature}
                </span>
              ))}
            </div>
          </section>

          <section className="mt-5 grid gap-4 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Schedule</h3>
              <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                {group.schedule}
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {group.scheduleNames.length ? (
                  group.scheduleNames.map((name) => (
                    <span key={name} className="rounded-md border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-600">
                      {name}
                    </span>
                  ))
                ) : (
                  <span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-500">manual/on-demand</span>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Guardrails</h3>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <MetricTile label="Expected Every" value={group.expectedEveryHours > 0 ? `${group.expectedEveryHours}h` : "manual"} compact />
                <MetricTile label="Critical After" value={group.criticalAfterHours > 0 ? `${group.criticalAfterHours}h` : "manual"} compact />
              </div>
            </div>
          </section>

          <section className="mt-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Jobs In This Group</h3>
            <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Job</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Last Run</th>
                    <th className="px-3 py-2">Runtime</th>
                  </tr>
                </thead>
                <tbody>
                  {group.jobs.map((job) => (
                    <tr key={job.name} className="border-t border-slate-100">
                      <td className="px-3 py-2">
                        <div className="font-medium text-slate-900">{job.name}</div>
                        <div className="text-xs text-slate-500">{job.blocking ? "blocking" : "nonblocking"}</div>
                      </td>
                      <td className="px-3 py-2"><StatusBadge status={job.status} /></td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-700">{formatPacificDateTime(job.lastRunAt)}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-slate-700">{formatDuration(job.runtimeSeconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mt-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Last 10 Runs</h3>
              <MetricPills stats={latestStats.length ? latestStats : group.stats} empty="No counters" />
            </div>
            <div className="mt-2 overflow-hidden rounded-lg border border-slate-200">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Run</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Finished</th>
                    <th className="px-3 py-2">Runtime</th>
                    <th className="px-3 py-2">Changed</th>
                  </tr>
                </thead>
                <tbody>
                  {lastRuns.length ? (
                    lastRuns.map((run) => (
                      <tr key={run.runId} className="border-t border-slate-100 align-top">
                        <td className="px-3 py-2">
                          <div className="font-mono text-xs text-slate-700">{shortRunId(run.runId)}</div>
                          <div className="mt-1 text-xs text-slate-500">{run.eventbridgeScheduleName ?? run.triggerSource ?? "manual"}</div>
                        </td>
                        <td className="px-3 py-2"><StatusBadge status={runStatusToHealth(run.status)} /></td>
                        <td className="whitespace-nowrap px-3 py-2 text-slate-700">{formatPacificDateTime(run.finishedAt ?? run.startedAt)}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-slate-700">{formatDuration(run.runtimeSeconds)}</td>
                        <td className="px-3 py-2">
                          <MetricPills stats={run.stats ?? []} empty="No counters" />
                          {run.errorSummary ? <div className="mt-1 text-xs text-red-700">{run.errorSummary}</div> : null}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>No run history recorded.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function MetricTile({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <div className={`rounded-lg border border-slate-200 bg-slate-50 ${compact ? "p-2" : "p-3"}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 font-semibold text-slate-900 ${compact ? "text-sm" : "text-base"}`}>{value}</div>
    </div>
  );
}

function MetricPills({ stats, empty }: { stats: Array<{ label: string; value: string }>; empty: string }) {
  if (!stats.length) return <span className="text-xs text-slate-500">{empty}</span>;

  return (
    <div className="flex flex-wrap gap-1">
      {stats.map((stat) => (
        <span key={`${stat.label}-${stat.value}`} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
          <span className="text-slate-500">{stat.label}</span>{" "}
          <span className="font-medium text-slate-900">{stat.value}</span>
        </span>
      ))}
    </div>
  );
}

function LegacyGroupPanel({ title, cadence, detail, jobs }: { title: string; cadence: string; detail: string; jobs: HealthJob[] }) {
  const failed = jobs.filter((job) => job.status === "failed").length;
  const blocked = jobs.filter((job) => job.status === "blocked").length;
  const running = jobs.filter((job) => job.status === "running").length;
  const delayed = jobs.filter((job) => job.status === "delayed").length;
  const ok = jobs.filter((job) => job.status === "ok").length;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-slate-900">{title}</div>
          <div className="text-xs text-slate-500">{cadence}</div>
        </div>
        <div className="flex gap-1 text-xs">
          <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-800">{ok} ok</span>
          <span className="rounded-md bg-blue-50 px-2 py-1 text-blue-800">{running} run</span>
          <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-800">{delayed} late</span>
          <span className="rounded-md bg-orange-50 px-2 py-1 text-orange-800">{blocked} blocked</span>
          <span className="rounded-md bg-red-50 px-2 py-1 text-red-800">{failed} fail</span>
        </div>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-600">{detail}</p>
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
    blocked: {
      label: "Blocked",
      icon: ShieldAlert,
      className: "border-orange-200 bg-orange-50 text-orange-800",
    },
    running: {
      label: "Running",
      icon: RotateCw,
      className: "border-blue-200 bg-blue-50 text-blue-800",
    },
    unknown: {
      label: "Unknown",
      icon: HelpCircle,
      className: "border-slate-200 bg-slate-50 text-slate-700",
    },
    skipped: {
      label: "Skipped",
      icon: PauseCircle,
      className: "border-slate-200 bg-white text-slate-600",
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

function ModeBadge({ blocking, enabled }: { blocking: boolean; enabled: boolean }) {
  if (!enabled) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600">
        <PauseCircle className="h-3.5 w-3.5" />
        Disabled
      </span>
    );
  }
  if (!blocking) {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">
        <ShieldAlert className="h-3.5 w-3.5" />
        Nonblocking
      </span>
    );
  }
  return (
    <span className="inline-flex rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700">
      Blocking
    </span>
  );
}

function groupRank(group: string) {
  const index = AWS_GROUP_ORDER.indexOf(group);
  return index === -1 ? 999 : index;
}

function formatGroupName(group: string) {
  if (!group) return "--";
  return group
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function runStatusToHealth(status: SchedulerRun["status"]): HealthStatus {
  if (status === "ok") return "ok";
  if (status === "degraded") return "delayed";
  if (status === "failed" || status === "cancelled") return "failed";
  if (status === "blocked") return "blocked";
  if (status === "running") return "running";
  return "unknown";
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

function formatDuration(seconds?: number | null) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US");
}

function shortRunId(value?: string | null) {
  if (!value) return "--";
  return value.length > 8 ? value.slice(0, 8) : value;
}

function shortTaskArn(value?: string | null) {
  if (!value) return "--";
  const parts = value.split("/");
  return parts[parts.length - 1] || value;
}
