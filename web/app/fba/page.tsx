"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  PackageOpen,
  RefreshCw,
  Save,
  Search,
  Truck,
} from "lucide-react";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";
import { DataFreshness } from "../DataFreshness";
import { mutationHeaders } from "../mutationHeaders";

type FbaDetail = {
  item_id: string;
  source_type?: "purchase_item" | "amazon_return_recovery";
  source_status?: string | null;
  supplier_order_id: string | null;
  order_date: string | null;
  amazon_title: string | null;
  asin: string;
  system: string | null;
  quantity: number;
  unit_cost: number | null;
  sell_price: number | null;
  supplier: string | null;
};

type FbaRow = {
  asin: string;
  msku: string | null;
  title: string | null;
  system: string | null;
  cost_per_unit: number | null;
  total_cost: number;
  sell_price: number | null;
  last_sold_price: number | null;
  last_sold_at: string | null;
  current_buy_box_price: number | null;
  low_fba_new_price_current: number | null;
  buy_box_price_avg90: number | null;
  profit_per_unit: number | null;
  roi: number | null;
  amazon_fee_estimate: number | null;
  amazon_fee_estimate_basis_price: number | null;
  referral_fee_estimate: number | null;
  non_referral_fee_estimate: number | null;
  referral_fee_rate: number | null;
  fee_estimate_status: string | null;
  fee_cache_updated_at: string | null;
  keepa_cache_updated_at: string | null;
  pricing_cache_updated_at: string | null;
  quantity: number;
  purchase_date: string | null;
  supplier: string;
  details: FbaDetail[];
};

type FbaData = {
  totals: {
    units: number;
    cost: number;
    asins: number;
    pricing_cache_oldest_at: string | null;
  };
  rows: FbaRow[];
};

type ShipmentDetail = {
  id: string;
  item_id: string | null;
  asin: string | null;
  amazon_title: string | null;
  system: string | null;
  seller_sku: string | null;
  fnsku: string | null;
  quantity_sent: number;
  expected_quantity: number | null;
  received_quantity: number | null;
  available_quantity: number | null;
  reserved_quantity: number | null;
  unfulfillable_quantity: number | null;
  missing_quantity: number | null;
  outbound_remaining_quantity: number | null;
  unit_cost: number | null;
  cost_sent: number | null;
  outbound_remaining_cost: number | null;
  amazon_received_cost: number | null;
  amazon_available_cost: number | null;
  source: "mbop" | "amazon_return_recovery" | "amazon_v2024_box";
};

type ShipmentRow = {
  id: string;
  shipment_code: string;
  workflow_status: string | null;
  amazon_status_raw: string | null;
  amazon_status_normalized: string | null;
  fulfillment_center_id: string | null;
  carrier_name: string | null;
  tracking_number: string | null;
  carrier_tracking_url: string | null;
  carrier_pickup_at: string | null;
  carrier_delivery_eta: string | null;
  carrier_delivered_at: string | null;
  amazon_checked_in_at: string | null;
  amazon_receiving_started_at: string | null;
  amazon_closed_at: string | null;
  all_units_available_at: string | null;
  units_sent: number;
  units_expected: number | null;
  units_received: number | null;
  units_available: number | null;
  units_reserved: number | null;
  units_unfulfillable: number | null;
  units_missing: number | null;
  fba_availability_pct: number | null;
  cost_sent: number | null;
  outbound_remaining_cost: number | null;
  amazon_received_cost: number | null;
  amazon_available_cost: number | null;
  attention_flags: string[];
  finalized_at: string | null;
  last_amazon_sync_at: string | null;
  detail_source: "mbop" | "amazon_v2024_box";
  fba_availability_tracked: boolean;
  details: ShipmentDetail[];
};

type ShipmentData = {
  totals: {
    shipments: number;
    units_sent: number;
    units_received: number;
    units_available: number;
    outbound_remaining_cost: number;
  };
  rows: ShipmentRow[];
};

type QuantityDraft = Record<string, string>;
type SellPriceDraft = Record<string, string>;

const LAST_OPENED_ASIN_KEY = "mbop:fba:last-opened-asin";

