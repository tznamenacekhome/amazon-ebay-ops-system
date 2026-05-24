import { Plus, Save, X } from "lucide-react";

import type { PurchaseRow } from "./types";
import {
  formatDate,
  formatMoney,
  getDisplayDeliveryDate,
  getEbayTitle,
  getOperationalStatus,
  getPrimaryTitle,
  getShipmentStatus,
  rowKey,
} from "./utils";

type PurchaseDetailDrawerProps = {
  row: PurchaseRow;
  drawerAsin: string;
  drawerSellPrice: string;
  drawerEbayTitle: string;
  drawerUnitCost: string;
  savingKey: string | null;
  onAsinChange: (value: string) => void;
  onSellPriceChange: (value: string) => void;
  onEbayTitleChange: (value: string) => void;
  onUnitCostChange: (value: string) => void;
  onAddSplitItem: () => void;
  onSave: () => void;
  onClose: () => void;
};

export function PurchaseDetailDrawer({
  row,
  drawerAsin,
  drawerSellPrice,
  drawerEbayTitle,
  drawerUnitCost,
  savingKey,
  onAsinChange,
  onSellPriceChange,
  onEbayTitleChange,
  onUnitCostChange,
  onAddSplitItem,
  onSave,
  onClose,
}: PurchaseDetailDrawerProps) {
  const operationalStatus = getOperationalStatus(row);
  const drawerAmazonTitle = row.asin ? getPrimaryTitle(row) : "--";
  const isSaving = savingKey === rowKey(row);

  return (
    <div className="fixed inset-0 z-40">
      <button
        className="absolute inset-0 bg-slate-900/30"
        onClick={onClose}
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
            onClick={onClose}
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

            <div className="mt-1 font-medium">{drawerAmazonTitle}</div>

            {getEbayTitle(row) && (
              <>
                <div className="mt-4 text-xs uppercase tracking-wide text-slate-500">
                  eBay Title
                </div>

                <div className="mt-1 text-sm text-slate-700">
                  {getEbayTitle(row)}
                </div>
              </>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 p-4">
            <div className="grid gap-3">
              <label className="grid gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                eBay Title
                <textarea
                  value={drawerEbayTitle}
                  onChange={(event) => onEbayTitleChange(event.target.value)}
                  className="min-h-20 rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-900"
                  placeholder="Enter eBay listing title"
                />
              </label>

              <label className="grid gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                Purchase Price
                <CurrencyInput
                  value={drawerUnitCost}
                  onChange={onUnitCostChange}
                />
              </label>

              <label className="grid gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                ASIN
                <input
                  value={drawerAsin}
                  onChange={(event) => onAsinChange(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-900"
                  placeholder="Enter ASIN"
                />
              </label>

              <label className="grid gap-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                Sell Price
                <CurrencyInput
                  value={drawerSellPrice}
                  onChange={onSellPriceChange}
                />
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={onSave}
                  disabled={isSaving}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  <Save className="h-4 w-4" />
                  {isSaving ? "Saving" : "Save"}
                </button>

                <button
                  onClick={onAddSplitItem}
                  disabled={isSaving}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  <Plus className="h-4 w-4" />
                  Split Item
                </button>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-2 gap-3 text-sm">
            <Detail label="Order Date" value={formatDate(row.order_date)} />
            <Detail label="ETA" value={formatDate(getDisplayDeliveryDate(row))} />
            <Detail label="Order ID" value={row.supplier_order_id || ""} />
            <Detail label="System" value={row.system || ""} />
            <Detail label="Quantity" value={String(row.quantity ?? "")} />
            <Detail label="Unit Cost" value={formatMoney(row.unit_cost)} />
            <Detail label="Carrier" value={row.carrier || ""} />
            <Detail label="Delivered" value={formatDate(row.delivered_date)} />
            <Detail label="Status" value={operationalStatus.label} />
            <Detail label="Carrier Status" value={getShipmentStatus(row)} />
            <Detail label="eBay Status" value={row.order_status || ""} />
          </section>

          <section>
            <div className="text-xs uppercase tracking-wide text-slate-500">
              Tracking
            </div>

            <div className="mt-1 break-all rounded-lg bg-slate-50 p-3 text-sm">
              {row.tracking_number || "No tracking number"}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function CurrencyInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm font-normal normal-case tracking-normal text-slate-500">
        $
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-300 py-2 pl-7 pr-3 text-sm font-normal normal-case tracking-normal text-slate-900"
        inputMode="decimal"
        placeholder="0.00"
      />
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

      <div className="mt-1 font-medium text-slate-800">{value || "--"}</div>
    </div>
  );
}
