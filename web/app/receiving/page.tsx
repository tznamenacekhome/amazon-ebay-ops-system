"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, PackageCheck, RefreshCw, Search, X } from "lucide-react";
import { DataFreshness } from "../DataFreshness";
import { mutationHeaders } from "../mutationHeaders";

import type { PurchaseRow } from "../purchases/types";
import {
  amazonAsinUrl,
  formatDate,
  formatMoney,
  getDisplayDeliveryDate,
  getOperationalStatus,
} from "../purchases/utils";
import {
  cleanTrackingScanValue,
  isLikelyTrackingScan,
  normalizeTrackingScan,
} from "./trackingScan";

type ReceivingDraft = {
  quantityReceived: string;
  returnPending: boolean;
  marketplace: "Amazon" | "eBay";
  asin: string;
  sellPrice: string;
  receivingOutcome: ReceivingOutcome;
  conditionIssue: string;
  imageClues: string[];
  receivingNotes: string;
};

type ReceivingOutcome =
  | "correct_item"
  | "wrong_item"
  | "wrong_condition"
  | "packaging_issue"
  | "incomplete_item"
  | "listed_successfully";

const RECEIVING_CONFIRMATION_TOKEN = "operator_receive_v2";

type SortColumn =
  | "date"
  | "order"
  | "item"
  | "system"
  | "quantity"
  | "cost"
  | "carrier"
  | "tracking"
  | "eta"
  | "status";

type SortDirection = "asc" | "desc";

