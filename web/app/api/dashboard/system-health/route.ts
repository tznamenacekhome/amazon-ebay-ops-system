import fs from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { createServerSupabaseClient, isCloudDeployment } from "../../_server";

type HealthJob = {
  name: string;
  status: "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";
  lastRunAt: string | null;
  hoursSinceLastRun: number | null;
  expectedEveryHours: number | null;
  schedule: string | null;
  message: string | null;
};

type SchedulerGroup = {
  key: string;
  label: string;
  domain: string;
  cadence: string;
  schedule: string;
  scheduleNames?: string[];
  description?: string;
  features?: string[];
  expectedEveryHours?: number;
  criticalAfterHours?: number;
  status: "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";
  lastRunAt: string | null;
  lastSuccessAt: string | null;
  hoursSinceLastSuccess: number | null;
  latestRun: {
    runId?: string;
    status: string;
    startedAt?: string | null;
    finishedAt?: string | null;
    runtimeSeconds: number | null;
    eventbridgeScheduleName: string | null;
    triggerSource: string | null;
    stats?: Array<{ label: string; value: string }>;
  } | null;
  recentRuns?: Array<{
    runId: string;
    status: string;
    startedAt: string | null;
    finishedAt: string | null;
    runtimeSeconds: number | null;
    triggerSource: string | null;
    eventbridgeScheduleName: string | null;
    errorSummary: string | null;
    stats?: Array<{ label: string; value: string }>;
  }>;
  jobs: Array<{
    name: string;
    status: string;
    lastRunAt: string | null;
    runtimeSeconds: number | null;
    blocking: boolean;
    message: string | null;
  }>;
};

type RecentRun = {
  runId: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  group: string | null;
  status: "success" | "partial" | "failed" | "running" | "blocked" | "unknown";
  failedJobs: number;
  totalJobs: number;
  summary: string | null;
};

type DynamicQueryResult = {
  data?: Array<Record<string, unknown>> | null;
  error?: { message: string } | null;
};

type DynamicQuery = PromiseLike<DynamicQueryResult> & {
  select: (columns: string) => DynamicQuery;
  order: (column: string, options?: { ascending?: boolean; nullsFirst?: boolean }) => DynamicQuery;
  limit: (count: number) => DynamicQuery;
  in: (column: string, values: unknown[]) => DynamicQuery;
};

const supabase = createServerSupabaseClient();

