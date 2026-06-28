"use client";

import { useEffect, useState, type ReactNode } from "react";
import { RefreshCw, Search, X } from "lucide-react";

type QueueSummary = {
  total_customer_returns: number;
  filtered_customer_returns: number;
  with_reimbursement_evidence: number;
  without_reimbursement_evidence: number;
  with_customer_comments: number;
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

type QueueResponse = {
  generated_at: string;
  summary: QueueSummary;
  rows: QueueRow[];
};

type DetailResponse = {
  row: QueueRow;
  customer_return: CustomerReturnRow;
  reimbursement_evidence: ReimbursementRow[];
  raw_evidence: {
    customer_return: unknown;
    reimbursements: unknown[];
  };
};

export default function AmazonReturnRecoveryPage() {
  const [searchText, setSearchText] = useState("");
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
  }, [searchText]);

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
        <label className="block">
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
      </section>

      <section className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1320px] text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Return Date</th>
                <th className="px-3 py-2">Title</th>
                <th className="px-3 py-2">ASIN</th>
                <th className="px-3 py-2">SKU / FNSKU</th>
                <th className="px-3 py-2">LPN</th>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Disposition / Status</th>
                <th className="px-3 py-2">Comments</th>
                <th className="px-3 py-2">Reimbursement</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={9}>
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
                  <td className="px-3 py-8 text-center text-slate-500" colSpan={9}>
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
}: {
  detail: DetailResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const customerReturn = detail?.customer_return ?? null;
  const reimbursements = detail?.reimbursement_evidence ?? [];

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
                  <InfoPair label="Return Date" value={formatDate(customerReturn.return_date)} />
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
