import { useCallback, useEffect, useState } from "react";

import type {
  PurchaseQuery,
  PurchaseRow,
  PurchaseStats,
  PurchasesApiResponse,
} from "./types";
import { rowKey } from "./utils";

const PURCHASE_CACHE_KEY = "mbop:purchases:v7";
const PURCHASE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

type PurchaseCache = {
  savedAt: number;
  response: PurchasesApiResponse;
};

type LoadPurchasesOptions = {
  forceRefresh?: boolean;
};

export function usePurchases(query: PurchaseQuery) {
  const [rows, setRows] = useState<PurchaseRow[]>([]);
  const [stats, setStats] = useState<PurchaseStats>({
    total: 0,
    visible: 0,
    needsReview: 0,
    delivered: 0,
  });
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cacheKey = `${PURCHASE_CACHE_KEY}:${buildQueryString(query)}`;

  const writeCache = useCallback((response: PurchasesApiResponse) => {
    if (typeof window === "undefined") return;

    try {
      const cache: PurchaseCache = {
        savedAt: Date.now(),
        response,
      };
      window.localStorage.setItem(cacheKey, JSON.stringify(cache));
    } catch {
      // Cache writes are best-effort only.
    }
  }, [cacheKey]);

  const readCache = useCallback(() => {
    if (typeof window === "undefined") return null;

    try {
      const rawCache = window.localStorage.getItem(cacheKey);
      if (!rawCache) return null;

      const cache = JSON.parse(rawCache) as PurchaseCache;

      if (!Array.isArray(cache.response?.rows) || !Number.isFinite(cache.savedAt)) {
        return null;
      }

      if (Date.now() - cache.savedAt > PURCHASE_CACHE_TTL_MS) {
        return null;
      }

      return cache.response;
    } catch {
      return null;
    }
  }, [cacheKey]);

  const loadPurchases = useCallback(async (options: LoadPurchasesOptions = {}) => {
    setLoading(true);
    setError(null);

    try {
      if (!options.forceRefresh) {
        const cachedRows = readCache();

        if (cachedRows) {
          applyResponse(cachedRows);
          setLoading(false);
          return;
        }
      }

      const response = await fetch(`/api/purchases?${buildQueryString(query)}`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Failed to load purchases: ${response.status}`);
      }

      const data = (await response.json()) as PurchasesApiResponse | PurchaseRow[];
      const apiResponse = normalizeResponse(data, query);

      applyResponse(apiResponse);
      writeCache(apiResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load purchases.");
    } finally {
      setLoading(false);
    }
  }, [query, readCache, writeCache]);

  useEffect(() => {
    // Initial client-side load for this operational workspace.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPurchases();
  }, [loadPurchases]);

  const patchPurchase = useCallback(
    async (row: PurchaseRow, updates: Partial<PurchaseRow>) => {
      const key = rowKey(row);
      setSavingKey(key);
      setError(null);

      try {
        const response = await fetch("/api/purchases", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            purchase_id: row.purchase_id,
            item_id: row.item_id,
            ...updates,
          }),
        });

        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || `Save failed: ${response.status}`);
        }

        const result = await response.json();
        const patchedRows: PurchaseRow[] = [
          result.item,
          ...(result.propagated_items ?? []),
        ].filter(Boolean);
        const patchedRowsByItemId = new Map(
          patchedRows
            .filter((patchedRow) => patchedRow.item_id)
            .map((patchedRow) => [patchedRow.item_id, patchedRow])
        );

        setRows((currentRows) => {
          const nextRows = currentRows.map((currentRow) => {
            const patchedRow = currentRow.item_id
              ? patchedRowsByItemId.get(currentRow.item_id)
              : null;

            if (patchedRow) {
              return {
                ...currentRow,
                ...patchedRow,
                sell_price:
                  "target_price" in patchedRow
                    ? patchedRow.target_price
                    : currentRow.sell_price,
              };
            }

            return rowKey(currentRow) === key
              ? { ...currentRow, ...updates }
              : currentRow;
          });

          return nextRows;
        });

        return {
          ...row,
          ...updates,
          ...(result.item ?? {}),
          sell_price:
            result.item && "target_price" in result.item
              ? result.item.target_price
              : updates.sell_price ?? row.sell_price,
        };
      } catch (err) {
        setError(err instanceof Error ? err.message : "Save failed.");
        return null;
      } finally {
        setSavingKey(null);
      }
    },
    []
  );

  const createSplitItem = useCallback(async (row: PurchaseRow) => {
    const key = rowKey(row);
    setSavingKey(key);
    setError(null);

    try {
      const response = await fetch("/api/purchases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_item_id: row.item_id,
          title: "Split item",
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Split item failed: ${response.status}`);
      }

      const result = await response.json();
      const item = result.item as PurchaseRow;
      const newRow = {
        ...row,
        ...item,
        ebay_title: item.title,
        amazon_title: null,
        asin: null,
        sell_price: null,
        target_price: null,
      };

      setRows((currentRows) => {
        const nextRows = [newRow, ...currentRows];
        return nextRows;
      });

      return newRow;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Split item failed.");
      return null;
    } finally {
      setSavingKey(null);
    }
  }, []);

  return {
    rows,
    stats,
    totalRows,
    loading,
    savingKey,
    error,
    setError,
    loadPurchases,
    patchPurchase,
    createSplitItem,
  };

  function applyResponse(response: PurchasesApiResponse) {
    const reportableRows = filterReportableRows(response.rows);
    setRows(reportableRows);
    setTotalRows(response.total);
    setStats(response.stats);
  }
}

function filterReportableRows(rows: PurchaseRow[]) {
  return rows.filter((row) => !row.exclude_from_purchase_reporting);
}

function normalizeResponse(
  data: PurchasesApiResponse | PurchaseRow[],
  query: PurchaseQuery
): PurchasesApiResponse {
  if (Array.isArray(data)) {
    return {
      rows: data,
      total: data.length,
      page: query.page,
      pageSize: query.pageSize,
      stats: {
        total: data.length,
        visible: data.length,
        needsReview: 0,
        delivered: 0,
      },
    };
  }

  return data;
}

function buildQueryString(query: PurchaseQuery) {
  const params = new URLSearchParams({
    search: query.searchText,
    asinFilter: query.asinFilter,
    statusFilter: query.statusFilter,
    sortColumn: query.sortColumn,
    sortDirection: query.sortDirection,
    page: String(query.page),
    pageSize: String(query.pageSize),
  });

  return params.toString();
}
