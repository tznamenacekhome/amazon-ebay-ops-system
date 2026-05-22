"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  PanelRightOpen,
  RefreshCw,
  Save,
  Search,
  X,
} from "lucide-react";

type PurchaseRow = {
  purchase_id?: string;
  item_id?: string;
  supplier_order_id?: string;
  order_date?: string;
  amazon_title?: string | null;
  title?: string | null;
  ebay_title?: string | null;
  asin?: string | null;
  system?: string | null;
  quantity?: number | null;
  unit_cost?: number | null;
  sell_price?: number | null;
  target_price?: number | null;
  tracking_number?: string | null;
  carrier?: string | null;
  shipment_status?: string | null;
  normalized_status?: string | null;
  estimated_delivery_date?: string | null;
  delivered_date?: string | null;
  current_status?: string | null;
};

function formatDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "2-digit",
  });
}

function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function rowKey(row: PurchaseRow) {
  return row.item_id || row.purchase_id || row.supplier_order_id || "";
}

function amazonAsinUrl(asin: string) {
  return `https://www.amazon.com/dp/${asin}`;
}

function amazonSearchUrl(title: string) {
  return `https://www.amazon.com/s?k=${encodeURIComponent(title)}`;
}

function ebayOrderUrl(orderId?: string | null) {
  if (!orderId) return "";
  return `https://order.ebay.com/ord/show?orderId=${orderId}#/`;
}

function getPrimaryTitle(row: PurchaseRow) {
  return row.amazon_title || row.ebay_title || row.title || "Untitled item";
}

function getEbayTitle(row: PurchaseRow) {
  return row.ebay_title || "";
}

