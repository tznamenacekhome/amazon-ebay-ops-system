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

const POLL_INTERVAL_MS = 10_000;
const MAX_WAIT_MS = 30 * 60 * 1000;

export async function runOnDemandRefresh(
  target: RefreshTarget,
  reloadData: () => Promise<void>,
  setNotice: (notice: RefreshNotice | null) => void,
) {
  setNotice({ tone: "info", text: "Starting sync refresh..." });

  const response = await fetch("/api/sync-refresh", {
    method: "POST",
    headers: mutationHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ target }),
  });
  const payload = await response.json().catch(() => ({}));

  if (response.status === 409) {
    setNotice({
      tone: "warning",
      text: payload?.message || "A sync is already running. Try again after it finishes.",
    });
    await reloadData();
    return;
  }

  if (!response.ok) {
    throw new Error(payload?.error || payload?.message || `Refresh failed: ${response.status}`);
  }

  if (payload?.status === "no_sync_required") {
    setNotice({ tone: "success", text: payload.message || "Reloaded current data." });
    await reloadData();
    return;
  }

  if (payload?.executionMode === "aws-ecs" || payload?.taskArn) {
    setNotice({
      tone: "info",
      text: payload?.message ||
        "Started the AWS scheduler task. Check System Health for progress; data will update after it finishes.",
    });
    return;
  }

  setNotice({
    tone: "info",
    text: payload?.message
      ? `${payload.message} Waiting for completion before reloading data.`
      : "Sync refresh started. Waiting for completion before reloading data.",
  });

  const completed = await waitForSyncToFinish();
  if (completed) {
    setNotice({ tone: "success", text: "Sync refresh complete. Reloaded latest data." });
    await reloadData();
    return;
  }

  setNotice({
    tone: "warning",
    text: "Sync refresh is still running. Data will update after it completes; check System Health for progress.",
  });
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

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
