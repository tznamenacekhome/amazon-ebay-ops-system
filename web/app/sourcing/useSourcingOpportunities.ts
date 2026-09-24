"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { sourcingResources } from "./sourcingResourceCache";
import type { SourcingBatch, SourcingOpportunity } from "./types";

export function useSourcingOpportunities(
  status: string,
  type: string,
  searchText: string,
  sourceMode: string,
  scope = "all_open",
  inventoryFilter = "all",
  enabled = true,
  exclusionReason = "all",
) {
  const [rows, setRows] = useState<SourcingOpportunity[]>([]);
  const [businessSuppressions,setBusinessSuppressions]=useState<Array<{asin:string;current_velocity:number|null;required_velocity:number|null;last_evaluated_at:string|null}>>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [batch, setBatch] = useState<SourcingBatch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exclusionOptions, setExclusionOptions] = useState<Array<{code: string; label: string; count: number}>>([]);
  const [freshnessError, setFreshnessError] = useState<string | null>(null);
  useEffect(() => {
    const update = () => setFreshnessError(sourcingResources.getFreshnessError());
    update();
    return sourcingResources.subscribeFreshness(update);
  }, []);

  const request = useRef<AbortController | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(searchText);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchText), 250);
    return () => clearTimeout(timer);
  }, [searchText]);

  const load = useCallback(async (force = false, background = false) => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    if (force) sourcingResources.invalidate();
    if (!enabled) { setLoading(false); return; }
    if (!background) setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ status, type, limit: scope === "closest_excluded" ? "50" : "150" });
      params.set("scope", scope);
      params.set("format", "list");
      if (sourceMode !== "all") params.set("sourceMode", sourceMode);
      if (inventoryFilter !== "all") params.set("inventoryFilter", inventoryFilter);
      if (scope === "closest_excluded" && exclusionReason !== "all") params.set("exclusionReason", exclusionReason);
      if (debouncedSearch.trim()) params.set("q", debouncedSearch.trim());
      const response = await sourcingResources.get(`/api/sourcing/opportunities?${params}`, { fresh: force });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to load sourcing opportunities.");
      if (controller.signal.aborted) return;
      setRows(payload.opportunities ?? []);
      setBusinessSuppressions(payload.businessSuppressions ?? []);
      setSummary(payload.summary ?? {});
      setExclusionOptions(payload.exclusionOptions ?? []);
      setBatch(payload.batch ?? null);
      if (status === "open" && scope !== "closest_excluded" && payload.cacheVersion !== null) sourcingResources.prefetchAfterBuyList();
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Failed to load sourcing opportunities.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [inventoryFilter, scope, debouncedSearch, sourceMode, status, type, enabled, exclusionReason]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const unsubscribe = sourcingResources.subscribe(() => { void load(false, true); });
    return () => { request.current?.abort(); unsubscribe(); };
  }, [load]);
  const reload = useCallback(() => load(true), [load]);
  const refreshInBackground = useCallback(() => load(true, true), [load]);

  const removeRows = useCallback((opportunityIds: string[]) => {
    sourcingResources.invalidate();
    const ids = new Set(opportunityIds);
    // API summary counts cover the full qualified set, not just displayed rows.
    // Keep those authoritative counts until the post-action reload completes.
    setRows(currentRows => currentRows.filter(row => !ids.has(row.opportunityId)));
  }, []);

  return { rows, businessSuppressions, summary, batch, loading, error, freshnessError, exclusionOptions, reload, refreshInBackground, removeRows, setError };
}
