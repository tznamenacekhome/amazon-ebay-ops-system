"use client";

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw, Search } from "lucide-react";

type Purchase = {
  item_id: string;
  purchase_id: string;
  order_date: string | null;
  supplier: string | null;
  supplier_order_id: string | null;
  title: string | null;
  system: string | null;
  asin: string | null;
  sell_price: number | string | null;
  unit_cost: number | string | null;
  quantity: number | string | null;
  current_status: string | null;
  tracking_number: string | null;
  supplier_listing_url: string | null;
  carrier: string | null;
  delivery_status: string | null;
  estimated_delivery_date: string | null;
  delivered_date: string | null;
};

function amazonUrl(asin: string | null) {
  return asin ? `https://www.amazon.com/dp/${asin}` : null;
}

function ebayOrderUrl(orderId: string | null) {
  if (!orderId) return null;

  return `https://order.ebay.com/ord/show?orderId=${orderId}#/`;
}

function formatCurrency(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";

  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) return "—";

  return `$${numericValue.toFixed(2)}`;
}

function formatShortDate(value: string | null) {
  if (!value) return "—";

  const datePart = value.slice(0, 10);
  const [year, month, day] = datePart.split("-");

  if (!year || !month || !day) return "—";

  return `${month}/${day}/${year.slice(2)}`;
}