export async function GET(request: NextRequest) {
  const health = await fetchHealth(request);
  const jobs = (health?.jobs ?? []) as HealthJob[];
  const schedulerGroups = (health?.schedulerGroups ?? []) as SchedulerGroup[];
  const summary = health?.summary ?? {};
  const recentRuns = await readRecentRuns();
  const failedJobs = Number(summary.failed ?? 0);
  const failedGroups = Number(summary.failedGroups ?? schedulerGroups.filter((group) => group.status === "failed").length);
  const blockedJobs = Number(summary.blocked ?? 0);
  const blockedGroups = Number(summary.blockedGroups ?? schedulerGroups.filter((group) => group.status === "blocked").length);
  const runningJobs = Number(summary.running ?? 0);
  const runningGroups = Number(summary.runningGroups ?? schedulerGroups.filter((group) => group.status === "running").length);
  const staleDomains = Number(summary.delayed ?? 0);
  const delayedGroups = Number(summary.delayedGroups ?? schedulerGroups.filter((group) => group.status === "delayed").length);
  const latestRunFailedJobs = recentRuns[0]?.failedJobs ?? 0;

  return NextResponse.json({
    refreshedAt: health?.generatedAt ?? new Date().toISOString(),
    summary: {
      overallStatus:
        latestRunFailedJobs > 0 || blockedJobs > 0 || failedGroups > 0 || blockedGroups > 0
          ? "error"
          : staleDomains > 0 || runningJobs > 0 || delayedGroups > 0 || runningGroups > 0
            ? "warning"
            : jobs.length || schedulerGroups.length
              ? "healthy"
              : "unknown",
      staleDomains,
      failedJobsLastRun: latestRunFailedJobs,
      schedulerGroups: Number(summary.groups ?? schedulerGroups.length),
      healthyGroups: Number(summary.healthyGroups ?? schedulerGroups.filter((group) => group.status === "ok").length),
      delayedGroups,
      failedGroups,
      runningGroups,
      blockedGroups,
      lastOrchestratorRunAt: recentRuns[0]?.finishedAt ?? null,
      lastSuccessfulCoreRunAt: latestSuccessfulGroup(recentRuns, [
        "core",
        "purchase-ingestion",
        "purchase-tracking",
        "returns-order-problems",
        "purchase-enrichment",
        "amazon-sales-recent",
      ]),
      lastSuccessfulDailyRunAt: latestSuccessfulGroup(recentRuns, [
        "daily",
        "finance-refresh",
        "business-value-finalizer",
        "fba-inventory-daily",
        "fba-shipments",
        "reconciliation",
        "repricing-catalog",
        "sourcing-catalog",
        "keepa-rolling-refresh",
      ]),
    },
    domains: jobs.map((job) => ({
      domain: job.name,
      label: job.name,
      status:
        job.status === "ok"
          ? "fresh"
          : job.status === "delayed"
            ? "stale"
            : job.status === "blocked"
              ? "failed"
              : job.status,
      lastSuccessAt: job.status === "ok" || job.status === "delayed" ? job.lastRunAt : null,
      lastAttemptAt: job.lastRunAt,
      expectedCadence: job.expectedEveryHours ? `${job.expectedEveryHours}h` : "--",
      schedule: job.schedule ?? "--",
      ageHours: job.hoursSinceLastRun,
      message: job.message,
    })),
    schedulerGroups: schedulerGroups.map((group) => {
      const hasJobTelemetry = group.jobs.some((job) => Boolean(job.lastRunAt));
      return {
        group: group.key,
        label: group.label,
        domain: group.domain,
        description: group.description ?? null,
        features: group.features ?? [],
        status: group.status === "unknown" && !group.lastRunAt && !hasJobTelemetry ? "pending first run" : group.status,
        cadence: group.cadence,
        schedule: group.schedule,
        scheduleNames: group.scheduleNames ?? [],
        expectedEveryHours: group.expectedEveryHours ?? null,
        criticalAfterHours: group.criticalAfterHours ?? null,
        lastRunAt: group.lastRunAt,
        lastSuccessAt: group.lastSuccessAt,
        ageHours: group.hoursSinceLastSuccess,
        runtimeSeconds: group.latestRun?.runtimeSeconds ?? null,
        trigger: group.latestRun?.eventbridgeScheduleName ?? group.latestRun?.triggerSource ?? null,
        latestRun: group.latestRun ?? null,
        recentRuns: group.recentRuns ?? [],
        jobs: group.jobs,
        stats: (group as SchedulerGroup & { stats?: Array<{ label: string; value: string }> }).stats ?? [],
        jobsOk: group.jobs.filter((job) => job.status === "ok").length,
        jobsFailed: group.jobs.filter((job) => job.status === "failed").length,
        jobsRunning: group.jobs.filter((job) => job.status === "running").length,
        jobsTotal: group.jobs.length,
        message: group.jobs.find((job) => job.message)?.message ?? null,
      };
    }),
    recentRuns,
    localFileSignals: {
      status: isCloudDeployment() ? "unavailable_in_cloud_deployment" : "available",
      message: isCloudDeployment()
        ? "Local scheduler log files remain on the local sync machine during Phase 1."
        : null,
    },
    capacity: {
      supabaseStatus: "unknown",
      databaseSizeMb: null,
      diskIoWarning: null,
      message: "Capacity metrics are not queried automatically from dashboard page load.",
    },
    externalLimits: {
      keepaTokens: keepaTokens(jobs),
      keepaTokenStatus: keepaTokens(jobs) === null ? "unknown" : keepaTokens(jobs)! < 50 ? "low" : "ok",
      amazonThrottleWarnings: null,
      easyPostErrors: jobs.filter((job) => job.name.toLowerCase().includes("easypost") && job.status === "failed").length,
      message: "External limit details are summarized from sync health only; no external APIs are called.",
    },
  });
}

