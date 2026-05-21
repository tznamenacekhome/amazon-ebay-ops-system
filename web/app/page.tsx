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
  sell_price: number | null;
  unit_cost: number | null;
  quantity: number | null;
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
  return orderId
    ? `https://www.ebay.com/mesh/ord/details?orderid=${orderId}`
    : null;
}

export default function Home() {
  const [rows, setRows] = useState<Purchase[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("notReceived");
  const [search, setSearch] = useState("");

  async function loadPurchases() {
    setLoading(true);

    const res = await fetch("/api/purchases");
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
        return (
          !!row.delivered_date &&
          row.current_status !== "received"
        );
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
    (sum, r) =>
      sum +
      Number(r.unit_cost ?? 0) *
        Number(r.quantity ?? 0),
    0
  );

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-7xl p-6">

        <header className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold">
              Purchases
            </h1>

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
            subtitle={`Buy cost: $${readyCost.toFixed(2)}`}
          />

          <Kpi
            title="Needs ASIN"
            value={rows
              .filter((r) => !r.asin)
              .length.toString()}
            subtitle="Missing Amazon match"
          />

        </section>

        <section className="mb-4 flex flex-wrap items-center gap-2">

          <div className="relative min-w-80 flex-1">

            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />

            <input
              value={search}
              onChange={(e) =>
                setSearch(e.target.value)
              }
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
            onClick={() =>
              setFilter("deliveredNotReceived")
            }
          />

          <FilterButton
            label="All"
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />

        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">

          {loading ? (
            <div className="p-8 text-slate-500">
              Loading purchases...
            </div>
          ) : (
            <table className="w-full text-sm">

              <thead className="bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500">

                <tr>
                  <th className="p-3">Date</th>
                  <th>eBay Item</th>
                  <th>Amazon Match</th>
                  <th>Sell Price</th>
                  <th>Cost</th>
                  <th>Qty</th>
                  <th>Delivery</th>
                  <th>ETA</th>
                  <th>eBay Order</th>
                  <th>Tracking</th>
                </tr>

              </thead>

              <tbody className="divide-y divide-slate-100">

                {filtered.map((row) => {

                  const amazon = amazonUrl(row.asin);

                  const ebay = ebayOrderUrl(
                    row.supplier_order_id
                  );

                  const amazonSearch =
                    `https://www.amazon.com/s?k=${encodeURIComponent(
                      `${row.title ?? ""} ${row.system ?? ""}`
                    )}`;

                  return (
                    <tr
                      key={row.item_id}
                      className="hover:bg-slate-50"
                    >

                      <td className="p-3 text-slate-500">
                        {row.order_date?.slice(0, 10) ?? "—"}
                      </td>

                      <td>
                        <div className="font-medium">
                          {row.title ?? "Untitled"}
                        </div>

                        <div className="text-xs text-slate-500">
                          {row.system ?? ""}
                        </div>
                      </td>

                      <td>

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

                      <td>
                        {row.sell_price
                          ? `$${Number(
                              row.sell_price
                            ).toFixed(2)}`
                          : "—"}
                      </td>

                      <td>
                        {row.unit_cost
                          ? `$${Number(
                              row.unit_cost
                            ).toFixed(2)}`
                          : "—"}
                      </td>

                      <td>

                        <span className="font-semibold">
                          {row.quantity ?? 1}
                        </span>

                    

                      </td>

                      <td>
                        {row.delivery_status ??
                          row.current_status ??
                          "—"}
                      </td>

                      <td>
                        {row.estimated_delivery_date?.slice(
                          0,
                          10
                        ) ?? "—"}
                      </td>

                      <td>

                        {ebay ? (
                          <a
                            href={ebay}
                            target="_blank"
                            className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                          >
                            {row.supplier_order_id}

                            <ExternalLink className="h-3 w-3" />
                          </a>
                        ) : (
                          "—"
                        )}

                      </td>

                      <td className="font-mono text-xs">
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

      <div className="text-sm text-slate-500">
        {title}
      </div>

      <div className="mt-1 text-2xl font-semibold">
        {value}
      </div>

      <div className="mt-1 text-xs text-slate-500">
        {subtitle}
      </div>

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