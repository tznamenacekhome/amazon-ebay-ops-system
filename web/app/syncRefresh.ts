"use client";

import { mutationHeaders } from "./mutationHeaders";

export type RefreshTarget =
  | "purchases"
  | "dashboard"
  | "sales-orders"
  | "inventory-reconciliation"
  | "repricing"
  | "fba"
  | "fba-pricing";

export type RefreshNotice = {
  tone: "info" | "success" | "warning";
  text: string;
};

export type PersistedRefreshState = {
  target: RefreshTarget;
  runId: string | null;
  startedAt: string;
  completedAt?: string;
  notice: RefreshNotice;
};

const POLL_INTERVAL_MS = 10_000;
const MAX_WAIT_MS = 30 * 60 * 1000;

export async function runOnDemandRefresh(
  target: RefreshTarget,
  reloadData: () => Promise<void>,
  setNotice: (notice: RefreshNotice | null) => void,
  options: { persistKey?: string } = {},
) {
  const startingNotice = { tone: "info" as const, text: "Starting sync refresh..." };
  setNotice(startingNotice);
  persistRefresh(options.persistKey, {
    target,
    runId: null,
    startedAt: new Date().toISOString(),
    notice: startingNotice,
  });

  const response = await fetch("/api/sync-refresh", {
    method: "POST",
    headers: mutationHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ target }),
  });
  const payload = await response.json().catch(() => ({}));

  if (response.status === 409) {
    const notice = {
      tone: "warning",
      text: payload?.message || "A sync is already running. Try again after it finishes.",
    } satisfies RefreshNotice;
    setNotice(notice);
    persistRefresh(options.persistKey, {
      target,
      runId: null,
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      notice,
    });
    await reloadData();
    return;
  }

  if (!response.ok) {
    throw new Error(payload?.error || payload?.message || `Refresh failed: ${response.status}`);
  }

  if (payload?.status === "no_sync_required") {
    const notice = { tone: "success" as const, text: payload.message || "Reloaded current data." };
    setNotice(notice);
    persistRefresh(options.persistKey, {
      target,
      runId: null,
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      notice,
    });
    await reloadData();
    return;
  }

  const queuedNotice = {
    tone: "info",
    text: startedNoticeText(payload),
  } satisfies RefreshNotice;
  setNotice(queuedNotice);

  const runId = typeof payload?.runId === "string" ? payload.runId : null;
  persistRefresh(options.persistKey, {
    target,
    runId,
    startedAt: new Date().toISOString(),
    notice: queuedNotice,
  });
  const completed = runId ? await waitForRunToFinish(runId, setNotice, options.persistKey, target) : await waitForLegacySyncToFinish();
  if (completed?.done) {
    const notice = completionNotice(completed);
    setNotice(notice);
    persistRefresh(options.persistKey, {
      target,
      runId,
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      notice,
    });
    await reloadData();
    return;
  }

  const warningNotice = {
    tone: "warning",
    text: "Sync refresh is still running. Data will update after it completes; check System Health for progress.",
  } satisfies RefreshNotice;
  setNotice(warningNotice);
  persistRefresh(options.persistKey, {
    target,
    runId,
    startedAt: new Date().toISOString(),
    notice: warningNotice,
  });
}