async function fetchHealth(request: NextRequest) {
  try {
    const response = await fetch(systemHealthUrl(request), { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

function systemHealthUrl(request: NextRequest) {
  if (isCloudDeployment()) {
    return `http://127.0.0.1:${process.env.PORT || "3103"}/api/system-health`;
  }
  return new URL("/api/system-health", request.url);
}

async function readRecentRuns(): Promise<RecentRun[]> {
  if (isCloudDeployment()) return readCloudRecentRuns();

  const logPath = path.resolve(process.cwd(), "..", "logs", "sync_runs.jsonl");
  if (!fs.existsSync(logPath)) return [];
  const lines = fs.readFileSync(logPath, "utf8").trim().split(/\r?\n/).filter(Boolean).slice(-200);
  const byRun = new Map<string, RecentRun>();
  for (const line of lines) {
    try {
      const row = JSON.parse(line);
      const runId = row.run_id ?? "manual";
      const current = byRun.get(runId) ?? { runId, startedAt: null, finishedAt: null, group: row.group ?? null, status: "unknown", failedJobs: 0, totalJobs: 0, summary: null };
      current.startedAt = minDate(current.startedAt, row.started_at);
      current.finishedAt = maxDate(current.finishedAt, row.finished_at);
      current.totalJobs += 1;
      if (row.status === "failed" || row.status === "blocked") current.failedJobs += 1;
      current.status = current.failedJobs > 0 ? "partial" : "success";
      current.summary = `${current.totalJobs} job(s), ${current.failedJobs} failed`;
      byRun.set(runId, current);
    } catch {
      // Ignore malformed log lines.
    }
  }
  return [...byRun.values()].sort((left, right) => String(right.finishedAt ?? "").localeCompare(String(left.finishedAt ?? ""))).slice(0, 10);
}

async function readCloudRecentRuns(): Promise<RecentRun[]> {
  const { data: runs, error } = await dynamicFrom("scheduler_runs")
    .select("run_id,group_name,status,started_at,finished_at,error_summary")
    .order("started_at", { ascending: false, nullsFirst: false })
    .limit(10);

  if (error || !runs?.length) return [];

  const runIds = runs.map((run) => stringValue(run.run_id)).filter(Boolean);
  const { data: jobs } = runIds.length
    ? await dynamicFrom("scheduler_run_jobs")
        .select("run_id,status")
        .in("run_id", runIds)
    : { data: [] };

  const jobCounts = new Map<string, { failed: number; total: number }>();
  for (const job of jobs ?? []) {
    const runId = stringValue(job.run_id);
    if (!runId) continue;
    const current = jobCounts.get(runId) ?? { failed: 0, total: 0 };
    current.total += 1;
    const status = stringValue(job.status);
    if (status === "failed" || status === "blocked") current.failed += 1;
    jobCounts.set(runId, current);
  }

  return runs.map((run) => {
    const runId = stringValue(run.run_id) || null;
    const status = stringValue(run.status);
    const counts = runId ? jobCounts.get(runId) : undefined;
    const failedJobs = counts?.failed ?? 0;
    const totalJobs = counts?.total ?? 0;

    return {
      runId,
      startedAt: stringValue(run.started_at) || null,
      finishedAt: stringValue(run.finished_at) || null,
      group: stringValue(run.group_name) || null,
      status: normalizeRunStatus(status, failedJobs),
      failedJobs,
      totalJobs,
      summary: stringValue(run.error_summary) || `${totalJobs} job(s), ${failedJobs} failed`,
    };
  });
}

function latestSuccessfulGroup(runs: RecentRun[], groups: string[]) {
  return runs.find((run) => run.group && groups.includes(run.group) && run.status === "success")?.finishedAt ?? null;
}
function keepaTokens(jobs: HealthJob[]) {
  const keepa = jobs.find((job) => job.name.toLowerCase().includes("keepa"));
  const tokenStat = (keepa as unknown as { stats?: Array<{ label: string; value: string }> })?.stats?.find((stat) => stat.label.toLowerCase().includes("tokens"));
  if (!tokenStat) return null;
  const value = Number(String(tokenStat.value).replace(/,/g, ""));
  return Number.isFinite(value) ? value : null;
}
function minDate(left: string | null, right: string | null | undefined) {
  if (!right) return left;
  if (!left) return right;
  return right < left ? right : left;
}
function maxDate(left: string | null, right: string | null | undefined) {
  if (!right) return left;
  if (!left) return right;
  return right > left ? right : left;
}

function dynamicFrom(table: string): DynamicQuery {
  return supabase.from(table) as unknown as DynamicQuery;
}

function normalizeRunStatus(status: string, failedJobs: number): RecentRun["status"] {
  if (status === "running") return "running";
  if (status === "blocked") return "blocked";
  if (status === "failed") return "failed";
  if (status === "degraded" || failedJobs > 0) return "partial";
  if (status === "ok") return "success";
  return "unknown";
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}
