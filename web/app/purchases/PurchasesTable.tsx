import { PanelRightOpen } from "lucide-react";

import { EditablePriceCell } from "./EditablePriceCell";
import type { PurchaseRow } from "./types";
import {
  amazonAsinUrl,
  amazonSearchUrl,
  ebayOrderUrl,
  formatDate,
  formatMoney,
  getAmazonSearchTerm,
  getEbayTitle,
  getShipmentStatus,
  isDelivered,
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
      <table className="min-w-[1320px] border-collapse text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="w-[78px] px-2 py-2">Date</th>
            <th className="w-[118px] px-2 py-2">Order</th>
            <th className="w-[430px] px-2 py-2">Item</th>
            <th className="w-[118px] px-2 py-2">ASIN</th>
            <th className="w-[96px] px-2 py-2">System</th>
            <th className="w-[46px] px-2 py-2">Qty</th>
            <th className="w-[90px] px-2 py-2">Unit Cost</th>
            <th className="w-[112px] px-2 py-2">Sell Price</th>
            <th className="w-[78px] px-2 py-2">Carrier</th>
            <th className="w-[84px] px-2 py-2">ETA</th>
            <th className="w-[84px] px-2 py-2">Status</th>
            <th className="w-[52px] px-2 py-2 text-center">Details</th>
          </tr>
        </thead>

        <tbody>
          {loading ? (
            <tr>
              <td className="px-2 py-6 text-center text-slate-500" colSpan={12}>
                Loading purchases...
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td className="px-2 py-6 text-center text-slate-500" colSpan={12}>
                No purchases found.
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const key = rowKey(row);
              const hasMatchedAsin = !!row.asin;
              const amazonTitle = row.amazon_title || "";
              const ebayTitle = getEbayTitle(row) || row.title || "";
              const primaryTitle = hasMatchedAsin
                ? amazonTitle || ebayTitle || "Untitled item"
                : ebayTitle || amazonTitle || "Untitled item";
              const showEbaySubtitle =
                hasMatchedAsin && !!amazonTitle && !!ebayTitle;
              const delivered = isDelivered(row);
              const deliveryDate = delivered
                ? row.delivered_date
                : row.estimated_delivery_date;
              const priceValue =
                priceDrafts[key] ??
                (row.sell_price ?? row.target_price ?? "").toString();

              return (
                <tr
                  key={key}
                  className="border-t border-slate-100 align-top hover:bg-slate-50"
                >
                  <td className="whitespace-nowrap px-2 py-2">
                    {formatDate(row.order_date)}
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

                  <td className="px-2 py-2">
                    {row.asin ? (
                      <a
                        href={amazonAsinUrl(row.asin)}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-blue-700 hover:underline"
                      >
                        {row.asin}
                      </a>
                    ) : (
                      <div>
                        <a
                          href={amazonSearchUrl(getAmazonSearchTerm(row))}
                          target="_blank"
                          rel="noreferrer"
                          className="whitespace-nowrap text-xs text-slate-500 hover:underline"
                        >
                          Search Amazon
                        </a>
                      </div>
                    )}
                  </td>

                  <td className="px-2 py-2">{row.system || ""}</td>
                  <td className="px-2 py-2">{row.quantity ?? ""}</td>
                  <td className="whitespace-nowrap px-2 py-2">
                    {formatMoney(row.unit_cost)}
                  </td>

                  <td className="px-2 py-2">
                    <EditablePriceCell
                      value={priceValue}
                      isSaving={savingKey === key}
                      onChange={(value) => onPriceDraftChange(key, value)}
                      onSave={() => onSaveSellPrice(row)}
                    />
                  </td>

                  <td className="px-2 py-2">{row.carrier || ""}</td>
                  <td
                    className={`whitespace-nowrap px-2 py-2 font-medium ${
                      delivered ? "text-green-700" : "text-amber-700"
                    }`}
                  >
                    {formatDate(deliveryDate)}
                  </td>
                  <td className="px-2 py-2">{getShipmentStatus(row)}</td>

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
