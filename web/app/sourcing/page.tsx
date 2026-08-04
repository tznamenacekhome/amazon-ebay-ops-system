"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  Ban,
  RefreshCw,
  Search,
} from "lucide-react";
import type { SourcingBatch, SourcingOpportunity, SourcingRun, SourcingSettings } from "./types";
import { useSourcingOpportunities } from "./useSourcingOpportunities";
import { dismissReasons } from "./matchingTaxonomy";
import { mutationHeaders } from "../mutationHeaders";
import { KeepaPriceIndicator } from "../components/KeepaPriceIndicator";

const tabs = ["Replenishment", "Closest Excluded", "Coverage Cycle", "Watchlist", "Purchased Pending Match", "Sourcing History", "Matching Intelligence", "Settings"] as const;
const opportunityTypes = ["all", "buy_now", "multi_unit", "best_offer", "auction", "watch"] as const;
const GIXEN_URL = "https://www.gixen.com/main/index.php";
type SourcingActionPayload = {
  actionType: string;
  reason?: string;
  notes?: string;
  imageClues?: string[];
  diagnosticsFeedback?: {
    allAssumptionsCorrect: boolean;
    incorrectRows: string[];
    failedRuleFamilies?: string[];
    evidenceSources?: string[];
    legacyIncorrectRows?: string[];
    note?: string | null;
  };
  requiredMaxLandedCost?: number;
  requiredRoiPercent?: number;
  expectedPurchaseCost?: number;
  inventoryBaselineUnits?: number;
  myQuantity?: number;
  myPipelineQuantity?: number;
  myPurchasedQuantity?: number;
  myReceivedQuantity?: number;
  myOutboundQuantity?: number;
};

