import { useCallback, useEffect, useState } from "react";

import type { PurchaseRow } from "./types";
import { rowKey } from "./utils";

export function usePurchases() {
  const [rows, setRows] = useState<PurchaseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPurchases = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/purchases", { cache: "no-store" });

      if (!response.ok) {
        throw new Error(`Failed to load purchases: ${response.status}`);
      }

      const data = await response.json();
      const purchases: PurchaseRow[] = Array.isArray(data)
        ? data
        : data.purchases || data.rows || [];

      setRows(purchases);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load purchases.");
    } finally {
      setLoading(false);
    }
  }, []);

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

        setRows((currentRows) =>
          currentRows.map((currentRow) => {
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
          })
        );

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

      setRows((currentRows) => [newRow, ...currentRows]);

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
    loading,
    savingKey,
    error,
    setError,
    loadPurchases,
    patchPurchase,
    createSplitItem,
  };
}
