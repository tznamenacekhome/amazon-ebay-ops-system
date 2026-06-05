import { ExternalLink, Plus, RotateCcw, Save, X } from "lucide-react";
import { useState } from "react";

import { SYSTEM_OPTIONS } from "./systemOptions";
import type { PurchaseRow } from "./types";
import {
  formatDate,
  formatMoney,
  getDisplayDeliveryDate,
  getEbayTitle,
  getOperationalStatus,
  getShipmentStatus,
  rowKey,
} from "./utils";

type PurchaseDetailDrawerProps = {
  row: PurchaseRow;
  drawerAsin: string;
  drawerAmazonTitle: string;
  drawerSellPrice: string;
  drawerEbayTitle: string;
  drawerUnitCost: string;
  drawerSystem: string;
  savingKey: string | null;
  onAsinChange: (value: string) => void;
  onAmazonTitleChange: (value: string) => void;
  onSellPriceChange: (value: string) => void;
  onEbayTitleChange: (value: string) => void;
  onUnitCostChange: (value: string) => void;
  onSystemChange: (value: string) => void;
  onAddSplitItem: () => void;
  onMarkReturnPending: () => void;
  onProblemAction?: (action: string, payload?: { notes?: string; amount?: number | null; tracking_number?: string | null }) => void;
  onSave: () => void;
  onClose: () => void;
};

