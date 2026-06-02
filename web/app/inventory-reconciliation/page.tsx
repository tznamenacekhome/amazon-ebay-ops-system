"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";
import { DataFreshness } from "../DataFreshness";

type ReconciliationFinding = {
  id: string;
  severity: "info" | "warning" | "critical";
  issue_label: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  mbop_quantity: number | null;
  amazon_total_quantity: number | null;
};

type ReconciliationData = {
  inventoryVisibility: {
    latestReconciliation: {
      reconciliation_type: string;
      status: string;
      completed_at: string | null;
    } | null;
    reconciliationBySeverity: {
      critical: number;
      warning: number;
      info: number;
    };
    openFindings: ReconciliationFinding[];
  };
};

export default function InventoryReconciliationPage() {
  const [data, setData] = useState<ReconciliationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);
  const [freshnessKey, setFreshnessKey] = useState(0);

  useEffect(() => {
    loadReconciliation();
  }, []);

  async function loadReconciliation() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/dashboard/purchases", { cache: "no-store" });
      if (!response.ok) throw new Error(`Failed to load reconciliation: ${response.status}`);
      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reconciliation.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshReconciliation() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("inventory-reconciliation", loadReconciliation, setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  const latest = data?.inventoryVisibility.latestReconciliation;
  const severity = data?.inventoryVisibility.reconciliationBySeverity;

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inventory Reconciliation</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Open findings compare MBOP inventory-position projections against external inventory snapshots, currently Amazon FBA.
            Treat these as investigation prompts: confirm the source snapshot, then correct workflow state, mapping, or external inventory as appropriate.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="inventory-reconciliation" refreshKey={freshnessKey} />
          <button
            onClick={refreshReconciliation}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {refreshNotice && (
        <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${noticeClass(refreshNotice.tone)}`}>
          {refreshNotice.text}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="mb-4 grid gap-3 md:grid-cols-4">
        <Summary label="Latest run" value={latest?.completed_at ? formatDateTime(latest.completed_at) : "--"} />
        <Summary label="Critical" value={formatNumber(severity?.critical)} />
        <Summary label="Warning" value={formatNumber(severity?.warning)} />
        <Summary label="Info" value={formatNumber(severity?.info)} />
      </section>

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-base font-semibold">How To Address</h2>
        <div className="mt-2 grid gap-3 text-sm text-slate-600 md:grid-cols-3">
          <div>
            <div className="font-medium text-slate-800">MBOP missing from Amazon</div>
            <p>Confirm whether the item is still received, in FBA prep, sold, or transferred to eBay. Update the owning workflow, not the reconciliation row.</p>
          </div>
          <div>
            <div className="font-medium text-slate-800">Amazon unknown to MBOP</div>
            <p>Usually legacy FBA inventory, SKU mapping gaps, or opening-balance inventory. Confirm ASIN/SKU and add mapping/backfill context if needed.</p>
          </div>
          <div>
            <div className="font-medium text-slate-800">Unsellable / non-buyable</div>
            <p>Review Seller Central when units are damaged, unsellable, or not available for sale. Listing catalog issues are ignored when your FBA units are sellable.</p>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-sm font-medium uppercase tracking-wide text-slate-500">Open Findings</div>
          <h2 className="mt-1 text-lg font-semibold">Current Reconciliation Work Queue</h2>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Issue</th>
              <th className="px-3 py-2">ASIN / SKU</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2 text-right">MBOP</th>
              <th className="px-3 py-2 text-right">Amazon</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={5}>
                  Loading reconciliation findings...
                </td>
              </tr>
            ) : data?.inventoryVisibility.openFindings.length ? (
              data.inventoryVisibility.openFindings.map((finding) => (
                <tr key={finding.id} className="border-t border-slate-100">
                  <td className="px-3 py-2">
                    <div className="font-medium">{finding.issue_label}</div>
                    <div className="text-xs uppercase text-slate-500">{finding.severity}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{finding.asin || "--"}</div>
                    <div className="text-xs text-slate-500">{finding.seller_sku || "--"}</div>
                  </td>
                  <td className="max-w-[520px] truncate px-3 py-2">{finding.title || "--"}</td>
                  <td className="px-3 py-2 text-right">{formatNumber(finding.mbop_quantity)}</td>
                  <td className="px-3 py-2 text-right">{formatNumber(finding.amazon_total_quantity)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={5}>
                  No open reconciliation findings.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US");
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
