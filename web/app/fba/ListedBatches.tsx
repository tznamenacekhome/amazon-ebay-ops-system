"use client";

import { useEffect, useState } from "react";
import type { ListingBatch } from "./ListingBatches";

export function ListedBatches({ onOpen, refreshKey }: {
  onOpen: (batch: ListingBatch) => void;
  refreshKey: number;
}) {
  const [rows, setRows] = useState<ListingBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch("/api/amazon-listing-batches", { cache: "no-store", signal: controller.signal });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Failed to load listing batches.");
        setRows(payload.rows);
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Failed to load listing batches.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [refreshKey]);

  async function open(id: string) {
    setOpening(id);
    setError(null);
    try {
      const response = await fetch(`/api/amazon-listing-batches?id=${encodeURIComponent(id)}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Failed to open listing batch.");
      onOpen(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open listing batch.");
    } finally {
      setOpening(null);
    }
  }

  return <section className="mb-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
    <div className="border-b px-3 py-2">
      <h2 className="font-semibold">FBA and MF listing batches</h2>
      <p className="text-xs text-slate-500">Latest 100 batches, including drafts and exports awaiting completion.</p>
    </div>
    {error && <p role="alert" className="px-3 py-2 text-sm text-red-700">{error}</p>}
    <table className="w-full text-left text-sm">
      <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>
        <th className="px-3 py-2">Method</th><th className="px-3 py-2">Batch</th><th className="px-3 py-2">Status</th>
        <th className="px-3 py-2 text-right">Selected units</th><th className="px-3 py-2 text-right">Exported units</th><th className="px-3 py-2 text-right">Listed units</th>
        <th className="px-3 py-2">Exported</th><th className="px-3 py-2">Completed</th><th className="px-3 py-2" />
      </tr></thead>
      <tbody>{loading ? <tr><td colSpan={9} className="px-3 py-6 text-center text-slate-500">Loading listing batches...</td></tr>
        : rows.length === 0 ? <tr><td colSpan={9} className="px-3 py-6 text-center text-slate-500">No listing batches found.</td></tr>
        : rows.map(row => <tr key={row.id} className="border-t border-slate-100">
          <td className="px-3 py-2 font-medium">{row.fulfillment_method}</td>
          <td className="px-3 py-2">{row.external_reference}</td>
          <td className="px-3 py-2 capitalize">{row.status.replaceAll("_", " ")}</td>
          <td className="px-3 py-2 text-right">{Object.values(row.selection).reduce((sum, quantity) => sum + Number(quantity || 0), 0)}</td>
          <td className="px-3 py-2 text-right">{row.allocations?.reduce((sum, allocation) => sum + allocation.quantity, 0) || 0}</td>
          <td className="px-3 py-2 text-right">{row.allocations?.reduce((sum, allocation) => sum + allocation.listed_quantity, 0) || 0}</td>
          <td className="px-3 py-2">{row.exported_at ? new Date(row.exported_at).toLocaleString() : "—"}</td>
          <td className="px-3 py-2">{row.completed_at ? new Date(row.completed_at).toLocaleString() : "—"}</td>
          <td className="px-3 py-2"><button type="button" disabled={opening !== null} onClick={() => void open(row.id)} className="rounded border border-slate-300 px-3 py-1 disabled:opacity-50">{opening === row.id ? "Opening..." : "Open"}</button></td>
        </tr>)}</tbody>
    </table>
  </section>;
}
