"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  Ban,
  Clipboard,
  Eye,
  RefreshCw,
  Search,
  ShoppingBag,
} from "lucide-react";
import type { SourcingBatch, SourcingOpportunity, SourcingRun, SourcingSettings } from "./types";
import { useSourcingOpportunities } from "./useSourcingOpportunities";
import { dismissReasonGroups } from "./matchingTaxonomy";
import { mutationHeaders } from "../mutationHeaders";

const tabs = ["Replenishment", "Coverage Cycle", "Watchlist", "Purchased Pending Match", "Sourcing History", "Matching Intelligence", "Settings"] as const;
const opportunityTypes = ["all", "buy_now", "multi_unit", "best_offer", "auction", "watch"] as const;
const GIXEN_URL = "https://www.gixen.com/main/index.php";
type SourcingActionPayload = {
  actionType: string;
  reason?: string;
  notes?: string;
  imageClues?: string[];
  requiredMaxLandedCost?: number;
  requiredRoiPercent?: number;
  expectedPurchaseCost?: number;
};

export default function SourcingPage() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("Replenishment");
  const [status, setStatus] = useState("open");
  const [type, setType] = useState("all");
  const [sourceMode, setSourceMode] = useState("all");
  const [searchText, setSearchText] = useState("");
  const effectiveStatus =
    activeTab === "Watchlist"
      ? "watching"
      : activeTab === "Purchased Pending Match"
        ? "purchased_pending_match"
        : status;
  const { rows, summary, batch, loading, error, reload, removeRows, setError } = useSourcingOpportunities(
    effectiveStatus,
    type,
    searchText,
    sourceMode,
  );
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [dismissRow, setDismissRow] = useState<SourcingOpportunity | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDismissOpen, setBulkDismissOpen] = useState(false);
  const [sourcingRefreshRunning, setSourcingRefreshRunning] = useState(false);
  const [batchContinueRunning, setBatchContinueRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const visibleRows = useMemo(() => {
    if (activeTab === "Purchased Pending Match") return rows.filter((row) => row.status === "purchased_pending_match");
    if (activeTab === "Replenishment" || activeTab === "Watchlist") return rows;
    return [];
  }, [activeTab, rows]);
  const selectedRows = useMemo(
    () => visibleRows.filter((row) => selectedIds.has(row.opportunityId)),
    [selectedIds, visibleRows],
  );

  async function act(row: SourcingOpportunity, payload: SourcingActionPayload) {
    setActionBusyId(row.opportunityId);
    setError(null);
    try {
      const response = await fetch(`/api/sourcing/opportunities/${row.opportunityId}/actions`, {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Action failed.");
      removeRows([row.opportunityId]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
      } finally {
      setActionBusyId(null);
    }
  }

  async function bulkAct(rowsToUpdate: SourcingOpportunity[], payloadForRow: (row: SourcingOpportunity) => SourcingActionPayload) {
    if (!rowsToUpdate.length) return;
    setActionBusyId("bulk");
    setError(null);
    try {
      for (const row of rowsToUpdate) {
        const response = await fetch(`/api/sourcing/opportunities/${row.opportunityId}/actions`, {
          method: "POST",
          headers: mutationHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payloadForRow(row)),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error ?? "Action failed.");
      }
      setSelectedIds(new Set());
      removeRows(rowsToUpdate.map((row) => row.opportunityId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk action failed.");
    } finally {
      setActionBusyId(null);
    }
  }

  async function refreshSourcingWorkflow() {
    setSourcingRefreshRunning(true);
    setError(null);
    setNotice("Starting unified sourcing coverage cycle...");
    try {
      const response = await fetch("/api/sourcing/runs", {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ execute: true }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Sourcing workflow failed.");
      const startedAwsTask = payload.executionMode === "aws-ecs" || payload.status === "started";
      setSelectedIds(new Set());
      await reload();
      setNotice(
        startedAwsTask
          ? "AWS sourcing coverage task started. Opportunities refresh after the ECS task finishes."
          : "Sourcing coverage run complete. Loaded fresh opportunities.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sourcing workflow failed.");
      setNotice(null);
    } finally {
      setSourcingRefreshRunning(false);
    }
  }

  async function continueSourcingBatch() {
    setBatchContinueRunning(true);
    setError(null);
    setNotice("Starting unified sourcing coverage cycle for remaining quota...");
    try {
      const response = await fetch("/api/sourcing/runs", {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ execute: true }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to start sourcing coverage cycle.");
      const startedAwsTask = payload.executionMode === "aws-ecs" || payload.status === "started";
      await reload();
      setNotice(
        startedAwsTask
          ? "AWS sourcing coverage task started. It will check live eBay quota before spending calls."
          : "Sourcing coverage run complete. Loaded fresh opportunities.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start sourcing coverage cycle.");
      setNotice(null);
    } finally {
      setBatchContinueRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 p-5 text-slate-950">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Sourcing Workspace</h1>
          <p className="text-sm text-slate-600">
            Replenishment candidates from Amazon demand, eBay supply, and MBOP scoring.
          </p>
        </div>
        <button
          onClick={() => void refreshSourcingWorkflow()}
          disabled={sourcingRefreshRunning}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${loading || sourcingRefreshRunning ? "animate-spin" : ""}`} />
          {sourcingRefreshRunning ? "Running Sourcing" : "Run Sourcing"}
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2 border-b border-slate-300">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`border-b-2 px-3 py-2 text-sm font-medium ${
              activeTab === tab
                ? "border-slate-950 text-slate-950"
                : "border-transparent text-slate-500 hover:text-slate-900"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {notice ? <div className="mb-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">{notice}</div> : null}
      {error ? <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}

      {activeTab === "Sourcing History" ? (
        <SourcingHistory />
      ) : activeTab === "Coverage Cycle" ? (
        <CoverageCyclePanel />
      ) : activeTab === "Matching Intelligence" ? (
        <MatchingIntelligencePanel />
      ) : activeTab === "Settings" ? (
        <SourcingSettingsPanel onApplied={reload} />
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label="Open Rows" value={summary.total ?? visibleRows.length} />
            <Metric label="Buy Now" value={summary.buyNow ?? 0} />
            <Metric label="Best Offer" value={summary.bestOffer ?? 0} />
            <Metric label="Auction" value={summary.auction ?? 0} />
            <Metric label="Multi-Unit" value={summary.multiUnit ?? 0} />
          </div>
          {activeTab === "Replenishment" ? (
            <BatchStatus batch={batch} busy={batchContinueRunning} onContinue={() => void continueSourcingBatch()} />
          ) : null}

          <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white p-2 shadow-sm">
            <div className="relative min-w-80 flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                className="h-9 w-full rounded-md border border-slate-300 pl-9 pr-3 text-sm outline-none focus:border-slate-500"
                placeholder="Search ASIN, Amazon title, or eBay title"
              />
            </div>
            {activeTab === "Replenishment" ? (
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
              >
                <option value="open">Open</option>
                <option value="all">All</option>
                <option value="rejected">Rejected</option>
                <option value="dismissed">Dismissed</option>
                <option value="roi_snoozed">ROI Snoozed</option>
              </select>
            ) : null}
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            >
              {opportunityTypes.map((value) => (
                <option key={value} value={value}>
                  {label(value)}
                </option>
              ))}
            </select>
            <select
              value={sourceMode}
              onChange={(event) => setSourceMode(event.target.value)}
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            >
              <option value="all">All Sources</option>
              <option value="1_recently_sold">Coverage: Recently Sold</option>
              <option value="2_purchased_not_sent">Coverage: Purchased Not Sent</option>
              <option value="3_catalog_remaining">Coverage: Catalog Remaining</option>
              <option value="recent_sales">Recently Sold</option>
              <option value="full_listings">All Listings</option>
            </select>
          </div>

          <ReplenishmentTable
            rows={visibleRows}
            loading={loading}
            actionBusyId={actionBusyId}
            selectedIds={selectedIds}
            selectedCount={selectedRows.length}
            onAction={act}
            onBulkWatch={() => void bulkAct(selectedRows, watchPayload)}
            onBulkPurchased={() => void bulkAct(selectedRows, (row) => ({ actionType: "purchased", expectedPurchaseCost: row.landedCost ?? undefined }))}
            onBulkDismiss={() => setBulkDismissOpen(true)}
            onToggleSelected={(row) => {
              setSelectedIds((current) => {
                const next = new Set(current);
                if (next.has(row.opportunityId)) next.delete(row.opportunityId);
                else next.add(row.opportunityId);
                return next;
              });
            }}
            onToggleAll={() => {
              setSelectedIds((current) => {
                const visibleIds = visibleRows.map((row) => row.opportunityId);
                const allSelected = visibleIds.length > 0 && visibleIds.every((id) => current.has(id));
                return allSelected ? new Set() : new Set(visibleIds);
              });
            }}
            onDismiss={setDismissRow}
            purchasedMode={activeTab === "Purchased Pending Match"}
          />
          {dismissRow ? (
            <DismissOpportunityDialog
              row={dismissRow}
              actionBusyId={actionBusyId}
              onClose={() => setDismissRow(null)}
              onBlockAsin={async (notes, imageClues) => {
                await act(dismissRow, { actionType: "block_asin", notes, imageClues });
                setDismissRow(null);
              }}
              onDismiss={async (reason, notes, imageClues) => {
                await act(dismissRow, { actionType: "dismiss", reason, notes, imageClues });
                setDismissRow(null);
              }}
            />
          ) : null}
          {bulkDismissOpen ? (
            <BulkDismissOpportunityDialog
              rows={selectedRows}
              busy={actionBusyId === "bulk"}
              onClose={() => setBulkDismissOpen(false)}
              onBlockAsins={async (notes, imageClues) => {
                await bulkAct(selectedRows, () => ({ actionType: "block_asin", notes, imageClues }));
                setBulkDismissOpen(false);
              }}
              onDismiss={async (reason, notes, imageClues) => {
                await bulkAct(selectedRows, () => ({ actionType: "dismiss", reason, notes, imageClues }));
                setBulkDismissOpen(false);
              }}
            />
          ) : null}
        </>
      )}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
    </div>
  );
}

function BatchStatus({ batch, busy, onContinue }: { batch: SourcingBatch | null; busy: boolean; onContinue: () => void }) {
  if (!batch) return null;
  const funnel = batch.funnel_json && typeof batch.funnel_json === "object" ? batch.funnel_json as Record<string, unknown> : {};
  const canContinue = (batch.seeds_remaining ?? 0) > 0;
  const budgetMode = (batch.requested_opportunity_count ?? 0) === 0;
  const quota = typeof funnel.ebay_browse_quota === "object" && funnel.ebay_browse_quota !== null ? funnel.ebay_browse_quota as Record<string, unknown> : null;
  const quotaRemaining = typeof quota?.remaining === "number" ? quota.remaining : null;
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-700">
        <span className="font-medium text-slate-900">Batch {batch.batch_sequence ?? "--"}</span>
        <span>{budgetMode ? `${batch.qualifying_opportunity_count ?? 0} current rows` : `${batch.qualifying_opportunity_count ?? 0}/${batch.requested_opportunity_count ?? 100} current rows`}</span>
        <span>{batch.cumulative_qualifying_count ?? 0} cumulative</span>
        <span>{batch.cumulative_seeds_searched ?? 0} seeds searched</span>
        {typeof batch.api_call_count === "number" ? <span>{batch.api_call_count} Browse calls</span> : null}
        {quotaRemaining !== null ? <span>{quotaRemaining} quota remaining at start</span> : null}
        <span>{batch.seeds_remaining ?? 0} remaining</span>
        {typeof funnel.hard_blocked_opportunities === "number" ? <span>{funnel.hard_blocked_opportunities} blocked</span> : null}
        {batch.stop_reason ? <span>{label(batch.stop_reason)}</span> : null}
      </div>
      <button
        type="button"
        onClick={onContinue}
        disabled={busy || !canContinue}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
        {busy ? "Starting" : "Spend Remaining Quota"}
      </button>
    </div>
  );
}

function ReplenishmentTable({
  rows,
  loading,
  actionBusyId,
  selectedIds,
  selectedCount,
  onAction,
  onBulkWatch,
  onBulkPurchased,
  onBulkDismiss,
  onToggleSelected,
  onToggleAll,
  onDismiss,
  purchasedMode,
}: {
  rows: SourcingOpportunity[];
  loading: boolean;
  actionBusyId: string | null;
  selectedIds: Set<string>;
  selectedCount: number;
  onAction: (row: SourcingOpportunity, payload: SourcingActionPayload) => Promise<void>;
  onBulkWatch: () => void;
  onBulkPurchased: () => void;
  onBulkDismiss: () => void;
  onToggleSelected: (row: SourcingOpportunity) => void;
  onToggleAll: () => void;
  onDismiss: (row: SourcingOpportunity) => void;
  purchasedMode: boolean;
}) {
  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.has(row.opportunityId));
  const bulkDisabled = selectedCount === 0 || actionBusyId === "bulk";

  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="max-h-[calc(100vh-250px)] overflow-auto">
        <table className="min-w-[112rem] table-fixed text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th colSpan={14} className="border-b border-slate-200 bg-white px-2 py-2">
                <div className="flex flex-wrap items-center gap-2 normal-case tracking-normal">
                  <span className="text-sm font-medium text-slate-700">{selectedCount} selected</span>
                  {!purchasedMode ? (
                    <>
                      <button disabled={bulkDisabled} onClick={onBulkWatch} className="bulk-button">Watch selected</button>
                      <button disabled={bulkDisabled} onClick={onBulkPurchased} className="bulk-button">Mark selected purchased / offer made</button>
                      <button disabled={bulkDisabled} onClick={onBulkDismiss} className="bulk-button-danger">Dismiss selected</button>
                    </>
                  ) : null}
                </div>
              </th>
            </tr>
            <tr>
              <th className="w-10 px-2 py-2">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  aria-label="Select all visible sourcing rows"
                  className="sourcing-checkbox"
                />
              </th>
              <th className="w-36 px-3 py-2">eBay</th>
              <th className="w-36 px-3 py-2">Amazon</th>
              <th className="w-[26rem] px-2 py-2">Opportunity</th>
              <th className="w-24 px-2 py-2">Cost</th>
              <th className="w-24 px-2 py-2">Last Sold</th>
              <th className="w-24 px-2 py-2">Keepa 90</th>
              <th className="w-24 px-2 py-2">Keepa Now</th>
              <th className="w-24 px-2 py-2">Profit</th>
              <th className="w-16 px-2 py-2">ROI</th>
              <th className="w-24 px-2 py-2">Velocity</th>
              <th className="w-32 px-2 py-2">Type</th>
              <th className="w-40 px-2 py-2">Flags</th>
              <th className="w-60 px-2 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={14} className="px-3 py-8 text-center text-slate-500">Loading sourcing rows...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={14} className="px-3 py-8 text-center text-slate-500">No sourcing rows found for this view.</td></tr>
            ) : (
              rows.map((row) => (
                <tr key={row.opportunityId} className="align-top hover:bg-slate-50">
                  <td className="px-2 py-2 align-middle">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(row.opportunityId)}
                      onChange={() => onToggleSelected(row)}
                      aria-label={`Select ${row.ebayTitle}`}
                      className="sourcing-checkbox"
                    />
                  </td>
                  <td className="px-3 py-2">
                    {row.ebayImageUrl ? (
                      <OptionalImageLink href={row.ebayUrl}>
                        <SourcingThumbnail src={row.ebayImageUrl} />
                      </OptionalImageLink>
                    ) : (
                      <OptionalImageLink href={row.ebayUrl}>
                        <SourcingThumbnail />
                      </OptionalImageLink>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {row.amazonImageUrl ? (
                      <OptionalImageLink href={row.amazonUrl}>
                        <SourcingThumbnail src={row.amazonImageUrl} />
                      </OptionalImageLink>
                    ) : (
                      <SourcingThumbnail />
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="font-medium text-slate-950">{row.ebayTitle}</div>
                    <div className="mt-1 text-sm text-slate-600">
                      <span>{row.amazonTitle}</span>{" "}
                      <Link href={row.amazonUrl} target="_blank" className="font-medium text-blue-700 hover:underline">
                        {row.asin}
                      </Link>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>{row.sellerUsername ?? "unknown seller"}</span>
                      <span>{row.conditionName ?? "condition unknown"}</span>
                      <span>{row.itemLocationCountry ?? "location unknown"}</span>
                      <span>qty {row.quantityAvailable ?? "--"}</span>
                    </div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <CostCell row={row} />
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium">{money(row.lastSalePrice)}</div>
                    <div className="text-xs text-slate-500">{dateOnly(row.lastSoldAt)}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium">{money(row.keepaAvg90Price)}</div>
                    <div className="text-xs text-slate-500">{row.keepaAvg90Label ?? "--"}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium">{money(row.keepaCurrentPrice)}</div>
                    <div className="text-xs text-slate-500">{row.keepaCurrentPriceLabel ?? "--"}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className={
                      row.estimatedProfit === null
                        ? "font-medium text-slate-500"
                        : row.estimatedProfit < 0
                          ? "font-medium text-red-700"
                          : "font-medium text-emerald-700"
                    }>
                      {money(row.estimatedProfit)}
                    </div>
                    <div className="text-xs text-slate-500">total {money(row.totalProfitOpportunity)}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">{percent(row.estimatedRoiPercent)}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div>{number(row.monthlyVelocity)}/mo</div>
                    <div className="text-xs text-slate-500">{row.currentInventoryUnits ?? 0} on hand</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <OpportunityTypeCell row={row} />
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-col items-start gap-1">
                      {row.aiFlags.length ? row.aiFlags.map((flag) => <span key={flag} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">{flag}</span>) : <span className="text-xs text-slate-400">None</span>}
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <div className="grid grid-cols-4 gap-1">
                      {row.opportunityType === "auction" && row.ebayItemId ? (
                        <button
                          onClick={() => void navigator.clipboard.writeText(row.ebayItemId ?? "")}
                          className="icon-button"
                          title="Copy item ID for Gixen"
                        >
                          <Clipboard className="h-4 w-4" />
                        </button>
                      ) : null}
                      {!purchasedMode ? (
                        <>
                          <button disabled={actionBusyId === row.opportunityId} onClick={() => void onAction(row, watchPayload(row))} className="icon-button" title="Watch">
                            <Eye className="h-4 w-4" />
                          </button>
                          <button disabled={actionBusyId === row.opportunityId} onClick={() => void onAction(row, { actionType: "purchased", expectedPurchaseCost: row.landedCost ?? undefined })} className="icon-button" title="Purchased / offer made">
                            <ShoppingBag className="h-4 w-4" />
                          </button>
                          <button disabled={actionBusyId === row.opportunityId} onClick={() => onDismiss(row)} className="icon-button" title="Dismiss">
                            <Ban className="h-4 w-4" />
                          </button>
                        </>
                      ) : (
                        <span className="text-xs text-slate-500">Waiting for eBay import match</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <style jsx>{`
        .icon-button {
          display: inline-flex;
          height: 2.75rem;
          width: 2.75rem;
          align-items: center;
          justify-content: center;
          border-radius: 0.375rem;
          border: 1px solid rgb(203 213 225);
          color: rgb(71 85 105);
          background: white;
        }
        .icon-button:hover {
          background: rgb(248 250 252);
          color: rgb(15 23 42);
        }
        .sourcing-checkbox {
          height: 1.5rem;
          width: 1.5rem;
          cursor: pointer;
          accent-color: rgb(15 23 42);
        }
        .bulk-button,
        .bulk-button-danger {
          height: 2rem;
          border-radius: 0.375rem;
          border: 1px solid rgb(203 213 225);
          background: white;
          padding: 0 0.75rem;
          font-size: 0.875rem;
          font-weight: 500;
          color: rgb(51 65 85);
        }
        .bulk-button:hover {
          background: rgb(248 250 252);
          color: rgb(15 23 42);
        }
        .bulk-button-danger {
          border-color: rgb(254 202 202);
          background: rgb(254 242 242);
          color: rgb(185 28 28);
        }
        .bulk-button-danger:hover {
          background: rgb(254 226 226);
        }
        .bulk-button:disabled,
        .bulk-button-danger:disabled {
          cursor: not-allowed;
          opacity: 0.5;
        }
      `}</style>
    </div>
  );
}

function CostCell({ row }: { row: SourcingOpportunity }) {
  const originalCostLabel = originalCurrencyCostLabel(row);
  if (row.shippingQuoteStatus === "unknown_no_cost" || row.shippingQuoteStatus === "unknown_no_options") {
    return (
      <div>
        <div className="font-medium text-slate-500">Needs quote</div>
        <div className="text-xs text-slate-500">Item {money(row.itemPrice)}</div>
        {originalCostLabel ? <div className="text-xs text-slate-500">{originalCostLabel}</div> : null}
        <div className="text-xs font-medium text-amber-700">{row.shippingQuoteLabel}</div>
      </div>
    );
  }

  return (
    <div>
      <div className="font-medium">{money(row.landedCost)}</div>
      <div className="text-xs text-slate-500">
        {row.shippingQuoteStatus === "known_free" ? "Free shipping" : `Shipping ${money(row.shippingPrice)}`}
      </div>
      {originalCostLabel ? <div className="text-xs text-slate-500">{originalCostLabel}</div> : null}
    </div>
  );
}

function OpportunityTypeCell({ row }: { row: SourcingOpportunity }) {
  if (row.opportunityType === "auction" && row.ebayItemId) {
    return (
      <div>
        <Link
          href={GIXEN_URL}
          target="_blank"
          onClick={() => void navigator.clipboard.writeText(legacyItemId(row.ebayItemId ?? ""))}
          className="font-medium text-blue-700 hover:underline"
          title="Open Gixen and copy eBay item number"
        >
          Auction
        </Link>
        <AmountLine label="max bid" row={row} amountUsd={row.suggestedMaxBid} />
      </div>
    );
  }

  if (row.opportunityType === "best_offer") {
    return (
      <div>
        <div>{label(row.opportunityType ?? "")}</div>
        <AmountLine label="max offer" row={row} amountUsd={row.suggestedOfferPrice} />
        <div className="text-xs text-slate-500">{percent(row.requiredOfferPercentOfAsk)} of ask</div>
        <div className="text-xs text-slate-500">landed cap {money(row.maxProfitableLandedCost)}</div>
      </div>
    );
  }

  return <div>{label(row.opportunityType ?? "")}</div>;
}

function AmountLine({ label: lineLabel, row, amountUsd }: { label: string; row: SourcingOpportunity; amountUsd: number | null | undefined }) {
  return <div className="text-xs text-slate-500">{lineLabel} {offerBidAmountLabel(row, amountUsd)}</div>;
}

function DismissOpportunityDialog({
  row,
  actionBusyId,
  onClose,
  onBlockAsin,
  onDismiss,
}: {
  row: SourcingOpportunity;
  actionBusyId: string | null;
  onClose: () => void;
  onBlockAsin: (notes: string, imageClues: string[]) => Promise<void>;
  onDismiss: (reason: string, notes: string, imageClues: string[]) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [imageClues, setImageClues] = useState<string[]>([]);
  const busy = actionBusyId === row.opportunityId;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20 p-4">
      <div className="w-full max-w-lg rounded-md border border-slate-200 bg-white shadow-2xl">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dismiss Opportunity</div>
          <div className="mt-1 text-sm font-medium text-slate-950">{row.ebayTitle}</div>
          <div className="mt-1 font-mono text-xs text-slate-500">{row.asin}</div>
        </div>
        <div className="space-y-3 px-4 py-4">
          <label className="block text-sm font-medium text-slate-700">
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-24 w-full rounded-md border border-slate-300 p-2 text-sm" />
          </label>
          <ImageClueButtons selected={imageClues} onChange={setImageClues} />
          <div className="rounded-md border border-red-200 bg-red-50 p-3">
            <div className="text-sm font-medium text-red-900">Block this ASIN from sourcing</div>
            <div className="mt-1 text-xs text-red-700">
              Use this when the Amazon ASIN itself should not be replenished, even if similar listings appear again.
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={() => void onBlockAsin(notes, imageClues)}
              className="mt-3 inline-flex h-9 items-center gap-2 rounded-md border border-red-300 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Ban className="h-4 w-4" />
              Block ASIN
            </button>
          </div>
          <DismissReasonButtons
            busy={busy}
            onChoose={(reason) => void onDismiss(reason, notes, imageClues)}
          />
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button onClick={onClose} disabled={busy} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function BulkDismissOpportunityDialog({
  rows,
  busy,
  onClose,
  onBlockAsins,
  onDismiss,
}: {
  rows: SourcingOpportunity[];
  busy: boolean;
  onClose: () => void;
  onBlockAsins: (notes: string, imageClues: string[]) => Promise<void>;
  onDismiss: (reason: string, notes: string, imageClues: string[]) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [imageClues, setImageClues] = useState<string[]>([]);
  const uniqueAsinCount = new Set(rows.map((row) => row.asin).filter(Boolean)).size;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20 p-4">
      <div className="w-full max-w-lg rounded-md border border-slate-200 bg-white shadow-2xl">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dismiss Selected</div>
          <div className="mt-1 text-sm font-medium text-slate-950">{rows.length} sourcing rows selected</div>
        </div>
        <div className="space-y-3 px-4 py-4">
          <label className="block text-sm font-medium text-slate-700">
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-24 w-full rounded-md border border-slate-300 p-2 text-sm" />
          </label>
          <ImageClueButtons selected={imageClues} onChange={setImageClues} />
          <div className="rounded-md border border-red-200 bg-red-50 p-3">
            <div className="text-sm font-medium text-red-900">Block selected ASINs from sourcing</div>
            <div className="mt-1 text-xs text-red-700">
              Blocks {uniqueAsinCount} ASIN{uniqueAsinCount === 1 ? "" : "s"} and dismisses the selected opportunity rows.
            </div>
            <button
              type="button"
              disabled={busy || rows.length === 0}
              onClick={() => {
                if (window.confirm(`Block ${uniqueAsinCount} ASIN${uniqueAsinCount === 1 ? "" : "s"} from future sourcing?`)) {
                  void onBlockAsins(notes, imageClues);
                }
              }}
              className="mt-3 inline-flex h-9 items-center gap-2 rounded-md border border-red-300 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Ban className="h-4 w-4" />
              Block ASIN
            </button>
          </div>
          <DismissReasonButtons
            busy={busy || rows.length === 0}
            onChoose={(reason) => void onDismiss(reason, notes, imageClues)}
          />
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button onClick={onClose} disabled={busy} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function DismissReasonButtons({
  busy,
  onChoose,
}: {
  busy: boolean;
  onChoose: (reason: string) => void;
}) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-slate-700">Choose reason to dismiss</div>
      <div className="space-y-3">
        {dismissReasonGroups.map((group) => (
          <div key={group.label}>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{group.label}</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {group.reasons.map(([value, reasonLabel]) => (
                <button
                  key={value}
                  disabled={busy}
                  onClick={() => onChoose(value)}
                  className="rounded-md border border-slate-300 bg-white px-3 py-2 text-left text-sm font-medium text-slate-700 hover:border-red-200 hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {reasonLabel}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const imageClueOptions = [
  ["pegi", "PEGI"],
  ["greatest_hits", "Greatest Hits"],
  ["disc_only", "Disc Only"],
  ["missing_shrink_wrap", "Missing Shrink Wrap"],
  ["reseal", "Reseal"],
  ["damaged_case", "Damaged Case"],
] as const;

function ImageClueButtons({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <div>
      <div className="mb-2 text-sm font-medium text-slate-700">Image clues</div>
      <div className="flex flex-wrap gap-2">
        {imageClueOptions.map(([value, clueLabel]) => {
          const active = selected.includes(value);
          return (
            <button
              key={value}
              type="button"
              onClick={() => onChange(active ? selected.filter((item) => item !== value) : [...selected, value])}
              className={`rounded-md border px-3 py-2 text-sm font-medium ${
                active
                  ? "border-blue-300 bg-blue-50 text-blue-700"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {clueLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function OptionalImageLink({ href, children }: { href: string | null; children: ReactNode }) {
  if (!href) return <>{children}</>;
  return (
    <Link href={href} target="_blank" className="block w-32 rounded-md outline-none ring-offset-2 hover:ring-2 hover:ring-blue-400 focus:ring-2 focus:ring-blue-500">
      {children}
    </Link>
  );
}

function SourcingThumbnail({ src }: { src?: string | null }) {
  const className = "h-32 w-32 rounded-md border border-slate-200 bg-slate-50";
  if (!src) {
    return <div className={`flex ${className} items-center justify-center text-slate-400`}>--</div>;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" className={`${className} object-contain`} loading="lazy" />
  );
}

function SourcingHistory() {
  const [runs, setRuns] = useState<SourcingRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [serverRunCount, setServerRunCount] = useState<number | null>(null);

  async function loadHistory() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50", _: String(Date.now()) });
      const response = await fetch(`/api/sourcing/history?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? "Failed to load sourcing history.");
      setRuns(payload.runs ?? []);
      setServerRunCount(typeof payload.runCount === "number" ? payload.runCount : null);
      setRefreshedAt(typeof payload.refreshedAt === "string" ? payload.refreshedAt : new Date().toISOString());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sourcing history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  useEffect(() => {
    if (!runs.some((run) => run.status === "running" || run.status === "planned")) return;
    const timer = window.setInterval(() => void loadHistory(), 15000);
    return () => window.clearInterval(timer);
  }, [runs]);

  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <div>
          <div className="text-sm font-semibold text-slate-800">Sourcing Runs</div>
          <div className="text-xs text-slate-500">
            {refreshedAt ? `Last refreshed ${date(refreshedAt)} · ${serverRunCount ?? runs.length} rows returned` : ""}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadHistory()}
          disabled={loading}
          className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>
      {error ? <div className="border-b border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div> : null}
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Started</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Seeds</th>
            <th className="px-3 py-2">Candidates</th>
            <th className="px-3 py-2">Shown</th>
            <th className="px-3 py-2">Message</th>
            <th className="px-3 py-2">Run ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {loading && !runs.length ? <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-500">Loading run history...</td></tr> : runs.map((run) => {
            const status = sourcingRunStatusLabel(run);
            return (
              <tr key={run.sourcing_run_id}>
                <td className="px-3 py-2">{date(run.started_at)}</td>
                <td className="px-3 py-2">{label(run.run_type)}</td>
                <td className="px-3 py-2">{status}</td>
                <td className="px-3 py-2">{run.seed_asin_count ?? 0}</td>
                <td className="px-3 py-2">{run.ebay_candidate_count ?? 0}</td>
                <td className="px-3 py-2">{run.presented_opportunity_count ?? run.opportunity_count ?? 0}</td>
                <td className="max-w-96 px-3 py-2 text-xs text-slate-600">{sourcingRunMessage(run)}</td>
                <td className="px-3 py-2 font-mono text-xs">{run.sourcing_run_id}</td>
              </tr>
            );
          })}
          {!loading && !runs.length ? <tr><td colSpan={8} className="px-3 py-6 text-center text-slate-500">No sourcing runs found.</td></tr> : null}
        </tbody>
      </table>
    </div>
  );
}

function CoverageCyclePanel() {
  const [summary, setSummary] = useState<CoverageCycleSummary | null>(null);
  const [items, setItems] = useState<CoverageCycleItem[]>([]);
  const [runs, setRuns] = useState<CoverageDailyRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [queueSearch, setQueueSearch] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [summaryResponse, itemsResponse, runsResponse] = await Promise.all([
        fetch("/api/sourcing/coverage-cycle", { cache: "no-store" }),
        fetch(`/api/sourcing/coverage-cycle/items?pageSize=50&search=${encodeURIComponent(queueSearch)}`, { cache: "no-store" }),
        fetch("/api/sourcing/daily-runs?limit=20", { cache: "no-store" }),
      ]);
      const [summaryPayload, itemsPayload, runsPayload] = await Promise.all([
        summaryResponse.json(),
        itemsResponse.json(),
        runsResponse.json(),
      ]);
      if (!summaryResponse.ok) throw new Error(summaryPayload.error ?? "Failed to load coverage cycle.");
      if (!itemsResponse.ok) throw new Error(itemsPayload.error ?? "Failed to load coverage queue.");
      if (!runsResponse.ok) throw new Error(runsPayload.error ?? "Failed to load daily runs.");
      setSummary(summaryPayload);
      setItems(itemsPayload.items ?? []);
      setRuns(runsPayload.runs ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load coverage cycle.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) return <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading coverage cycle...</div>;
  if (error) return <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  const cycle = summary?.cycle;
  if (!cycle) return <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">No coverage cycle found.</div>;
  const lastRun = summary?.lastRun;

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-900">{summary?.statusMessage ?? "Coverage cycle"}</div>
            <div className="text-xs text-slate-500">Cycle {cycle.cycle_number ?? cycle.coverage_cycle_id} started {date(cycle.started_at)}</div>
          </div>
          <button onClick={() => void load()} className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          <Metric label="Coverage" value={Math.round(cycle.completion_percentage ?? 0)} />
          <Metric label="Eligible ASINs" value={cycle.total_eligible_asins ?? 0} />
          <Metric label="Searched" value={cycle.searched_count ?? 0} />
          <Metric label="Remaining" value={cycle.remaining_count ?? 0} />
          <Metric label="Calls Today" value={lastRun?.api_call_count ?? 0} />
          <Metric label="Quota Left" value={lastRun?.ending_browse_quota_remaining ?? lastRun?.starting_browse_quota_remaining ?? 0} />
        </div>
        <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-4">
          <div>Cycle status: <span className="font-medium text-slate-800">{label(cycle.status ?? "")}</span></div>
          <div>Last run: <span className="font-medium text-slate-800">{date(lastRun?.started_at)}</span></div>
          <div>Stop reason: <span className="font-medium text-slate-800">{stopReasonLabel(lastRun?.stop_reason ?? cycle.last_stop_reason ?? "", lastRun)}</span></div>
          <div>Next reset: <span className="font-medium text-slate-800">{date(lastRun?.browse_quota_reset_at ?? cycle.last_quota_reset_at)}</span></div>
        </div>
      </div>

      <div className="rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Priority Buckets</div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Priority</th>
              <th className="px-3 py-2">Bucket</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2 text-right">Searched</th>
              <th className="px-3 py-2 text-right">Remaining</th>
              <th className="px-3 py-2">Progress</th>
              <th className="px-3 py-2">Next Item</th>
            </tr>
          </thead>
          <tbody>
            {(summary?.bucketSummary ?? []).map((bucket, index) => (
              <tr key={bucket.priorityBucket} className="border-t border-slate-100">
                <td className="px-3 py-2">{index + 1}</td>
                <td className="px-3 py-2 font-medium">{bucket.label}</td>
                <td className="px-3 py-2 text-right">{bucket.total}</td>
                <td className="px-3 py-2 text-right">{bucket.searched}</td>
                <td className="px-3 py-2 text-right">{bucket.remaining}</td>
                <td className="px-3 py-2">
                  <div className="h-2 w-40 rounded bg-slate-200">
                    <div className="h-2 rounded bg-emerald-600" style={{ width: `${Math.min(bucket.progress, 100)}%` }} />
                  </div>
                </td>
                <td className="px-3 py-2 text-xs">
                  {bucket.nextItem ? <span><span className="font-mono">{bucket.nextItem.asin}</span> {bucket.nextItem.amazonTitle}</span> : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
            <div className="text-sm font-semibold">Current Queue</div>
            <input
              value={queueSearch}
              onChange={(event) => setQueueSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void load();
              }}
              className="h-8 w-64 rounded-md border border-slate-300 px-2 text-xs"
              placeholder="Search queue"
            />
          </div>
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Pos</th>
                <th className="px-3 py-2">ASIN</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">Bucket</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.cycle_item_id} className="border-t border-slate-100">
                  <td className="px-3 py-2">{item.queue_position}</td>
                  <td className="px-3 py-2 font-mono">{item.asin}</td>
                  <td className="px-3 py-2">{item.amazon_title ?? "--"}</td>
                  <td className="px-3 py-2">{label(item.priority_bucket)}</td>
                  <td className="px-3 py-2">{label(item.processing_status)}</td>
                </tr>
              ))}
              {!items.length ? <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-500">No queue rows found.</td></tr> : null}
            </tbody>
          </table>
        </div>

        <div className="rounded-md border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Daily Runs</div>
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2 text-right">Quota Start</th>
                <th className="px-3 py-2 text-right">Calls</th>
                <th className="px-3 py-2 text-right">Search</th>
                <th className="px-3 py-2 text-right">Detail</th>
                <th className="px-3 py-2 text-right">Retries</th>
                <th className="px-3 py-2 text-right">ASINs</th>
                <th className="px-3 py-2 text-right">Filtered</th>
                <th className="px-3 py-2 text-right">Resolved</th>
                <th className="px-3 py-2 text-right">Changed</th>
                <th className="px-3 py-2 text-right">Opps</th>
                <th className="px-3 py-2">Stop</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const search = ebaySearchSummary(run);
                return (
                  <tr key={run.sourcing_run_id} className="border-t border-slate-100 align-top">
                    <td className="px-3 py-2">{date(run.started_at)}</td>
                    <td className="px-3 py-2 text-right">{run.starting_browse_quota_remaining ?? "--"}</td>
                    <td className="px-3 py-2 text-right">{run.api_call_count ?? 0}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "search_call_count")}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "detail_call_count")}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "retry_http_attempt_count")}</td>
                    <td className="px-3 py-2 text-right">{run.asins_searched_this_run ?? 0}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "summary_filtered_count") + numberMetric(search, "summary_profitability_filtered_count")}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "detail_calls_missing_data_resolved_count")}</td>
                    <td className="px-3 py-2 text-right">{numberMetric(search, "detail_calls_changed_decision_count")}</td>
                    <td className="px-3 py-2 text-right">{run.opportunity_count ?? 0}</td>
                    <td className="px-3 py-2">
                      <div>{stopReasonLabel(run.stop_reason ?? run.status ?? "", run)}</div>
                      <DetailReasonBreakdown summary={search} />
                    </td>
                  </tr>
                );
              })}
              {!runs.length ? <tr><td colSpan={12} className="px-3 py-6 text-center text-slate-500">No daily sourcing runs found.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

type CoverageCycleSummary = {
  cycle: {
    coverage_cycle_id: string;
    cycle_number?: number | null;
    status?: string | null;
    started_at?: string | null;
    completion_percentage?: number | null;
    total_eligible_asins?: number | null;
    searched_count?: number | null;
    remaining_count?: number | null;
    last_stop_reason?: string | null;
    last_quota_reset_at?: string | null;
  } | null;
  bucketSummary: Array<{
    priorityBucket: string;
    label: string;
    total: number;
    searched: number;
    remaining: number;
    progress: number;
    nextItem: { asin: string; amazonTitle: string | null; queuePosition: number | null } | null;
  }>;
  lastRun: CoverageDailyRun | null;
  statusMessage: string | null;
};

type CoverageCycleItem = {
  cycle_item_id: string;
  queue_position: number | null;
  asin: string | null;
  amazon_title: string | null;
  priority_bucket: string;
  processing_status: string;
};

type CoverageDailyRun = {
  sourcing_run_id: string;
  started_at: string | null;
  status: string | null;
  stop_reason: string | null;
  starting_browse_quota_remaining: number | null;
  ending_browse_quota_remaining: number | null;
  browse_quota_reset_at: string | null;
  asins_searched_this_run: number | null;
  api_call_count: number | null;
  opportunity_count: number | null;
  raw_summary_json?: unknown;
};

function ebaySearchSummary(run: CoverageDailyRun) {
  return objectRecord(objectRecord(run.raw_summary_json)?.ebay_search);
}

function numberMetric(summary: Record<string, unknown> | null | undefined, key: string) {
  const value = summary?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function DetailReasonBreakdown({ summary }: { summary: Record<string, unknown> | null | undefined }) {
  const breakdown = objectRecord(summary?.detail_reason_breakdown);
  const counts = objectRecord(summary?.detail_reason_counts);
  const reasons = Object.entries(breakdown ?? {}).filter(([, value]) => objectRecord(value));
  const fallbackReasons = reasons.length ? [] : Object.entries(counts ?? {}).filter(([, value]) => typeof value === "number" && value > 0);
  const rows = reasons.length
    ? reasons.map(([reason, value]) => ({ reason, values: objectRecord(value) }))
    : fallbackReasons.map(([reason, value]) => ({ reason, values: { calls: value } as Record<string, unknown> }));
  if (!rows.length) return null;
  return (
    <details className="mt-1 text-[11px] text-slate-500">
      <summary className="cursor-pointer text-slate-600">Detail reasons</summary>
      <table className="mt-1 min-w-80 text-left">
        <thead>
          <tr className="text-slate-400">
            <th className="py-1 pr-3 font-medium">Reason</th>
            <th className="py-1 pr-3 text-right font-medium">Calls</th>
            <th className="py-1 pr-3 text-right font-medium">Resolved</th>
            <th className="py-1 pr-3 text-right font-medium">Changed</th>
            <th className="py-1 pr-3 text-right font-medium">Retained</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ reason, values }) => (
            <tr key={reason}>
              <td className="py-0.5 pr-3">{label(reason)}</td>
              <td className="py-0.5 pr-3 text-right">{numberMetric(values, "calls")}</td>
              <td className="py-0.5 pr-3 text-right">{numberMetric(values, "missing_data_resolved")}</td>
              <td className="py-0.5 pr-3 text-right">{numberMetric(values, "decision_changed")}</td>
              <td className="py-0.5 pr-3 text-right">{numberMetric(values, "candidate_retained")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

function MatchingIntelligencePanel() {
  const [data, setData] = useState<MatchingIntelligenceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/sourcing/matching-intelligence", { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "Failed to load matching intelligence.");
        setData(payload);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load matching intelligence."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">Loading matching intelligence...</div>;
  if (error) return <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Examples" value={data.summary.exampleCount} />
        <Metric label="Snapshots" value={data.summary.snapshotCount} />
        <Metric label="Reviewed Opps" value={data.summary.reviewedOpportunityCount} />
        <Metric label="Action Records" value={data.summary.actionCount} />
        <Metric label="Examples w/ Notes" value={data.summary.examplesWithNotes} />
        <Metric label="Examples w/ Snapshots" value={data.summary.examplesWithSnapshots} />
        <Metric label="Purchased/Offered" value={data.summary.purchasedOrOfferedCount} />
        <Metric label="Matched Later" value={data.summary.purchasedOrOfferedMatchedCount} />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <CountPanel title="Labels" rows={data.countsByLabel} />
        <DismissalStatsPanel rows={data.dismissalReasonStats} />
        <CountPanel title="Sourcing Actions" rows={data.countsBySourcingAction} />
        <CountPanel title="Image Clues" rows={data.countsByImageClue} />
        <CountPanel title="Sources" rows={data.countsBySource} />
        <CountPanel title="Seller Status" rows={data.countsBySellerStatus} />
      </div>
      <NearMissPanel rows={data.nearMisses} />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="rounded-md border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Recent Dismissal Notes</div>
          <div className="divide-y divide-slate-100">
            {data.recentNotes.length ? data.recentNotes.map((row, index) => (
              <div key={`${row.reason}-${index}`} className="px-3 py-2 text-sm">
                <div className="font-medium text-slate-800">{label(row.reason)}</div>
                <div className="text-slate-600">{row.note}</div>
                <div className="text-xs text-slate-400">{row.label} · {dateOnly(row.createdAt)}</div>
              </div>
            )) : <div className="px-3 py-6 text-sm text-slate-500">No dismissal notes captured yet.</div>}
          </div>
        </div>
        <div className="rounded-md border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Seller Warnings</div>
          <div className="divide-y divide-slate-100">
            {data.sellersToWatch.length ? data.sellersToWatch.map((row) => (
              <div key={row.sellerUsername ?? ""} className="grid grid-cols-4 gap-2 px-3 py-2 text-sm">
                <div className="col-span-2 font-medium text-slate-800">{row.sellerUsername}</div>
                <div>{row.status}</div>
                <div className="text-right">{number(row.trustScore)}</div>
                <div className="col-span-4 text-xs text-slate-500">
                  {row.productConditionReturns ?? 0} product/condition strikes · {row.purchases ?? 0}/{row.opportunities ?? 0} conversions
                </div>
              </div>
            )) : <div className="px-3 py-6 text-sm text-slate-500">No watch/avoid sellers yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function CountPanel({ title, rows }: { title: string; rows: Array<{ key: string; count: number }> }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">{title}</div>
      <div className="divide-y divide-slate-100">
        {rows.length ? rows.map((row) => (
          <div key={row.key} className="flex items-center justify-between px-3 py-2 text-sm">
            <span>{label(row.key)}</span>
            <span className="font-semibold">{row.count}</span>
          </div>
        )) : <div className="px-3 py-6 text-sm text-slate-500">No data yet.</div>}
      </div>
    </div>
  );
}

function DismissalStatsPanel({ rows }: { rows: MatchingIntelligenceData["dismissalReasonStats"] }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Dismiss Reasons</div>
      <div className="divide-y divide-slate-100">
        {rows.length ? rows.map((row) => (
          <div key={row.key} className="grid grid-cols-12 items-center gap-2 px-3 py-2 text-sm">
            <span className="col-span-5">{label(row.key)}</span>
            <span className="col-span-2 text-right font-semibold">{row.count}</span>
            <span className="col-span-3 text-right text-slate-600">{row.withNotes} notes</span>
            <span className="col-span-2 text-right text-xs text-slate-500">{number(row.noteRate)}%</span>
          </div>
        )) : <div className="px-3 py-6 text-sm text-slate-500">No dismissals yet.</div>}
      </div>
    </div>
  );
}

function NearMissPanel({ rows }: { rows: MatchingIntelligenceData["nearMisses"] }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Near Miss Review Queue</div>
      <div className="divide-y divide-slate-100">
        {rows.length ? rows.map((row, index) => (
          <div key={`${row.asin}-${index}`} className="grid gap-1 px-3 py-2 text-sm lg:grid-cols-[120px_minmax(0,1fr)_110px]">
            <div className="font-mono text-xs text-slate-500">{row.asin}</div>
            <div className="min-w-0">
              <div className="font-medium text-slate-800">{row.rejectedTitle}</div>
              <div className="text-xs text-slate-500">Positive: {row.positiveTitle ?? "--"}</div>
              {row.note ? <div className="text-xs text-slate-500">Note: {row.note}</div> : null}
            </div>
            <div className="text-right text-xs text-slate-500">
              <div>{number(row.similarity)}%</div>
              <div>{label(row.reason ?? row.label ?? "")}</div>
            </div>
          </div>
        )) : <div className="px-3 py-6 text-sm text-slate-500">No near misses detected yet.</div>}
      </div>
    </div>
  );
}

type MatchingIntelligenceData = {
  summary: {
    exampleCount: number;
    snapshotCount: number;
    sellerCount: number;
    examplesWithNotes: number;
    examplesWithSnapshots: number;
    reviewedOpportunityCount: number;
    actionCount: number;
    missingDismissalNotes: number;
    purchasedOrOfferedCount: number;
    purchasedOrOfferedMatchedCount: number;
  };
  countsByLabel: Array<{ key: string; count: number }>;
  countsByDismissReason: Array<{ key: string; count: number }>;
  dismissalReasonStats: Array<{ key: string; count: number; withNotes: number; withoutNotes: number; noteRate: number }>;
  countsByImageClue: Array<{ key: string; count: number }>;
  countsBySourcingAction: Array<{ key: string; count: number }>;
  countsBySource: Array<{ key: string; count: number }>;
  countsBySellerStatus: Array<{ key: string; count: number }>;
  recentNotes: Array<{ reason: string; note: string; label: string; source: string; createdAt: string | null }>;
  nearMisses: Array<{
    asin: string | null;
    amazonTitle: string | null;
    rejectedTitle: string | null;
    positiveTitle: string | null;
    reason: string | null;
    label: string | null;
    similarity: number;
    note: string | null;
    createdAt: string | null;
  }>;
  sellersToWatch: Array<{
    sellerUsername: string | null;
    status: string | null;
    trustScore: number | null;
    productConditionReturns: number | null;
    opportunities: number | null;
    purchases: number | null;
  }>;
};

function SourcingSettingsPanel({ onApplied }: { onApplied: () => Promise<void> }) {
  const [settings, setSettings] = useState<SourcingSettings | null>(null);
  const [itemCountriesText, setItemCountriesText] = useState("");
  const [excludedKeywordsText, setExcludedKeywordsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/sourcing/settings")
      .then((response) => response.json())
      .then((payload) => {
        setSettings(payload.settings);
        setItemCountriesText((payload.settings?.item_location_countries ?? []).join(", "));
        setExcludedKeywordsText((payload.settings?.excluded_keywords ?? []).join(", "));
      });
  }, []);

  async function save() {
    if (!settings) return;
    const settingsToSave = {
      ...settings,
      item_location_countries: parseCommaList(itemCountriesText),
      excluded_keywords: parseCommaList(excludedKeywordsText),
    };
    setSaving(true);
    setNotice(null);
    try {
      const response = await fetch("/api/sourcing/settings", {
        method: "PATCH",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(settingsToSave),
      });
      const payload = await response.json();
      if (response.ok) {
        setSettings(payload.settings);
        setItemCountriesText((payload.settings?.item_location_countries ?? []).join(", "));
        setExcludedKeywordsText((payload.settings?.excluded_keywords ?? []).join(", "));
        setNotice("Settings saved. Applying to current opportunities...");
        const applyResponse = await fetch("/api/sourcing/settings/apply", {
          method: "POST",
          headers: mutationHeaders(),
        });
        const applyPayload = await applyResponse.json().catch(() => ({}));
        if (!applyResponse.ok) {
          setNotice(applyPayload.error ?? "Settings saved, but opportunity refresh failed.");
        } else if (applyPayload?.executionMode === "aws-ecs" || applyPayload?.taskArn) {
          setNotice("Settings saved. AWS scoring refresh started; check System Health for progress.");
        } else {
          await onApplied();
          setNotice("Settings applied and opportunity list refreshed.");
        }
      } else {
        setNotice(payload.error ?? "Settings save failed.");
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Settings save failed.");
    } finally {
      setSaving(false);
    }
  }

  if (!settings) return <div className="text-sm text-slate-500">Loading settings...</div>;

  return (
    <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
      <div className="grid gap-3 md:grid-cols-4">
        <NumberField label="Min Amazon Price" value={settings.min_amazon_price} onChange={(value) => setSettings({ ...settings, min_amazon_price: value })} />
        <NumberField label="Min ROI %" value={settings.min_roi_percent} onChange={(value) => setSettings({ ...settings, min_roi_percent: value })} />
        <NumberField label="Min Profit" value={settings.min_profit_dollars} onChange={(value) => setSettings({ ...settings, min_profit_dollars: value })} />
        <NumberField label="Sales Lookback Days" value={settings.sales_lookback_days} onChange={(value) => setSettings({ ...settings, sales_lookback_days: value })} />
        <TextField label="Buyer ZIP" value={settings.buyer_zip} onChange={(value) => setSettings({ ...settings, buyer_zip: value })} />
        <TextField label="Buyer Country" value={settings.buyer_country} onChange={(value) => setSettings({ ...settings, buyer_country: value })} />
        <TextField label="Item Countries" value={itemCountriesText} onChange={setItemCountriesText} />
        <NumberField label="Best Offer Min Ask %" value={settings.best_offer_min_ask_percent} onChange={(value) => setSettings({ ...settings, best_offer_min_ask_percent: value })} />
      </div>
      <label className="mt-4 block text-sm font-medium text-slate-700">
        Excluded Keywords
        <textarea
          value={excludedKeywordsText}
          onChange={(event) => setExcludedKeywordsText(event.target.value)}
          className="mt-1 min-h-20 w-full rounded-md border border-slate-300 p-2 text-sm"
        />
      </label>
      <div className="mt-4 flex items-center gap-3">
        <button onClick={() => void save()} disabled={saving} className="rounded-md bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
          {saving ? "Saving and applying..." : "Save Settings"}
        </button>
        {notice ? <span className="text-sm text-slate-600">{notice}</span> : null}
      </div>
    </div>
  );
}

function NumberField({ label: fieldLabel, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="text-sm font-medium text-slate-700">
      {fieldLabel}
      <input type="number" value={value ?? 0} onChange={(event) => onChange(Number(event.target.value))} className="mt-1 h-9 w-full rounded-md border border-slate-300 px-2 text-sm" />
    </label>
  );
}

function TextField({ label: fieldLabel, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="text-sm font-medium text-slate-700">
      {fieldLabel}
      <input value={value ?? ""} onChange={(event) => onChange(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 px-2 text-sm" />
    </label>
  );
}

function label(value: string) {
  if (value === "ebay_out_of_quota" || value === "ebay_rate_limited") return "Out of quota";
  if (value === "quota_reserve_reached") return "Run budget reached";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function stopReasonLabel(value: string | null | undefined, run?: CoverageDailyRun | null) {
  if (!value) return "";
  if (value !== "quota_reserve_reached") return label(value);
  return hasRemainingBrowseQuota(run) ? "Run budget reached" : "Quota reserve reached";
}

function hasRemainingBrowseQuota(run?: CoverageDailyRun | null) {
  const endingQuota = run?.ending_browse_quota_remaining;
  if (typeof endingQuota !== "number") return false;
  return endingQuota > quotaReserve(run);
}

function quotaReserve(run?: CoverageDailyRun | null) {
  const summary = objectRecord(run?.raw_summary_json);
  const daily = objectRecord(summary?.daily_catalog_sourcing);
  const reserve = daily?.quota_reserve;
  return typeof reserve === "number" && Number.isFinite(reserve) ? reserve : 0;
}

function money(value: number | null | undefined) {
  return typeof value === "number" ? `$${value.toFixed(2)}` : "--";
}

function originalCurrencyCostLabel(row: SourcingOpportunity) {
  if (!row.originalCurrency || row.originalItemPrice === null) return null;
  const parts = [`Orig ${formatCurrency(row.originalItemPrice, row.originalCurrency)}`];
  if (row.originalShippingPrice !== null) {
    parts.push(`ship ${formatCurrency(row.originalShippingPrice, row.originalCurrency)}`);
  }
  return parts.join(" + ");
}

function offerBidAmountLabel(row: SourcingOpportunity, amountUsd: number | null | undefined) {
  if (typeof amountUsd !== "number") return "--";
  const originalAmount = originalCurrencyAmount(row, amountUsd);
  if (!originalAmount) return `${money(amountUsd)} USD`;
  return `${money(amountUsd)} USD / ${formatCurrency(originalAmount.amount, originalAmount.currency)}`;
}

function originalCurrencyAmount(row: SourcingOpportunity, amountUsd: number) {
  if (!row.originalCurrency || row.originalCurrency.toUpperCase() === "USD") return null;
  if (typeof row.originalItemPrice !== "number" || typeof row.itemPrice !== "number" || row.itemPrice <= 0) return null;
  return {
    currency: row.originalCurrency,
    amount: amountUsd * (row.originalItemPrice / row.itemPrice),
  };
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
  }).format(value);
}

function percent(value: number | null | undefined) {
  return typeof value === "number" ? `${Math.round(value)}%` : "--";
}

function number(value: number | null | undefined) {
  return typeof value === "number" ? value.toFixed(1) : "--";
}

function watchReferencePurchaseCost(row: SourcingOpportunity) {
  if (row.opportunityType === "best_offer" && row.suggestedOfferPrice !== null) return row.suggestedOfferPrice;
  if (row.landedCost !== null) return row.landedCost;
  return row.itemPrice;
}

function watchPayload(row: SourcingOpportunity): SourcingActionPayload {
  return {
    actionType: "watch",
    expectedPurchaseCost: watchReferencePurchaseCost(row) ?? undefined,
    requiredMaxLandedCost: row.maxProfitableLandedCost ?? undefined,
    requiredRoiPercent: row.estimatedRoiPercent ?? undefined,
  };
}

function parseCommaList(value: string) {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function sourcingRunStatusLabel(run: SourcingRun) {
  const stopReason = sourcingRunStopReason(run);
  if (isQuotaStop(stopReason)) return "Out of quota";
  if (stopReason === "quota_reserve_reached") return "Run budget reached";
  return label(run.status);
}

function sourcingRunMessage(run: SourcingRun) {
  const stopReason = sourcingRunStopReason(run);
  if (isQuotaStop(stopReason)) {
    const reset = sourcingRunQuotaReset(run);
    return reset ? `eBay Browse quota exhausted. Resets ${date(reset)}.` : "eBay Browse quota exhausted.";
  }
  if (stopReason === "quota_reserve_reached") {
    return "MBOP stopped after its Browse call budget was reached; eBay may still report remaining quota.";
  }
  if (typeof run.scored_opportunity_count === "number" && typeof run.presented_opportunity_count === "number") {
    return `Scored ${run.scored_opportunity_count}; shown ${run.presented_opportunity_count}.`;
  }
  return run.error_message ?? "";
}

function sourcingRunStopReason(run: SourcingRun) {
  if (run.stop_reason) return run.stop_reason;
  if (run.batch_stop_reason) return run.batch_stop_reason;
  const summary = objectRecord(run.raw_summary_json);
  const daily = objectRecord(summary?.daily_catalog_sourcing);
  const progressive = objectRecord(summary?.progressive_batch);
  const search = objectRecord(summary?.ebay_search);
  return stringValue(daily?.stop_reason) ?? stringValue(progressive?.stop_reason) ?? stringValue(search?.stop_reason);
}

function sourcingRunQuotaReset(run: SourcingRun) {
  if (run.browse_quota_reset_at) return run.browse_quota_reset_at;
  const summary = objectRecord(run.raw_summary_json);
  const daily = objectRecord(summary?.daily_catalog_sourcing);
  const endingQuota = objectRecord(daily?.ending_quota);
  const startingQuota = objectRecord(daily?.starting_quota);
  const progressive = objectRecord(summary?.progressive_batch);
  const quota = objectRecord(progressive?.ebay_browse_quota);
  return stringValue(endingQuota?.reset) ?? stringValue(startingQuota?.reset) ?? stringValue(quota?.reset);
}

function isQuotaStop(stopReason: string | null) {
  return stopReason === "ebay_out_of_quota" || stopReason === "ebay_rate_limited";
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value ? value : null;
}

function date(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "--";
}

function dateOnly(value: string | null | undefined) {
  return value ? new Date(value).toLocaleDateString() : "--";
}

function legacyItemId(value: string) {
  const match = value.match(/\b\d{9,15}\b/);
  return match?.[0] ?? value;
}
