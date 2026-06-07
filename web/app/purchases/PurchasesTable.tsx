import { ArrowDown, ArrowUp, ArrowUpDown, PanelRightOpen } from "lucide-react";

import { EditablePriceCell } from "./EditablePriceCell";
import type {
  PurchaseRow,
  PurchaseSortColumn,
  PurchaseSortDirection,
} from "./types";
import {
  amazonAsinUrl,
  amazonSearchUrl,
  ebayOrderUrl,
  formatDate,
  formatMoney,
  getAmazonSearchTerm,
  getDisplayDeliveryDate,
  getDisplayTitleParts,
  getOperationalStatus,
  getShipmentStatus,
  isDelivered,
  rowKey,
} from "./utils";

type PurchasesTableProps = {
  rows: PurchaseRow[];
  loading: boolean;
  priceDrafts: Record<string, string>;
  savingKey: string | null;
  sortColumn: PurchaseSortColumn;
  sortDirection: PurchaseSortDirection;
  onSort: (column: PurchaseSortColumn) => void;
  onPriceDraftChange: (key: string, value: string) => void;
  onSaveSellPrice: (row: PurchaseRow) => void;
  onSelectRow: (row: PurchaseRow) => void;
};

export function PurchasesTable({
  rows,
  loading,
  priceDrafts,
  savingKey,
  sortColumn,
  sortDirection,
  onSort,
  onPriceDraftChange,
  onSaveSellPrice,
  onSelectRow,
}: PurchasesTableProps) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-[1320px] border-collapse text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <SortableHeader
              label="Date"
              column="order_date"
              className="w-[78px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Order"
              column="supplier_order_id"
              className="w-[118px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Item"
              column="item"
              className="w-[430px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="ASIN"
              column="asin"
              className="w-[118px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="System"
              column="system"
              className="w-[96px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Qty"
              column="quantity"
              className="w-[46px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Unit Cost"
              column="unit_cost"
              className="w-[90px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Sell Price"
              column="sell_price"
              className="w-[112px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Carrier"
              column="carrier"
              className="w-[78px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="ETA"
              column="eta"
              className="w-[84px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
            <SortableHeader
              label="Status"
              column="status"
              className="w-[84px]"
              sortColumn={sortColumn}
              sortDirection={sortDirection}
              onSort={onSort}
            />
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
              const { primaryTitle, ebayTitle, showEbaySubtitle } =
                getDisplayTitleParts(row);
              const delivered = isDelivered(row);
              const operationalStatus = getOperationalStatus(row);
              const shipmentStatus = getShipmentStatus(row);
              const displayStatus =
                row.replacement_tracking_number && shipmentStatus
                  ? titleCase(shipmentStatus)
                  : operationalStatus.label;
              const displayDelivered =
                delivered || normalizeStatus(shipmentStatus) === "delivered";
              const deliveryDate = getDisplayDeliveryDate(row);
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
                      <div>
                        <a
                          href={ebayOrderUrl(row.supplier_order_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="text-blue-700 hover:underline"
                        >
                          {row.supplier_order_id}
                        </a>
                        {hasOpenCase(row) && (
                          <div className="mt-1 inline-flex rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800">
                            Case Open
                          </div>
                        )}
                      </div>
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

                  <td className="px-2 py-2">
                    <div>{row.carrier || ""}</div>
                    {row.tracking_number && (
                      <div className="mt-1 break-all text-xs text-slate-500">
                        {row.tracking_number}
                      </div>
                    )}
                  </td>
                  <td
                    className={`whitespace-nowrap px-2 py-2 font-medium ${
                      displayDelivered ? "text-green-700" : "text-yellow-600"
                    }`}
                  >
                    {formatDate(deliveryDate)}
                  </td>
                  <td className="px-2 py-2">{displayStatus}</td>

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

function hasOpenCase(row: PurchaseRow) {
  return Boolean(
    row.problem_is_open &&
      (row.ebay_return_id || row.ebay_inquiry_id || row.ebay_case_id || row.workflow_state)
  );
}

function normalizeStatus(value?: string | null) {
  return (value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function titleCase(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function SortableHeader({
  label,
  column,
  className,
  sortColumn,
  sortDirection,
  onSort,
}: {
  label: string;
  column: PurchaseSortColumn;
  className: string;
  sortColumn: PurchaseSortColumn;
  sortDirection: PurchaseSortDirection;
  onSort: (column: PurchaseSortColumn) => void;
}) {
  const isActive = sortColumn === column;
  const Icon = isActive
    ? sortDirection === "asc"
      ? ArrowUp
      : ArrowDown
    : ArrowUpDown;

  return (
    <th className={`${className} px-2 py-2`}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="flex w-full items-center gap-1 text-left font-semibold hover:text-slate-900"
      >
        <span>{label}</span>
        <Icon
          className={`h-3.5 w-3.5 ${
            isActive ? "text-slate-800" : "text-slate-400"
          }`}
        />
      </button>
    </th>
  );
}
