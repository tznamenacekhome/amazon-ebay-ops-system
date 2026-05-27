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

const PAGE_SIZE = 100;

export default function PurchasesPage() {
  const [viewMode, setViewMode] = useState<"purchases" | "order_problems">(
    "purchases"
  );
  const [searchText, setSearchText] = useState("");
  const [asinFilter, setAsinFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("active");
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
    }),
    [
      effectiveAsinFilter,
      effectiveSortColumn,
      effectiveSortDirection,
      effectiveStatusFilter,
      page,
      searchText,
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

        <button
          onClick={() => loadPurchases({ forceRefresh: true })}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

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
          Order Problems includes past-ETA rows, stale/no-tracking rows between 7 and 90 days old,
          carrier exceptions, and return-pending rows. Use this list for supplier, carrier, or refund follow-up.
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
