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
import type { SourcingOpportunity, SourcingRun, SourcingSettings } from "./types";
import { useSourcingOpportunities } from "./useSourcingOpportunities";
import { dismissReasonGroups } from "./matchingTaxonomy";
import { mutationHeaders } from "../mutationHeaders";

const tabs = ["Replenishment", "Watchlist", "Purchased Pending Match", "Sourcing History", "Matching Intelligence", "Settings"] as const;
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
  const { rows, summary, loading, error, reload, removeRows, setError } = useSourcingOpportunities(
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
    setNotice("Starting sourcing workflow...");
    try {
      const runTypes = sourceMode === "all" ? ["recent_sales", "full_listings"] : [sourceMode];
      for (const runType of runTypes) {
        setNotice(`Running ${runType === "full_listings" ? "all listings" : "recently sold"} sourcing workflow...`);
        const response = await fetch("/api/sourcing/runs", {
          method: "POST",
          headers: mutationHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ runType, execute: true }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error ?? "Sourcing workflow failed.");
      }
      setSelectedIds(new Set());
      await reload();
      setNotice("Sourcing workflow complete. Loaded fresh opportunities.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sourcing workflow failed.");
      setNotice(null);
    } finally {
      setSourcingRefreshRunning(false);
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
        <table className="min-w-full text-left text-sm">
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
              <th className="w-32 px-2 py-2">eBay</th>
              <th className="w-32 px-2 py-2">Amazon</th>
              <th className="w-[26rem] px-2 py-2">Opportunity</th>
              <th className="w-24 px-2 py-2">Cost</th>
              <th className="w-24 px-2 py-2">Last Sold</th>
              <th className="w-24 px-2 py-2">Keepa 90</th>
              <th className="w-24 px-2 py-2">Keepa Now</th>
              <th className="w-24 px-2 py-2">Profit</th>
              <th className="w-16 px-2 py-2">ROI</th>
              <th className="w-24 px-2 py-2">Velocity</th>
              <th className="w-24 px-2 py-2">Type</th>
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
                  <td className="px-2 py-2">
                    {row.ebayImageUrl ? (
                      <OptionalImageLink href={row.ebayUrl}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={row.ebayImageUrl} alt="" className="h-28 w-28 rounded object-cover" />
                      </OptionalImageLink>
                    ) : (
                      <OptionalImageLink href={row.ebayUrl}>
                        <div className="flex h-28 w-28 items-center justify-center rounded bg-slate-100 text-slate-400">--</div>
                      </OptionalImageLink>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {row.amazonImageUrl ? (
                      <OptionalImageLink href={row.amazonUrl}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={row.amazonImageUrl} alt="" className="h-28 w-28 rounded object-cover" />
                      </OptionalImageLink>
                    ) : (
                      <div className="flex h-28 w-28 items-center justify-center rounded bg-slate-100 text-slate-400">--</div>
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
        <div className="text-xs text-slate-500">max bid {money(row.suggestedMaxBid)}</div>
      </div>
    );
  }

  if (row.opportunityType === "best_offer") {
    return (
      <div>
        <div>{label(row.opportunityType ?? "")}</div>
        <div className="text-xs text-slate-500">max offer {money(row.suggestedOfferPrice)}</div>
        <div className="text-xs text-slate-500">{percent(row.requiredOfferPercentOfAsk)} of ask</div>
        <div className="text-xs text-slate-500">landed cap {money(row.maxProfitableLandedCost)}</div>
      </div>
    );
  }

  return <div>{label(row.opportunityType ?? "")}</div>;
}

function DismissOpportunityDialog({
  row,
  actionBusyId,
  onClose,
  onDismiss,
}: {
  row: SourcingOpportunity;
  actionBusyId: string | null;
  onClose: () => void;
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
        </div>
        <div className="space-y-3 px-4 py-4">
          <label className="block text-sm font-medium text-slate-700">
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 min-h-24 w-full rounded-md border border-slate-300 p-2 text-sm" />
          </label>
          <ImageClueButtons selected={imageClues} onChange={setImageClues} />
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
  onDismiss,
}: {
  rows: SourcingOpportunity[];
  busy: boolean;
  onClose: () => void;
  onDismiss: (reason: string, notes: string, imageClues: string[]) => Promise<void>;
}) {
  const [notes, setNotes] = useState("");
  const [imageClues, setImageClues] = useState<string[]>([]);

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
    <Link href={href} target="_blank" className="block rounded-md outline-none ring-offset-2 hover:ring-2 hover:ring-blue-400 focus:ring-2 focus:ring-blue-500">
      {children}
    </Link>
  );
}

function SourcingHistory() {
  const [runs, setRuns] = useState<SourcingRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/sourcing/history")
      .then((response) => response.json())
      .then((payload) => setRuns(payload.runs ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="rounded-md border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Started</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Seeds</th>
            <th className="px-3 py-2">Candidates</th>
            <th className="px-3 py-2">Opportunities</th>
            <th className="px-3 py-2">Run ID</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {loading ? <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-500">Loading run history...</td></tr> : runs.map((run) => (
            <tr key={run.sourcing_run_id}>
              <td className="px-3 py-2">{date(run.started_at)}</td>
              <td className="px-3 py-2">{label(run.run_type)}</td>
              <td className="px-3 py-2">{run.status}</td>
              <td className="px-3 py-2">{run.seed_asin_count ?? 0}</td>
              <td className="px-3 py-2">{run.ebay_candidate_count ?? 0}</td>
              <td className="px-3 py-2">{run.opportunity_count ?? 0}</td>
              <td className="px-3 py-2 font-mono text-xs">{run.sourcing_run_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