export default function ReceivingPage() {
  const [rows, setRows] = useState<PurchaseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [selectedRow, setSelectedRow] = useState<PurchaseRow | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ReceivingDraft>>({});
  const [sortColumn, setSortColumn] = useState<SortColumn>("date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [refreshing, setRefreshing] = useState(false);
  const [freshnessKey, setFreshnessKey] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const lastAutoOpenedSearch = useRef("");
  const detailOpenedAt = useRef(0);

  const loadQueue = useCallback(async () => {
    try {
      const response = await fetch("/api/receiving", { cache: "no-store" });

      if (!response.ok) {
        throw new Error(`Failed to load receiving queue: ${response.status}`);
      }

      setRows(await response.json());
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load receiving queue."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  async function refreshReceiving() {
    setRefreshing(true);
    setError(null);
    try {
      await loadQueue();
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadQueue();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [loadQueue]);

  useEffect(() => {
    searchInputRef.current?.focus();
  }, []);

  const filteredRows = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    const trackingScan = normalizeTrackingScan(searchText);
    const trackingCandidates = new Set(
      trackingScan.candidates.map((candidate) => candidate.toUpperCase())
    );
    const normalizedSearch = trackingScan.normalizedInput.toUpperCase();
    const likelyTrackingScan = isLikelyTrackingScan(searchText);
    if (!needle) return rows;

    return rows.filter((row) => {
      const normalizedTracking = cleanTrackingScanValue(
        row.tracking_number
      ).toUpperCase();
      const normalizedOrder = cleanTrackingScanValue(
        row.supplier_order_id
      ).toUpperCase();

      if (
        trackingMatchesScan(
          normalizedTracking,
          normalizedSearch,
          trackingCandidates
        )
      ) {
        return true;
      }

      if (normalizedOrder && normalizedSearch && normalizedOrder === normalizedSearch) {
        return true;
      }

      if (likelyTrackingScan) {
        return false;
      }

      return [
        row.supplier_order_id,
        row.tracking_number,
        row.carrier,
        row.title,
        row.ebay_title,
        row.amazon_title,
        row.asin,
        row.system,
        row.current_status,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle));
    });
  }, [rows, searchText]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((left, right) => {
      const result = compareRows(left, right, sortColumn);
      return sortDirection === "asc" ? result : -result;
    });
  }, [filteredRows, sortColumn, sortDirection]);

  const openDetail = useCallback(
    (row: PurchaseRow) => {
      const groupRows = hasUsableTrackingNumber(row.tracking_number)
        ? rows.filter((candidate) =>
            hasSameTrackingNumber(candidate.tracking_number, row.tracking_number)
          )
        : rows.filter((candidate) => candidate.purchase_id === row.purchase_id);

      const nextDrafts: Record<string, ReceivingDraft> = {};

      for (const groupRow of groupRows) {
        nextDrafts[receivingRowKey(groupRow)] = {
          quantityReceived: defaultQuantityReceivedDraft(groupRow),
          returnPending: false,
          marketplace: "Amazon",
          asin: groupRow.asin || "",
          sellPrice: formatPriceDraft(groupRow.sell_price ?? groupRow.target_price),
          receivingOutcome: "correct_item",
          conditionIssue: "",
          imageClues: [],
          receivingNotes: "",
        };
      }

      setDrafts(nextDrafts);
      detailOpenedAt.current = Date.now();
      setSelectedRow(row);
    },
    [rows]
  );

  useEffect(() => {
    const normalizedSearch = searchText.trim();
    if (
      normalizedSearch &&
      filteredRows.length === 1 &&
      lastAutoOpenedSearch.current !== normalizedSearch
    ) {
      openDetail(filteredRows[0]);
      lastAutoOpenedSearch.current = normalizedSearch;
    }
  }, [filteredRows, openDetail, searchText]);

  const detailRows = useMemo(() => {
    if (!selectedRow) return [];

    if (hasUsableTrackingNumber(selectedRow.tracking_number)) {
      return rows.filter(
        (row) => hasSameTrackingNumber(row.tracking_number, selectedRow.tracking_number)
      );
    }

    return rows.filter((row) => row.purchase_id === selectedRow.purchase_id);
  }, [rows, selectedRow]);

  const receivingValidationMessage = useMemo(() => {
    if (!selectedRow) return "";

    for (const row of detailRows) {
      const draft = drafts[receivingRowKey(row)];
      const marketplace = draft?.marketplace ?? "Amazon";
      const returnPending = draft?.returnPending ?? false;
      const expectedQuantity = Number(row.quantity ?? 1);
      const quantityReceived = parseQuantityReceived(
        draft?.quantityReceived,
        expectedQuantity
      );

      if (!Number.isFinite(quantityReceived) || quantityReceived < 0) {
        return "Quantity received must be zero or greater.";
      }

      if (!Number.isInteger(quantityReceived)) {
        return "Quantity received must be a whole number.";
      }

      if (quantityReceived > expectedQuantity) {
        return "Quantity received cannot exceed expected quantity.";
      }

      if (returnPending || quantityReceived <= 0 || marketplace === "eBay") {
        continue;
      }

      if (!draft?.asin.trim()) {
        return "ASIN is required for Amazon received items.";
      }

      if (!draft?.sellPrice.trim()) {
        return "Sell price is required for Amazon received items.";
      }

      if (Number.isNaN(Number(draft.sellPrice))) {
        return "Sell price must be a valid number.";
      }
    }

    return "";
  }, [detailRows, drafts, selectedRow]);

  const closeDetail = useCallback(() => {
    setSelectedRow(null);
    detailOpenedAt.current = 0;
    setTimeout(() => searchInputRef.current?.focus(), 0);
  }, []);

  const saveReceiving = useCallback(async (confirmationSource: "button" | "shortcut") => {
    if (!selectedRow) return;
    if (saving) return;

    const items = detailRows.map((row) => {
      const draft = drafts[receivingRowKey(row)];
      const expectedQuantity = Number(row.quantity ?? 1);
      return {
        item_id: row.item_id,
        package_link_id: row.package_link_id ?? null,
        quantity_received: parseQuantityReceived(
          draft?.quantityReceived,
          expectedQuantity
        ),
        return_pending: draft?.returnPending ?? false,
        marketplace: draft?.marketplace ?? "Amazon",
        asin: draft?.asin.trim().toUpperCase() || null,
        sell_price:
          draft?.sellPrice.trim() === "" ? null : Number(draft?.sellPrice),
        receiving_outcome: draft?.receivingOutcome ?? "correct_item",
        condition_issue: draft?.conditionIssue || null,
        image_clues: draft?.imageClues ?? [],
        receiving_notes: draft?.receivingNotes || null,
      };
    });

    if (items.some((item) => !item.item_id)) {
      setError("Every receiving row must have an item id.");
      return;
    }

    if (
      items.some(
        (item) =>
          !Number.isFinite(item.quantity_received) || item.quantity_received < 0
      )
    ) {
      setError("Quantity received must be zero or greater.");
      return;
    }

    if (receivingValidationMessage) {
      setError(receivingValidationMessage);
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const response = await fetch("/api/receiving", {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          items,
          confirmation: RECEIVING_CONFIRMATION_TOKEN,
          confirmation_source: confirmationSource,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Receiving save failed: ${response.status}`);
      }

      const itemIds = new Set(items.map((item) => item.item_id));
      setRows((currentRows) =>
        currentRows.filter((row) => !row.item_id || !itemIds.has(row.item_id))
      );
      detailOpenedAt.current = 0;
      setSelectedRow(null);
      setSearchText("");
      lastAutoOpenedSearch.current = "";
      setTimeout(() => searchInputRef.current?.focus(), 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Receiving save failed.");
    } finally {
      setSaving(false);
    }
  }, [detailRows, drafts, receivingValidationMessage, saving, selectedRow]);

  useEffect(() => {
    if (!selectedRow) return;

    function handleDetailKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDetail();
        return;
      }

      const target = event.target as HTMLElement | null;
      const targetTag = target?.tagName.toLowerCase();
      const isFormTarget =
        targetTag === "input" ||
        targetTag === "textarea" ||
        targetTag === "select" ||
        targetTag === "button" ||
        Boolean(target?.isContentEditable);
      const justOpenedDetail = Date.now() - detailOpenedAt.current < 1200;

      if (
        event.key === "Enter" &&
        (event.ctrlKey || event.metaKey) &&
        !event.repeat &&
        !isFormTarget &&
        !justOpenedDetail &&
        !saving &&
        !receivingValidationMessage
      ) {
        event.preventDefault();
        void saveReceiving("shortcut");
      }
    }

    window.addEventListener("keydown", handleDetailKeyDown);

    return () => window.removeEventListener("keydown", handleDetailKeyDown);
  }, [
    closeDetail,
    receivingValidationMessage,
    saveReceiving,
    saving,
    selectedRow,
  ]);

  function updateDraft(row: PurchaseRow, patch: Partial<ReceivingDraft>) {
    const key = receivingRowKey(row);
    const defaultDraft: ReceivingDraft = {
      quantityReceived: defaultQuantityReceivedDraft(row),
      returnPending: false,
      marketplace: "Amazon",
      asin: row.asin || "",
      sellPrice: formatPriceDraft(row.sell_price ?? row.target_price),
      receivingOutcome: "correct_item",
      conditionIssue: "",
      imageClues: [],
      receivingNotes: "",
    };

    setDrafts((current) => ({
      ...current,
      [key]: {
        ...defaultDraft,
        ...current[key],
        ...patch,
      },
    }));
  }

  function changeSort(column: SortColumn) {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    setSortColumn(column);
    setSortDirection(column === "date" ? "desc" : "asc");
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Receiving</h1>
          <p className="text-sm text-slate-600">
            MBOP delivered item verification workspace
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="receiving" refreshKey={freshnessKey} />
          <button
            onClick={refreshReceiving}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
          <div className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm">
            Scan Ready
          </div>
        </div>
      </div>

      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <div className="font-medium text-slate-700">
            {formatNumber(rows.length)} items ready to receive
          </div>
          {searchText.trim() && (
            <div className="text-slate-500">
              {formatNumber(filteredRows.length)} matching current search
            </div>
          )}
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-3 h-5 w-5 text-slate-400" />
          <input
            ref={searchInputRef}
            value={searchText}
            onChange={(event) => {
              setSearchText(event.target.value);
              lastAutoOpenedSearch.current = "";
            }}
            className="w-full rounded-lg border border-slate-300 py-3 pl-10 pr-10 text-lg"
            placeholder="Scan label or search order, tracking, title..."
          />
          {searchText && (
            <button
              onClick={() => {
                setSearchText("");
                lastAutoOpenedSearch.current = "";
                searchInputRef.current?.focus();
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              aria-label="Clear search"
              type="button"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full table-fixed text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <SortableHeader
                className="w-[84px]"
                label="Date"
                column="date"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[130px]"
                label="Order"
                column="order"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                label="Item"
                column="item"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[110px]"
                label="System"
                column="system"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[64px]"
                label="Qty"
                column="quantity"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[100px]"
                label="Cost"
                column="cost"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[100px]"
                label="Carrier"
                column="carrier"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[130px]"
                label="Tracking"
                column="tracking"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[92px]"
                label="ETA"
                column="eta"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <SortableHeader
                className="w-[120px]"
                label="Status"
                column="status"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td className="px-2 py-6 text-center text-slate-500" colSpan={10}>
                  Loading receiving queue...
                </td>
              </tr>
            ) : sortedRows.length === 0 ? (
              <tr>
                <td className="px-2 py-6 text-center text-slate-500" colSpan={10}>
                  No receiving candidates found.
                </td>
              </tr>
            ) : (
              sortedRows.map((row) => {
                const status = getOperationalStatus(row);
                return (
                  <tr
                    key={receivingRowKey(row)}
                    onClick={() => openDetail(row)}
                    className="cursor-pointer border-t border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-2 py-2">
                      {formatDate(row.order_date)}
                    </td>
                    <td className="px-2 py-2 text-blue-700">
                      {row.supplier_order_id || "--"}
                    </td>
                    <td className="px-2 py-2">
                      <div className="font-medium leading-snug">
                        {row.amazon_title || row.ebay_title || row.title || "--"}
                      </div>
                      {row.amazon_title && (row.ebay_title || row.title) && (
                        <div className="mt-1 line-clamp-2 text-xs text-slate-500">
                          ebay: {row.ebay_title || row.title}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2">{row.system || ""}</td>
                    <td className="px-2 py-2">{row.quantity ?? ""}</td>
                    <td className="whitespace-nowrap px-2 py-2">
                      {formatMoney(row.unit_cost)}
                    </td>
                    <td className="px-2 py-2">{row.carrier || ""}</td>
                    <td className="break-all px-2 py-2 text-xs">
                      <div>{row.tracking_number || "--"}</div>
                      {Number(row.package_count ?? 0) > 1 && (
                        <div className="mt-1 text-[11px] font-medium text-slate-500">
                          {row.packages_delivered ?? 0}/{row.package_count} packages delivered
                        </div>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2">
                      {formatDate(getDisplayDeliveryDate(row))}
                    </td>
                    <td className="px-2 py-2">{status.label}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </section>

      {selectedRow && (
        <div className="fixed inset-0 z-40 bg-slate-900/30 p-6">
          <section className="mx-auto flex max-h-full max-w-6xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
                  <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                  <PackageCheck className="h-4 w-4" />
                  Receiving Detail
                </div>
                <h2 className="mt-2 text-2xl font-semibold">
                  {selectedRow.supplier_order_id || "No order id"}
                </h2>
                <div className="mt-2 grid gap-1 text-lg text-slate-700 md:grid-cols-3">
                  <div>Carrier: {selectedRow.carrier || "--"}</div>
                  <div className="break-all">
                    Tracking: {selectedRow.tracking_number || "--"}
                  </div>
                  <div>
                    Items: {detailRows.length}
                    {Number(selectedRow.package_count ?? 0) > 1
                      ? ` | Packages: ${selectedRow.packages_delivered ?? 0}/${selectedRow.package_count} delivered`
                      : ""}
                  </div>
                </div>
              </div>

              <button
                onClick={closeDetail}
                className="rounded-lg border border-slate-300 p-2 hover:bg-slate-50"
                type="button"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              <div className="grid gap-4">
                {detailRows.map((row) => {
                  const key = receivingRowKey(row);
                  const ebayListingUrl = row.ebay_listing_url || getEbayListingUrl(row);
                  const amazonDisplayTitle = getAmazonDisplayTitle(row);
                  const expectedQuantity = Number(row.quantity ?? 1);
                  const draft = drafts[key] ?? {
                    quantityReceived: String(row.quantity ?? 1),
                    returnPending: false,
                    marketplace: "Amazon" as const,
                    asin: row.asin || "",
                    sellPrice: formatPriceDraft(row.sell_price ?? row.target_price),
                    receivingOutcome: "correct_item" as const,
                    conditionIssue: "",
                    imageClues: [],
                    receivingNotes: "",
                  };
                  const quantityReceived = parseQuantityReceived(
                    draft.quantityReceived,
                    expectedQuantity
                  );
                  const problemQuantity = getProblemQuantity(
                    draft,
                    expectedQuantity,
                    quantityReceived
                  );

                  return (
                    <div
                      key={key}
                      className="grid gap-5 rounded-lg border border-slate-200 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(460px,520px)]"
                    >
                      <div className="min-w-0">
                        <div className="text-xs uppercase tracking-wide text-slate-500">
                          eBay Title
                        </div>
                        {ebayListingUrl ? (
                          <a
                            href={ebayListingUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block text-xl font-semibold text-blue-700 hover:underline"
                          >
                            {row.ebay_title || row.title || "--"}
                          </a>
                        ) : (
                          <div className="mt-1 text-xl font-semibold">
                            {row.ebay_title || row.title || "--"}
                          </div>
                        )}
                        <div className="mt-2 text-sm font-medium text-slate-600">
                          System: {row.system || "--"}
                        </div>
                        <div className="mt-4 text-xs uppercase tracking-wide text-slate-500">
                          Amazon Title
                        </div>
                        {row.asin ? (
                          <a
                            href={amazonAsinUrl(row.asin)}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 block text-lg font-medium text-blue-700 hover:underline"
                          >
                            {amazonDisplayTitle}
                          </a>
                        ) : (
                          <div className="mt-1 text-lg text-slate-700">
                            {amazonDisplayTitle || "--"}
                          </div>
                        )}
                        <div className="mt-3 text-sm text-slate-500">
                          Expected: {row.quantity ?? 1}
                        </div>
                        {row.package_link_id && (
                          <div className="mt-2 text-sm text-slate-500">
                            Package: {row.package_tracking_number || row.tracking_number || "--"} |{" "}
                            {formatStatus(row.package_status || row.delivery_status)}
                          </div>
                        )}
                      </div>

                      <div className="grid min-w-0 gap-4 sm:grid-cols-[120px_minmax(150px,1fr)_140px]">
                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                          Qty Received
                          <input
                            type="number"
                            value={draft.quantityReceived}
                            onChange={(event) =>
                              updateDraft(row, {
                                quantityReceived: event.target.value,
                              })
                            }
                            className="h-14 w-full rounded-lg border border-slate-300 px-3 text-2xl font-semibold normal-case tracking-normal text-slate-900"
                            inputMode="numeric"
                            min={0}
                            max={expectedQuantity}
                            step={1}
                          />
                          <span
                            className={
                              problemQuantity > 0
                                ? "text-xs font-semibold normal-case tracking-normal text-amber-700"
                                : "text-xs font-medium normal-case tracking-normal text-slate-500"
                            }
                          >
                            {problemQuantity > 0
                              ? `${problemQuantity} to Order Problems`
                              : "No problem qty"}
                          </span>
                        </label>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                          Marketplace
                          <select
                            value={draft.marketplace}
                            onChange={(event) =>
                              updateDraft(row, {
                                marketplace: event.target.value as "Amazon" | "eBay",
                              })
                            }
                            className="h-14 w-full rounded-lg border border-slate-300 px-3 text-lg font-medium normal-case tracking-normal text-slate-900"
                            disabled={draft.returnPending}
                          >
                            <option value="Amazon">Amazon</option>
                            <option value="eBay">eBay</option>
                          </select>
                        </label>

                        <label className="mt-7 flex h-14 items-center justify-center gap-3 rounded-lg border border-slate-300 px-3 text-lg font-medium">
                          <input
                            type="checkbox"
                            checked={draft.returnPending}
                            onChange={(event) =>
                              updateDraft(row, {
                                returnPending: event.target.checked,
                              })
                            }
                            className="h-5 w-5"
                          />
                          Return
                        </label>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500 sm:col-span-1">
                          Outcome
                          <select
                            value={draft.receivingOutcome}
                            onChange={(event) =>
                              updateDraft(row, {
                                receivingOutcome: event.target.value as ReceivingOutcome,
                              })
                            }
                            className="h-12 w-full rounded-lg border border-slate-300 px-3 text-base font-medium normal-case tracking-normal text-slate-900"
                          >
                            <option value="correct_item">Correct Item</option>
                            <option value="wrong_item">Wrong Item</option>
                            <option value="wrong_condition">Wrong Condition</option>
                            <option value="packaging_issue">Packaging Issue</option>
                            <option value="incomplete_item">Incomplete Item</option>
                            <option value="listed_successfully">Listed Successfully</option>
                          </select>
                        </label>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                          Issue
                          <select
                            value={draft.conditionIssue}
                            onChange={(event) =>
                              updateDraft(row, {
                                conditionIssue: event.target.value,
                              })
                            }
                            className="h-12 w-full rounded-lg border border-slate-300 px-3 text-base font-medium normal-case tracking-normal text-slate-900"
                          >
                            <option value="">None</option>
                            <option value="wrong_product">Wrong Product</option>
                            <option value="wrong_platform">Wrong Platform</option>
                            <option value="wrong_edition_version">Wrong Edition / Version</option>
                            <option value="non_north_american_version">Non-North-American Version</option>
                            <option value="incomplete_product">Incomplete Product</option>
                            <option value="missing_shrink_wrap">Missing Shrink Wrap</option>
                            <option value="suspected_reseal">Suspected Reseal</option>
                            <option value="packaging_damage">Packaging Damage</option>
                            <option value="other">Other</option>
                          </select>
                        </label>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500 sm:col-span-1">
                          ASIN
                          <input
                            value={draft.asin}
                            onChange={(event) =>
                              updateDraft(row, {
                                asin: event.target.value,
                              })
                            }
                            className="h-12 w-full rounded-lg border border-slate-300 px-3 text-base font-medium uppercase normal-case tracking-normal text-slate-900 disabled:bg-slate-50 disabled:text-slate-400"
                            disabled={draft.returnPending || draft.marketplace === "eBay"}
                            placeholder="ASIN"
                          />
                        </label>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                          Sell Price
                          <div className="relative">
                            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-base font-normal normal-case tracking-normal text-slate-500">
                              $
                            </span>
                            <input
                              value={draft.sellPrice}
                              onChange={(event) =>
                                updateDraft(row, {
                                  sellPrice: event.target.value,
                                })
                              }
                              className="h-12 w-full rounded-lg border border-slate-300 pl-7 pr-3 text-base font-medium normal-case tracking-normal text-slate-900 disabled:bg-slate-50 disabled:text-slate-400"
                              disabled={draft.returnPending || draft.marketplace === "eBay"}
                              inputMode="decimal"
                              placeholder="0.00"
                            />
                          </div>
                        </label>

                        <div className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500">
                          Buy Price
                          <div className="flex h-12 items-center rounded-lg border border-slate-200 bg-slate-50 px-3 text-base font-medium normal-case tracking-normal text-slate-900">
                            {formatMoney(row.unit_cost)}
                          </div>
                        </div>

                        <div className="sm:col-span-3">
                          <div className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">Image Clues</div>
                          <ImageClueButtons
                            selected={draft.imageClues}
                            onChange={(imageClues) => updateDraft(row, { imageClues })}
                          />
                        </div>

                        <label className="grid min-w-0 content-start gap-2 text-sm font-medium uppercase tracking-wide text-slate-500 sm:col-span-3">
                          Notes
                          <textarea
                            value={draft.receivingNotes}
                            onChange={(event) => updateDraft(row, { receivingNotes: event.target.value })}
                            className="min-h-20 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-900"
                          />
                        </label>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-200 p-5">
              {receivingValidationMessage && (
                <div className="mr-auto self-center text-sm font-medium text-amber-700">
                  {receivingValidationMessage}
                </div>
              )}

              <button
                onClick={closeDetail}
                className="rounded-lg border border-slate-300 px-4 py-3 text-sm font-medium hover:bg-slate-50"
                type="button"
              >
                Cancel
              </button>
              <button
                onClick={() => saveReceiving("button")}
                disabled={saving || !!receivingValidationMessage}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                type="button"
              >
                <Check className="h-4 w-4" />
                {saving ? "Saving" : "Received"}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

function SortableHeader({
  label,
  column,
  sortColumn,
  sortDirection,
  onSort,
  className = "",
}: {
  label: string;
  column: SortColumn;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  onSort: (column: SortColumn) => void;
  className?: string;
}) {
  const active = sortColumn === column;
  const Icon = sortDirection === "asc" ? ArrowUp : ArrowDown;

  return (
    <th className={`px-2 py-2 ${className}`}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 font-semibold hover:text-slate-900"
      >
        {label}
        {active && <Icon className="h-3 w-3" />}
      </button>
    </th>
  );
}

function compareRows(left: PurchaseRow, right: PurchaseRow, column: SortColumn) {
  if (column === "date") return compareDates(left.order_date, right.order_date);
  if (column === "order") {
    return compareStrings(left.supplier_order_id, right.supplier_order_id);
  }
  if (column === "item") return compareStrings(displayTitle(left), displayTitle(right));
  if (column === "system") return compareStrings(left.system, right.system);
  if (column === "quantity") return compareNumbers(left.quantity, right.quantity);
  if (column === "cost") return compareNumbers(left.unit_cost, right.unit_cost);
  if (column === "carrier") return compareStrings(left.carrier, right.carrier);
  if (column === "tracking") {
    return compareStrings(left.tracking_number, right.tracking_number);
  }
  if (column === "eta") {
    return compareDates(getDisplayDeliveryDate(left), getDisplayDeliveryDate(right));
  }
  if (column === "status") {
    return compareStrings(
      getOperationalStatus(left).label,
      getOperationalStatus(right).label
    );
  }

  return 0;
}

function displayTitle(row: PurchaseRow) {
  return row.amazon_title || row.ebay_title || row.title || "";
}

function compareStrings(left?: string | null, right?: string | null) {
  return (left || "").localeCompare(right || "", undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function compareNumbers(left?: number | null, right?: number | null) {
  return Number(left ?? Number.NEGATIVE_INFINITY) -
    Number(right ?? Number.NEGATIVE_INFINITY);
}

function compareDates(left?: string | null, right?: string | null) {
  const leftTime = left ? new Date(left).getTime() : Number.NEGATIVE_INFINITY;
  const rightTime = right ? new Date(right).getTime() : Number.NEGATIVE_INFINITY;

  return leftTime - rightTime;
}

function getEbayListingUrl(row: PurchaseRow) {
  if (row.supplier_listing_url) return row.supplier_listing_url;

  const itemId = extractEbayItemId(row.supplier_sku);

  return itemId ? `https://www.ebay.com/itm/${itemId}` : null;
}

function getAmazonDisplayTitle(row: PurchaseRow) {
  if (!row.amazon_title) return row.asin || "";

  const systemLabel = amazonSystemLabel(row.system);
  if (!systemLabel) return row.amazon_title;

  const normalizedTitle = normalizeTitle(row.amazon_title);
  const normalizedSystem = normalizeTitle(systemLabel);

  return normalizedTitle.includes(normalizedSystem)
    ? row.amazon_title
    : `${row.amazon_title} - ${systemLabel}`;
}

function amazonSystemLabel(system?: string | null) {
  const normalized = (system || "").trim().toLowerCase();
  const labels: Record<string, string> = {
    "ps 5": "PlayStation 5",
    ps5: "PlayStation 5",
    "ps 4": "PlayStation 4",
    ps4: "PlayStation 4",
    switch: "Nintendo Switch",
    wii: "Nintendo Wii",
    "xbox one": "Xbox One",
    "xbox series x": "Xbox Series X",
    pc: "PC",
  };

  return labels[normalized] || system || "";
}

function normalizeTitle(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function formatPriceDraft(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }

  return Number(value).toFixed(2);
}

function parseQuantityReceived(value: string | undefined, fallback: number) {
  if (value === undefined || value.trim() === "") return fallback;
  return Number(value);
}

function defaultQuantityReceivedDraft(row: PurchaseRow) {
  if (row.package_link_id && row.package_quantity_expected === null) {
    return "0";
  }

  return String(row.package_quantity_expected ?? row.quantity ?? 1);
}

function getProblemQuantity(
  draft: ReceivingDraft,
  expectedQuantity: number,
  quantityReceived: number
) {
  if (!Number.isFinite(quantityReceived)) return 0;
  if (
    draft.returnPending ||
    ["wrong_item", "wrong_condition", "packaging_issue", "incomplete_item"].includes(
      draft.receivingOutcome
    ) ||
    Boolean(draft.conditionIssue)
  ) {
    return expectedQuantity;
  }
  if (quantityReceived < expectedQuantity) {
    return Math.max(0, expectedQuantity - Math.max(0, quantityReceived));
  }
  return 0;
}

function formatNumber(value: number) {
  return value.toLocaleString("en-US");
}

function extractEbayItemId(value?: string | null) {
  if (!value) return null;

  const match = value.match(/^(\d{9,15})(?:-|$)/);

  return match ? match[1] : null;
}

function hasUsableTrackingNumber(value?: string | null) {
  if (!value) return false;

  const normalizedValue = value.trim().toLowerCase();

  return ![
    "no tracking",
    "none",
    "n/a",
    "na",
    "not available",
    "refunded",
    "cancelled",
    "canceled",
    "shipped untracked",
    "shipped without tracking",
  ].includes(normalizedValue);
}

function hasSameTrackingNumber(left?: string | null, right?: string | null) {
  const normalizedLeft = cleanTrackingScanValue(left).toUpperCase();
  const normalizedRight = cleanTrackingScanValue(right).toUpperCase();

  return !!normalizedLeft && normalizedLeft === normalizedRight;
}

function receivingRowKey(row: PurchaseRow) {
  return row.package_link_id || row.item_id || row.purchase_id || row.supplier_order_id || "";
}

function formatStatus(value?: string | null) {
  if (!value) return "--";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function trackingMatchesScan(
  normalizedTracking: string,
  normalizedSearch: string,
  trackingCandidates: Set<string>
) {
  if (!normalizedTracking) return false;
  if (trackingCandidates.has(normalizedTracking)) return true;

  if (normalizedSearch.length > normalizedTracking.length) {
    return (
      normalizedTracking.length >= 12 &&
      normalizedSearch.endsWith(normalizedTracking)
    );
  }

  return false;
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
    <div className="flex flex-wrap gap-2">
      {imageClueOptions.map(([value, label]) => {
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
            {label}
          </button>
        );
      })}
    </div>
  );
}
