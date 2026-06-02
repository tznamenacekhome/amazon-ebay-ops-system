"use client";

import { useEffect, useState } from "react";

export type DataFreshnessScreen =
  | "purchases"
  | "dashboard"
  | "receiving"
  | "fba"
  | "repricing"
  | "sales-orders"
  | "inventory-reconciliation"
  | "system-health";

type FreshnessPayload = {
  screens?: Record<
    string,
    {
      lastUpdatedAt: string | null;
      source: string | null;
    }
  >;
};

type DataFreshnessProps = {
  screen: DataFreshnessScreen;
  refreshKey?: number;
};

export function DataFreshness({ screen, refreshKey = 0 }: DataFreshnessProps) {
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadFreshness() {
      setLoading(true);
      try {
        const response = await fetch(`/api/screen-data-freshness?screen=${screen}`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`Freshness failed: ${response.status}`);
        const payload = (await response.json()) as FreshnessPayload;
        const freshness = payload.screens?.[screen];
        if (!cancelled) {
          setLastUpdatedAt(freshness?.lastUpdatedAt ?? null);
          setSource(freshness?.source ?? null);
        }
      } catch {
        if (!cancelled) {
          setLastUpdatedAt(null);
          setSource(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadFreshness();

    return () => {
      cancelled = true;
    };
  }, [refreshKey, screen]);

  const value = loading
    ? "Checking..."
    : lastUpdatedAt
      ? formatPacificDateTime(lastUpdatedAt)
      : "Unknown";

  return (
    <div className="text-right text-xs leading-5 text-slate-500">
      <div>Last updated: {value}</div>
      {source ? <div className="text-slate-400">{source}</div> : null}
    </div>
  );
}

export function formatPacificDateTime(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";

  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}
