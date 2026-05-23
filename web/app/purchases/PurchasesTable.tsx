import { ArrowDown, ArrowUp, ArrowUpDown, PanelRightOpen } from "lucide-react";
import { useMemo, useState } from "react";

import { EditablePriceCell } from "./EditablePriceCell";
import type { PurchaseRow } from "./types";
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
  isDelivered,
  rowKey,
} from "./utils";

type SortDirection = "asc" | "desc";

type SortColumn =
  | "order_date"
  | "supplier_order_id"
  | "item"
  | "asin"
  | "system"
  | "quantity"
  | "unit_cost"
  | "sell_price"
  | "carrier"
  | "eta"
  | "status";

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
  const [sortState, setSortState] = useState<{
    column: SortColumn;
    direction: SortDirection;
  }>({
    column: "order_date",
    direction: "desc",
  });
  const sortedRows = useMemo(() => {
    return [...rows].sort((left, right) => {
      const comparison = compareRows(left, right, sortState.column);
      return sortState.direction === "asc" ? comparison : -comparison;
    });
  }, [rows, sortState]);

  function toggleSort(column: SortColumn) {
    setSortState((current) => ({
      column,
      direction:
        current.column === column && current.direction === "asc" ? "desc" : "asc",
    }));
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <table className="min-w-[1320px] border-collapse text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <SortableHeader
              label="Date"
              column="order_date"
              className="w-[78px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Order"
              column="supplier_order_id"
              className="w-[118px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Item"
              column="item"
              className="w-[430px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="ASIN"
              column="asin"
              className="w-[118px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="System"
              column="system"
              className="w-[96px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Qty"
              column="quantity"
              className="w-[46px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Unit Cost"
              column="unit_cost"
              className="w-[90px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Sell Price"
              column="sell_price"
              className="w-[112px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Carrier"
              column="carrier"
              className="w-[78px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="ETA"
              column="eta"
              className="w-[84px]"
              sortState={sortState}
              onSort={toggleSort}
            />
            <SortableHeader
              label="Status"
              column="status"
              className="w-[84px]"
              sortState={sortState}
              onSort={toggleSort}
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
          ) : sortedRows.length === 0 ? (
            <tr>
              <td className="px-2 py-6 text-center text-slate-500" colSpan={12}>
                No purchases found.
              </td>
            </tr>
          ) : (
            sortedRows.map((row) => {
              const key = rowKey(row);
              const { primaryTitle, ebayTitle, showEbaySubtitle } =
                getDisplayTitleParts(row);
              const delivered = isDelivered(row);
              const operationalStatus = getOperationalStatus(row);
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
                      delivered ? "text-green-700" : "text-yellow-600"
                    }`}
                  >
                    {formatDate(deliveryDate)}
                  </td>
                  <td className="px-2 py-2">{operationalStatus.label}</td>

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

function SortableHeader({
  label,
  column,
  className,
  sortState,
  onSort,
}: {
  label: string;
  column: SortColumn;
  className: string;
  sortState: {
    column: SortColumn;
    direction: SortDirection;
  };
  onSort: (column: SortColumn) => void;
}) {
  const isActive = sortState.column === column;
  const Icon = isActive
    ? sortState.direction === "asc"
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

function compareRows(left: PurchaseRow, right: PurchaseRow, column: SortColumn) {
  if (column === "order_date") {
    return compareDates(left.order_date, right.order_date);
  }

  if (column === "eta") {
    return compareDates(getDisplayDeliveryDate(left), getDisplayDeliveryDate(right));
  }

  if (column === "quantity") {
    return compareNumbers(left.quantity, right.quantity);
  }

  if (column === "unit_cost") {
    return compareNumbers(left.unit_cost, right.unit_cost);
  }

  if (column === "sell_price") {
    return compareNumbers(
      left.sell_price ?? left.target_price,
      right.sell_price ?? right.target_price
    );
  }

  return compareStrings(getSortText(left, column), getSortText(right, column));
}

function getSortText(row: PurchaseRow, column: SortColumn) {
  if (column === "supplier_order_id") return row.supplier_order_id || "";
  if (column === "item") return getDisplayTitleParts(row).primaryTitle;
  if (column === "asin") return row.asin || "";
  if (column === "system") return row.system || "";
  if (column === "carrier") return row.carrier || "";
  if (column === "status") return getOperationalStatus(row).label;

  return "";
}

function compareStrings(left: string, right: string) {
  const leftEmpty = left.trim() === "";
  const rightEmpty = right.trim() === "";

  if (leftEmpty && rightEmpty) return 0;
  if (leftEmpty) return 1;
  if (rightEmpty) return -1;

  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function compareNumbers(left?: number | null, right?: number | null) {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  const leftValid = !Number.isNaN(leftNumber) && left !== null && left !== undefined;
  const rightValid =
    !Number.isNaN(rightNumber) && right !== null && right !== undefined;

  if (!leftValid && !rightValid) return 0;
  if (!leftValid) return 1;
  if (!rightValid) return -1;

  return leftNumber - rightNumber;
}

function compareDates(left?: string | null, right?: string | null) {
  const leftTime = getDateTime(left);
  const rightTime = getDateTime(right);

  if (leftTime === null && rightTime === null) return 0;
  if (leftTime === null) return 1;
  if (rightTime === null) return -1;

  return leftTime - rightTime;
}

function getDateTime(value?: string | null) {
  if (!value) return null;

  const time = new Date(value).getTime();

  return Number.isNaN(time) ? null : time;
}