export default function Home() {
  const [rows, setRows] = useState<Purchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("notReceived");
  const [search, setSearch] = useState("");

  async function loadPurchases() {
    setLoading(true);

    const res = await fetch("/api/purchases", {
      cache: "no-store",
    });

    const data = await res.json();

    setRows(Array.isArray(data) ? data : []);
    setLoading(false);
  }

  useEffect(() => {
    loadPurchases();
  }, []);

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      const text =
        `${row.title ?? ""} ${row.asin ?? ""} ${row.supplier_order_id ?? ""} ${row.tracking_number ?? ""}`.toLowerCase();

      const matchesSearch = text.includes(search.toLowerCase());

      if (!matchesSearch) return false;

      if (filter === "notReceived") {
        return !row.delivered_date;
      }

      if (filter === "needsAsin") {
        return !row.asin;
      }

      if (filter === "deliveredNotReceived") {
        return !!row.delivered_date && row.current_status !== "received";
      }

      return true;
    });
  }, [rows, filter, search]);

  const readyForFba = rows.filter(
    (r) => r.current_status === "ready_for_fba"
  );

  const readyUnits = readyForFba.reduce(
    (sum, r) => sum + Number(r.quantity ?? 0),
    0
  );

  const readyCost = readyForFba.reduce(
    (sum, r) => sum + Number(r.unit_cost ?? 0) * Number(r.quantity ?? 0),
    0
  );

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="w-full px-6 py-6 2xl:px-10">
        <header className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold">Purchases</h1>

            <p className="text-slate-500">
              Live purchase and inbound delivery workspace.
            </p>
          </div>

          <button
            onClick={loadPurchases}
            className="flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-white"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </header>

        <section className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
          <Kpi
            title="Rows Loaded"
            value={rows.length.toString()}
            subtitle="Latest records"
          />

          <Kpi
            title="Shown"
            value={filtered.length.toString()}
            subtitle="Current filtered view"
          />

          <Kpi
            title="Ready for FBA"
            value={`${readyUnits} units`}
            subtitle={`Buy cost: ${formatCurrency(readyCost)}`}
          />

          <Kpi
            title="Needs ASIN"
            value={rows.filter((r) => !r.asin).length.toString()}
            subtitle="Missing Amazon match"
          />
        </section>

        <section className="mb-4 flex flex-wrap items-center gap-2">
          <div className="relative min-w-96 flex-1">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />

            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search title, ASIN, order, tracking..."
              className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3"
            />
          </div>

          <FilterButton
            label="Not Yet Received"
            active={filter === "notReceived"}
            onClick={() => setFilter("notReceived")}
          />

          <FilterButton
            label="Needs ASIN"
            active={filter === "needsAsin"}
            onClick={() => setFilter("needsAsin")}
          />

          <FilterButton
            label="Delivered Not Received"
            active={filter === "deliveredNotReceived"}
            onClick={() => setFilter("deliveredNotReceived")}
          />

          <FilterButton
            label="All"
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />
        </section>

        <section className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <div className="p-8 text-slate-500">Loading purchases...</div>
          ) : (
            <table className="min-w-[1900px] table-fixed text-sm">
              <thead className="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-[90px] whitespace-nowrap px-4 py-3">
                    Date
                  </th>
                  <th className="w-[430px] whitespace-nowrap px-4 py-3">
                    eBay Item
                  </th>
                  <th className="w-[150px] whitespace-nowrap px-4 py-3">
                    Amazon Match
                  </th>
                  <th className="w-[110px] whitespace-nowrap px-4 py-3 text-right">
                    Sell Price
                  </th>
                  <th className="w-[100px] whitespace-nowrap px-4 py-3 text-right">
                    Cost
                  </th>
                  <th className="w-[70px] whitespace-nowrap px-4 py-3 text-center">
                    Qty
                  </th>
                  <th className="w-[160px] whitespace-nowrap px-4 py-3">
                    Delivery
                  </th>
                  <th className="w-[100px] whitespace-nowrap px-4 py-3">
                    ETA
                  </th>
                  <th className="w-[190px] whitespace-nowrap px-4 py-3">
                    eBay Order
                  </th>
                  <th className="w-[280px] whitespace-nowrap px-4 py-3">
                    Tracking
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
                {filtered.map((row) => {
                  const amazon = amazonUrl(row.asin);
                  const ebay = ebayOrderUrl(row.supplier_order_id);

                  const amazonSearch = `https://www.amazon.com/s?k=${encodeURIComponent(
                    `${row.title ?? ""} ${row.system ?? ""}`
                  )}`;

                  return (
                    <tr key={row.item_id} className="hover:bg-slate-50">
                      <td className="whitespace-nowrap px-4 py-3 text-slate-500">
                        {formatShortDate(row.order_date)}
                      </td>

                      <td className="px-4 py-3">
                        <div className="truncate font-medium">
                          {row.title ?? "Untitled"}
                        </div>

                        <div className="truncate text-xs text-slate-500">
                          {row.system ?? ""}
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        {row.asin && amazon ? (
                          <a
                            href={amazon}
                            target="_blank"
                            className="font-mono text-blue-600 hover:underline"
                          >
                            {row.asin}
                          </a>
                        ) : (
                          <a
                            href={amazonSearch}
                            target="_blank"
                            className="rounded-full bg-yellow-100 px-2 py-1 text-xs font-medium text-yellow-800 hover:underline"
                          >
                            Needs Review
                          </a>
                        )}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {formatCurrency(row.sell_price)}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-right">
                        {formatCurrency(row.unit_cost)}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 text-center">
                        <span className="font-semibold">
                          {row.quantity ?? 1}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        {row.delivery_status ?? row.current_status ?? "—"}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        {formatShortDate(row.estimated_delivery_date)}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3">
                        {ebay ? (
                          <a
                            href={ebay}
                            target="_blank"
                            className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                          >
                            {row.supplier_order_id}
                            <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>

                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
                        {row.tracking_number ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}

function Kpi({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-sm text-slate-500">{title}</div>

      <div className="mt-1 text-2xl font-semibold">{value}</div>

      <div className="mt-1 text-xs text-slate-500">{subtitle}</div>
    </div>
  );
}

function FilterButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl px-4 py-2 text-sm ${
        active
          ? "bg-slate-900 text-white"
          : "border border-slate-200 bg-white text-slate-700"
      }`}
    >
      {label}
    </button>
  );
}