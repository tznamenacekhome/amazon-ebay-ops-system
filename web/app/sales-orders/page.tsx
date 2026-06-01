"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  RefreshCw,
  Search,
} from "lucide-react";
import { runOnDemandRefresh, type RefreshNotice } from "../syncRefresh";

type SalesOrderRow = {
  purchase_date: string | null;
  amazon_order_id: string;
  amazon_order_item_id: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity: number | null;
  sale_price: number | null;
  fulfillment_channel: string | null;
  order_status: string | null;
  is_replacement_order?: boolean | null;
  amazon_fees_excluding_fulfillment: number | null;
  fulfillment_cost: number | null;
  fulfillment_cost_source: string | null;
  cogs: number | null;
  cogs_source: string | null;
  net_profit: number | null;
  roi: number | null;
  data_status: string | null;
  display_data_status: string | null;
};

type SalesSummary = {
  revenue: number;
  amazonFees: number;
  fulfillment: number;
  cogs: number;
  netProfit: number;
  averageRoi: number | null;
  orderCount: number;
  unitCount: number;
  pendingFees: number;
  missingFees: number;
  missingCogs: number;
  missingFulfillment: number;
};

type SalesResponse = {
  rows: SalesOrderRow[];
  total: number;
  page: number;
  pageSize: number;
  summary: SalesSummary;
  lowRoiThreshold: number;
};

type SortDirection = "asc" | "desc";

const PAGE_SIZE = 100;
const dateRanges = ["7", "14", "30", "60", "90", "custom"];
const quickFilters = [
  ["recent", "Recent Orders"],
  ["profit_exceptions", "Profit Exceptions"],
  ["missing_data", "Missing Data"],
  ["mf_label_missing", "MF Label Missing"],
  ["losses", "Losses"],
];