export function readPersistedRefresh(persistKey: string): PersistedRefreshState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(persistKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedRefreshState;
    if (!parsed || typeof parsed !== "object" || !parsed.notice) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function resumePersistedRefresh(
  persistKey: string,
  reloadData: () => Promise<void>,
  setNotice: (notice: RefreshNotice | null) => void,
) {
  const stored = readPersistedRefresh(persistKey);
  if (!stored) return false;
  setNotice(stored.notice);
  if (stored.completedAt || !stored.runId) return false;

  const completed = await waitForRunToFinish(stored.runId, setNotice, persistKey, stored.target);
  if (!completed.done) return false;

  const notice = completionNotice(completed);
  setNotice(notice);
  persistRefresh(persistKey, {
    ...stored,
    completedAt: new Date().toISOString(),
    notice,
  });
  await reloadData();
  return true;
}

function startedNoticeText(payload: any) {
  if (payload?.executionMode === "aws-ecs" || payload?.taskArn) {
    return "Queued in AWS. Waiting for scheduler telemetry...";
  }
  return payload?.message
    ? `${payload.message} Waiting for completion before reloading data.`
    : "Sync refresh started. Waiting for completion before reloading data.";
}

type RunPollResult = {
  done: boolean;
  status?: string | null;
  summary?: {
    rowsRead: number;
    rowsInserted: number;
    rowsUpdated: number;
    rowsSkipped: number;
    rateLimitCount: number;
    failures: number;
  };
  error?: string | null;
};

async function waitForRunToFinish(
  runId: string,
  setNotice: (notice: RefreshNotice | null) => void,
  persistKey?: string,
  target?: RefreshTarget,
): Promise<RunPollResult> {
  const startedAt = Date.now();
  let sawRun = false;
  while (Date.now() - startedAt < MAX_WAIT_MS) {
    await sleep(POLL_INTERVAL_MS);
    const response = await fetch(`/api/sync-refresh?runId=${encodeURIComponent(runId)}`, { cache: "no-store" });
    if (!response.ok) return { done: false };
    const payload = await response.json();
    if (!payload?.found) {
      if (await localSyncIsRunning()) {
        return waitForLegacySyncToFinish();
      }
      const notice = { tone: "info" as const, text: "Queued in AWS. Waiting for the scheduler task to start..." };
      setNotice(notice);
      persistRunningNotice(persistKey, target, runId, notice);
      continue;
    }
    sawRun = true;
    const status = String(payload.run?.status ?? "");
    if (status === "running") {
      const notice = { tone: "info" as const, text: runningNoticeText(payload.jobs ?? []) };
      setNotice(notice);
      persistRunningNotice(persistKey, target, runId, notice);
      continue;
    }
    if (["ok", "degraded", "failed", "blocked", "cancelled"].includes(status)) {
      return {
        done: true,
        status,
        summary: payload.summary,
        error: payload.run?.error_summary ?? null,
      };
    }
  }
  return sawRun ? { done: false } : waitForLegacySyncToFinish();
}

function runningNoticeText(jobs: Array<{ job_name?: string; jobName?: string; status?: string }>) {
  const running = jobs.find((job) => job.status === "running");
  if (!running) return "Queued in AWS. Waiting for the next pricing job step...";
  const name = running.job_name ?? running.jobName ?? "pricing job";
  return `Running ${name}...`;
}

function completionNotice(result: RunPollResult): RefreshNotice {
  const summary = result.summary;
  const updated = (summary?.rowsInserted ?? 0) + (summary?.rowsUpdated ?? 0);
  const skipped = summary?.rowsSkipped ?? 0;
  const rateLimits = summary?.rateLimitCount ?? 0;
  const failures = summary?.failures ?? 0;
  const suffix = [
    updated ? `${updated} updates` : null,
    skipped ? `${skipped} skipped/error rows` : null,
    rateLimits ? `${rateLimits} quota waits/errors` : null,
  ].filter(Boolean).join(", ");

  if (result.status === "ok") {
    return { tone: "success", text: suffix ? `Pricing refresh complete: ${suffix}.` : "Pricing refresh complete. Reloaded latest data." };
  }
  if (result.status === "degraded" || failures || rateLimits || skipped) {
    return { tone: "warning", text: suffix ? `Pricing refresh completed with warnings: ${suffix}.` : "Pricing refresh completed with warnings." };
  }
  return { tone: "warning", text: result.error ? `Pricing refresh failed: ${result.error}` : "Pricing refresh failed or was blocked." };
}

async function waitForSyncToFinish() {
  const startedAt = Date.now();
  while (Date.now() - startedAt < MAX_WAIT_MS) {
    await sleep(POLL_INTERVAL_MS);
    const response = await fetch("/api/sync-refresh", { cache: "no-store" });
    if (!response.ok) return false;
    const payload = await response.json();
    if (!payload?.inProgress) return true;
  }
  return false;
}

async function waitForLegacySyncToFinish(): Promise<RunPollResult> {
  return { done: await waitForSyncToFinish(), status: "ok" };
}

async function localSyncIsRunning() {
  const response = await fetch("/api/sync-refresh", { cache: "no-store" });
  if (!response.ok) return false;
  const payload = await response.json().catch(() => ({}));
  return Boolean(payload?.inProgress);
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function persistRunningNotice(
  persistKey: string | undefined,
  target: RefreshTarget | undefined,
  runId: string,
  notice: RefreshNotice,
) {
  if (!target) return;
  persistRefresh(persistKey, {
    target,
    runId,
    startedAt: new Date().toISOString(),
    notice,
  });
}

function persistRefresh(persistKey: string | undefined, state: PersistedRefreshState) {
  if (!persistKey || typeof window === "undefined") return;
  window.localStorage.setItem(persistKey, JSON.stringify(state));
}
