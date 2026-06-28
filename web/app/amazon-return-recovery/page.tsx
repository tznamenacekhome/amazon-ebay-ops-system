"use client";

import { useEffect, useState, type ReactNode } from "react";
import { RefreshCw, Search, X } from "lucide-react";

type QueueSummary = {
  total_customer_returns: number;
  filtered_customer_returns: number;
  with_reimbursement_evidence: number;
  without_reimbursement_evidence: number;
  with_customer_comments: number;
  needs_inspection: number;
  needs_review: number;
  send_back_to_amazon: number;
  sell_on_ebay: number;
  dispose_donate: number;
  closed: number;
};

type OriginalSaleFinancialImpact = {
  order_date: string | null;
  order_status: string | null;
  fulfillment_channel: string | null;
  sale_price: number | null;
  item_price: number | null;
  principal_amount: number | null;
  cogs: number | null;
  cogs_source: string | null;
  amazon_fees_excluding_fulfillment: number | null;
  fulfillment_cost: number | null;
  fulfillment_cost_source: string | null;
  original_net_profit: number | null;
  roi: number | null;
  refund_amount: number | null;
  refund_currency: string | null;
  estimated_unrecoverable_fees: number | null;
  estimated_return_loss: number | null;
  profitability_status: string | null;
  data_status: "matched" | "needs_matching" | "multiple_possible" | "missing_profitability";
  confidence: "high" | "order_only" | "needs_matching";
  match_basis: string;
};

type QueueRow = {
  id: string;
  return_date: string | null;
  title: string;
  asin: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  lpn: string | null;
  return_reason: string | null;
  return_disposition: string | null;
  return_status: string | null;
  customer_comments: string | null;
  amazon_order_id: string | null;
  merchant_order_id: string | null;
  quantity: number | null;
  reimbursement_status: "Evidence found" | "No linked evidence";
  reimbursement_count: number;
  reimbursement_amount_total: number | null;
  reimbursement_currency: string | null;
  latest_reimbursement_approval_date: string | null;
  original_sale: OriginalSaleFinancialImpact;
  case_id: string | null;
  workflow_state: string;
  decision: string;
  inspection: InspectionEvidence;
};

type InspectionEvidence = {
  observed_condition: string | null;
  sealed_new_status: string | null;
  complete_item: "yes" | "no" | "unknown";
  wrong_item: "yes" | "no" | "unknown";
  notes: string | null;
  inspected_at: string | null;
  updated_at: string | null;
};

type CustomerReturnRow = {
  amazon_fba_customer_return_row_id: string;
  amazon_order_id: string | null;
  merchant_order_id: string | null;
  return_date: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  asin: string | null;
  product_name: string | null;
  title: string | null;
  quantity: number | null;
  fulfillment_center_id: string | null;
  detailed_disposition: string | null;
  reason: string | null;
  status: string | null;
  license_plate_number: string | null;
  customer_comments: string | null;
  raw_row_json: unknown;
};

type ReimbursementRow = {
  amazon_fba_reimbursement_row_id: string;
  approval_date: string | null;
  reimbursement_id: string | null;
  case_id: string | null;
  amazon_order_id: string | null;
  reason: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  asin: string | null;
  quantity_reimbursed: number | null;
  amount_total: number | null;
  amount_per_unit: number | null;
  currency: string | null;
  raw_row_json: unknown;
};

type ReturnRecoveryCaseRow = {
  amazon_return_recovery_case_id: string;
  workflow_state: string;
  decision: string;
  evidence_summary: string | null;
  inspected_at: string | null;
  closed_at: string | null;
  raw_evidence_json: unknown;
  updated_at: string | null;
};

type ReturnRecoveryEventRow = {
  amazon_return_recovery_event_id: string;
  amazon_return_recovery_case_id: string;
  event_type: string;
  event_source: string;
  event_at: string;
  message: string | null;
  notes: string | null;
  raw_event_json: unknown;
  created_at: string | null;
};

