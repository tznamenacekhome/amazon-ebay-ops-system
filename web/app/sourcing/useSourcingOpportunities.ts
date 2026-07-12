"use client";

import { useCallback, useEffect, useState } from "react";
import type { SourcingBatch, SourcingOpportunity } from "./types";

export function useSourcingOpportunities(status: string, type: string, searchText: string, sourceMode: string) {
  const [rows, setRows] = useState<SourcingOpportunity[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [batch, setBatch] = useState<SourcingBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status, type, limit: "150" });
      if (sourceMode !== "all") params.set("sourceMode", sourceMode);
      if (searchText.trim()) params.set("q", searchText.trim());
      params.set("_", String(Date.now()));
      const response = await fetch(`/api/sourcing/opportunities?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to load sourcing opportunities.");
      setRows(payload.opportunities ?? []);
      setSummary(payload.summary ?? {});
      setBatch(payload.batch ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sourcing opportunities.");
    } finally {
      setLoading(false);
    }
  }, [searchText, sourceMode, status, type]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const removeRows = useCallback((opportunityIds: string[]) => {
    const ids = new Set(opportunityIds);
    setRows((currentRows) => {
      const nextRows = currentRows.filter((row) => !ids.has(row.opportunityId));
      setSummary(summarizeRows(nextRows));
      return nextRows;
    });
  }, []);

  return { rows, summary, batch, loading, error, reload: load, removeRows, setError };
}

function summarizeRows(rows: SourcingOpportunity[]) {
  return {
    total: rows.length,
    buyNow: rows.filter((row) => row.opportunityType === "buy_now").length,
    bestOffer: rows.filter((row) => row.opportunityType === "best_offer").length,
    auction: rows.filter((row) => row.opportunityType === "auction").length,
    multiUnit: rows.filter((row) => row.opportunityType === "multi_unit").length,
  };
}