export default function PurchasesPage() {
  const [rows, setRows] = useState<PurchaseRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [searchText, setSearchText] = useState("");
  const [asinFilter, setAsinFilter] = useState("all");
  const [deliveryFilter, setDeliveryFilter] = useState("all");

  const [selectedRow, setSelectedRow] = useState<PurchaseRow | null>(null);
  const [drawerAsin, setDrawerAsin] = useState("");
  const [priceDrafts, setPriceDrafts] = useState<Record<string, string>>({});

  async function loadPurchases() {
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
  }

  useEffect(() => {
    loadPurchases();
  }, []);

  useEffect(() => {
    if (selectedRow) {
      setDrawerAsin(selectedRow.asin || "");
    }
  }, [selectedRow]);

  const filteredRows = useMemo(() => {
    const search = searchText.trim().toLowerCase();

    return rows.filter((row) => {
      const primaryTitle = getPrimaryTitle(row);
      const ebayTitle = getEbayTitle(row);
      const status = row.normalized_status || row.shipment_status || row.current_status || "";

      const matchesSearch =
        !search ||
        [
          primaryTitle,
          ebayTitle,
          row.asin,
          row.system,
          row.supplier_order_id,
          row.tracking_number,
          row.carrier,
          status,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search);

      const matchesAsin =
        asinFilter === "all" ||
        (asinFilter === "matched" && !!row.asin) ||
        (asinFilter === "needs_review" && !row.asin);

      const isDelivered =
        !!row.delivered_date ||
        status.toLowerCase() === "delivered" ||
        row.normalized_status?.toLowerCase() === "delivered";

      const matchesDelivery =
        deliveryFilter === "all" ||
        (deliveryFilter === "delivered" && isDelivered) ||
        (deliveryFilter === "not_delivered" && !isDelivered);

      return matchesSearch && matchesAsin && matchesDelivery;
    });
  }, [rows, searchText, asinFilter, deliveryFilter]);

  const stats = useMemo(() => {
    return {
      total: rows.length,
      visible: filteredRows.length,
      needsReview: rows.filter((row) => !row.asin).length,
      delivered: rows.filter(
        (row) =>
          row.delivered_date ||
          row.normalized_status?.toLowerCase() === "delivered" ||
          row.shipment_status?.toLowerCase() === "delivered"
      ).length,
    };
  }, [rows, filteredRows]);

  async function patchPurchase(row: PurchaseRow, updates: Partial<PurchaseRow>) {
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

      setRows((currentRows) =>
        currentRows.map((currentRow) =>
          rowKey(currentRow) === key ? { ...currentRow, ...updates } : currentRow
        )
      );

      setSelectedRow((current) =>
        current && rowKey(current) === key ? { ...current, ...updates } : current
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSavingKey(null);
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

    await patchPurchase(row, {
      sell_price: parsed,
      target_price: parsed,
    });

    setPriceDrafts((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  async function saveDrawerAsin() {
    if (!selectedRow) return;

    await patchPurchase(selectedRow, {
      asin: drawerAsin.trim().toUpperCase() || null,
    });
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

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Metric label="Total Rows" value={stats.total} />
        <Metric label="Visible" value={stats.visible} />
        <Metric label="Needs ASIN Review" value={stats.needsReview} />
        <Metric label="Delivered" value={stats.delivered} />
      </div>

      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[320px] flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm"
              placeholder="Search title, ASIN, order, tracking, carrier..."
            />
          </div>

          <select
            value={asinFilter}
            onChange={(event) => setAsinFilter(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="all">All ASINs</option>
            <option value="matched">Matched ASINs</option>
            <option value="needs_review">Needs Review</option>
          </select>

          <select
            value={deliveryFilter}
            onChange={(event) => setDeliveryFilter(event.target.value)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="all">All Deliveries</option>
            <option value="delivered">Delivered</option>
            <option value="not_delivered">Not Delivered</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1640px] border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-[90px] px-3 py-2">Date</th>
              <th className="w-[145px] px-3 py-2">Order</th>
              <th className="w-[390px] px-3 py-2">Item</th>
              <th className="w-[130px] px-3 py-2">ASIN</th>
              <th className="w-[115px] px-3 py-2">System</th>
              <th className="w-[70px] px-3 py-2">Qty</th>
              <th className="w-[110px] px-3 py-2">Unit Cost</th>
              <th className="w-[135px] px-3 py-2">Sell Price</th>
              <th className="w-[115px] px-3 py-2">Carrier</th>
              <th className="w-[145px] px-3 py-2">ETA</th>
              <th className="w-[145px] px-3 py-2">Delivered</th>
              <th className="w-[145px] px-3 py-2">Status</th>
              <th className="w-[70px] px-3 py-2 text-center">Details</th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-6 text-center text-slate-500" colSpan={13}>
                  Loading purchases...
                </td>
              </tr>
            ) : filteredRows.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-center text-slate-500" colSpan={13}>
                  No purchases found.
                </td>
              </tr>
            ) : (
              filteredRows.map((row) => {
                const key = rowKey(row);
                const primaryTitle = getPrimaryTitle(row);
                const ebayTitle = getEbayTitle(row);
                const priceValue =
                  priceDrafts[key] ??
                  (row.sell_price ?? row.target_price ?? "").toString();

                return (
                  <tr key={key} className="border-t border-slate-100 align-top hover:bg-slate-50">
                    <td className="whitespace-nowrap px-3 py-2">{formatDate(row.order_date)}</td>

                    <td className="px-3 py-2">
                      {row.supplier_order_id ? (
                        <a
                          href={ebayOrderUrl(row.supplier_order_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-blue-700 hover:underline"
                        >
                          {row.supplier_order_id}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    <td className="px-3 py-2">
                      <div className="font-medium leading-snug text-slate-900">
                        {primaryTitle}
                      </div>

                      {ebayTitle && (
                        <div className="mt-1 line-clamp-2 text-xs leading-snug text-slate-500">
                          {ebayTitle}
                        </div>
                      )}
                    </td>

                    <td className="px-3 py-2">
                      {row.asin ? (
                        <a
                          href={amazonAsinUrl(row.asin)}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline"
                        >
                          {row.asin}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : (
                        <div>
                          <a
                            href={amazonSearchUrl(primaryTitle)}
                            target="_blank"
                            rel="noreferrer"
                            className="text-slate-500 hover:underline"
                          >
                            Search Amazon
                          </a>
                          <div className="mt-1 text-xs font-medium text-amber-700">
                            Needs Review
                          </div>
                        </div>
                      )}
                    </td>

                    <td className="px-3 py-2">{row.system || ""}</td>
                    <td className="px-3 py-2">{row.quantity ?? ""}</td>
                    <td className="whitespace-nowrap px-3 py-2">{formatMoney(row.unit_cost)}</td>

                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <input
                          value={priceValue}
                          onChange={(event) =>
                            setPriceDrafts((current) => ({
                              ...current,
                              [key]: event.target.value,
                            }))
                          }
                          onBlur={() => saveSellPrice(row)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") event.currentTarget.blur();
                          }}
                          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
                          placeholder="0.00"
                        />

                        {savingKey === key && (
                          <span className="text-xs text-slate-500">Saving</span>
                        )}
                      </div>
                    </td>

                    <td className="px-3 py-2">{row.carrier || ""}</td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {formatDate(row.estimated_delivery_date)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {formatDate(row.delivered_date)}
                    </td>
                    <td className="px-3 py-2">
                      {row.normalized_status || row.shipment_status || row.current_status || ""}
                    </td>

 <td className="px-3 py-2 text-center">
  <button
    onClick={() => setSelectedRow(row)}
    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-100"
    title="Open details"
  >
    <PanelRightOpen className="h-4 w-4" />
  </button>
</td>

                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {selectedRow && (
        <div className="fixed inset-0 z-40">
          <button
            className="absolute inset-0 bg-slate-900/30"
            onClick={() => setSelectedRow(null)}
            aria-label="Close details drawer overlay"
          />

          <aside className="absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto bg-white p-5 shadow-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Purchase Details</h2>
                <p className="text-sm text-slate-500">
                  ASIN review and item details
                </p>
              </div>

              <button
                onClick={() => setSelectedRow(null)}
                className="rounded-lg border border-slate-300 p-2 hover:bg-slate-50"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-5">
              <section>
                <div className="text-xs uppercase tracking-wide text-slate-500">
                  Amazon Title
                </div>

                <div className="mt-1 font-medium">
                  {getPrimaryTitle(selectedRow)}
                </div>

                {getEbayTitle(selectedRow) && (
                  <>
                    <div className="mt-4 text-xs uppercase tracking-wide text-slate-500">
                      eBay Title
                    </div>

                    <div className="mt-1 text-sm text-slate-700">
                      {getEbayTitle(selectedRow)}
                    </div>
                  </>
                )}
              </section>

              <section className="rounded-xl border border-slate-200 p-4">
                <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  ASIN
                </label>

                <div className="mt-2 flex gap-2">
                  <input
                    value={drawerAsin}
                    onChange={(event) => setDrawerAsin(event.target.value)}
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                    placeholder="Enter ASIN"
                  />

                  <button
                    onClick={saveDrawerAsin}
                    disabled={savingKey === rowKey(selectedRow)}
                    className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                  >
                    <Save className="h-4 w-4" />
                    Save
                  </button>
                </div>
              </section>

              <section className="grid grid-cols-2 gap-3 text-sm">
                <Detail
                  label="Order Date"
                  value={formatDate(selectedRow.order_date)}
                />

                <Detail
                  label="Order ID"
                  value={selectedRow.supplier_order_id || ""}
                />

                <Detail
                  label="System"
                  value={selectedRow.system || ""}
                />

                <Detail
                  label="Quantity"
                  value={String(selectedRow.quantity ?? "")}
                />

                <Detail
                  label="Unit Cost"
                  value={formatMoney(selectedRow.unit_cost)}
                />

                <Detail
                  label="Sell Price"
                  value={formatMoney(
                    selectedRow.sell_price ?? selectedRow.target_price
                  )}
                />

                <Detail
                  label="Carrier"
                  value={selectedRow.carrier || ""}
                />

                <Detail
                  label="ETA"
                  value={formatDate(selectedRow.estimated_delivery_date)}
                />

                <Detail
                  label="Delivered"
                  value={formatDate(selectedRow.delivered_date)}
                />

                <Detail
                  label="Status"
                  value={
                    selectedRow.normalized_status ||
                    selectedRow.shipment_status ||
                    selectedRow.current_status ||
                    ""
                  }
                />
              </section>

              <section>
                <div className="text-xs uppercase tracking-wide text-slate-500">
                  Tracking
                </div>

                <div className="mt-1 break-all rounded-lg bg-slate-50 p-3 text-sm">
                  {selectedRow.tracking_number || "No tracking number"}
                </div>
              </section>
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>

      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Detail({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>

      <div className="mt-1 font-medium text-slate-800">
        {value || "—"}
      </div>
    </div>
  );
}