type QueueResponse = {
  generated_at: string;
  workflow: string;
  summary: QueueSummary;
  rows: QueueRow[];
};

type DetailResponse = {
  row: QueueRow;
  original_sale: OriginalSaleFinancialImpact;
  customer_return: CustomerReturnRow;
  reimbursement_evidence: ReimbursementRow[];
  primary_case: ReturnRecoveryCaseRow | null;
  inspection: InspectionEvidence;
  cases: ReturnRecoveryCaseRow[];
  events: ReturnRecoveryEventRow[];
  raw_evidence: {
    customer_return: unknown;
    reimbursements: unknown[];
  };
};

type WorkflowFilter =
  | "open"
  | "needs_review"
  | "send_back_to_amazon"
  | "sell_on_ebay"
  | "dispose_donate"
  | "closed"
  | "all";

const TRI_STATE_OPTIONS: Array<[string, string]> = [
  ["unknown", "Unknown"],
  ["yes", "Yes"],
  ["no", "No"],
];

const WORKFLOW_FILTERS: Array<{
  value: WorkflowFilter;
  label: string;
  countKey?: keyof QueueSummary;
}> = [
  { value: "open", label: "Open" },
  { value: "needs_review", label: "Needs Review", countKey: "needs_review" },
  { value: "send_back_to_amazon", label: "Send Back", countKey: "send_back_to_amazon" },
  { value: "sell_on_ebay", label: "Sell on eBay", countKey: "sell_on_ebay" },
  { value: "dispose_donate", label: "Dispose/Donate", countKey: "dispose_donate" },
  { value: "closed", label: "Closed", countKey: "closed" },
  { value: "all", label: "All", countKey: "total_customer_returns" },
];