export default function FbaPage() {
  const [activeView, setActiveView] = useState<"prep" | "shipments">("prep");
  const [data, setData] = useState<FbaData | null>(null);
  const [shipmentData, setShipmentData] = useState<ShipmentData | null>(null);
  const [expandedAsin, setExpandedAsin] = useState<string | null>(null);
  const [expandedShipment, setExpandedShipment] = useState<string | null>(null);
  const [shipmentId, setShipmentId] = useState("");
  const [prepSearchText, setPrepSearchText] = useState("");
  const [quantityDrafts, setQuantityDrafts] = useState<QuantityDraft>({});
  const [sellPriceDrafts, setSellPriceDrafts] = useState<SellPriceDraft>({});
  const [savingPriceAsin, setSavingPriceAsin] = useState<string | null>(null);
  const [lastOpenedAsin, setLastOpenedAsin] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.sessionStorage.getItem(LAST_OPENED_ASIN_KEY);
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);
  const [freshnessKey, setFreshnessKey] = useState(0);

  useEffect(() => {
    if (activeView === "prep") {
      loadFba();
    } else {
      loadShipments();
    }
  }, [activeView]);

  const selectedTotals = useMemo(() => {
    let units = 0;
    let cost = 0;

    for (const row of data?.rows ?? []) {
      for (const detail of row.details) {
        const quantity = parseQuantity(quantityDrafts[detail.item_id]);
        units += quantity;
        cost += quantity * Number(detail.unit_cost ?? 0);
      }
    }

    return { units, cost };
  }, [data, quantityDrafts]);

  const prepValueTotals = useMemo(() => {
    let sellValue = 0;
    let profit = 0;
    let costWithProfit = 0;
    let missingSellPrice = false;
    let missingProfit = false;

    for (const row of data?.rows ?? []) {
      const quantity = Number(row.quantity ?? 0);
      if (quantity <= 0) continue;

      if (row.sell_price === null || row.sell_price === undefined) {
        missingSellPrice = true;
      } else {
        sellValue += row.sell_price * quantity;
      }

      if (
        row.profit_per_unit === null ||
        row.profit_per_unit === undefined ||
        row.cost_per_unit === null ||
        row.cost_per_unit === undefined
      ) {
        missingProfit = true;
      } else {
        profit += row.profit_per_unit * quantity;
        costWithProfit += row.cost_per_unit * quantity;
      }
    }

    return {
      sellValue: missingSellPrice ? null : sellValue,
      profit: missingProfit ? null : profit,
      roi: !missingProfit && costWithProfit > 0 ? profit / costWithProfit : null,
    };
  }, [data]);

  const filteredPrepRows = useMemo(() => {
    const query = prepSearchText.trim().toLowerCase();
    if (!query) return data?.rows ?? [];

    const terms = query.split(/\s+/).filter(Boolean);

    return (data?.rows ?? []).filter((row) => {
      const haystack = [
        row.asin,
        row.title,
        row.system,
        row.supplier,
        row.purchase_date,
        ...row.details.flatMap((detail) => [
          detail.supplier_order_id,
          detail.amazon_title,
          detail.asin,
          detail.system,
          detail.supplier,
          detail.order_date,
        ]),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return terms.every((term) => haystack.includes(term));
    });
  }, [data, prepSearchText]);

  const validationMessage = useMemo(() => {
    if (!shipmentId.trim()) return "Shipment ID is required before saving.";
    if (selectedTotals.units <= 0) return "At least one unit must be included.";

    for (const row of data?.rows ?? []) {
      for (const detail of row.details) {
        const quantity = parseQuantity(quantityDrafts[detail.item_id]);
        if (
          detail.source_type === "amazon_return_recovery" &&
          quantity > 0 &&
          detail.source_status !== "Ready for Send to Amazon"
        ) {
          return detail.source_status || "This Amazon Return Recovery row is not eligible for Send to Amazon.";
        }
        if (quantity < 0) return "Quantity to send cannot be negative.";
        if (quantity > detail.quantity) {
          return "Quantity to send cannot exceed received quantity.";
        }
      }
    }

    return "";
  }, [data, quantityDrafts, selectedTotals.units, shipmentId]);

  async function loadFba() {
    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const response = await fetch("/api/fba-shipments", { cache: "no-store" });

      if (!response.ok) {
        throw new Error(`Failed to load FBA workflow: ${response.status}`);
      }

      const payload = (await response.json()) as FbaData;
      setData(payload);
      setQuantityDrafts(quantityDraftsForData(payload));
      setSellPriceDrafts(sellPriceDraftsForData(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load FBA workflow.");
    } finally {
      setLoading(false);
    }
  }

  async function loadShipments() {
    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const response = await fetch("/api/fba-shipments?mode=shipments", {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Failed to load FBA shipments: ${response.status}`);
      }

      setShipmentData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load FBA shipments.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshFba() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("fba", loadShipments, setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  async function updatePricing() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("fba-pricing", loadFba, setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pricing update failed.");
    } finally {
      setRefreshing(false);
      setFreshnessKey((current) => current + 1);
    }
  }

  function exportCsv() {
    const rows = getSelectedExportRows(data?.rows ?? [], quantityDrafts);
    const csvRows = [
      [
        "ASIN",
        "MSKU",
        "Title",
        "System",
        "Cost per unit",
        "List Price",
        "Quantity",
        "Purchase date",
        "Supplier",
      ],
      ...rows.map((row) => [
        row.asin,
        row.msku || "",
        row.title || "Missing Amazon title",
        row.system || "",
        moneyForCsv(row.cost_per_unit),
        moneyForCsv(row.sell_price),
        String(row.quantity),
        formatDate(row.purchase_date),
        row.supplier || "",
      ]),
    ];

    const blob = new Blob([csvRows.map(toCsvRow).join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `mbop-fba-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function saveShipment() {
    if (validationMessage) {
      setError(validationMessage);
      return;
    }

    const items = Object.entries(quantityDrafts)
      .map(([itemId, quantity]) => ({
        item_id: itemId,
        quantity_to_send: parseQuantity(quantity),
      }))
      .filter((item) => item.quantity_to_send > 0);

    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const response = await fetch("/api/fba-shipments", {
        method: "POST",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          shipment_id: shipmentId.trim(),
          items,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error || `Save failed: ${response.status}`);
      }

      setNotice(`Shipment ${shipmentId.trim()} saved.`);
      setShipmentId("");
      setExpandedAsin(null);
      await loadFba();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save shipment.");
    } finally {
      setSaving(false);
    }
  }

  async function saveSellPrice(row: FbaRow) {
    const draft = sellPriceDrafts[row.asin]?.trim() ?? "";
    const nextPrice = Number(draft);

    if (draft === "" || !Number.isFinite(nextPrice) || nextPrice < 0) {
      setError("Sell price must be zero or greater.");
      return;
    }

    setSavingPriceAsin(row.asin);
    setError(null);

    try {
      const response = await fetch("/api/fba-shipments", {
        method: "PATCH",
        headers: mutationHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          items: row.details.map((detail) => ({
            item_id: detail.item_id,
            target_price: nextPrice,
          })),
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.error || `Sell price save failed: ${response.status}`);
      }

      setData((current) =>
        current
          ? {
              ...current,
              rows: current.rows.map((currentRow) =>
                currentRow.asin === row.asin
                  ? rowWithSellPrice(currentRow, nextPrice)
                  : currentRow
              ),
            }
          : current
      );
      setSellPriceDrafts((current) => ({
        ...current,
        [row.asin]: formatPriceDraft(nextPrice),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save sell price.");
    } finally {
      setSavingPriceAsin(null);
    }
  }

  function markAsinOpened(asin: string) {
    setLastOpenedAsin(asin);
    window.sessionStorage.setItem(LAST_OPENED_ASIN_KEY, asin);
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ready to ship to Amazon FBA</h1>
          <p className="text-sm text-slate-600">
            MBOP shipment preparation and Amazon inbound visibility
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <DataFreshness screen="fba" refreshKey={freshnessKey} />
          <button
            onClick={activeView === "prep" ? updatePricing : refreshFba}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
            type="button"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing
              ? activeView === "prep"
                ? "Updating"
                : "Refreshing"
              : activeView === "prep"
                ? "Update Pricing"
                : "Refresh"}
          </button>
          {activeView === "prep" ? (
            <div className="text-xs text-slate-500">
              Oldest pricing cache: {formatDateTime(data?.totals.pricing_cache_oldest_at)}
            </div>
          ) : null}
          <button
            onClick={exportCsv}
            disabled={activeView !== "prep" || !data?.rows.length}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50 disabled:opacity-50"
            type="button"
          >
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {notice && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          {notice}
        </div>
      )}

      {refreshNotice && (
        <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${noticeClass(refreshNotice.tone)}`}>
          {refreshNotice.text}
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setActiveView("prep")}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm ${
            activeView === "prep"
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
          }`}
          type="button"
        >
          <PackageOpen className="h-4 w-4" />
          Prep Queue
        </button>
        <button
          onClick={() => setActiveView("shipments")}
          className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium shadow-sm ${
            activeView === "shipments"
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
          }`}
          type="button"
        >
          <Truck className="h-4 w-4" />
          Shipments
        </button>
      </div>

      {activeView === "shipments" ? (
        <ShipmentView
          data={shipmentData}
          loading={loading}
          expandedShipment={expandedShipment}
          setExpandedShipment={setExpandedShipment}
        />
      ) : (
        <>

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Search Prep Queue
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={prepSearchText}
              onChange={(event) => setPrepSearchText(event.target.value)}
              className="h-11 w-full rounded-lg border border-slate-300 pl-9 pr-3 text-base font-medium"
              placeholder="title, ASIN, order number"
            />
          </div>
        </label>
      </section>

      <section className="mb-4 grid gap-3 md:grid-cols-6">
        <MetricCard label="ASINs" value={loading ? "--" : formatNumber(data?.totals.asins)} />
        <MetricCard label="Units" value={loading ? "--" : formatNumber(data?.totals.units)} />
        <MetricCard label="Total Cost" value={loading ? "--" : formatMoney(data?.totals.cost)} />
        <MetricCard
          label="Total Sell Value"
          value={loading ? "--" : formatMoney(prepValueTotals.sellValue)}
        />
        <MetricCard
          label="Total Profit"
          value={loading ? "--" : formatMoney(prepValueTotals.profit)}
        />
        <MetricCard
          label="Total ROI"
          value={loading ? "--" : formatPercentRatio(prepValueTotals.roi)}
        />
      </section>

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-[minmax(260px,360px)_1fr_auto] lg:items-end">
          <label className="grid gap-1 text-sm font-medium text-slate-700">
            Amazon Shipment ID
            <input
              value={shipmentId}
              onChange={(event) => setShipmentId(event.target.value)}
              className="h-11 rounded-lg border border-slate-300 px-3 text-base font-medium"
              placeholder="example: FBA19F8YW7CV"
            />
          </label>

          <div className="text-sm text-slate-600">
            Included now:{" "}
            <span className="font-semibold text-slate-900">
              {formatNumber(selectedTotals.units)} units
            </span>
            {" / "}
            <span className="font-semibold text-slate-900">
              {formatMoney(selectedTotals.cost)}
            </span>
          </div>

          <button
            onClick={saveShipment}
            disabled={saving || !!validationMessage}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            type="button"
            title={validationMessage || "Save shipment"}
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving" : "Save Shipment"}
          </button>
        </div>
      </section>

      <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1500px] w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-10 px-3 py-2" />
              <th className="px-3 py-2">ASIN</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">System</th>
              <th className="px-3 py-2 text-right">Buy Price</th>
              <th className="px-3 py-2 text-right">Sell Price</th>
              <th className="px-3 py-2 text-right">Last Sold</th>
              <th className="px-3 py-2 text-right">Current Buy Box</th>
              <th className="px-3 py-2 text-right">90D Buy Box</th>
              <th className="px-3 py-2 text-right">Profit / ROI</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Purchase Date</th>
              <th className="px-3 py-2">Supplier</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={13}>
                  Loading FBA candidates...
                </td>
              </tr>
            ) : !data?.rows.length ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={13}>
                  No Received Amazon inventory is ready for FBA.
                </td>
              </tr>
            ) : !filteredPrepRows.length ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={13}>
                  No FBA candidates match search.
                </td>
              </tr>
            ) : (
              filteredPrepRows.map((row) => {
                const isLastOpened = row.asin === lastOpenedAsin;
                const isSellPriceBelowReferences = sellPriceBelowReferences(
                  row,
                  sellPriceDrafts[row.asin]
                );
                return (
                <Fragment key={row.asin}>
                  <tr
                    className={`border-t align-top ${
                      isLastOpened
                        ? "border-amber-200 bg-amber-50/80 ring-1 ring-inset ring-amber-200"
                        : "border-slate-100"
                    }`}
                  >
                    <td className="px-3 py-2">
                      <button
                        onClick={() =>
                          setExpandedAsin((current) =>
                            current === row.asin ? null : row.asin
                          )
                        }
                        className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                        type="button"
                        aria-label={`Toggle ${row.asin} detail`}
                      >
                        {expandedAsin === row.asin ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-medium">
                      <a
                        href={amazonAsinUrl(row.asin)}
                        target="_blank"
                        rel="noreferrer"
                        onClick={() => markAsinOpened(row.asin)}
                        className="text-blue-700 hover:underline"
                      >
                        {row.asin}
                      </a>
                    </td>
                    <td className="px-3 py-2 font-medium">
                      {row.title ? (
                        row.title
                      ) : (
                        <span className="text-amber-700">
                          Missing Amazon title
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">{row.system || "--"}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {formatMoney(row.cost_per_unit)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <input
                        value={sellPriceDrafts[row.asin] ?? ""}
                        onChange={(event) =>
                          setSellPriceDrafts((current) => ({
                            ...current,
                            [row.asin]: event.target.value,
                          }))
                        }
                        onBlur={() => {
                          if (priceDraftChanged(sellPriceDrafts[row.asin], row.sell_price)) {
                            void saveSellPrice(row);
                          }
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.currentTarget.blur();
                          }
                        }}
                        className={`h-9 w-24 rounded-md border px-2 text-right font-medium ${
                          isSellPriceBelowReferences
                            ? "border-amber-400 bg-amber-50 text-amber-950"
                            : "border-slate-300"
                        }`}
                        inputMode="decimal"
                        disabled={savingPriceAsin === row.asin}
                      />
                      {isSellPriceBelowReferences ? (
                        <div
                          className="mt-1 text-xs font-medium text-amber-700"
                          title="Sell price is below Last Sold, current Buy Box, and 90-day Buy Box average."
                        >
                          Below refs
                        </div>
                      ) : null}
                      {savingPriceAsin === row.asin ? (
                        <div className="text-xs text-slate-500">saving</div>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <div>{formatMoney(row.last_sold_price)}</div>
                      <div className="text-xs text-slate-500">
                        {formatDate(row.last_sold_at)}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <div>{formatMoney(row.current_buy_box_price)}</div>
                      {row.current_buy_box_price === null && row.low_fba_new_price_current !== null ? (
                        <div className="text-xs text-slate-500">
                          FBA low {formatMoney(row.low_fba_new_price_current)}
                        </div>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {formatMoney(row.buy_box_price_avg90)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {formatProfitRoi(row, sellPriceDrafts[row.asin])}
                      <div className="text-xs text-slate-500">
                        Fees {formatMoney(row.amazon_fee_estimate)}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-semibold">
                      {formatNumber(row.quantity)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {formatDate(row.purchase_date)}
                    </td>
                    <td className="px-3 py-2">{row.supplier || "--"}</td>
                  </tr>

                  {expandedAsin === row.asin && (
                    <tr className="border-t border-slate-100 bg-slate-50">
                      <td colSpan={13} className="px-3 py-3">
                        <DetailTable
                          details={row.details}
                          quantityDrafts={quantityDrafts}
                          setQuantityDrafts={setQuantityDrafts}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
              })
            )}
          </tbody>
        </table>
      </section>
        </>
      )}
    </main>
  );
}

function ShipmentView({
  data,
  loading,
  expandedShipment,
  setExpandedShipment,
}: {
  data: ShipmentData | null;
  loading: boolean;
  expandedShipment: string | null;
  setExpandedShipment: React.Dispatch<React.SetStateAction<string | null>>;
}) {
  return (
    <>
      <section className="mb-4 grid gap-3 md:grid-cols-5">
        <MetricCard label="Shipments" value={loading ? "--" : formatNumber(data?.totals.shipments)} />
        <MetricCard label="Units Sent" value={loading ? "--" : formatNumber(data?.totals.units_sent)} />
        <MetricCard label="Units Received" value={loading ? "--" : formatNumber(data?.totals.units_received)} />
        <MetricCard label="FBA Available" value={loading ? "--" : formatNumber(data?.totals.units_available)} />
        <MetricCard
          label="Outbound Value"
          value={loading ? "--" : formatMoney(data?.totals.outbound_remaining_cost)}
        />
      </section>

      <section className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-[1500px] w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-10 px-3 py-2" />
              <th className="px-3 py-2">Shipment</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">FC</th>
              <th className="px-3 py-2">Delivered</th>
              <th className="px-3 py-2">Milestones</th>
              <th className="px-3 py-2 text-right">Units</th>
              <th className="px-3 py-2 text-right">FBA Avail</th>
              <th className="px-3 py-2 text-right">Cost</th>
              <th className="px-3 py-2">Flags</th>
              <th className="px-3 py-2">Last Sync</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                  Loading FBA shipments...
                </td>
              </tr>
            ) : !data?.rows.length ? (
              <tr>
                <td className="px-3 py-8 text-center text-slate-500" colSpan={11}>
                  No FBA shipments found.
                </td>
              </tr>
            ) : (
              data.rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className="border-t border-slate-100 align-top">
                    <td className="px-3 py-2">
                      <button
                        onClick={() =>
                          setExpandedShipment((current) =>
                            current === row.id ? null : row.id
                          )
                        }
                        className="rounded-md p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                        type="button"
                        aria-label={`Toggle ${row.shipment_code} detail`}
                      >
                        {expandedShipment === row.id ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-semibold text-blue-700">
                      {row.shipment_code}
                      <div className="text-xs font-normal text-slate-500">
                        {formatDate(row.finalized_at)}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">
                        MBOP: {statusLabel(row.workflow_status)}
                      </div>
                      <div className="text-xs text-slate-500">
                        FBA: {statusLabel(row.amazon_status_normalized || row.amazon_status_raw)}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">{row.fulfillment_center_id || "--"}</td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {row.carrier_delivered_at ? (
                        <>
                          <div>{formatDate(row.carrier_delivered_at)}</div>
                          <div className="text-xs text-slate-500">delivered</div>
                        </>
                      ) : row.carrier_delivery_eta ? (
                        <div>ETA: {formatDate(row.carrier_delivery_eta)}</div>
                      ) : (
                        <div className="text-slate-500">No ETA</div>
                      )}
                      {row.tracking_number ? (
                        <a
                          className="block text-xs text-blue-700 hover:underline"
                          href={trackingUrl(row)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {row.tracking_number}
                        </a>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-600">
                      <div>Carrier picked up: {formatMilestoneDate(row.carrier_pickup_at)}</div>
                      <div>
                        Carrier delivered: {formatMilestoneDate(row.carrier_delivered_at)}
                      </div>
                      <div>Amazon checked-in: {formatMilestoneDate(row.amazon_checked_in_at)}</div>
                      <div>Amazon received: {formatMilestoneDate(row.amazon_receiving_started_at)}</div>
                      <div>Amazon available: {formatMilestoneDate(row.all_units_available_at)}</div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <div className="font-semibold">{formatNumber(row.units_sent)}</div>
                      <div className="text-xs text-slate-500">
                        Rec {formatNumber(row.units_received)} / Miss {formatNumber(row.units_missing)}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      {row.fba_availability_tracked ? (
                        <>
                          <div className="font-semibold">{formatPercent(row.fba_availability_pct)}</div>
                          <div className="text-xs text-slate-500">
                            {formatNumber(row.units_available)} avail / {formatNumber(row.units_reserved)} res
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="font-semibold text-slate-500">--</div>
                          <div className="text-xs text-slate-500">not tracked</div>
                        </>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-right">
                      <div>{formatMoney(row.cost_sent)}</div>
                      <div className="text-xs text-slate-500">
                        Out {formatMoney(row.outbound_remaining_cost)}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {row.attention_flags.length ? (
                        <div className="flex flex-wrap gap-1">
                          {row.attention_flags.map((flag) => (
                            <span
                              key={flag}
                              className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800"
                            >
                              {flag.replace(/_/g, " ")}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-500">--</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {formatDate(row.last_amazon_sync_at)}
                    </td>
                  </tr>
                  {expandedShipment === row.id && (
                    <tr className="border-t border-slate-100 bg-slate-50">
                      <td colSpan={11} className="px-3 py-3">
                        <ShipmentDetailTable details={row.details} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}

function ShipmentDetailTable({ details }: { details: ShipmentDetail[] }) {
  const detailSource = details[0]?.source;
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 text-sm font-medium text-slate-700">
        <div className="flex items-center gap-2">
          <Truck className="h-4 w-4" />
          Amazon Shipment Detail
        </div>
        {detailSource === "amazon_v2024_box" ? (
          <span className="text-xs font-normal text-slate-500">from Amazon box contents</span>
        ) : detailSource === "amazon_return_recovery" ? (
          <span className="text-xs font-normal text-slate-500">from Amazon Return Recovery</span>
        ) : null}
      </div>
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">ASIN / SKU</th>
            <th className="px-3 py-2">Title</th>
            <th className="px-3 py-2">System</th>
            <th className="px-3 py-2 text-right">Sent</th>
            <th className="px-3 py-2 text-right">Expected</th>
            <th className="px-3 py-2 text-right">Received</th>
            <th className="px-3 py-2 text-right">Available</th>
            <th className="px-3 py-2 text-right">Reserved</th>
            <th className="px-3 py-2 text-right">Missing</th>
            <th className="px-3 py-2 text-right">Outbound Cost</th>
          </tr>
        </thead>
        <tbody>
          {details.length ? (
            details.map((detail) => (
              <tr key={detail.id} className="border-t border-slate-100 align-top">
                <td className="whitespace-nowrap px-3 py-2">
                  <div className="font-medium text-blue-700">{detail.asin || "--"}</div>
                  <div className="text-xs text-slate-500">{detail.seller_sku || detail.fnsku || "--"}</div>
                </td>
                <td className="px-3 py-2">{detail.amazon_title || "--"}</td>
                <td className="px-3 py-2">{detail.system || "--"}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.quantity_sent)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.expected_quantity)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.received_quantity)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.available_quantity)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.reserved_quantity)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(detail.missing_quantity)}</td>
                <td className="px-3 py-2 text-right">{formatMoney(detail.outbound_remaining_cost)}</td>
              </tr>
            ))
          ) : (
            <tr className="border-t border-slate-100">
              <td className="px-3 py-6 text-center text-slate-500" colSpan={10}>
                No item detail captured for this shipment.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function getSelectedExportRows(rows: FbaRow[], quantityDrafts: QuantityDraft) {
  return rows.flatMap((row) => {
    let quantity = 0;
    let totalCost = 0;

    for (const detail of row.details) {
      const detailQuantity = parseQuantity(quantityDrafts[detail.item_id]);
      quantity += detailQuantity;
      totalCost += detailQuantity * Number(detail.unit_cost ?? 0);
    }

    if (quantity <= 0) return [];

    return [
      {
        ...row,
        quantity,
        total_cost: totalCost,
        cost_per_unit: quantity > 0 ? totalCost / quantity : null,
      },
    ];
  });
}

function quantityDraftsForData(data: FbaData) {
  const drafts: QuantityDraft = {};
  for (const row of data.rows) {
    for (const detail of row.details) {
      drafts[detail.item_id] =
        detail.source_type === "amazon_return_recovery" &&
        detail.source_status !== "Ready for Send to Amazon"
          ? "0"
          : String(detail.quantity);
    }
  }
  return drafts;
}

function sellPriceDraftsForData(data: FbaData) {
  const drafts: SellPriceDraft = {};
  for (const row of data.rows) {
    drafts[row.asin] = formatPriceDraft(row.sell_price);
  }
  return drafts;
}

function rowWithSellPrice(row: FbaRow, sellPrice: number): FbaRow {
  const amazonFeeEstimate = adjustedAmazonFeeEstimate(row, sellPrice);
  const profitPerUnit =
    row.cost_per_unit !== null && amazonFeeEstimate !== null
      ? sellPrice - row.cost_per_unit - amazonFeeEstimate
      : null;
  const roi =
    profitPerUnit !== null && row.cost_per_unit !== null && row.cost_per_unit > 0
      ? profitPerUnit / row.cost_per_unit
      : null;

  return {
    ...row,
    sell_price: sellPrice,
    amazon_fee_estimate: amazonFeeEstimate,
    profit_per_unit: profitPerUnit,
    roi,
    details: row.details.map((detail) => ({
      ...detail,
      sell_price: sellPrice,
    })),
  };
}

function priceDraftChanged(value: string | undefined, currentPrice: number | null) {
  const parsed = Number(String(value ?? "").trim());
  if (!Number.isFinite(parsed)) return true;
  return Math.round(parsed * 100) !== Math.round(Number(currentPrice ?? 0) * 100);
}

function formatPriceDraft(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }
  return Number(value).toFixed(2);
}

function formatProfitRoi(row: FbaRow, draft?: string) {
  const sellPrice = Number(String(draft ?? "").trim());
  const effectiveSellPrice = Number.isFinite(sellPrice) ? sellPrice : row.sell_price;
  const draftMatchesSaved = !priceDraftChanged(draft, row.sell_price);
  const amazonFeeEstimate =
    effectiveSellPrice === null || effectiveSellPrice === undefined
      ? null
      : adjustedAmazonFeeEstimate(row, effectiveSellPrice);
  if (
    effectiveSellPrice === null ||
    effectiveSellPrice === undefined ||
    amazonFeeEstimate === null ||
    !draftMatchesSaved ||
    row.cost_per_unit === null ||
    row.cost_per_unit === undefined
  ) {
    return <span className="text-slate-500">Update pricing</span>;
  }
  const profit = effectiveSellPrice - row.cost_per_unit - amazonFeeEstimate;
  const roi = row.cost_per_unit > 0 ? profit / row.cost_per_unit : null;
  return (
    <>
      <div className={profit < 0 ? "font-semibold text-red-700" : "font-semibold text-green-700"}>
        {formatMoney(profit)}
      </div>
      <div className="text-xs text-slate-500">{formatPercentRatio(roi)}</div>
    </>
  );
}

function sellPriceBelowReferences(row: FbaRow, draft?: string) {
  const sellPrice = Number(String(draft ?? "").trim());
  const effectiveSellPrice = Number.isFinite(sellPrice) ? sellPrice : row.sell_price;
  const references = [
    row.last_sold_price,
    row.current_buy_box_price,
    row.buy_box_price_avg90,
  ];

  if (
    effectiveSellPrice === null ||
    effectiveSellPrice === undefined ||
    references.some((value) => value === null || value === undefined)
  ) {
    return false;
  }

  return references.every((value) => effectiveSellPrice < Number(value));
}

function adjustedAmazonFeeEstimate(row: FbaRow, sellPrice: number) {
  if (
    row.non_referral_fee_estimate === null ||
    row.non_referral_fee_estimate === undefined ||
    row.referral_fee_rate === null ||
    row.referral_fee_rate === undefined
  ) {
    return row.amazon_fee_estimate;
  }

  return roundMoney(row.non_referral_fee_estimate + sellPrice * row.referral_fee_rate);
}

function DetailTable({
  details,
  quantityDrafts,
  setQuantityDrafts,
}: {
  details: FbaDetail[];
  quantityDrafts: QuantityDraft;
  setQuantityDrafts: React.Dispatch<React.SetStateAction<QuantityDraft>>;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 text-sm font-medium text-slate-700">
        <PackageOpen className="h-4 w-4" />
        Shipment Detail
      </div>
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Supplier Order</th>
            <th className="px-3 py-2">Order Date</th>
            <th className="px-3 py-2">Amazon Title</th>
            <th className="px-3 py-2">ASIN</th>
            <th className="px-3 py-2 text-right">Received Qty</th>
            <th className="px-3 py-2 text-right">Qty To Send</th>
            <th className="px-3 py-2 text-right">Cost / Unit</th>
            <th className="px-3 py-2">Status After Save</th>
          </tr>
        </thead>
        <tbody>
          {details.map((detail) => {
            const quantityToSend = parseQuantity(quantityDrafts[detail.item_id]);
            const remaining = Math.max(detail.quantity - quantityToSend, 0);

            return (
              <tr key={detail.item_id} className="border-t border-slate-100">
                <td className="whitespace-nowrap px-3 py-2 font-medium">
                  <div>{detail.supplier_order_id || "--"}</div>
                  {detail.source_type === "amazon_return_recovery" ? (
                    <div className="mt-1 inline-flex rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                      Amazon return
                    </div>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-3 py-2">
                  {formatDate(detail.order_date)}
                </td>
                <td className="px-3 py-2">{detail.amazon_title || "--"}</td>
                <td className="whitespace-nowrap px-3 py-2">
                  <a
                    href={amazonAsinUrl(detail.asin)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 hover:underline"
                  >
                    {detail.asin}
                  </a>
                </td>
                <td className="px-3 py-2 text-right">{detail.quantity}</td>
                <td className="px-3 py-2 text-right">
                  <input
                    value={quantityDrafts[detail.item_id] ?? String(detail.quantity)}
                    onChange={(event) =>
                      setQuantityDrafts((current) => ({
                        ...current,
                        [detail.item_id]: event.target.value,
                      }))
                    }
                    className="h-9 w-20 rounded-md border border-slate-300 px-2 text-right font-medium"
                    inputMode="numeric"
                  />
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right">
                  {formatMoney(detail.unit_cost)}
                </td>
                <td className="px-3 py-2">
                  {detail.source_type === "amazon_return_recovery" ? (
                    <span
                      className={
                        detail.source_status === "Ready for Send to Amazon"
                          ? "text-green-700"
                          : "text-amber-700"
                      }
                    >
                      {detail.source_status === "Ready for Send to Amazon"
                        ? "Will route Return Recovery case to FBA shipment"
                        : detail.source_status || "Not eligible for Send to Amazon"}
                    </span>
                  ) : quantityToSend === 0 ? (
                    <span className="text-slate-600">Remain Received</span>
                  ) : remaining > 0 ? (
                    <span className="text-amber-700">
                      {quantityToSend} Listed / {remaining} Received
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-green-700">
                      <Check className="h-4 w-4" />
                      Listed
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-sm font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value || "--"}</div>
    </div>
  );
}

function parseQuantity(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return 0;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(Math.floor(parsed), 0);
}

function toCsvRow(values: string[]) {
  return values
    .map((value) => `"${String(value).replace(/"/g, '""')}"`)
    .join(",");
}

function moneyForCsv(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "";
  }

  return Number(value).toFixed(2);
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toLocaleString("en-US");
}

function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }

  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  return `${Number(value).toLocaleString("en-US", {
    maximumFractionDigits: 1,
  })}%`;
}

function formatPercentRatio(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "--";
  }
  return `${(Number(value) * 100).toLocaleString("en-US", {
    maximumFractionDigits: 1,
  })}%`;
}

function statusLabel(value?: string | null) {
  if (!value) return "--";
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatMilestoneDate(value?: string | null) {
  return value ? formatDate(value) : "not captured";
}

function trackingUrl(row: ShipmentRow) {
  if (row.carrier_tracking_url) return row.carrier_tracking_url;
  return `https://www.ups.com/track?tracknum=${encodeURIComponent(row.tracking_number || "")}`;
}

function amazonAsinUrl(asin: string) {
  return `https://www.amazon.com/dp/${encodeURIComponent(asin)}`;
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}

function formatDate(value?: string | null) {
  if (!value) return "--";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "2-digit",
  });
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "2-digit",
    hour: "numeric",
    minute: "2-digit",
  });
}