export default function SalesOrdersPage() {
  const [data, setData] = useState<SalesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState("30");
  const [startDate, setStartDate] = useState(dateStringDaysAgo(30));
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10));
  const [fulfillment, setFulfillment] = useState("all");
  const [profitability, setProfitability] = useState("all");
  const [dataStatus, setDataStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [quickFilter, setQuickFilter] = useState("recent");
  const [sortColumn, setSortColumn] = useState("purchase_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [page, setPage] = useState(1);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState<RefreshNotice | null>(null);

  const totalPages = Math.max(Math.ceil((data?.total ?? 0) / PAGE_SIZE), 1);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      range,
      startDate,
      endDate,
      fulfillment,
      profitability,
      dataStatus,
      search,
      quickFilter,
      sortColumn,
      sortDirection,
      page: String(page),
      pageSize: String(PAGE_SIZE),
    });
    return params.toString();
  }, [
    dataStatus,
    endDate,
    fulfillment,
    page,
    profitability,
    quickFilter,
    range,
    search,
    sortColumn,
    sortDirection,
    startDate,
  ]);

  useEffect(() => {
    loadSalesOrders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryString]);

  function updateRange(nextRange: string) {
    setRange(nextRange);
    setPage(1);
    if (nextRange !== "custom") {
      setStartDate(dateStringDaysAgo(Number(nextRange)));
      setEndDate(new Date().toISOString().slice(0, 10));
    }
  }

  async function loadSalesOrders() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/sales-orders?${queryString}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Failed to load sales orders: ${response.status}`);
      }
      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sales orders.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshSalesOrders() {
    setRefreshing(true);
    setError(null);
    try {
      await runOnDemandRefresh("sales-orders", loadSalesOrders, setRefreshNotice);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  function updateSort(column: string) {
    setPage(1);
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortColumn(column);
    setSortDirection(column === "title" ? "asc" : "desc");
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sales Orders</h1>
          <p className="text-sm text-slate-600">
            Amazon seller orders, fees, fulfillment cost, COGS, and profitability
          </p>
        </div>

        <button
          onClick={refreshSalesOrders}
          disabled={refreshing}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50"
          type="button"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {refreshNotice && (
        <div className={`mb-4 rounded-lg border px-3 py-2 text-sm ${noticeClass(refreshNotice.tone)}`}>
          {refreshNotice.text}
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4" />
          {error}
        </div>
      )}

      <section className="mb-4 grid gap-3 xl:grid-cols-10">
        <Metric label="Revenue" value={formatMoney(data?.summary.revenue)} />
        <Metric label="Amazon Fees" value={formatMoney(data?.summary.amazonFees)} />
        <Metric label="Fulfillment" value={formatMoney(data?.summary.fulfillment)} />
        <Metric label="COGS" value={formatMoney(data?.summary.cogs)} />
        <Metric label="Net Profit" value={formatMoney(data?.summary.netProfit)} />
        <Metric label="Avg ROI" value={formatPercent(data?.summary.averageRoi)} />
        <Metric label="Pending" value={formatNumber(data?.summary.pendingFees)} />
        <Metric label="Missing Fees" value={formatNumber(data?.summary.missingFees)} />
        <Metric label="Missing COGS" value={formatNumber(data?.summary.missingCogs)} />
        <Metric
          label="Missing Fulfillment"
          value={formatNumber(data?.summary.missingFulfillment)}
        />
      </section>

      <section className="mb-4 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
        <div className="mb-3 flex flex-wrap gap-2">
          {quickFilters.map(([value, label]) => (
            <button
              key={value}
              onClick={() => {
                setQuickFilter(value);
                setPage(1);
              }}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                quickFilter === value
                  ? "bg-slate-900 text-white"
                  : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_150px_150px_190px_220px]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              className="h-10 w-full rounded-md border border-slate-300 pl-9 pr-3 text-sm"
              placeholder="Search order ID, ASIN, SKU, title"
            />
          </label>

          <select
            value={fulfillment}
            onChange={(event) => {
              setFulfillment(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
          >
            <option value="all">All fulfillment</option>
            <option value="fba">FBA</option>
            <option value="mf">MF</option>
          </select>

          <select
            value={profitability}
            onChange={(event) => {
              setProfitability(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
          >
            <option value="all">All profit</option>
            <option value="profitable">Profitable</option>
            <option value="low_roi">Low ROI</option>
            <option value="loss">Loss</option>
          </select>

          <select
            value={dataStatus}
            onChange={(event) => {
              setDataStatus(event.target.value);
              setPage(1);
            }}
            className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
          >
            <option value="all">All data status</option>
            <option value="complete">Complete</option>
            <option value="pending_fees">Pending</option>
            <option value="missing_fees">Missing Fees</option>
            <option value="missing_fulfillment_cost">Missing Fulfillment Cost</option>
            <option value="missing_cogs">Missing COGS</option>
          </select>

          <div className="flex gap-2">
            <select
              value={range}
              onChange={(event) => updateRange(event.target.value)}
              className="h-10 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm"
            >
              {dateRanges.map((value) => (
                <option key={value} value={value}>
                  {value === "custom" ? "Custom" : `${value} days`}
                </option>
              ))}
            </select>
          </div>
        </div>

        {range === "custom" && (
          <div className="mt-3 flex flex-wrap gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(event) => {
                setStartDate(event.target.value);
                setPage(1);
              }}
              className="h-10 rounded-md border border-slate-300 px-3 text-sm"
            />
            <input
              type="date"
              value={endDate}
              onChange={(event) => {
                setEndDate(event.target.value);
                setPage(1);
              }}
              className="h-10 rounded-md border border-slate-300 px-3 text-sm"
            />
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <SortableHeader label="Date" column="purchase_date" active={sortColumn} direction={sortDirection} onSort={updateSort} />
              <SortableHeader label="Amazon Order ID" column="amazon_order_id" active={sortColumn} direction={sortDirection} onSort={updateSort} />
              <SortableHeader label="ASIN" column="asin" active={sortColumn} direction={sortDirection} onSort={updateSort} />
              <SortableHeader label="Title" column="title" active={sortColumn} direction={sortDirection} onSort={updateSort} />
              <SortableHeader label="Qty" column="quantity" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="Sale Price" column="sale_price" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="Fulfillment Method" column="fulfillment_channel" active={sortColumn} direction={sortDirection} onSort={updateSort} />
              <SortableHeader label="Amazon Fees" column="amazon_fees_excluding_fulfillment" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="Fulfillment" column="fulfillment_cost" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="COGS" column="cogs" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="Net Profit" column="net_profit" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="ROI" column="roi" active={sortColumn} direction={sortDirection} onSort={updateSort} align="right" />
              <SortableHeader label="Data Status" column="data_status" active={sortColumn} direction={sortDirection} onSort={updateSort} />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={13} className="px-3 py-8 text-center text-slate-500">
                  Loading sales orders...
                </td>
              </tr>
            ) : !data?.rows.length ? (
              <tr>
                <td colSpan={13} className="px-3 py-8 text-center text-slate-500">
                  No sales orders match the current filters.
                </td>
              </tr>
            ) : (
              data.rows.map((row) => (
                <tr key={`${row.amazon_order_id}-${row.amazon_order_item_id}`} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap px-3 py-2">{formatDate(row.purchase_date)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-medium text-blue-700">{row.amazon_order_id}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.asin || "--"}</td>
                  <td className="min-w-72 px-3 py-2">
                    <div className="font-medium text-slate-900">{row.title || "--"}</div>
                    <div className="text-xs text-slate-500">{row.seller_sku || "--"}</div>
                  </td>
                  <td className="px-3 py-2 text-right">{formatNumber(row.quantity)}</td>
                  <td className="px-3 py-2 text-right">{formatMoney(row.sale_price)}</td>
                  <td className="whitespace-nowrap px-3 py-2">{formatFulfillment(row.fulfillment_channel)}</td>
                  <td className="px-3 py-2 text-right">{formatMoney(row.amazon_fees_excluding_fulfillment)}</td>
                  <td className="px-3 py-2 text-right">
                    <div>{formatMoney(row.fulfillment_cost)}</div>
                    <div className="text-xs text-slate-500">{formatSource(row.fulfillment_cost_source)}</div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div>{formatMoney(row.cogs)}</div>
                    <div className="text-xs text-slate-500">{formatSource(row.cogs_source)}</div>
                  </td>
                  <td className={`px-3 py-2 text-right font-semibold ${Number(row.net_profit ?? 0) < 0 ? "text-red-700" : "text-slate-900"}`}>
                    {formatMoney(row.net_profit)}
                  </td>
                  <td className="px-3 py-2 text-right">{formatPercent(row.roi)}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <StatusBadge status={row.display_data_status ?? row.data_status} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
        <div>
          {formatNumber(data?.total)} rows · {formatNumber(data?.summary.orderCount)} orders · Low ROI &lt;{" "}
          {formatPercent(data?.lowRoiThreshold)}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((current) => Math.max(current - 1, 1))}
            disabled={page <= 1}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium disabled:opacity-50"
            type="button"
          >
            Previous
          </button>
          <span>
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((current) => Math.min(current + 1, totalPages))}
            disabled={page >= totalPages}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 font-medium disabled:opacity-50"
            type="button"
          >
            Next
          </button>
        </div>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}

function SortableHeader({
  label,
  column,
  active,
  direction,
  onSort,
  align = "left",
}: {
  label: string;
  column: string;
  active: string;
  direction: SortDirection;
  onSort: (column: string) => void;
  align?: "left" | "right";
}) {
  const isActive = active === column;
  const Icon = direction === "asc" ? ArrowUp : ArrowDown;

  return (
    <th className={`px-3 py-2 ${align === "right" ? "text-right" : ""}`}>
      <button
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-1 ${align === "right" ? "justify-end" : ""}`}
        type="button"
      >
        {label}
        {isActive && <Icon className="h-3 w-3" />}
      </button>
    </th>
  );
}

function StatusBadge({ status }: { status?: string | null }) {
  const label = formatSource(status);
  const warning = status && status !== "complete";
  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${
        warning ? "bg-amber-50 text-amber-800" : "bg-green-50 text-green-700"
      }`}
    >
      {label || "--"}
    </span>
  );
}

function formatFulfillment(value?: string | null) {
  const normalized = (value || "").toLowerCase();
  if (["afn", "amazon", "amazonfulfilled"].includes(normalized)) return "FBA";
  if (["mfn", "merchant", "merchantfulfilled"].includes(normalized)) return "MF";
  return value || "--";
}

function formatSource(value?: string | null) {
  if (!value) return "";
  if (value === "pending_fees") return "Pending";
  if (value === "missing_fees") return "Missing Fees";
  if (value === "replacement") return "Replacement";
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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

function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function formatPercent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toLocaleString("en-US");
}

function dateStringDaysAgo(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function noticeClass(tone: RefreshNotice["tone"]) {
  if (tone === "success") return "border-green-200 bg-green-50 text-green-700";
  if (tone === "warning") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-blue-200 bg-blue-50 text-blue-700";
}