export default function AmazonReturnRecoveryPage() {
  const [searchText, setSearchText] = useState("");
  const [workflowFilter, setWorkflowFilter] = useState<WorkflowFilter>("open");
  const [data, setData] = useState<QueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      loadQueue(searchText);
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [searchText, workflowFilter]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    loadDetail(selectedId);
  }, [selectedId]);

  async function loadQueue(query = searchText) {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      params.set("workflow", workflowFilter);
      params.set("limit", "250");
      const response = await fetch(`/api/amazon/return-recovery?${params.toString()}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Failed to load Amazon returns: ${response.status}`);
      }
      setData(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Amazon returns.");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(id: string) {
    setDetailLoading(true);
    setDetailError(null);

    try {
      const response = await fetch(`/api/amazon/return-recovery/${id}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Failed to load return detail: ${response.status}`);
      }
      setDetail(await response.json());
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Failed to load return detail.");
    } finally {
      setDetailLoading(false);
    }
  }

  const rows = data?.rows ?? [];
  const summary = data?.summary;

  return (
    <main className="min-h-screen bg-slate-100 p-4 text-slate-900">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Amazon Returns</h1>
          <p className="text-sm text-slate-600">FBA customer return recovery queue</p>
        </div>
        <button
          type="button"
          onClick={() => loadQueue()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <section className="mb-4 grid gap-3 xl:grid-cols-5">
        <Metric label="Customer Returns" value={formatNumber(summary?.total_customer_returns)} loading={loading} />
        <Metric label="Showing" value={formatNumber(summary?.filtered_customer_returns)} loading={loading} />
        <Metric label="Evidence Found" value={formatNumber(summary?.with_reimbursement_evidence)} loading={loading} />
        <Metric label="No Evidence" value={formatNumber(summary?.without_reimbursement_evidence)} loading={loading} />
        <Metric label="Has Comments" value={formatNumber(summary?.with_customer_comments)} loading={loading} />
      </section>

      <section className="mb-4 rounded-md border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block min-w-[320px] flex-1">
            <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Scan / Search</span>
            <div className="relative max-w-3xl">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              autoFocus
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none ring-blue-500 focus:ring-2"
              placeholder="LPN, order ID, ASIN, SKU, FNSKU, title, reason, comments"
            />
            </div>
          </label>
          <WorkflowFilterButtons
            value={workflowFilter}
            summary={summary}
            onChange={setWorkflowFilter}
          />
        </div>
      </section>

      <section className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1660px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Customer Return Date</th>
                <th className="px-3 py-2">Original Order Date / Sale</th>
                <th className="px-3 py-2">Financial Impact</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">ASIN</th>
                <th className="px-3 py-2">SKU / FNSKU</th>
                <th className="px-3 py-2">LPN</th>
                <th className="px-3 py-2">Workflow</th>
                <th className="px-3 py-2">Amazon Reason</th>
                <th className="px-3 py-2">Amazon Disposition / Status</th>
                <th className="px-3 py-2">Comments</th>
                <th className="px-3 py-2">Reimbursement</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={12}>
                    Loading Amazon returns...
                  </td>
                </tr>
              ) : rows.length ? (
                rows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setSelectedId(row.id)}
                    className="cursor-pointer border-t border-slate-100 align-top hover:bg-blue-50/50"
                  >
                    <td className="whitespace-nowrap px-3 py-2 font-medium">{formatDate(row.return_date)}</td>
                    <td className="w-[160px] px-3 py-2">
                      <div className="font-medium">{formatDate(row.original_sale.order_date)}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {formatMoney(row.original_sale.sale_price)}
                      </div>
                    </td>
                    <td className="w-[190px] px-3 py-2">
                      <div className="font-medium">{financialStatusLabel(row.original_sale)}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        Refund {formatMoney(row.original_sale.refund_amount, row.original_sale.refund_currency)}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">
                        Loss: Needs financial mapping
                      </div>
                    </td>
                    <td className="w-[300px] px-3 py-2">
                      <div className="line-clamp-2 font-medium leading-snug">{row.title}</div>
                      <div className="mt-1 text-xs text-slate-500">{row.amazon_order_id ?? "--"}</div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-medium text-slate-800">
                      {row.asin ?? "--"}
                    </td>
                    <td className="w-[190px] px-3 py-2">
                      <div className="font-medium">{row.seller_sku ?? row.sku ?? "--"}</div>
                      <div className="text-xs text-slate-500">{row.fnsku ?? "--"}</div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-medium">{row.lpn ?? "--"}</td>
                    <td className="w-[170px] px-3 py-2">
                      <WorkflowPill row={row} />
                    </td>
                    <td className="w-[170px] px-3 py-2">
                      <ReturnReason reason={row.return_reason} />
                    </td>
                    <td className="w-[190px] px-3 py-2">
                      <div className="font-medium">{row.return_disposition ?? "--"}</div>
                      <div className="text-xs text-slate-500">{row.return_status ?? "--"}</div>
                    </td>
                    <td className="w-[260px] px-3 py-2 text-slate-600">
                      <div className="line-clamp-2">{row.customer_comments ?? "--"}</div>
                    </td>
                    <td className="w-[180px] px-3 py-2">
                      <EvidencePill row={row} />
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={12}>
                    No Amazon customer returns match the current search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selectedId ? (
        <ReturnDetailDrawer
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={() => setSelectedId(null)}
          onSaved={() => {
            if (selectedId) loadDetail(selectedId);
            loadQueue();
          }}
        />
      ) : null}
    </main>
  );
}

