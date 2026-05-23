import { Save, X } from "lucide-react";

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
  savingKey: string | null;
  onAsinChange: (value: string) => void;
  onSaveAsin: () => void;
  onClose: () => void;
};

export function PurchaseDetailDrawer({
  row,
  drawerAsin,
  savingKey,
  onAsinChange,
  onSaveAsin,
  onClose,
}: PurchaseDetailDrawerProps) {
  const operationalStatus = getOperationalStatus(row);
  const drawerAmazonTitle = row.asin ? getPrimaryTitle(row) : "--";

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
            <label className="text-xs font-medium uppercase tracking-wide text-slate-500">
              ASIN
            </label>

            <div className="mt-2 flex gap-2">
              <input
                value={drawerAsin}
                onChange={(event) => onAsinChange(event.target.value)}
                className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                placeholder="Enter ASIN"
              />

              <button
                onClick={onSaveAsin}
                disabled={savingKey === rowKey(row)}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
              >
                <Save className="h-4 w-4" />
                Save
              </button>
            </div>
          </section>

          <section className="grid grid-cols-2 gap-3 text-sm">
            <Detail label="Order Date" value={formatDate(row.order_date)} />
            <Detail label="ETA" value={formatDate(getDisplayDeliveryDate(row))} />
            <Detail label="Order ID" value={row.supplier_order_id || ""} />
            <Detail label="System" value={row.system || ""} />
            <Detail label="Quantity" value={String(row.quantity ?? "")} />
            <Detail label="Unit Cost" value={formatMoney(row.unit_cost)} />
            <Detail
              label="Sell Price"
              value={formatMoney(row.sell_price ?? row.target_price)}
            />
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
