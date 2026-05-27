import { PanelRightOpen } from "lucide-react";

import type { PurchaseRow } from "./types";
import {
  ebayOrderUrl,
  formatDate,
  getDisplayTitleParts,
  getOperationalStatus,
  rowKey,
} from "./utils";

type PurchaseProblemTableProps = {
  rows: PurchaseRow[];
  loading: boolean;
  onSelectRow: (row: PurchaseRow) => void;
};

export function PurchaseProblemTable({
  rows,
  loading,
  onSelectRow,
}: PurchaseProblemTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-[1120px] border-collapse text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="w-[170px] px-2 py-2">Issue</th>
            <th className="w-[70px] px-2 py-2 text-right">Age</th>
            <th className="w-[120px] px-2 py-2">Order</th>
            <th className="w-[430px] px-2 py-2">Item</th>
            <th className="w-[90px] px-2 py-2">Order Date</th>
            <th className="w-[90px] px-2 py-2">ETA</th>
            <th className="w-[150px] px-2 py-2">Tracking</th>
            <th className="w-[120px] px-2 py-2">Status</th>
            <th className="w-[52px] px-2 py-2 text-center">Details</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td className="px-2 py-6 text-center text-slate-500" colSpan={9}>
                Loading order problems...
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td className="px-2 py-6 text-center text-slate-500" colSpan={9}>
                No order problems found.
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const problem = getOrderProblem(row);
              const { primaryTitle, ebayTitle, showEbaySubtitle } =
                getDisplayTitleParts(row);

              return (
                <tr
                  key={rowKey(row)}
                  className="border-t border-slate-100 align-top hover:bg-slate-50"
                >
                  <td className="px-2 py-2">
                    <div className="font-medium text-slate-900">{problem.issue}</div>
                    <div className="text-xs text-slate-500">{problem.guidance}</div>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-right">
                    {formatAge(problem.ageDays)}
                  </td>
                  <td className="px-2 py-2">
                    {row.supplier_order_id ? (
                      <a
                        href={ebayOrderUrl(row.supplier_order_id)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-700 hover:underline"
                      >
                        {row.supplier_order_id}
                      </a>
                    ) : (
                      <span className="text-slate-400">--</span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="font-medium leading-snug text-slate-900">
                      {primaryTitle}
                    </div>
                    {showEbaySubtitle && (
                      <div className="mt-1 line-clamp-2 text-xs leading-snug text-slate-500">
                        ebay: {ebayTitle}
                      </div>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2">
                    {formatDate(row.order_date)}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 font-medium text-yellow-700">
                    {formatDate(row.estimated_delivery_date)}
                  </td>
                  <td className="px-2 py-2">
                    <div>{row.tracking_number || "--"}</div>
                    <div className="text-xs text-slate-500">{row.carrier || ""}</div>
                  </td>
                  <td className="px-2 py-2">{getOperationalStatus(row).label}</td>
                  <td className="px-2 py-2 text-center">
                    <button
                      onClick={() => onSelectRow(row)}
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
  );
}

function getOrderProblem(row: PurchaseRow) {
  const status = getOperationalStatus(row).value;
  const orderAge = ageDays(row.order_date);
  const etaAge = ageDays(row.estimated_delivery_date);

  if (status === "exception") {
    return {
      issue: "Carrier exception",
      guidance: "Review carrier tracking and contact seller or carrier if needed.",
      ageDays: orderAge,
    };
  }

  if (status === "return_pending") {
    return {
      issue: "Return pending",
      guidance: "Open or follow up on the return/refund workflow.",
      ageDays: orderAge,
    };
  }

  if (
    ["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"].includes(status) &&
    orderAge !== null &&
    orderAge >= 7
  ) {
    return {
      issue: "Tracking stale/no tracking",
      guidance: "Check eBay order details and ask seller for a usable shipment update.",
      ageDays: orderAge,
    };
  }

  return {
    issue: "Past ETA",
    guidance: "Delivery estimate has passed; check tracking and seller communication.",
    ageDays: etaAge,
  };
}

function ageDays(value?: string | null) {
  const date = parseDate(value);
  if (!date) return null;
  const now = new Date();
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  return Math.floor((today.getTime() - date.getTime()) / 86_400_000);
}

function parseDate(value?: string | null) {
  if (!value) return null;
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

function formatAge(value: number | null) {
  return value === null ? "--" : `${value.toLocaleString("en-US")}d`;
}