function ReturnDetailDrawer({
  detail,
  loading,
  error,
  onClose,
  onSaved,
}: {
  detail: DetailResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const customerReturn = detail?.customer_return ?? null;
  const reimbursements = detail?.reimbursement_evidence ?? [];
  const originalSale = detail?.original_sale ?? detail?.row.original_sale ?? null;
  const events = detail?.events ?? [];
  const [inspectionForm, setInspectionForm] = useState({
    observed_condition: "",
    sealed_new_status: "unknown",
    complete_item: "unknown",
    wrong_item: "unknown",
    notes: "",
    decision: "needs_review",
  });
  const [savingInspection, setSavingInspection] = useState(false);
  const [saveInspectionError, setSaveInspectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!detail) return;
    setInspectionForm({
      observed_condition: detail.inspection.observed_condition ?? "",
      sealed_new_status: detail.inspection.sealed_new_status ?? "unknown",
      complete_item: detail.inspection.complete_item,
      wrong_item: detail.inspection.wrong_item,
      notes: detail.inspection.notes ?? "",
      decision: detail.row.decision ?? "needs_review",
    });
    setSaveInspectionError(null);
  }, [detail?.row.id, detail?.inspection.updated_at]);

  async function saveInspection() {
    if (!detail) return;
    setSavingInspection(true);
    setSaveInspectionError(null);

    try {
      const response = await fetch(`/api/amazon/return-recovery/${detail.row.id}/actions`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-mbop-csrf": "1",
        },
        body: JSON.stringify({
          action: "record_inspection",
          ...inspectionForm,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error ?? `Failed to save inspection: ${response.status}`);
      }
      onSaved();
    } catch (err) {
      setSaveInspectionError(err instanceof Error ? err.message : "Failed to save inspection.");
    } finally {
      setSavingInspection(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
      <button
        type="button"
        className="absolute inset-0 bg-slate-950/25"
        onClick={onClose}
        aria-label="Close Amazon return detail overlay"
      />
      <aside className="absolute right-0 top-0 flex h-full w-full max-w-4xl flex-col bg-white shadow-xl">
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Amazon Return
              </div>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">
                {detail?.row.asin ?? customerReturn?.asin ?? "--"}
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-600">
                {detail?.row.title ?? customerReturn?.title ?? customerReturn?.product_name ?? "--"}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-300 p-2 text-slate-600 hover:bg-slate-50"
              aria-label="Close Amazon return detail"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-4">
          {loading ? (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-8 text-center text-sm text-slate-500">
              Loading return detail...
            </div>
          ) : error ? (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          ) : customerReturn ? (
            <div className="space-y-5">
              <DetailSection title="Amazon Customer Return Details">
                <div className="grid gap-3 md:grid-cols-3">
                  <InfoPair label="Return Reason" value={customerReturn.reason} important />
                  <InfoPair label="Disposition" value={customerReturn.detailed_disposition} />
                  <InfoPair label="Status" value={customerReturn.status} />
                  <InfoPair label="LPN" value={customerReturn.license_plate_number} important />
                  <InfoPair label="Amazon Order ID" value={customerReturn.amazon_order_id} />
                  <InfoPair label="Customer Return Date" value={formatDate(customerReturn.return_date)} />
                  <InfoPair label="ASIN" value={customerReturn.asin} />
                  <InfoPair label="SKU" value={customerReturn.seller_sku ?? customerReturn.sku} />
                  <InfoPair label="FNSKU" value={customerReturn.fnsku} />
                  <InfoPair label="Quantity" value={formatNumber(customerReturn.quantity)} />
                  <InfoPair label="Fulfillment Center" value={customerReturn.fulfillment_center_id} />
                  <InfoPair label="Merchant Order ID" value={customerReturn.merchant_order_id} />
                </div>
                <div className="mt-4">
                  <div className="text-xs font-medium uppercase text-slate-500">Customer Comments</div>
                  <div className="mt-1 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900">
                    {customerReturn.customer_comments ?? "--"}
                  </div>
                </div>
                <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  Amazon return reason/disposition is evidence only. Final condition and disposition require manual inspection; customer damaged does not automatically mean unsellable.
                </div>
              </DetailSection>

              <DetailSection title="Inspection / Decision">
                <div className="space-y-4">
                  <div className="grid gap-3 md:grid-cols-3">
                    <SelectField
                      label="Observed Condition"
                      value={inspectionForm.observed_condition}
                      onChange={(value) =>
                        setInspectionForm((current) => ({ ...current, observed_condition: value }))
                      }
                      options={[
                        ["", "Not recorded"],
                        ["new_sealed", "New sealed"],
                        ["new_opened", "New opened"],
                        ["used_like_new", "Used like new"],
                        ["used_good", "Used good"],
                        ["damaged", "Damaged"],
                        ["missing_parts", "Missing parts"],
                        ["wrong_item", "Wrong item"],
                        ["unknown", "Unknown"],
                      ]}
                    />
                    <SelectField
                      label="Sealed / New Status"
                      value={inspectionForm.sealed_new_status}
                      onChange={(value) =>
                        setInspectionForm((current) => ({ ...current, sealed_new_status: value }))
                      }
                      options={[
                        ["unknown", "Unknown"],
                        ["sealed_new", "Sealed new"],
                        ["opened_new", "Opened new"],
                        ["not_new", "Not new"],
                      ]}
                    />
                    <SelectField
                      label="Final Disposition"
                      value={inspectionForm.decision}
                      onChange={(value) =>
                        setInspectionForm((current) => ({ ...current, decision: value }))
                      }
                      options={[
                        ["needs_review", "Needs review"],
                        ["send_back_to_amazon", "Send back to Amazon"],
                        ["sell_on_ebay", "Sell/list on eBay"],
                        ["dispose_donate", "Dispose/donate"],
                      ]}
                    />
                    <SelectField
                      label="Complete Item"
                      value={inspectionForm.complete_item}
                      onChange={(value) =>
                        setInspectionForm((current) => ({ ...current, complete_item: value }))
                      }
                      options={TRI_STATE_OPTIONS}
                    />
                    <SelectField
                      label="Wrong Item"
                      value={inspectionForm.wrong_item}
                      onChange={(value) =>
                        setInspectionForm((current) => ({ ...current, wrong_item: value }))
                      }
                      options={TRI_STATE_OPTIONS}
                    />
                    <InfoPair
                      label="Current Workflow"
                      value={formatStatusText(detail?.row.workflow_state ?? "needs_inspection")}
                    />
                  </div>
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium uppercase text-slate-500">Notes</span>
                    <textarea
                      value={inspectionForm.notes}
                      onChange={(event) =>
                        setInspectionForm((current) => ({ ...current, notes: event.target.value }))
                      }
                      className="min-h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-blue-500 focus:ring-2"
                      placeholder="Observed condition, missing components, wrong item details, or handling notes"
                    />
                  </label>
                  {saveInspectionError ? (
                    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                      {saveInspectionError}
                    </div>
                  ) : null}
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs text-slate-500">
                      Saved inspections append timeline events and keep Amazon evidence read-only.
                    </div>
                    <button
                      type="button"
                      onClick={saveInspection}
                      disabled={savingInspection}
                      className="rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingInspection ? "Saving..." : "Save Inspection"}
                    </button>
                  </div>
                </div>
              </DetailSection>

              <DetailSection title="Original Sale / Return Financial Context">
                {originalSale ? (
                  <div className="space-y-4">
                    <div className="grid gap-3 md:grid-cols-3">
                      <InfoPair label="Original Order Date" value={displayDate(originalSale.order_date)} />
                      <InfoPair label="Order Status" value={displayValue(originalSale.order_status)} />
                      <InfoPair label="Fulfillment" value={displayValue(originalSale.fulfillment_channel)} />
                      <InfoPair label="Sale Price" value={displayMoney(originalSale.sale_price)} important />
                      <InfoPair label="Item Price" value={displayMoney(originalSale.item_price)} />
                      <InfoPair label="Principal Amount" value={displayMoney(originalSale.principal_amount)} />
                      <InfoPair label="COGS" value={displayMoney(originalSale.cogs)} important />
                      <InfoPair label="COGS Source" value={displayValue(originalSale.cogs_source)} />
                      <InfoPair label="Refund Amount" value={displayMoney(originalSale.refund_amount, originalSale.refund_currency)} />
                      <InfoPair
                        label="Unrecoverable Fees"
                        value={displayFinancialMapping(originalSale.estimated_unrecoverable_fees)}
                      />
                      <InfoPair
                        label="Estimated Return Loss"
                        value={displayFinancialMapping(originalSale.estimated_return_loss)}
                      />
                      <InfoPair
                        label="Current Profit Status"
                        value={displayValue(originalSale.profitability_status)}
                      />
                      <InfoPair label="Data Status" value={financialStatusLabel(originalSale)} />
                      <InfoPair label="Confidence" value={formatStatusText(originalSale.confidence)} />
                    </div>
                    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                      <span className="font-medium text-slate-900">Match basis: </span>
                      {originalSale.match_basis}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
                    Needs matching.
                  </div>
                )}
              </DetailSection>

              <DetailSection title="Event Timeline">
                {events.length ? (
                  <div className="space-y-3">
                    {events.map((event) => (
                      <div
                        key={event.amazon_return_recovery_event_id}
                        className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-semibold text-slate-900">
                            {formatStatusText(event.event_type)}
                          </div>
                          <div className="text-xs text-slate-500">{formatDateTime(event.event_at)}</div>
                        </div>
                        <div className="mt-1 text-sm text-slate-700">{event.message ?? "--"}</div>
                        {event.notes ? (
                          <div className="mt-1 text-sm text-slate-600">{event.notes}</div>
                        ) : null}
                        <div className="mt-1 text-xs text-slate-500">
                          {formatStatusText(event.event_source)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
                    No inspection or disposition events recorded yet.
                  </div>
                )}
              </DetailSection>

              <DetailSection title="Reimbursement Evidence">
                {reimbursements.length ? (
                  <div className="overflow-hidden rounded-md border border-slate-200">
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                        <tr>
                          <th className="px-3 py-2">Reimbursement ID</th>
                          <th className="px-3 py-2">Case ID</th>
                          <th className="px-3 py-2">Reason</th>
                          <th className="px-3 py-2 text-right">Qty</th>
                          <th className="px-3 py-2 text-right">Amount / Unit</th>
                          <th className="px-3 py-2">Currency</th>
                          <th className="px-3 py-2">Approval Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reimbursements.map((row) => (
                          <tr key={row.amazon_fba_reimbursement_row_id} className="border-t border-slate-100">
                            <td className="px-3 py-2 font-medium">{row.reimbursement_id ?? "--"}</td>
                            <td className="px-3 py-2">{row.case_id ?? "--"}</td>
                            <td className="px-3 py-2">{row.reason ?? "--"}</td>
                            <td className="px-3 py-2 text-right">{formatNumber(row.quantity_reimbursed)}</td>
                            <td className="px-3 py-2 text-right">{formatMoney(row.amount_per_unit, row.currency)}</td>
                            <td className="px-3 py-2">{row.currency ?? "--"}</td>
                            <td className="px-3 py-2">{formatDate(row.approval_date)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
                    No linked reimbursement evidence found.
                  </div>
                )}
              </DetailSection>

              <DetailSection title="Raw Amazon Evidence">
                <div className="space-y-3">
                  <RawEvidence title="Customer Return Raw Row" value={detail?.raw_evidence.customer_return} />
                  {reimbursements.length ? (
                    reimbursements.map((row, index) => (
                      <RawEvidence
                        key={row.amazon_fba_reimbursement_row_id}
                        title={`Reimbursement Raw Row ${index + 1}`}
                        value={row.raw_row_json}
                      />
                    ))
                  ) : (
                    <RawEvidence title="Reimbursement Raw Rows" value={[]} />
                  )}
                </div>
              </DetailSection>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">{children}</div>
    </section>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<[string, string]>;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-blue-500 focus:ring-2"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function WorkflowFilterButtons({
  value,
  summary,
  onChange,
}: {
  value: WorkflowFilter;
  summary?: QueueSummary;
  onChange: (value: WorkflowFilter) => void;
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase text-slate-500">Workflow</div>
      <div className="flex flex-wrap gap-2">
        {WORKFLOW_FILTERS.map((filter) => {
          const selected = filter.value === value;
          const count = filter.countKey ? summary?.[filter.countKey] : null;
          return (
            <button
              key={filter.value}
              type="button"
              onClick={() => onChange(filter.value)}
              className={`rounded-md border px-2.5 py-1.5 text-xs font-semibold ${
                selected
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {filter.label}
              {typeof count === "number" ? ` ${formatNumber(count)}` : ""}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function InfoPair({
  label,
  value,
  important = false,
}: {
  label: string;
  value?: string | null;
  important?: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className={`mt-1 break-words text-sm ${important ? "font-semibold text-slate-950" : "text-slate-800"}`}>
        {value ?? "--"}
      </div>
    </div>
  );
}

function RawEvidence({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="rounded-md border border-slate-200 bg-slate-50">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-slate-700">{title}</summary>
      <pre className="max-h-72 overflow-auto border-t border-slate-200 p-3 text-xs leading-relaxed text-slate-700">
        {JSON.stringify(value ?? null, null, 2)}
      </pre>
    </details>
  );
}

function Metric({ label, value, loading }: { label: string; value: string; loading: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold">{loading ? "--" : value}</div>
    </div>
  );
}

function ReturnReason({ reason }: { reason?: string | null }) {
  return (
    <span className="inline-flex max-w-full rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800">
      <span className="truncate">{reason ?? "--"}</span>
    </span>
  );
}

function EvidencePill({ row }: { row: QueueRow }) {
  if (!row.reimbursement_count) {
    return (
      <span className="inline-flex rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-semibold text-slate-700">
        No linked evidence
      </span>
    );
  }

  return (
    <div>
      <span className="inline-flex rounded border border-green-200 bg-green-50 px-2 py-0.5 text-xs font-semibold text-green-700">
        Evidence found
      </span>
      <div className="mt-1 text-xs text-slate-500">
        {formatNumber(row.reimbursement_count)} / {formatMoney(row.reimbursement_amount_total, row.reimbursement_currency)}
      </div>
    </div>
  );
}

function WorkflowPill({ row }: { row: QueueRow }) {
  const label = row.decision === "needs_review"
    ? formatStatusText(row.workflow_state)
    : formatStatusText(row.decision);
  const color =
    row.decision === "send_back_to_amazon"
      ? "border-blue-200 bg-blue-50 text-blue-700"
      : row.decision === "sell_on_ebay"
        ? "border-green-200 bg-green-50 text-green-700"
        : row.decision === "dispose_donate"
          ? "border-slate-300 bg-slate-100 text-slate-700"
          : "border-amber-200 bg-amber-50 text-amber-800";
  return (
    <div>
      <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-semibold ${color}`}>
        {label}
      </span>
      {row.inspection.inspected_at ? (
        <div className="mt-1 text-xs text-slate-500">
          Inspected {formatDate(row.inspection.inspected_at)}
        </div>
      ) : null}
    </div>
  );
}

function financialStatusLabel(originalSale: OriginalSaleFinancialImpact) {
  if (originalSale.confidence === "needs_matching") return "Needs matching";
  if (originalSale.data_status === "missing_profitability") return "Needs matching";
  if (originalSale.data_status === "multiple_possible") return "Needs matching";
  return originalSale.profitability_status ?? formatStatusText(originalSale.data_status);
}

function displayValue(value?: string | null) {
  return value ?? "Not available";
}

function displayDate(value?: string | null) {
  return value ? formatDate(value) : "Not available";
}

function displayMoney(value?: number | null, currency?: string | null) {
  return value === null || value === undefined ? "Not available" : formatMoney(value, currency);
}

function displayFinancialMapping(value?: number | null, currency?: string | null) {
  return value === null || value === undefined ? "Needs financial mapping" : formatMoney(value, currency);
}

function formatStatusText(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return formatDate(value);
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

function formatDate(value?: string | null) {
  if (!value) return "--";
  const match = value.match(/^\d{4}-\d{2}-\d{2}/);
  return match?.[0] ?? "--";
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatMoney(value?: number | null, currency?: string | null) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "--";
  const currencyCode = currency && /^[A-Z]{3}$/.test(currency) ? currency : "USD";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(Number(value));
  } catch {
    return `${currency ?? ""} ${Number(value).toFixed(2)}`.trim();
  }
}
