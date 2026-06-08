"use client";

import { useCallback, useEffect, useState } from "react";
import type { SourcingOpportunity } from "./types";

export function useSourcingOpportunities(status: string, type: string, searchText: string, sourceMode: string) {
  const [rows, setRows] = useState<SourcingOpportunity[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status, type, limit: "150" });
      if (sourceMode !== "all") params.set("sourceMode", sourceMode);
      if (searchText.trim()) params.set("q", searchText.trim());
      const response = await fetch(`/api/sourcing/opportunities?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to load sourcing opportunities.");
      setRows(payload.opportunities ?? []);
      setSummary(payload.summary ?? {});
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

  return { rows, summary, loading, error, reload: load, setError };
}
