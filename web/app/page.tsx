"use client";

import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import { PurchaseDetailDrawer } from "./purchases/PurchaseDetailDrawer";
import { PurchaseFilters } from "./purchases/PurchaseFilters";
import { PurchaseMetrics } from "./purchases/PurchaseMetrics";
import { PurchaseProblemTable } from "./purchases/PurchaseProblemTable";
import { PurchasesTable } from "./purchases/PurchasesTable";
import type {
  PurchaseQuery,
  PurchaseRow,
  PurchaseSortColumn,
  PurchaseSortDirection,
} from "./purchases/types";
import { usePurchases } from "./purchases/usePurchases";
import { rowKey } from "./purchases/utils";
import { runOnDemandRefresh, type RefreshNotice } from "./syncRefresh";
import { DataFreshness } from "./DataFreshness";
import { mutationHeaders } from "./mutationHeaders";

const PAGE_SIZE = 100;

export default function PurchasesPage() {
  const [viewMode, setViewMode] = useState<"purchases" | "order_problems">(
    "purchases"
  );
  const [searchText, setSearchText] = useState("");
  const [asinFilter, setAsinFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");
  const [problemStage, setProblemStage] = useState("open");
  const [sortColumn, setSortColumn] = useState<PurchaseSortColumn>("order_date");
  const [sortDirection, setSortDirection] =
    useState<PurchaseSortDirection>("desc");
  const [page, setPage] = useState(1);
  const effectiveAsinFilter =
    viewMode === "order_problems" ? "order_problems" : asinFilter;
  const effectiveStatusFilter =
    viewMode === "order_problems" ? "active" : statusFilter;
  const effectiveSortColumn =
    viewMode === "order_problems" ? "order_date" : sortColumn;
  const effectiveSortDirection =
    viewMode === "order_problems" ? "asc" : sortDirection;
  const query = useMemo<PurchaseQuery>(
    () => ({
      searchText,
      asinFilter: effectiveAsinFilter,
      statusFilter: effectiveStatusFilter,
      sortColumn: effectiveSortColumn,
      sortDirection: effectiveSortDirection,
      page,
      pageSize: PAGE_SIZE,
      problemStage: viewMode === "order_problems" ? problemStage : undefined,
    }),
    [
      effectiveAsinFilter,
      effectiveSortColumn,
      effectiveSortDirection,
      effectiveStatusFilter,
      page,
      problemStage,
      searchText,
      viewMode,
    ]
  );

  const {
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
  } = usePurchases(query);

  const [selectedRow, setSelectedRow] = useState<PurchaseRow | null>(null);
  const [drawerAsin, setDrawerAsin] = useState("");
  const [drawerAmazonTitle, setDrawerAmazonTitle] = useState("");
  const [drawerSellPrice, setDrawerSellPrice] = useState("");
  const [drawerEbayTitle, setDrawerEbayTitle] = useState("");
  const [drawerUnitCost, setDrawerUnitCost] = useState("");
  const [drawerSystem, setDrawerSystem] = useState("");
  const [priceDrafts, setPriceDrafts] = useState<Record<string, string>>({});
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);
  const [freshnessKey, setFreshnessKey] = useState(0);

  async function refreshPurchases() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh(
        "purchases",
        () => loadPurchases({ forceRefresh: true }),
        setRefreshNotice,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  async function saveSellPrice(row: PurchaseRow) {
    const key = rowKey(row);
    const draft = priceDrafts[key];

    if (draft === undefined) return;

    const parsed = draft.trim() === "" ? null : Number(draft);

    if (draft.trim() !== "" && Number.isNaN(parsed)) {
      setError("Sell price must be a valid number.");
      return;
    }

    const updatedRow = await patchPurchase(row, {
      sell_price: parsed,
      target_price: parsed,
    });

    if (updatedRow) {
      setSelectedRow((current) =>
        current && rowKey(current) === key ? updatedRow : current
      );
    }

    setPriceDrafts((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  async function saveDrawerMatch() {
    if (!selectedRow) return;

    const parsedUnitCost =
      drawerUnitCost.trim() === "" ? null : Number(drawerUnitCost);
    const parsedSellPrice =
      drawerSellPrice.trim() === "" ? null : Number(drawerSellPrice);

    if (drawerUnitCost.trim() !== "" && Number.isNaN(parsedUnitCost)) {
      setError("Purchase price must be a valid number.");
      return;
    }

    if (drawerSellPrice.trim() !== "" && Number.isNaN(parsedSellPrice)) {
      setError("Sell price must be a valid number.");
      return;
    }

    const updatedRow = await patchPurchase(selectedRow, {
      asin: drawerAsin.trim().toUpperCase() || null,
      amazon_title: drawerAmazonTitle.trim() || null,
      sell_price: parsedSellPrice,
      target_price: parsedSellPrice,
      title: drawerEbayTitle.trim() || null,
      ebay_title: drawerEbayTitle.trim() || null,
      unit_cost: parsedUnitCost,
      system: drawerSystem || null,
    });

    if (updatedRow) {
      setSelectedRow(updatedRow);
      setDrawerAmazonTitle(updatedRow.amazon_title || "");
      setDrawerSellPrice(formatPriceDraft(updatedRow.sell_price ?? updatedRow.target_price));
      setDrawerUnitCost(formatPriceDraft(updatedRow.unit_cost));
      setDrawerEbayTitle(updatedRow.ebay_title || updatedRow.title || "");
      setDrawerSystem(updatedRow.system || "");
    }
  }

  async function addSplitItem() {
    if (!selectedRow) return;

    const newRow = await createSplitItem(selectedRow);

    if (newRow) {
      setSelectedRow(newRow);
      setDrawerAsin("");
      setDrawerAmazonTitle("");
      setDrawerSellPrice("");
      setDrawerEbayTitle(newRow.ebay_title || newRow.title || "");
      setDrawerUnitCost("");
      setDrawerSystem(newRow.system || "");
    }
  }

  async function markSelectedReturnPending() {
    if (!selectedRow) return;

    const updatedRow = await patchPurchase(selectedRow, {
      current_status: "return_pending",
    });

    if (updatedRow) {
      setSelectedRow(updatedRow);
    }
  }

  async function runSelectedProblemAction(
    action: string,
    payload: { notes?: string; amount?: number | null; tracking_number?: string | null; problem_type?: string | null } = {},
  ) {
    if (!selectedRow?.problem_case_id) return;

    setError(null);

    try {
      const response = await fetch(`/api/order-problems/${selectedRow.problem_case_id}/actions`, {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ action, ...payload }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Workflow action failed: ${response.status}`);
      }

      const result = await response.json();
      const updatedCase = result.case as Record<string, unknown> | null;
      const event = result.event as NonNullable<PurchaseRow["problem_events"]>[number] | null;
      await loadPurchases({ forceRefresh: true });

      if (
        updatedCase &&
        updatedCase.is_open !== false &&
        !String(updatedCase.workflow_state ?? "").startsWith("resolved_") &&
        !String(updatedCase.workflow_state ?? "").startsWith("closed_")
      ) {
        setSelectedRow((current) =>
          current
            ? {
                ...current,
                problem_type: String(updatedCase.problem_type ?? current.problem_type ?? ""),
                workflow_state: String(updatedCase.workflow_state ?? current.workflow_state ?? ""),
                problem_priority: String(updatedCase.priority ?? current.problem_priority ?? ""),
                problem_is_open: Boolean(updatedCase.is_open),
                problem_needs_response: Boolean(updatedCase.needs_response),
                problem_next_action: String(updatedCase.next_action ?? ""),
                problem_next_action_due_at: String(updatedCase.next_action_due_at ?? ""),
                ebay_return_status: String(updatedCase.ebay_return_status ?? current.ebay_return_status ?? ""),
                problem_episode_kind: String(updatedCase.episode_kind ?? current.problem_episode_kind ?? ""),
                problem_episode_sequence: numberOrNull(updatedCase.episode_sequence) ?? current.problem_episode_sequence ?? null,
                problem_opened_reason: String(updatedCase.opened_reason ?? current.problem_opened_reason ?? ""),
                problem_resolved_reason: String(updatedCase.resolved_reason ?? current.problem_resolved_reason ?? ""),
                problem_superseded_by_case_id: String(updatedCase.superseded_by_case_id ?? current.problem_superseded_by_case_id ?? ""),
                problem_source_artifact_type: String(updatedCase.source_artifact_type ?? current.problem_source_artifact_type ?? ""),
                expected_refund_amount: numberOrNull(updatedCase.expected_refund_amount),
                actual_refund_amount: numberOrNull(updatedCase.actual_refund_amount),
                partial_refund_amount: numberOrNull(updatedCase.partial_refund_amount),
                replacement_tracking_number: String(
                  updatedCase.replacement_tracking_number ?? current.replacement_tracking_number ?? "",
                ),
                problem_notes: String(updatedCase.notes ?? current.problem_notes ?? ""),
                problem_events: event
                  ? [event, ...(current.problem_events ?? [])].slice(0, 12)
                  : current.problem_events,
              }
            : current,
        );
      } else {
        setSelectedRow(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow action failed.");
    }
  }

  function updatePriceDraft(key: string, value: string) {
    setPriceDrafts((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function updateSearchText(value: string) {
    setSearchText(value);
    setPage(1);
  }

  function updateAsinFilter(value: string) {
    setAsinFilter(value);
    setPage(1);
  }

  function updateStatusFilter(value: string) {
    setStatusFilter(value);
    setPage(1);
  }

  function updateSort(column: PurchaseSortColumn) {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection(column === "order_date" ? "desc" : "asc");
    }
    setPage(1);
  }

  function updateViewMode(mode: "purchases" | "order_problems") {
    setViewMode(mode);
    setPage(1);
  }

  const totalPages = Math.max(Math.ceil(totalRows / PAGE_SIZE), 1);

  function openDetails(row: PurchaseRow) {
    setSelectedRow(row);
    setDrawerAsin(row.asin || "");
    setDrawerAmazonTitle(row.amazon_title || "");
    setDrawerSellPrice(formatPriceDraft(row.sell_price ?? row.target_price));
    setDrawerEbayTitle(row.ebay_title || row.title || "");
    setDrawerUnitCost(formatPriceDraft(row.unit_cost));
    setDrawerSystem(row.system || "");
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Purchases</h1>
          <p className="text-sm text-slate-600">
            MBOP purchase verification workspace
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="purchases" refreshKey={freshnessKey} />
          <button
            onClick={refreshPurchases}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
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

      <div className="mb-4 flex flex-wrap gap-2">
        <TabButton
          active={viewMode === "purchases"}
          onClick={() => updateViewMode("purchases")}
        >
          Purchases
        </TabButton>
        <TabButton
          active={viewMode === "order_problems"}
          onClick={() => updateViewMode("order_problems")}
        >
          Order Problems
        </TabButton>
      </div>

      {viewMode === "purchases" ? (
        <>
          <PurchaseMetrics stats={stats} />

          <PurchaseFilters
            searchText={searchText}
            asinFilter={asinFilter}
            statusFilter={statusFilter}
            onSearchTextChange={updateSearchText}
            onAsinFilterChange={updateAsinFilter}
            onStatusFilterChange={updateStatusFilter}
          />
        </>
      ) : (
        <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-600 shadow-sm">
          Order Problems is an episode queue for past-ETA rows, stale/no-tracking rows,
          carrier exceptions, and return/refund follow-up. Closed episodes stay as history.
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {viewMode === "purchases" ? (
        <PurchasesTable
          rows={rows}
          loading={loading}
          priceDrafts={priceDrafts}
          savingKey={savingKey}
          sortColumn={sortColumn}
          sortDirection={sortDirection}
          onSort={updateSort}
          onPriceDraftChange={updatePriceDraft}
          onSaveSellPrice={saveSellPrice}
          onSelectRow={openDetails}
        />
      ) : (
        <PurchaseProblemTable
          rows={rows}
          loading={loading}
          stage={problemStage}
          onStageChange={(value) => {
            setProblemStage(value);
            setPage(1);
          }}
          onSelectRow={openDetails}
        />
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
        <div>
          Showing page {page} of {totalPages} ({totalRows.toLocaleString("en-US")} rows)
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={page <= 1 || loading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
            disabled={page >= totalPages || loading}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>

      {selectedRow && (
        <PurchaseDetailDrawer
          row={selectedRow}
          drawerAsin={drawerAsin}
          drawerAmazonTitle={drawerAmazonTitle}
          drawerSellPrice={drawerSellPrice}
          drawerEbayTitle={drawerEbayTitle}
          drawerUnitCost={drawerUnitCost}
          drawerSystem={drawerSystem}
          savingKey={savingKey}
          onAsinChange={setDrawerAsin}
          onAmazonTitleChange={setDrawerAmazonTitle}
          onSellPriceChange={setDrawerSellPrice}
          onEbayTitleChange={setDrawerEbayTitle}
          onUnitCostChange={setDrawerUnitCost}
          onSystemChange={setDrawerSystem}
          onAddSplitItem={addSplitItem}
          onMarkReturnPending={markSelectedReturnPending}
          onProblemAction={runSelectedProblemAction}
          onSave={saveDrawerMatch}
          onClose={() => setSelectedRow(null)}
        />
      )}
    </main>
  );
}

function TabButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-2 text-sm font-medium shadow-sm ${
        active
          ? "border-slate-900 bg-slate-900 text-white"
          : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
      }`}
    >
      {children}
    </button>
  );
}

function formatPriceDraft(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }

  return Number(value).toFixed(2);
}

function numberOrNull(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}
