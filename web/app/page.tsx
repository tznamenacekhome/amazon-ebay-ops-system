"use client";

import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import { PurchaseDetailDrawer } from "./purchases/PurchaseDetailDrawer";
import { PurchaseFilters } from "./purchases/PurchaseFilters";
import { PurchaseMetrics } from "./purchases/PurchaseMetrics";
import { PurchasesTable } from "./purchases/PurchasesTable";
import { getPurchaseStats } from "./purchases/purchaseStats";
import type { PurchaseRow } from "./purchases/types";
import { usePurchaseFilters } from "./purchases/usePurchaseFilters";
import { usePurchases } from "./purchases/usePurchases";
import { rowKey } from "./purchases/utils";

export default function PurchasesPage() {
  const {
    rows,
    loading,
    savingKey,
    error,
    setError,
    loadPurchases,
    patchPurchase,
    createSplitItem,
  } = usePurchases();

  const {
    searchText,
    asinFilter,
    statusFilter,
    filteredRows,
    setSearchText,
    setAsinFilter,
    setStatusFilter,
  } = usePurchaseFilters(rows);

  const [selectedRow, setSelectedRow] = useState<PurchaseRow | null>(null);
  const [drawerAsin, setDrawerAsin] = useState("");
  const [drawerSellPrice, setDrawerSellPrice] = useState("");
  const [drawerEbayTitle, setDrawerEbayTitle] = useState("");
  const [drawerUnitCost, setDrawerUnitCost] = useState("");
  const [priceDrafts, setPriceDrafts] = useState<Record<string, string>>({});

  const stats = useMemo(() => {
    return getPurchaseStats(rows, filteredRows);
  }, [rows, filteredRows]);

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
      sell_price: parsedSellPrice,
      target_price: parsedSellPrice,
      title: drawerEbayTitle.trim() || null,
      ebay_title: drawerEbayTitle.trim() || null,
      unit_cost: parsedUnitCost,
    });

    if (updatedRow) {
      setSelectedRow(updatedRow);
      setDrawerSellPrice(formatPriceDraft(updatedRow.sell_price ?? updatedRow.target_price));
      setDrawerUnitCost(formatPriceDraft(updatedRow.unit_cost));
      setDrawerEbayTitle(updatedRow.ebay_title || updatedRow.title || "");
    }
  }

  async function addSplitItem() {
    if (!selectedRow) return;

    const newRow = await createSplitItem(selectedRow);

    if (newRow) {
      setSelectedRow(newRow);
      setDrawerAsin("");
      setDrawerSellPrice("");
      setDrawerEbayTitle(newRow.ebay_title || newRow.title || "");
      setDrawerUnitCost("");
    }
  }

  function updatePriceDraft(key: string, value: string) {
    setPriceDrafts((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function openDetails(row: PurchaseRow) {
    setSelectedRow(row);
    setDrawerAsin(row.asin || "");
    setDrawerSellPrice(formatPriceDraft(row.sell_price ?? row.target_price));
    setDrawerEbayTitle(row.ebay_title || row.title || "");
    setDrawerUnitCost(formatPriceDraft(row.unit_cost));
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Purchases</h1>
          <p className="text-sm text-slate-600">
            eBay purchase verification workspace
          </p>
        </div>

        <button
          onClick={loadPurchases}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      <PurchaseMetrics stats={stats} />

      <PurchaseFilters
        searchText={searchText}
        asinFilter={asinFilter}
        statusFilter={statusFilter}
        onSearchTextChange={setSearchText}
        onAsinFilterChange={setAsinFilter}
        onStatusFilterChange={setStatusFilter}
      />

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <PurchasesTable
        rows={filteredRows}
        loading={loading}
        priceDrafts={priceDrafts}
        savingKey={savingKey}
        onPriceDraftChange={updatePriceDraft}
        onSaveSellPrice={saveSellPrice}
        onSelectRow={openDetails}
      />

      {selectedRow && (
        <PurchaseDetailDrawer
          row={selectedRow}
          drawerAsin={drawerAsin}
          drawerSellPrice={drawerSellPrice}
          drawerEbayTitle={drawerEbayTitle}
          drawerUnitCost={drawerUnitCost}
          savingKey={savingKey}
          onAsinChange={setDrawerAsin}
          onSellPriceChange={setDrawerSellPrice}
          onEbayTitleChange={setDrawerEbayTitle}
          onUnitCostChange={setDrawerUnitCost}
          onAddSplitItem={addSplitItem}
          onSave={saveDrawerMatch}
          onClose={() => setSelectedRow(null)}
        />
      )}
    </main>
  );
}

function formatPriceDraft(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }

  return Number(value).toFixed(2);
}
