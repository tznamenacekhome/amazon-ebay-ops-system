"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SourcingBatch, SourcingOpportunity } from "./types";

export function useSourcingOpportunities(
  status: string,
  type: string,
  searchText: string,
  sourceMode: string,
  scope = "all_open",
  inventoryFilter = "all",
  enabled = true,
) {
  const [rows, setRows] = useState<SourcingOpportunity[]>([]);
  const [businessSuppressions,setBusinessSuppressions]=useState<Array<{asin:string;current_velocity:number|null;required_velocity:number|null;last_evaluated_at:string|null}>>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [batch, setBatch] = useState<SourcingBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cache = useRef(new Map<string, { savedAt: number; payload: {
    opportunities?: SourcingOpportunity[];
    businessSuppressions?: typeof businessSuppressions;
    summary?: Record<string, number>;
    batch?: SourcingBatch | null;
  } }>());
  const request = useRef<AbortController | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(searchText);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchText), 250);
    return () => clearTimeout(timer);
  }, [searchText]);

  const load = useCallback(async (force = false) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    if (force) cache.current.clear();
    if (!enabled) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status, type, limit: scope === "closest_excluded" ? "50" : "150" });
      params.set("scope", scope);
      if (sourceMode !== "all") params.set("sourceMode", sourceMode);
      if (inventoryFilter !== "all") params.set("inventoryFilter", inventoryFilter);
      if (debouncedSearch.trim()) params.set("q", debouncedSearch.trim());
      const key = params.toString();
      const cached = cache.current.get(key);
      const apply = (payload: NonNullable<typeof cached>["payload"]) => {
        setRows(payload.opportunities ?? []);
        setBusinessSuppressions(payload.businessSuppressions ?? []);
        setSummary(payload.summary ?? {});
        setBatch(payload.batch ?? null);
      };
      // A short, hook-local cache makes return visits instant. Every mutation reload
      // invalidates every tab; nothing is shared across users or browser sessions.
      if (cached && Date.now() - cached.savedAt < 15_000) { apply(cached.payload); return; }
      setRows([]);
      const response = await fetch(`/api/sourcing/opportunities?${params.toString()}`, { cache: "no-store", signal: controller.signal });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to load sourcing opportunities.");
      if (controller.signal.aborted) return;
      if (cache.current.size >= 8) cache.current.delete(cache.current.keys().next().value!);
      cache.current.set(key, { savedAt: Date.now(), payload });
      apply(payload);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Failed to load sourcing opportunities.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [inventoryFilter, scope, debouncedSearch, sourceMode, status, type, enabled]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    return () => request.current?.abort();
  }, [load]);
  const reload = useCallback(() => load(true), [load]);

  const removeRows = useCallback((opportunityIds: string[]) => {
    cache.current.clear();
    const ids = new Set(opportunityIds);
    setRows((currentRows) => {
      const nextRows = currentRows.filter((row) => !ids.has(row.opportunityId));
      setSummary(summarizeRows(nextRows));
      return nextRows;
    });
  }, []);

  return { rows, businessSuppressions, summary, batch, loading, error, reload, removeRows, setError };
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
