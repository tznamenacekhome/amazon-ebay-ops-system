"use client";

import { PanelRightOpen } from "lucide-react";

import type { PurchaseRow } from "./types";
import {
  ebayOrderUrl,
  ebayProblemDetailUrl,
  formatDate,
  formatMoney,
  getDisplayTitleParts,
  rowKey,
} from "./utils";

type PurchaseProblemTableProps = {
  rows: PurchaseRow[];
  loading: boolean;
  stage: string;
  onStageChange: (stage: string) => void;
  onSelectRow: (row: PurchaseRow) => void;
};

const STAGE_FILTERS = [
  ["open", "All Open Problems"],
  ["candidates", "Candidates"],
  ["return_needed", "Return Needed"],
  ["return_opened", "Return Opened"],
  ["needs_response", "Needs My Response"],
  ["waiting_on_seller", "Waiting on Seller"],
  ["ready_to_ship", "Ready to Ship Back"],
  ["return_shipped", "Return Shipped"],
  ["refund_pending", "Refund Pending"],
  ["missing_item_pending", "Missing Item Pending"],
  ["escalation_available", "Escalation Available"],
  ["resolved", "Resolved / Closed"],
] as const;

export function PurchaseProblemTable({
  rows,
  loading,
  stage,
  onStageChange,
  onSelectRow,
}: PurchaseProblemTableProps) {
  const stats = getProblemStats(rows);

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50 px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Order Problems</div>
            <div className="text-xs text-slate-500">
              Episode queue for delivery problems, return follow-up, seller responses, refunds, and missing items.
            </div>
          </div>
          <div className="text-xs text-slate-500">
            {rows.length.toLocaleString("en-US")} rows in current filter
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
          <ProblemStat label="Episodes" value={stats.total} />
          <ProblemStat label="Urgent" value={stats.urgent} tone={stats.urgent > 0 ? "red" : "slate"} />
          <ProblemStat label="Refund Pending" value={stats.refundPending} tone={stats.refundPending > 0 ? "amber" : "slate"} />
          <ProblemStat label="Returns Open" value={stats.returnsOpen} />
          <ProblemStat label="Missing Items" value={stats.missingItems} />
          <ProblemStat label="Candidates" value={stats.candidates} />
          <ProblemStat label="No eBay Link" value={stats.noEbayLink} tone={stats.noEbayLink > 0 ? "amber" : "slate"} />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {STAGE_FILTERS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => onStageChange(value)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                stage === value
                  ? "bg-slate-900 text-white"
                  : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-[1320px] border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-[90px] px-2 py-2">Priority</th>
              <th className="w-[190px] px-2 py-2">Episode</th>
              <th className="w-[115px] px-2 py-2">Dates</th>
              <th className="w-[130px] px-2 py-2">Order ID</th>
              <th className="w-[360px] px-2 py-2">Item</th>
              <th className="w-[90px] px-2 py-2">System</th>
              <th className="w-[180px] px-2 py-2">Status</th>
              <th className="w-[240px] px-2 py-2">Next Action</th>
              <th className="w-[110px] px-2 py-2 text-right">Expected Refund</th>
              <th className="w-[110px] px-2 py-2 text-right">Received Refund</th>
              <th className="w-[120px] px-2 py-2">Tracking / ETA</th>
              <th className="w-[52px] px-2 py-2 text-center">Details</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td className="px-2 py-6 text-center text-slate-500" colSpan={12}>
                  Loading order problems...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td className="px-2 py-6 text-center text-slate-500" colSpan={12}>
                  No order problems found.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const { primaryTitle, ebayTitle, showEbaySubtitle } =
                  getDisplayTitleParts(row);
                const ebayStatus = [row.ebay_return_state, row.ebay_return_status]
                  .filter(Boolean)
                  .join(" / ");
                const detailUrl = ebayProblemDetailUrl(row);
                const detailLabel = problemDetailLabel(row);

                return (
                  <tr
                    key={row.problem_case_id || rowKey(row)}
                    className="border-t border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="px-2 py-2">
                      <PriorityBadge value={row.problem_priority} needsResponse={row.problem_needs_response} />
                    </td>
                    <td className="px-2 py-2">
                      <div>{problemTypeLabel(row.problem_type)}</div>
                      <div className="text-xs text-slate-500">{episodeLabel(row)}</div>
                      <span className={`mt-1 inline-flex rounded border px-1.5 py-0.5 text-[11px] font-medium ${artifactBadgeClass(row)}`}>
                        {artifactLabel(row)}
                      </span>
                    </td>
                    <td className="px-2 py-2">
                      <div>{formatPacificDate(problemStatusDate(row)) || "--"}</div>
                      <div className="text-xs text-slate-500">Order {formatDate(row.order_date) || "--"}</div>
                    </td>
                    <td className="px-2 py-2">
                      {row.supplier_order_id ? (
                        <div>
                          <a
                            href={ebayOrderUrl(row.supplier_order_id)}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-blue-700 hover:underline"
                            title="Open eBay order"
                          >
                            {row.supplier_order_id}
                          </a>
                          {detailUrl ? (
                            <a
                              href={detailUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-1 block text-xs text-slate-500 hover:text-blue-700 hover:underline"
                            >
                              {detailLabel}
                            </a>
                          ) : null}
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
                    <td className="px-2 py-2">{row.system || "--"}</td>
                    <td className="px-2 py-2">
                      <div className="font-medium text-slate-900">{workflowStateLabel(row.workflow_state)}</div>
                      <div className="text-xs text-slate-500">{statusDateDetail(row)}</div>
                      {ebayStatus ? <div className="text-xs text-slate-500">eBay {titleCase(ebayStatus)}</div> : null}
                    </td>
                    <td className="px-2 py-2">
                      <div>{row.problem_next_action || "--"}</div>
                      <NextActionDetail row={row} />
                      <ReturnTrackingDetail row={row} />
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RefundAmount value={row.expected_refund_amount} fallback={estimatedRefund(row)} />
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RefundAmount value={row.actual_refund_amount} />
                    </td>
                    <td className="px-2 py-2">
                      <div className="break-all">{row.return_tracking_number || row.replacement_tracking_number || row.tracking_number || "--"}</div>
                      <div className="text-xs text-slate-500">
                        {formatDate(row.problem_return_tracking_delivered_at || row.problem_replacement_estimated_delivery_date || row.estimated_delivery_date)}
                      </div>
                      {row.problem_return_tracking_status && (
                        <div className="text-xs text-slate-500">
                          Return {titleCase(row.problem_return_tracking_status)}
                        </div>
                      )}
                      {row.problem_replacement_carrier_status && (
                        <div className="text-xs text-slate-500">
                          {titleCase(row.problem_replacement_carrier_status)}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <button
                        onClick={() => onSelectRow(row)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-300 bg-white text-slate-700 shadow-sm hover:bg-slate-100"
                        title="Open details"
                        type="button"
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
    </div>
  );
}

function NextActionDetail({ row }: { row: PurchaseRow }) {
  if (row.workflow_state === "refund_pending") {
    return null;
  }

  const escalationDate = formatDate(row.problem_escalation_available_at);
  if (escalationDate) {
    return (
      <div className="mt-1 text-xs font-medium text-amber-700">
        Escalate available {escalationDate}
      </div>
    );
  }

  return null;
}

function ReturnTrackingDetail({ row }: { row: PurchaseRow }) {
  if (!row.return_tracking_number) return null;
  const status = row.problem_return_tracking_status ? titleCase(row.problem_return_tracking_status) : "Tracking";
  const delivered = formatDate(row.problem_return_tracking_delivered_at);
  const label = delivered ? `Return delivered ${delivered}` : `Return ${status}`;
  const content = row.problem_return_tracking_url ? (
    <a href={row.problem_return_tracking_url} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
      {label}
    </a>
  ) : (
    label
  );
  return <div className="mt-1 text-xs text-slate-500">{content}</div>;
}

function problemDetailLabel(row: PurchaseRow) {
  if (row.ebay_current_type === "ORDER_CANCELLATION" || row.problem_source === "ebay_cancellation_sync") {
    return "Cancellation Details";
  }
  if (row.ebay_return_id) {
    return "Return Details";
  }
  if (row.ebay_inquiry_id) {
    return "Inquiry Details";
  }
  if (row.ebay_case_id) {
    return "eBay Case Details";
  }
  return "Episode Details";
}

type ProblemStats = {
  total: number;
  urgent: number;
  refundPending: number;
  returnsOpen: number;
  missingItems: number;
  candidates: number;
  noEbayLink: number;
};

function getProblemStats(rows: PurchaseRow[]): ProblemStats {
  return rows.reduce<ProblemStats>(
    (stats, row) => {
      const workflowState = row.workflow_state || "";
      const problemType = row.problem_type || "";
      const problemSource = row.problem_source || "";
      const needsEbayLink = new Set([
        "return_opened",
        "refund_pending",
        "label_pending",
        "label_received",
        "return_shipped",
        "seller_received_return",
        "replacement_pending",
        "replacement_shipped",
        "escalation_available",
        "escalated",
      ]).has(workflowState);
      const hasEbayLink = Boolean(row.ebay_action_url || row.ebay_return_id || row.ebay_inquiry_id || row.ebay_case_id);

      stats.total += 1;
      if (row.problem_needs_response || row.problem_priority === "high" || workflowState === "seller_message_needs_response") {
        stats.urgent += 1;
      }
      if (workflowState === "refund_pending") {
        stats.refundPending += 1;
      }
      if (workflowState === "return_opened" || problemSource === "ebay_return_sync") {
        stats.returnsOpen += 1;
      }
      if (problemType === "missing_items" || workflowState === "replacement_pending" || workflowState === "replacement_shipped") {
        stats.missingItems += 1;
      }
      if (workflowState === "candidate") {
        stats.candidates += 1;
      }
      if (needsEbayLink && !hasEbayLink) {
        stats.noEbayLink += 1;
      }

      return stats;
    },
    {
      total: 0,
      urgent: 0,
      refundPending: 0,
      returnsOpen: 0,
      missingItems: 0,
      candidates: 0,
      noEbayLink: 0,
    },
  );
}

function ProblemStat({
  label,
  value,
  tone = "blue",
}: {
  label: string;
  value: number;
  tone?: "amber" | "blue" | "red" | "slate";
}) {
  const toneClasses =
    tone === "red"
      ? "border-red-200 bg-red-50 text-red-700"
      : tone === "amber"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : tone === "slate"
          ? "border-slate-200 bg-white text-slate-700"
          : "border-blue-200 bg-blue-50 text-blue-700";

  return (
    <div className={`rounded-md border px-2.5 py-2 ${toneClasses}`}>
      <div className="text-[11px] font-medium uppercase tracking-wide">{label}</div>
      <div className="mt-0.5 text-lg font-semibold leading-none">{value.toLocaleString("en-US")}</div>
    </div>
  );
}

function PriorityBadge({
  value,
  needsResponse,
}: {
  value?: string | null;
  needsResponse?: boolean | null;
}) {
  if (needsResponse) {
    return <span className="rounded bg-red-100 px-2 py-1 text-xs font-semibold text-red-700">Urgent</span>;
  }

  const label = value ? titleCase(value) : "Normal";
  const className =
    value === "high"
      ? "bg-orange-100 text-orange-700"
      : value === "low"
        ? "bg-slate-100 text-slate-600"
        : "bg-blue-100 text-blue-700";

  return <span className={`rounded px-2 py-1 text-xs font-semibold ${className}`}>{label}</span>;
}

function workflowStateLabel(value?: string | null) {
  const labels: Record<string, string> = {
    candidate: "Candidate",
    return_needed: "Return Needed",
    return_opened: "Return Opened",
    seller_message_needs_response: "Needs Response",
    waiting_on_seller: "Waiting on Seller",
    partial_refund_offered: "Partial Refund Offered",
    partial_refund_accepted: "Partial Refund Accepted",
    label_pending: "Waiting for Label",
    label_received: "Ready to Ship Back",
    return_shipped: "Return Shipped",
    seller_received_return: "Seller Received",
    refund_pending: "Refund Pending",
    replacement_pending: "Replacement Pending",
    replacement_shipped: "Replacement Shipped",
    replacement_received: "Missing Item Received",
    escalation_available: "Escalation Available",
    escalated: "Escalated",
    resolved_refunded: "Resolved Refunded",
    resolved_received_item: "Resolved Item Received",
    closed_no_action: "Closed",
    closed_no_refund: "Closed No Refund",
  };
  return labels[value || ""] || titleCase(value || "Unknown");
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

function sourceLabel(value?: string | null) {
  const labels: Record<string, string> = {
    derived_order_problem: "System candidate",
    receiving_return_pending: "Receiving",
    manual: "MBOP",
    ebay_return_sync: "eBay return",
    ebay_inquiry_sync: "eBay inquiry",
    ebay_cancellation_sync: "eBay cancellation",
  };
  return labels[value || ""] || titleCase(value || "");
}

function episodeLabel(row: PurchaseRow) {
  const sequence = row.problem_episode_sequence ? `Episode ${row.problem_episode_sequence}` : "Episode";
  const kind = episodeKindLabel(row.problem_episode_kind);
  return kind ? `${sequence} - ${kind}` : sequence;
}

function episodeKindLabel(value?: string | null) {
  const labels: Record<string, string> = {
    delivery_delay: "Delivery Delay",
    carrier_stall: "Carrier Stall",
    carrier_exception: "Carrier Exception",
    item_not_received: "Item Not Received",
    replacement_tracking: "Replacement Tracking",
    damaged_item: "Damaged Item",
    incomplete_item: "Incomplete Item",
    cancelled_refund: "Cancelled Refund",
    return_request: "Return Request",
    refund_followup: "Refund Follow-Up",
  };
  return labels[value || ""] || (value ? titleCase(value) : "");
}

function artifactLabel(row: PurchaseRow) {
  const labels: Record<string, string> = {
    derived_candidate: "MBOP episode",
    ebay_inquiry: "eBay inquiry case",
    ebay_return: "eBay return case",
    ebay_case: "eBay case",
    receiving_exception: "Receiving episode",
    manual: "Manual episode",
  };
  return labels[row.problem_source_artifact_type || ""] || sourceLabel(row.problem_source);
}

function artifactBadgeClass(row: PurchaseRow) {
  const source = row.problem_source_artifact_type || "";
  if (source === "ebay_return" || source === "ebay_inquiry" || source === "ebay_case") {
    return "border-blue-200 bg-blue-50 text-blue-800";
  }
  if (source === "derived_candidate") {
    return "border-slate-200 bg-slate-50 text-slate-700";
  }
  if (source === "receiving_exception") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  return "border-slate-200 bg-white text-slate-600";
}

function RefundAmount({
  value,
  fallback,
}: {
  value?: number | null;
  fallback?: number | null;
}) {
  const formatted = formatMoney(value);
  if (formatted) return <span>{formatted}</span>;

  const fallbackFormatted = formatMoney(fallback);
  if (fallbackFormatted) {
    return <span className="text-slate-500">~{fallbackFormatted}</span>;
  }

  return <span className="text-slate-400">--</span>;
}

function estimatedRefund(row: PurchaseRow) {
  if (row.workflow_state === "candidate") return null;
  const unitCost = Number(row.unit_cost);
  const quantity = Number(row.quantity ?? 1);
  if (!Number.isFinite(unitCost) || unitCost <= 0) return null;
  if (!Number.isFinite(quantity) || quantity <= 0) return unitCost;
  return unitCost * quantity;
}

function problemStatusDate(row: PurchaseRow) {
  const datesByState: Record<string, string | null | undefined> = {
    candidate: row.problem_first_detected_at,
    return_needed: row.problem_return_needed_at,
    return_opened: row.problem_ebay_return_opened_at,
    seller_message_needs_response: row.problem_seller_message_last_at,
    waiting_on_seller: row.problem_operator_responded_at,
    partial_refund_offered: row.problem_partial_refund_offered_at,
    partial_refund_accepted: row.problem_partial_refund_accepted_at,
    label_pending: row.problem_last_detected_at,
    label_received: row.problem_label_available_at,
    return_shipped: row.problem_return_shipped_at || row.problem_replacement_shipped_at,
    seller_received_return: row.problem_seller_received_return_at,
    refund_pending: row.problem_refund_due_at,
    replacement_pending: row.problem_replacement_promised_at,
    replacement_shipped: row.problem_replacement_shipped_at,
    replacement_received: row.problem_replacement_received_at,
    escalation_available: row.problem_escalation_available_at,
    escalated: row.problem_escalated_at,
    resolved_refunded: row.problem_refund_received_at || row.problem_closed_at,
    resolved_received_item: row.problem_replacement_received_at || row.problem_closed_at,
    closed_no_action: row.problem_closed_at,
    closed_no_refund: row.problem_closed_at,
  };

  return datesByState[row.workflow_state || ""] || row.problem_last_detected_at || row.problem_first_detected_at;
}

function statusDateDetail(row: PurchaseRow) {
  const workflowState = row.workflow_state || "";
  const labels: Record<string, string> = {
    candidate: "Detected",
    return_needed: "Return needed",
    return_opened: "Opened",
    seller_message_needs_response: "Seller message",
    waiting_on_seller: "Waiting since",
    partial_refund_offered: "Offered",
    partial_refund_accepted: "Accepted",
    label_pending: "Waiting since",
    label_received: "Label provided",
    return_shipped: "Shipped",
    seller_received_return: "Delivered to seller",
    refund_pending: "Refund issued",
    replacement_pending: "Replacement promised",
    replacement_shipped: "Replacement shipped",
    replacement_received: "Replacement received",
    escalation_available: "Available",
    escalated: "Escalated",
    resolved_refunded: "Refund confirmed",
    resolved_received_item: "Received",
    closed_no_action: "Closed",
    closed_no_refund: "Closed",
  };
  const date = statusEnteredDate(row);
  const label = labels[workflowState] || "Updated";
  return date ? `${label} ${formatPacificDate(date)}` : sourceLabel(row.problem_source);
}

function statusEnteredDate(row: PurchaseRow) {
  const datesByState: Record<string, string | null | undefined> = {
    candidate: row.problem_first_detected_at,
    return_needed: row.problem_return_needed_at,
    return_opened: row.problem_ebay_return_opened_at,
    seller_message_needs_response: row.problem_seller_message_last_at,
    waiting_on_seller: row.problem_operator_responded_at || row.problem_last_detected_at,
    partial_refund_offered: row.problem_partial_refund_offered_at,
    partial_refund_accepted: row.problem_partial_refund_accepted_at,
    label_pending: row.problem_last_detected_at,
    label_received: row.problem_label_available_at || row.problem_return_label_printed_at,
    return_shipped: row.problem_return_shipped_at || row.problem_replacement_shipped_at,
    seller_received_return: row.problem_return_tracking_delivered_at || row.problem_seller_received_return_at,
    refund_pending: row.problem_refund_due_at,
    replacement_pending: row.problem_replacement_promised_at,
    replacement_shipped: row.problem_replacement_shipped_at,
    replacement_received: row.problem_replacement_received_at,
    escalation_available: row.problem_escalation_available_at,
    escalated: row.problem_escalated_at,
    resolved_refunded: row.problem_refund_received_at || row.problem_closed_at,
    resolved_received_item: row.problem_replacement_received_at || row.problem_closed_at,
    closed_no_action: row.problem_closed_at,
    closed_no_refund: row.problem_closed_at,
  };
  return datesByState[row.workflow_state || ""] || row.problem_last_detected_at || row.problem_first_detected_at;
}

function ageDays(value?: string | null) {
  const date = parseDate(value);
  if (!date) return null;
  const now = new Date();
  return Math.floor((now.getTime() - date.getTime()) / 86_400_000);
}

function parseDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function formatAge(value: number | null) {
  return value === null ? "--" : `${value.toLocaleString("en-US")}d old`;
}

function formatPacificDate(value?: string | null) {
  if (!value) return "";

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatDate(value);
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    month: "2-digit",
    day: "2-digit",
    year: "2-digit",
  }).formatToParts(date);
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  const year = parts.find((part) => part.type === "year")?.value ?? "";
  return month && day && year ? `${month}/${day}/${year}` : "";
}

function titleCase(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
