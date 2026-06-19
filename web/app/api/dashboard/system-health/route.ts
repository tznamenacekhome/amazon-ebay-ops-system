import fs from "fs";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import { isCloudDeployment } from "../../_server";

type HealthJob = {
  name: string;
  status: "ok" | "delayed" | "failed" | "unknown" | "skipped" | "running" | "blocked";
  lastRunAt: string | null;
  hoursSinceLastRun: number | null;
  expectedEveryHours: number | null;
  schedule: string | null;
  message: string | null;
};

export async function GET(request: NextRequest) {
  const health = await fetchHealth(request);
  const jobs = (health?.jobs ?? []) as HealthJob[];
  const summary = health?.summary ?? {};
  const recentRuns = readRecentRuns();
  const failedJobs = Number(summary.failed ?? 0);
  const blockedJobs = Number(summary.blocked ?? 0);
  const runningJobs = Number(summary.running ?? 0);
  const staleDomains = Number(summary.delayed ?? 0);

  return NextResponse.json({
    refreshedAt: health?.generatedAt ?? new Date().toISOString(),
    summary: {
      overallStatus:
        failedJobs > 0 || blockedJobs > 0
          ? "error"
          : staleDomains > 0 || runningJobs > 0
            ? "warning"
            : jobs.length
              ? "healthy"
              : "unknown",
      staleDomains,
      failedJobsLastRun: failedJobs,
      lastOrchestratorRunAt: recentRuns[0]?.finishedAt ?? null,
      lastSuccessfulCoreRunAt: latestSuccessfulGroup(recentRuns, "core"),
      lastSuccessfulDailyRunAt: latestSuccessfulGroup(recentRuns, "daily"),
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
    const response = await fetch(new URL("/api/system-health", request.url), { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

function readRecentRuns() {
  if (isCloudDeployment()) return [];

  const logPath = path.resolve(process.cwd(), "..", "logs", "sync_runs.jsonl");
  if (!fs.existsSync(logPath)) return [];
  const lines = fs.readFileSync(logPath, "utf8").trim().split(/\r?\n/).filter(Boolean).slice(-200);
  const byRun = new Map<string, { runId: string | null; startedAt: string | null; finishedAt: string | null; group: string | null; status: "success" | "partial" | "failed" | "unknown"; failedJobs: number; totalJobs: number; summary: string | null }>();
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

function latestSuccessfulGroup(runs: ReturnType<typeof readRecentRuns>, group: string) {
  return runs.find((run) => run.group === group && run.status === "success")?.finishedAt ?? null;
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