export default function SourcingPage() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("Replenishment");
  const [status, setStatus] = useState("open");
  const [type, setType] = useState("all");
  const [sourceMode, setSourceMode] = useState("all");
  const [scope, setScope] = useState("all_open");
  const [searchText, setSearchText] = useState("");
  const effectiveStatus =
    activeTab === "Closest Excluded"
      ? "all"
      : activeTab === "Watchlist"
        ? "watching"
        : activeTab === "Purchased Pending Match"
          ? "purchased_pending_match"
          : status;
  const { rows, summary, batch, loading, error, reload, removeRows, setError } = useSourcingOpportunities(
    effectiveStatus,
    type,
    searchText,
    sourceMode,
    activeTab === "Closest Excluded" ? "closest_excluded" : activeTab === "Replenishment" ? scope : "all_open",
  );
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [dismissRow, setDismissRow] = useState<SourcingOpportunity | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDismissOpen, setBulkDismissOpen] = useState(false);
  const [batchContinueRunning, setBatchContinueRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const visibleRows = useMemo(() => {
    if (activeTab === "Purchased Pending Match") return rows.filter((row) => row.status === "purchased_pending_match");
    if (activeTab === "Replenishment" || activeTab === "Watchlist" || activeTab === "Closest Excluded") return rows;
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
    <main className="min-h-screen bg-slate-100 py-5 pl-5 pr-3 text-slate-950">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">Sourcing Workspace</h1>
          <p className="text-sm text-slate-600">
            Replenishment candidates from Amazon demand, eBay supply, and MBOP scoring.
          </p>
        </div>
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
            <Metric label={activeTab === "Replenishment" ? "Actionable Rows" : "Open Rows"} value={summary.total ?? visibleRows.length} />
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
                value={scope}
                onChange={(event) => setScope(event.target.value)}
                className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
              >
                <option value="all_open">All Open</option>
                <option value="new_this_run">New This Run</option>
                <option value="prior_unreviewed">Prior Unreviewed</option>
              </select>
            ) : null}
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
                <option value="inventory_snoozed">Inventory Snoozed</option>
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
            onBulkWatch={() => void bulkAct(selectedRows, watchPayload)}
            onBulkWaitForSellThrough={() => void bulkAct(selectedRows, inventorySnoozePayload)}
            onBulkPurchased={() => void bulkAct(selectedRows, (row) => ({ actionType: "purchased", expectedPurchaseCost: row.landedCost ?? undefined }))}
            onBulkDismiss={() => {
              if (selectedRows.length === 1) {
                setDismissRow(selectedRows[0]);
                return;
              }
              setBulkDismissOpen(true);
            }}
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
            purchasedMode={activeTab === "Purchased Pending Match"}
            closestExcludedMode={activeTab === "Closest Excluded"}
          />
          {dismissRow ? (
            <DismissOpportunityDialog
              key={dismissRow.opportunityId}
              row={dismissRow}
              actionBusyId={actionBusyId}
              initialDiagnosticsOpen={activeTab === "Replenishment" || activeTab === "Closest Excluded"}
              onClose={() => setDismissRow(null)}
              onBlockAsin={async (notes, imageClues) => {
                await act(dismissRow, { actionType: "block_asin", notes, imageClues });
                setDismissRow(null);
              }}
              onDismiss={async (reason, notes, imageClues, diagnosticsFeedback) => {
                await act(dismissRow, { actionType: "dismiss", reason, notes, imageClues, diagnosticsFeedback });
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
  onBulkWatch,
  onBulkWaitForSellThrough,
  onBulkPurchased,
  onBulkDismiss,
  onToggleSelected,
  onToggleAll,
  purchasedMode,
  closestExcludedMode,
}: {
  rows: SourcingOpportunity[];
  loading: boolean;
  actionBusyId: string | null;
  selectedIds: Set<string>;
  selectedCount: number;
  onBulkWatch: () => void;
  onBulkWaitForSellThrough: () => void;
  onBulkPurchased: () => void;
  onBulkDismiss: () => void;
  onToggleSelected: (row: SourcingOpportunity) => void;
  onToggleAll: () => void;
  purchasedMode: boolean;
  closestExcludedMode: boolean;
}) {
  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.has(row.opportunityId));
  const bulkDisabled = selectedCount === 0 || actionBusyId === "bulk";

  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="max-h-[calc(100vh-250px)] overflow-auto">
        <table className="min-w-[96rem] table-fixed text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th colSpan={13} className="border-b border-slate-200 bg-white px-2 py-2">
                <div className="flex flex-wrap items-center gap-2 normal-case tracking-normal">
                  <span className="text-sm font-medium text-slate-700">{selectedCount} selected</span>
                  {!purchasedMode && !closestExcludedMode ? (
                    <>
                      <button disabled={bulkDisabled} onClick={onBulkWatch} className="bulk-button">Watch selected</button>
                      <button disabled={bulkDisabled} onClick={onBulkWaitForSellThrough} className="bulk-button">Wait for sell-through</button>
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
              <th className="w-32 px-2 py-2">Last Sold</th>
              <th className="w-24 px-2 py-2">Keepa 90</th>
              <th className="w-24 px-2 py-2">Keepa Now</th>
              <th className="w-28 px-2 py-2">My Price</th>
              <th className="w-24 px-2 py-2">Profit</th>
              <th className="w-16 px-2 py-2">ROI</th>
              <th className="w-32 px-2 py-2">Type</th>
              <th className="w-40 px-2 py-2">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={13} className="px-3 py-8 text-center text-slate-500">Loading sourcing rows...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={13} className="px-3 py-8 text-center text-slate-500">No sourcing rows found for this view.</td></tr>
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
                    {!closestExcludedMode ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        <PresentationBadge row={row} />
                      </div>
                    ) : null}
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
                      {closestExcludedMode ? <span>near miss {number(row.nearMissRank)}</span> : null}
                    </div>
                    {closestExcludedMode ? <ExcludedBecause reason={row.exclusionReason ?? null} /> : null}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <CostCell row={row} />
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium">{money(row.lastSalePrice)}</div>
                    <div className="text-xs text-slate-500">{dateOnly(row.lastSoldAt)}</div>
                    <div className="mt-1 text-[11px] leading-tight text-slate-500">
                      <span>{row.unitsSold90d ?? 0}</span>
                      <span className="text-slate-400"> / </span>
                      <span>{row.unitsSold120d ?? 0}</span>
                      <span className="text-slate-400"> / </span>
                      <span>{row.unitsSold365d ?? 0}</span>
                    </div>
                    <div className="text-[10px] uppercase leading-tight text-slate-400">
                      90 / 120 / 365
                    </div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium">{money(row.keepaAvg90Price)}</div>
                    <div className="text-xs text-slate-500">{row.keepaAvg90Label ?? "--"}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <KeepaPriceIndicator
                      price={row.keepaCurrentPrice}
                      fulfillment={row.keepaCurrentPriceFulfillment}
                      isBuyBox={row.keepaCurrentPriceIsBuyBox}
                      noData={!row.keepaCurrentPriceSource || row.keepaCurrentPriceSource === "no_data"}
                      usedOnly={row.keepaCurrentPriceSource === "used_only"}
                      formatMoney={money}
                    />
                    <div className="text-xs text-slate-500">{row.keepaCurrentPriceLabel ?? "--"}</div>
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    <div className="font-medium text-slate-900">{money(row.myPrice)}</div>
                    {row.myQuantity > 0 ? (
                      <div className="text-xs text-slate-500">{row.myQuantity} in stock</div>
                    ) : (
                      <div className="text-xs text-slate-400">not in stock</div>
                    )}
                    {row.myPipelineQuantity > 0 ? (
                      <div className="text-xs font-medium text-blue-700" title={myPipelineTitle(row)}>
                        +{row.myPipelineQuantity} pipeline
                      </div>
                    ) : null}
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
                    <OpportunityTypeCell row={row} />
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-col items-start gap-1">
                      <SourcingFlags flags={row.aiFlags} />
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

function SourcingFlags({ flags }: { flags: string[] }) {
  const visibleFlags = flags.filter(isVisibleSourcingFlag);
  if (!visibleFlags.length) return <span className="text-xs text-slate-400">None</span>;
  return visibleFlags.map((flag) => (
    <span key={flag} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
      {flag}
    </span>
  ));
}

function isVisibleSourcingFlag(flag: string) {
  const text = flag.toLowerCase();
  return (
    text.includes("unknown shipping estimate") ||
    text.includes("suppressed listing") ||
    text.includes("return-heavy asin") ||
    text.includes("historical non_match") ||
    text.includes("historical condition_problem") ||
    text.includes("historical negative") ||
    text.includes("seller warning: avoid") ||
    text.includes("seller warning: watch") ||
    text.includes("platform mismatch") ||
    text.includes("wrong platform") ||
    text.includes("title token") ||
    text.includes("title overlap") ||
    text.includes("no meaningful title") ||
    text.includes("excluded keyword") ||
    text.includes("digital") ||
    text.includes("download") ||
    text.includes("incomplete listing") ||
    text.includes("accessory/not game") ||
    text.includes("not a game") ||
    text.includes("non-north-american") ||
    text.includes("non-video-game category") ||
    text.includes("game name") ||
    text.includes("numeric") ||
    text.includes("installment") ||
    text.includes("edition") ||
    text.includes("version") ||
    text.includes("pickup") ||
    text.includes("delivery") ||
    text.includes("non-us item location")
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

function PresentationBadge({ row }: { row: SourcingOpportunity }) {
  const labelText = row.isNewThisRun ? "New This Run" : "Previously Presented";
  const dateText = row.lastPresentedAt ?? row.firstPresentedAt;
  return (
    <>
      <span
        className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
          row.isNewThisRun ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
        }`}
      >
        {labelText}
      </span>
      {dateText ? <span className="rounded bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-500">{dateOnly(dateText)}</span> : null}
    </>
  );
}

function ExcludedBecause({ reason }: { reason: SourcingOpportunity["exclusionReason"] | null }) {
  const label = reason?.label ?? "Unknown - inspect diagnostics";
  const summary = reason?.summary ?? "No backend exclusion reason was returned.";
  const moreCount = reason?.secondaryReasons?.length ?? 0;
  const statusText = reason?.eligible === true
    ? "Current rules: eligible"
    : `Final: ${reason?.finalRecommendation ?? reason?.finalStatus ?? "not available"}`;
  return (
    <div className="mt-2 max-w-xl rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-xs text-amber-950">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-semibold text-amber-900">Excluded Because</span>
        <span className="rounded bg-white px-1.5 py-0.5 text-[11px] font-medium text-amber-800">{reason?.severity ?? "unknown"}</span>
        {moreCount ? <span className="text-[11px] text-amber-700">+{moreCount} more</span> : null}
      </div>
      <div className="mt-1 font-medium">{label}</div>
      <div className="mt-0.5 text-amber-800">{summary}</div>
      <div className="mt-0.5 text-[11px] text-amber-700">
        Source: {reason?.source ?? "unknown"} / {statusText}
      </div>
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
  initialDiagnosticsOpen,
  onClose,
  onBlockAsin,
  onDismiss,
}: {
  row: SourcingOpportunity;
  actionBusyId: string | null;
  initialDiagnosticsOpen: boolean;
  onClose: () => void;
  onBlockAsin: (notes: string, imageClues: string[]) => Promise<void>;
  onDismiss: (
    reason: string,
    notes: string,
    imageClues: string[],
    diagnosticsFeedback: {
      allAssumptionsCorrect: boolean;
      failedRuleFamilies: string[];
      evidenceSources: string[];
      legacyIncorrectRows: string[];
      incorrectRows: string[];
      note?: string | null;
    },
  ) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [imageClues, setImageClues] = useState<string[]>([]);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(initialDiagnosticsOpen);
  const [allAssumptionsCorrect, setAllAssumptionsCorrect] = useState(false);
  const [failedRuleFamilies, setFailedRuleFamilies] = useState<string[]>([]);
  const busy = actionBusyId === row.opportunityId;
  const diagnosticsFeedback = {
    allAssumptionsCorrect,
    failedRuleFamilies: allAssumptionsCorrect ? [] : failedRuleFamilies,
    evidenceSources: allAssumptionsCorrect ? [] : evidenceSourcesForRuleFamilies(failedRuleFamilies),
    legacyIncorrectRows: allAssumptionsCorrect ? [] : legacyRowsForRuleFamilies(failedRuleFamilies),
    incorrectRows: allAssumptionsCorrect ? [] : legacyRowsForRuleFamilies(failedRuleFamilies),
    note: notes.trim() || null,
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/20 p-4">
      <div className={`w-full rounded-md border border-slate-200 bg-white shadow-2xl ${diagnosticsOpen ? "max-w-7xl" : "max-w-lg"}`}>
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Dismiss Opportunity</div>
          <div className="mt-1 text-sm font-medium text-slate-950">{row.ebayTitle}</div>
          <div className="mt-1 font-mono text-xs text-slate-500">{row.asin}</div>
        </div>
        <div className={`grid gap-0 ${diagnosticsOpen ? "lg:grid-cols-[minmax(380px,480px)_1fr]" : ""}`}>
          <div className="space-y-3 px-4 py-3">
            <DismissReasonButtons
              busy={busy}
              onChoose={(reason) => void onDismiss(reason, notes, imageClues, diagnosticsFeedback)}
            />
            <ImageClueButtons selected={imageClues} onChange={setImageClues} />
            <button
              type="button"
              disabled={busy}
              onClick={() => void onBlockAsin(notes, imageClues)}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-red-300 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Ban className="h-4 w-4" />
              Block ASIN
            </button>
            <button
              type="button"
              onClick={() => setDiagnosticsOpen((current) => !current)}
              className="ml-2 inline-flex h-9 items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 hover:bg-blue-100"
            >
              {diagnosticsOpen ? "Hide Diagnostics" : "Matching Diagnostics"}
            </button>
            <label className="block text-sm font-medium text-slate-700">
              Notes
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-12 w-full rounded-md border border-slate-300 p-2 text-sm" />
            </label>
          </div>
          {diagnosticsOpen ? (
            <DiagnosticComparisonPanel
              row={row}
              allAssumptionsCorrect={allAssumptionsCorrect}
              failedRuleFamilies={failedRuleFamilies}
              onAllCorrectChange={(checked) => {
                setAllAssumptionsCorrect(checked);
                if (checked) setFailedRuleFamilies([]);
              }}
              onFailedRuleFamiliesChange={(families) => {
                setFailedRuleFamilies(families);
                if (families.length) setAllAssumptionsCorrect(false);
              }}
            />
          ) : null}
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
        <div className="space-y-3 px-4 py-3">
          <DismissReasonButtons
            busy={busy || rows.length === 0}
            onChoose={(reason) => void onDismiss(reason, notes, imageClues)}
          />
          <ImageClueButtons selected={imageClues} onChange={setImageClues} />
          <button
            type="button"
            disabled={busy || rows.length === 0 || uniqueAsinCount === 0}
            onClick={() => {
              if (window.confirm(`Block ${uniqueAsinCount} ASIN${uniqueAsinCount === 1 ? "" : "s"} from future sourcing?`)) {
                void onBlockAsins(notes, imageClues);
              }
            }}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-red-300 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Ban className="h-4 w-4" />
            Block ASIN
          </button>
          <label className="block text-sm font-medium text-slate-700">
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-12 w-full rounded-md border border-slate-300 p-2 text-sm" />
          </label>
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

function DiagnosticComparisonPanel({
  row,
  allAssumptionsCorrect,
  failedRuleFamilies,
  onAllCorrectChange,
  onFailedRuleFamiliesChange,
}: {
  row: SourcingOpportunity;
  allAssumptionsCorrect: boolean;
  failedRuleFamilies: string[];
  onAllCorrectChange: (checked: boolean) => void;
  onFailedRuleFamiliesChange: (families: string[]) => void;
}) {
  const comparison = row.diagnosticComparison;
  const rows = comparison?.rows ?? [];
  const identityRows = diagnosticsIdentityRows(row, rows);
  const evidenceRows = diagnosticsEvidenceRows(row, rows);
  const summaryRows = diagnosticsSummaryRows(identityRows, comparison?.hardBlocks ?? [], comparison?.warnings ?? []);
  const hardBlocks = cleanDiagnosticMessages(comparison?.hardBlocks ?? []);
  const warnings = cleanDiagnosticMessages(comparison?.warnings ?? []);
  const failed = new Set(failedRuleFamilies);

  return (
    <aside className="max-h-[72vh] overflow-auto border-t border-slate-200 bg-slate-50 p-3 lg:border-l lg:border-t-0">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Why MBOP Matched These</div>
          <div className="text-sm text-slate-700">Parsed identity on each side, followed by the listing evidence MBOP used.</div>
        </div>
        <label className="flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700">
          <input
            type="checkbox"
            checked={allAssumptionsCorrect}
            onChange={(event) => onAllCorrectChange(event.target.checked)}
            className="h-4 w-4"
          />
          All matching assumptions are correct
        </label>
      </div>
      {hardBlocks.length || warnings.length ? (
        <div className="mb-3 grid gap-2 text-xs md:grid-cols-2">
          {hardBlocks.length ? <DiagnosticMessageList title="Hard Blocks" messages={hardBlocks} tone="danger" /> : null}
          {warnings.length ? <DiagnosticMessageList title="Warnings" messages={warnings} tone="warning" /> : null}
        </div>
      ) : null}
      <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="grid grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_64px] border-b border-slate-100 bg-slate-100 px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <div>Derived Identity</div>
          <div>Amazon</div>
          <div>eBay</div>
          <div className="text-center">Wrong</div>
        </div>
        <div className="divide-y divide-slate-100">
          {identityRows.length ? identityRows.map((diagnosticRow) => {
            const family = diagnosticRow.ruleFamily ?? diagnosticRow.key;
            const active = failed.has(family);
            const status = summaryStatusForRow(diagnosticRow, hardBlocks, warnings);
            return (
              <div key={diagnosticRow.key} className={`grid grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_64px] items-center gap-2 px-2 py-2 text-xs ${status === "fail" ? "bg-rose-50" : status === "warning" ? "bg-amber-50" : ""}`}>
                <div className="font-medium text-slate-800">{diagnosticRow.label}</div>
                <div className="break-words text-slate-700">{formatCompactDiagnosticCell(diagnosticRow.amazon)}</div>
                <div className="break-words text-slate-700">{formatCompactDiagnosticCell(diagnosticRow.ebay)}</div>
                <label className="inline-flex items-center justify-center text-slate-700">
                  <input
                    type="checkbox"
                    checked={active}
                    disabled={allAssumptionsCorrect}
                    onChange={(event) => {
                      const next = new Set(failed);
                      if (event.target.checked) next.add(family);
                      else next.delete(family);
                      onFailedRuleFamiliesChange([...next]);
                    }}
                    className="h-4 w-4"
                    aria-label={`${diagnosticRow.label} incorrect match`}
                  />
                </label>
              </div>
            );
          }) : <div className="px-3 py-6 text-center text-sm text-slate-500">Diagnostics not available.</div>}
        </div>
      </div>
      <div className="mt-3 overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-100 bg-slate-100 px-2 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Evidence Used</div>
        <div className="grid gap-0 divide-y divide-slate-100 text-xs md:grid-cols-2 md:divide-x md:divide-y-0">
          {evidenceRows.map((diagnosticRow) => (
            <EvidenceRow key={diagnosticRow.key} row={diagnosticRow} />
          ))}
          {!evidenceRows.length ? <div className="px-3 py-4 text-slate-500">Evidence not available.</div> : null}
        </div>
      </div>
      <div className="mt-3 rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Matching Summary</div>
        <div className="flex flex-wrap gap-2">
          {summaryRows.map((item) => (
            <span key={item.label} className={`inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium ${summaryClass(item.status)}`}>
              <span aria-hidden="true">{summaryIcon(item.status)}</span>
              {item.label}
            </span>
          ))}
          <span className="ml-auto inline-flex items-center gap-2 rounded bg-slate-900 px-2 py-1 text-xs font-semibold text-white">
            Overall <span>{friendlyRecommendation(comparison?.recommendation, hardBlocks)}</span>
          </span>
        </div>
      </div>
    </aside>
  );
}

type DiagnosticsDisplayRow = {
  key: string;
  label: string;
  amazon: string | null;
  ebay: string | null;
  evidence: string | null;
  kind?: "identity" | "evidence" | "context";
  ruleFamily?: string;
  evidenceSource?: string;
  photoUrls?: string[];
};

type SummaryStatus = "pass" | "warning" | "fail" | "unknown";

const DIAGNOSTIC_IDENTITY_KEYS = [
  "core_game_identity",
  "installment_number",
  "platform_system",
  "edition_version",
  "region",
  "package_bundle_contents",
  "completeness",
  "digital_physical",
];

const DIAGNOSTIC_EVIDENCE_KEYS = [
  "amazon_title",
  "ebay_title",
  "ebay_game_name",
  "ebay_item_specifics",
  "ebay_description",
  "photos",
  "category",
];

const SUMMARY_LABELS: Record<string, string> = {
  core_game_identity: "Core Game",
  platform_system: "Platform",
  edition_version: "Edition",
  region: "Region",
};

function diagnosticsIdentityRows(row: SourcingOpportunity, rows: NonNullable<SourcingOpportunity["diagnosticComparison"]>["rows"]): DiagnosticsDisplayRow[] {
  const byKey = new Map(rows.map((item) => [item.key, item]));
  return DIAGNOSTIC_IDENTITY_KEYS
    .map((key) => byKey.get(key))
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .map((item) => identityDisplayRow(row, item))
    .filter((item) => hasUsefulDiagnosticValue(item.amazon) || hasUsefulDiagnosticValue(item.ebay));
}

function identityDisplayRow(row: SourcingOpportunity, item: NonNullable<SourcingOpportunity["diagnosticComparison"]>["rows"][number]): DiagnosticsDisplayRow {
  const diagnostics = diagnosticRecord(row.matchingDiagnostics);
  const staticRules = diagnosticRecord(diagnostics.static_rules);
  const evidence = diagnosticRecord(staticRules.normalized_evidence ?? diagnostics.normalized_evidence);
  const titleOverlap = diagnosticRecord(staticRules.title_overlap ?? diagnostics.title_overlap);
  const numeric = diagnosticRecord(staticRules.numeric_identity ?? diagnostics.numeric_identity);
  const gameName = firstArrayText(evidence.game_name_values) ?? firstDiagnosticEvidence("ebay_game_name", row);
  const sharedIdentity = sharedTitleIdentity(titleOverlap, row.amazonTitle, row.ebayTitle, gameName);
  const platform = firstArrayText(evidence.platform_values);
  const region = firstArrayText(evidence.region_code_values) ?? firstArrayText(evidence.country_of_origin_values);
  const features = firstArrayText(evidence.features_values);
  const format = firstArrayText(evidence.format_values) ?? firstArrayText(evidence.type_values);

  if (item.key === "core_game_identity") {
    const amazonCore = coreGameDisplayName(row.amazonTitle, gameName, sharedIdentity);
    return { ...item, amazon: amazonCore ?? sharedIdentity ?? item.amazon, ebay: gameName ?? sharedIdentity ?? item.ebay };
  }
  if (item.key === "installment_number") {
    return {
      ...item,
      amazon: numericIdentitySummary(numeric, "amazon") ?? "Base game",
      ebay: numericIdentitySummary(numeric, "ebay") ?? "Base game",
    };
  }
  if (item.key === "platform_system") return { ...item, ebay: platform ?? item.ebay };
  if (item.key === "region") return { ...item, ebay: region ?? item.ebay };
  if (item.key === "package_bundle_contents") return { ...item, ebay: features ?? item.ebay };
  if (item.key === "completeness") return { ...item, amazon: "Complete physical game", ebay: plainOutcome(item.ebay, "No incompleteness found") };
  if (item.key === "digital_physical") return { ...item, amazon: "Physical game", ebay: format ?? plainOutcome(item.ebay, "Physical listing") };
  return item;
}

function diagnosticsEvidenceRows(row: SourcingOpportunity, rows: NonNullable<SourcingOpportunity["diagnosticComparison"]>["rows"]): DiagnosticsDisplayRow[] {
  const byKey = new Map(rows.map((item) => [item.key, item]));
  return DIAGNOSTIC_EVIDENCE_KEYS
    .map((key) => {
      const item = byKey.get(key);
      if (!item) return null;
      if (key === "ebay_description") return { ...item, ebay: descriptionPreview(item.ebay) };
      if (key === "photos") return { ...item, ebay: null, photoUrls: sourcingPhotoUrls(row) };
      return item;
    })
    .filter((item): item is DiagnosticsDisplayRow => Boolean(item))
    .filter((item) => item.key === "photos" || hasUsefulDiagnosticValue(item.ebay));
}

function EvidenceRow({ row }: { row: DiagnosticsDisplayRow }) {
  if (row.key === "photos") {
    const urls = row.photoUrls ?? [];
    return (
      <div className="grid grid-cols-[128px_minmax(0,1fr)] gap-2 px-2 py-2">
        <div className="font-medium text-slate-700">Photos</div>
        {urls.length ? (
          <div className="flex gap-2">
            {urls.slice(0, 3).map((url) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={url} src={url} alt="" className="h-14 w-14 rounded border border-slate-200 bg-slate-50 object-contain" loading="lazy" />
            ))}
          </div>
        ) : (
          <div className="text-slate-600">{formatCompactDiagnosticCell(row.ebay)}</div>
        )}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[128px_minmax(0,1fr)] gap-2 px-2 py-2">
      <div className="font-medium text-slate-700">{row.label}</div>
      <div className="break-words text-slate-600">{formatCompactDiagnosticCell(row.ebay)}</div>
    </div>
  );
}

function DiagnosticMessageList({ title, messages, tone }: { title: string; messages: string[]; tone: "danger" | "warning" }) {
  const className = tone === "danger" ? "border-rose-200 bg-rose-50 text-rose-950" : "border-amber-200 bg-amber-50 text-amber-950";
  return (
    <div className={`rounded-md border p-2 ${className}`}>
      <div className="mb-1 font-semibold">{title}</div>
      <div className="space-y-1">
        {messages.map((message) => <div key={message}>{message}</div>)}
      </div>
    </div>
  );
}

function formatCompactDiagnosticCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "string") {
    const text = stripHtml(value).replace(/\bResult:\s*pass;?\s*/gi, "").replace(/\bpass\b/gi, "").replace(/\s+/g, " ").trim();
    return text || "Not available";
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(formatCompactDiagnosticCell).filter((item) => item !== "Not available").join(", ") || "Not available";
  return "Structured diagnostic";
}

function hasUsefulDiagnosticValue(value: unknown) {
  return formatCompactDiagnosticCell(value) !== "Not available";
}

function diagnosticRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringArrayValue(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter(Boolean) : [];
}

function firstArrayText(value: unknown) {
  return stringArrayValue(value)[0] ?? null;
}

function firstDiagnosticEvidence(key: string, row: SourcingOpportunity) {
  return row.diagnosticComparison?.rows.find((item) => item.key === key)?.ebay ?? null;
}

function sharedTitleIdentity(titleOverlap: Record<string, unknown>, amazonTitle: string, ebayTitle: string, ebayGameName: string | null) {
  const shared = stringArrayValue(titleOverlap.shared_title_tokens ?? titleOverlap.shared_tokens);
  if (!shared.length) return null;
  const source = ebayGameName ?? ebayTitle ?? amazonTitle;
  const sourceWords = source.match(/[a-z0-9]+(?:['-][a-z0-9]+)*/gi) ?? [];
  const ordered = sourceWords.filter((word, index) => {
    const normalized = word.toLowerCase().replace(/s$/, "");
    return shared.includes(normalized) && sourceWords.findIndex((candidate) => candidate.toLowerCase().replace(/s$/, "") === normalized) === index;
  });
  return titleCase(ordered.join(" ")) || titleCase(shared.join(" "));
}

function coreGameDisplayName(amazonTitle: string, ebayGameName: string | null, sharedIdentity: string | null) {
  if (ebayGameName && containsSameCoreTokens(amazonTitle, ebayGameName)) return ebayGameName;
  return cleanedCoreTitle(amazonTitle) ?? sharedIdentity;
}

function containsSameCoreTokens(title: string, candidate: string) {
  const titleTokens = normalizedDisplayTokens(title);
  const candidateTokens = normalizedDisplayTokens(candidate);
  if (!candidateTokens.length) return false;
  if (!candidateTokens.every((token) => titleTokens.includes(token))) return false;
  const titleNumbers = titleTokens.filter((token) => /^\d+$/.test(token));
  const candidateNumbers = candidateTokens.filter((token) => /^\d+$/.test(token));
  return titleNumbers.every((number) => candidateNumbers.includes(number) || isPlatformNumber(number, title));
}

function cleanedCoreTitle(value: string) {
  const text = value
    .replace(/\[[^\]]*\]/g, " ")
    .replace(/\([^)]*\)/g, " ")
    .replace(/\b(?:playstation|sony|microsoft|nintendo|xbox|switch|ps[1-5]|ps4|ps5|xbox one|xbox 360|wii u?|3ds|ds|pc)\b/gi, " ")
    .replace(/\b(?:complete edition|limited edition|special edition|collector'?s edition|brand new|new|sealed|video game)\b/gi, " ")
    .replace(/\s+[-:]\s*$/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text || null;
}

function normalizedDisplayTokens(value: string) {
  return (value.match(/[a-z0-9]+/gi) ?? []).map((token) => token.toLowerCase());
}

function isPlatformNumber(number: string, title: string) {
  return new RegExp(`\\b(?:playstation|ps|xbox)\\s*${number}\\b`, "i").test(title);
}

function numericIdentitySummary(numeric: Record<string, unknown>, side: "amazon" | "ebay") {
  const identities = stringArrayValue(numeric[`${side}_identity_numbers`]);
  const baseIdentities = stringArrayValue(numeric[`${side}_base_identities`]);
  if (identities.length) return identities.join(", ");
  if (baseIdentities.length) return baseIdentities.map((value) => `${titleCase(value)} base`).join(", ");
  return null;
}

function plainOutcome(value: unknown, passFallback: string) {
  const text = formatCompactDiagnosticCell(value);
  if (text === "Not available") return null;
  if (/^Result:\s*pass\b/i.test(String(value))) return passFallback;
  return text;
}

function descriptionPreview(value: unknown) {
  const text = stripHtml(formatCompactDiagnosticCell(value));
  return text.length > 220 ? `${text.slice(0, 220).trim()}...` : text;
}

function stripHtml(value: string) {
  return value
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, "\"")
    .replace(/&#39;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function sourcingPhotoUrls(row: SourcingOpportunity) {
  const diagnostics = diagnosticRecord(row.matchingDiagnostics);
  const staticRules = diagnosticRecord(diagnostics.static_rules);
  const evidence = diagnosticRecord(staticRules.normalized_evidence ?? diagnostics.normalized_evidence);
  const urls = [row.ebayImageUrl, ...stringArrayValue(evidence.image_urls)]
    .map((url) => String(url ?? "").trim())
    .filter(Boolean);
  return [...new Set(urls)].slice(0, 3);
}

function cleanDiagnosticMessages(messages: string[]) {
  return messages.map((message) => message.replace(/^Blocked:\s*/i, "").trim()).filter(Boolean);
}

function diagnosticsSummaryRows(identityRows: DiagnosticsDisplayRow[], hardBlocks: string[], warnings: string[]) {
  return identityRows
    .filter((item) => item.key in SUMMARY_LABELS)
    .map((item) => ({ label: SUMMARY_LABELS[item.key], status: summaryStatusForRow(item, hardBlocks, warnings) }));
}

function summaryStatusForRow(row: DiagnosticsDisplayRow, hardBlocks: string[], warnings: string[]): SummaryStatus {
  const haystack = [row.key, row.ruleFamily, row.label, row.amazon, row.ebay, row.evidence].join(" ").toLowerCase();
  const blockText = hardBlocks.join(" ").toLowerCase();
  const warningText = warnings.join(" ").toLowerCase();
  if (blockText && summaryTerms(row).some((term) => blockText.includes(term))) return "fail";
  if (warningText && summaryTerms(row).some((term) => warningText.includes(term))) return "warning";
  if (haystack.includes("not available")) return "unknown";
  return "pass";
}

function summaryTerms(row: DiagnosticsDisplayRow) {
  if (row.key === "core_game_identity") return ["title", "game name", "different game", "core game", "overlap"];
  if (row.key === "platform_system") return ["platform", "system"];
  if (row.key === "edition_version") return ["edition", "version"];
  if (row.key === "region") return ["region", "north american", "pal", "ntsc"];
  return [row.label.toLowerCase()];
}

function friendlyRecommendation(recommendation: string | null | undefined, hardBlocks: string[]) {
  if (hardBlocks.length) return "Rejected";
  if (!recommendation) return "Review";
  return recommendation.replace(/^Probable Non-Match$/i, "Rejected");
}

function summaryIcon(status: SummaryStatus) {
  if (status === "fail") return "x";
  if (status === "warning") return "!";
  if (status === "unknown") return "-";
  return "+";
}

function summaryClass(status: SummaryStatus) {
  if (status === "fail") return "bg-rose-50 text-rose-800";
  if (status === "warning") return "bg-amber-50 text-amber-800";
  if (status === "unknown") return "bg-slate-100 text-slate-600";
  return "bg-emerald-50 text-emerald-800";
}

function titleCase(value: string) {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase()).trim();
}

function evidenceSourcesForRuleFamilies(families: string[]) {
  const defaults: Record<string, string[]> = {
    core_game_identity: ["amazon_title", "ebay_title", "ebay_game_name"],
    numeric_installment: ["amazon_title", "ebay_title", "ebay_item_specifics"],
    platform: ["amazon_title", "ebay_title", "platform_metadata", "ebay_item_specifics"],
    edition_version: ["amazon_title", "ebay_title", "ebay_item_specifics"],
    region: ["ebay_item_specifics", "category"],
    completeness: ["ebay_title", "ebay_item_specifics", "ebay_description", "primary_image", "additional_images"],
    digital_physical: ["ebay_title", "ebay_item_specifics", "ebay_description", "category"],
    category_product_type: ["category", "ebay_item_specifics", "ebay_title"],
    seller_listing_photo_consistency: ["primary_image", "additional_images", "ebay_title"],
    other: ["other"],
  };
  return [...new Set(families.flatMap((family) => defaults[family] ?? ["other"]))];
}

function legacyRowsForRuleFamilies(families: string[]) {
  const legacy: Record<string, string[]> = {
    core_game_identity: ["core_game_identity"],
    numeric_installment: ["installment_number"],
    platform: ["platform_system"],
    edition_version: ["edition_version"],
    region: ["region"],
    completeness: ["completeness", "package_bundle_contents"],
    digital_physical: ["digital_physical"],
    category_product_type: ["category", "format_type"],
    seller_listing_photo_consistency: ["seller_listing_photo_consistency"],
    other: ["opportunity_context"],
  };
  return [...new Set(families.flatMap((family) => legacy[family] ?? ["opportunity_context"]))];
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
      <div className="grid gap-2 sm:grid-cols-2">
        {dismissReasons.map(([value, reasonLabel]) => (
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
        <div className="grid grid-cols-2 gap-3 md:grid-cols-7">
          <Metric label="Coverage" value={Math.round(cycle.completion_percentage ?? 0)} />
          <Metric label="Eligible ASINs" value={cycle.total_eligible_asins ?? 0} />
          <Metric label="Searched" value={cycle.searched_count ?? 0} />
          <Metric label="Remaining" value={cycle.remaining_count ?? 0} />
          <Metric label="Opportunities Presented" value={summary?.opportunitiesPresented?.total ?? 0} />
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

      {summary?.completedCycles?.length ? (
        <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">
          <div className="mb-3 text-sm font-semibold text-slate-900">Completed Cycle History</div>
          <div className="grid gap-3 xl:grid-cols-3">
            {summary.completedCycles.map((completed) => (
              <CompletedCycleCard key={completed.cycle?.coverage_cycle_id} summary={completed} />
            ))}
          </div>
        </div>
      ) : null}

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
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full text-left text-xs">
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
    </div>
  );
}

function CompletedCycleCard({ summary }: { summary: CoverageCycleSnapshot }) {
  const cycle = summary.cycle;
  const lastRun = summary.lastRun;
  if (!cycle) return null;
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="mb-2">
        <div className="text-sm font-semibold text-slate-900">Cycle {cycle.cycle_number ?? cycle.coverage_cycle_id}</div>
        <div className="text-xs text-slate-500">
          {date(cycle.started_at)} - {date(cycle.completed_at)}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <HistoryMetric label="Coverage" value={`${Math.round(cycle.completion_percentage ?? 0)}%`} />
        <HistoryMetric label="Eligible" value={String(cycle.total_eligible_asins ?? 0)} />
        <HistoryMetric label="Searched" value={String(cycle.searched_count ?? 0)} />
        <HistoryMetric label="Remaining" value={String(cycle.remaining_count ?? 0)} />
        <HistoryMetric label="Opportunities Presented" value={String(summary.opportunitiesPresented?.total ?? 0)} />
        <HistoryMetric label="Calls" value={String(lastRun?.api_call_count ?? 0)} />
        <HistoryMetric label="Quota Left" value={String(lastRun?.ending_browse_quota_remaining ?? lastRun?.starting_browse_quota_remaining ?? 0)} />
      </div>
      <div className="mt-2 grid gap-1 text-xs text-slate-600">
        <div>Stop: <span className="font-medium text-slate-800">{stopReasonLabel(lastRun?.stop_reason ?? cycle.last_stop_reason ?? "", lastRun)}</span></div>
        <div>Reset: <span className="font-medium text-slate-800">{date(lastRun?.browse_quota_reset_at ?? cycle.last_quota_reset_at)}</span></div>
      </div>
      <div className="mt-3 space-y-2">
        {summary.bucketSummary.map((bucket) => (
          <div key={bucket.priorityBucket}>
            <div className="mb-1 flex items-center justify-between gap-2 text-xs">
              <span className="font-medium text-slate-700">{bucket.label}</span>
              <span className="text-slate-500">{bucket.searched}/{bucket.total}</span>
            </div>
            <div className="h-2 rounded bg-slate-200">
              <div className="h-2 rounded bg-emerald-600" style={{ width: `${Math.min(bucket.progress, 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistoryMetric({ label: metricLabel, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 bg-slate-50 px-2 py-1">
      <div className="font-semibold uppercase tracking-wide text-slate-500">{metricLabel}</div>
      <div className="mt-0.5 font-medium text-slate-900">{value}</div>
    </div>
  );
}

type CoverageCycleSnapshot = {
  cycle: {
    coverage_cycle_id: string;
    cycle_number?: number | null;
    status?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    completion_percentage?: number | null;
    total_eligible_asins?: number | null;
    searched_count?: number | null;
    remaining_count?: number | null;
    last_run_id?: string | null;
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
  opportunitiesPresented?: {
    total: number;
    buyNow: number;
    bestOffer: number;
    auction: number;
    multiUnit: number;
  };
  statusMessage: string | null;
};

type CoverageCycleSummary = CoverageCycleSnapshot & {
  completedCycles?: CoverageCycleSnapshot[];
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

function myPipelineTitle(row: SourcingOpportunity) {
  return [
    row.myPurchasedQuantity > 0 ? `${row.myPurchasedQuantity} purchased/not received` : null,
    row.myReceivedQuantity > 0 ? `${row.myReceivedQuantity} received/not sent` : null,
    row.myOutboundQuantity > 0 ? `${row.myOutboundQuantity} outbound to Amazon` : null,
  ].filter(Boolean).join("; ");
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

function inventorySnoozePayload(row: SourcingOpportunity): SourcingActionPayload {
  return {
    actionType: "inventory_snooze",
    inventoryBaselineUnits: row.myQuantity + row.myPipelineQuantity,
    myQuantity: row.myQuantity,
    myPipelineQuantity: row.myPipelineQuantity,
    myPurchasedQuantity: row.myPurchasedQuantity,
    myReceivedQuantity: row.myReceivedQuantity,
    myOutboundQuantity: row.myOutboundQuantity,
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