export function PurchaseDetailDrawer({
  row,
  drawerAsin,
  drawerAmazonTitle,
  drawerSellPrice,
  drawerEbayTitle,
  drawerUnitCost,
  drawerSystem,
  savingKey,
  onAsinChange,
  onAmazonTitleChange,
  onSellPriceChange,
  onEbayTitleChange,
  onUnitCostChange,
  onSystemChange,
  onAddSplitItem,
  onMarkReturnPending,
  onProblemAction,
  onSave,
  onClose,
}: PurchaseDetailDrawerProps) {
  const [problemNotes, setProblemNotes] = useState("");
  const [problemAmount, setProblemAmount] = useState("");
  const [problemTracking, setProblemTracking] = useState("");
  const operationalStatus = getOperationalStatus(row);
  const displayAmazonTitle = row.asin ? drawerAmazonTitle || row.amazon_title || "--" : "--";
  const isSaving = savingKey === rowKey(row);
  const isReturnPending = operationalStatus.value === "return_pending";
  const hasProblemCase = Boolean(row.problem_case_id);

  function runProblemAction(action: string) {
    const amount = problemAmount.trim() === "" ? null : Number(problemAmount);
    onProblemAction?.(action, {
      notes: problemNotes,
      amount: Number.isFinite(amount) ? amount : null,
      tracking_number: problemTracking,
    });
    setProblemNotes("");
    setProblemAmount("");
    setProblemTracking("");
  }

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

            <div className="mt-1 font-medium">{displayAmazonTitle}</div>

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

          {hasProblemCase && (
            <section className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
              <div className="mb-3">
                <div className="text-xs uppercase tracking-wide text-amber-700">
                  Order Problem Workflow
                </div>
                <div className="mt-1 text-sm text-slate-700">
                  {workflowStateLabel(row.workflow_state)} / {problemTypeLabel(row.problem_type)}
                </div>
                {row.problem_next_action && (
                  <div className="mt-1 text-sm font-medium text-slate-900">
                    {row.problem_next_action}
                  </div>
                )}
                {row.ebay_action_url && (
                  <a
                    href={row.ebay_action_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-blue-700 hover:underline"
                  >
                    <ExternalLink className="h-4 w-4" />
                    Open eBay action
                  </a>
                )}
              </div>

              <div className="grid gap-2">
                <textarea
                  value={problemNotes}
                  onChange={(event) => setProblemNotes(event.target.value)}
                  className="min-h-16 rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm"
                  placeholder="Optional workflow note"
                />
                <div className="grid grid-cols-2 gap-2">
                  <CurrencyInput value={problemAmount} onChange={setProblemAmount} />
                  <input
                    value={problemTracking}
                    onChange={(event) => setProblemTracking(event.target.value)}
                    className="rounded-lg border border-amber-200 bg-white px-3 py-2 text-sm"
                    placeholder="Return/replacement tracking"
                  />
                </div>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2">
                <WorkflowButton label="Return Needed" onClick={() => runProblemAction("mark_return_needed")} />
                <WorkflowButton label="Return Opened" onClick={() => runProblemAction("mark_return_opened")} />
                <WorkflowButton label="Seller Messaged" onClick={() => runProblemAction("mark_seller_messaged")} />
                <WorkflowButton label="I Responded" onClick={() => runProblemAction("mark_operator_responded")} />
                <WorkflowButton label="Partial Offered" onClick={() => runProblemAction("mark_partial_refund_offered")} />
                <WorkflowButton label="Partial Accepted" onClick={() => runProblemAction("mark_partial_refund_accepted")} />
                <WorkflowButton label="Label Available" onClick={() => runProblemAction("mark_label_available")} />
                <WorkflowButton label="Return Shipped" onClick={() => runProblemAction("mark_return_shipped")} />
                <WorkflowButton label="Seller Received" onClick={() => runProblemAction("mark_seller_received_return")} />
                <WorkflowButton label="Refund Pending" onClick={() => runProblemAction("mark_refund_pending")} />
                <WorkflowButton label="Refund Received" onClick={() => runProblemAction("mark_refund_received")} />
                <WorkflowButton label="Missing Pending" onClick={() => runProblemAction("mark_missing_item_pending")} />
                <WorkflowButton label="Replacement Shipped" onClick={() => runProblemAction("mark_replacement_shipped")} />
                <WorkflowButton label="Missing Received" onClick={() => runProblemAction("mark_missing_item_received")} />
                <WorkflowButton label="Escalation Available" onClick={() => runProblemAction("mark_escalation_available")} />
                <WorkflowButton label="Escalated" onClick={() => runProblemAction("mark_escalated")} />
                <WorkflowButton label="Close No Refund" onClick={() => runProblemAction("close_no_refund")} />
                <WorkflowButton label="Close" onClick={() => runProblemAction("close_resolve")} />
              </div>

              {row.problem_notes && (
                <div className="mt-3 whitespace-pre-wrap rounded-lg bg-white p-3 text-sm text-slate-700">
                  {row.problem_notes}
                </div>
              )}
            </section>
          )}

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
                System
                <select
                  value={drawerSystem}
                  onChange={(event) => onSystemChange(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-900"
                >
                  <option value="">Select system</option>
                  {SYSTEM_OPTIONS.map((system) => (
                    <option key={system} value={system}>
                      {system}
                    </option>
                  ))}
                </select>
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
                Amazon Title
                <input
                  value={drawerAmazonTitle}
                  onChange={(event) => onAmazonTitleChange(event.target.value)}
                  className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-900"
                  placeholder="Enter Amazon title"
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

                <button
                  onClick={onMarkReturnPending}
                  disabled={isSaving || isReturnPending}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                  type="button"
                >
                  <RotateCcw className="h-4 w-4" />
                  {isReturnPending ? "Return Pending" : "Mark Return Pending"}
                </button>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-2 gap-3 text-sm">
            <Detail label="Order Date" value={formatDate(row.order_date)} />
            <Detail label="ETA" value={formatDate(getDisplayDeliveryDate(row))} />
            <Detail label="Order ID" value={row.supplier_order_id || ""} />
            <Detail label="System" value={drawerSystem || row.system || ""} />
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

function WorkflowButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg border border-amber-300 bg-white px-2 py-2 text-xs font-medium text-slate-700 hover:bg-amber-100"
    >
      {label}
    </button>
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

function workflowStateLabel(value?: string | null) {
  return titleCase(value || "unknown");
}

function problemTypeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    late_delivery_candidate: "Late Delivery Candidate",
    stale_tracking_candidate: "Stale Tracking Candidate",
    carrier_exception_candidate: "Carrier Exception Candidate",
    return_needed: "Return Needed",
    not_as_listed: "Wrong Item / Not as Listed",
    buyer_choice: "Changed Plan / Return Anyway",
    missing_items: "Missing Item / Incomplete Order",
    cancelled_refund_followup: "Cancelled / Refund Follow-Up",
  };
  return labels[value || ""] || titleCase(value || "Unknown");
}

function titleCase(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
