import { ExternalLink, PanelRightOpen } from "lucide-react";

import { EditablePriceCell } from "./EditablePriceCell";
import type { PurchaseRow } from "./types";
import {
  amazonAsinUrl,
  amazonSearchUrl,
  ebayOrderUrl,
  formatDate,
  formatMoney,
  getEbayTitle,
  getPrimaryTitle,
  getShipmentStatus,
  rowKey,
} from "./utils";

type PurchasesTableProps = {
  rows: PurchaseRow[];
  loading: boolean;
  priceDrafts: Record<string, string>;
  savingKey: string | null;
  onPriceDraftChange: (key: string, value: string) => void;
  onSaveSellPrice: (row: PurchaseRow) => void;
  onSelectRow: (row: PurchaseRow) => void;
};

export function PurchasesTable({
  rows,
  loading,
  priceDrafts,
  savingKey,
  onPriceDraftChange,
  onSaveSellPrice,
  onSelectRow,
}: PurchasesTableProps) {
  return (
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
          ) : rows.length === 0 ? (
            <tr>
              <td className="px-3 py-6 text-center text-slate-500" colSpan={13}>
                No purchases found.
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const key = rowKey(row);
              const primaryTitle = getPrimaryTitle(row);
              const ebayTitle = getEbayTitle(row);
              const priceValue =
                priceDrafts[key] ??
                (row.sell_price ?? row.target_price ?? "").toString();

              return (
                <tr
                  key={key}
                  className="border-t border-slate-100 align-top hover:bg-slate-50"
                >
                  <td className="whitespace-nowrap px-3 py-2">
                    {formatDate(row.order_date)}
                  </td>

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
                      <span className="text-slate-400">--</span>
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
                  <td className="whitespace-nowrap px-3 py-2">
                    {formatMoney(row.unit_cost)}
                  </td>

                  <td className="px-3 py-2">
                    <EditablePriceCell
                      value={priceValue}
                      isSaving={savingKey === key}
                      onChange={(value) => onPriceDraftChange(key, value)}
                      onSave={() => onSaveSellPrice(row)}
                    />
                  </td>

                  <td className="px-3 py-2">{row.carrier || ""}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {formatDate(row.estimated_delivery_date)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {formatDate(row.delivered_date)}
                  </td>
                  <td className="px-3 py-2">{getShipmentStatus(row)}</td>

                  <td className="px-3 py-2 text-center">
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
