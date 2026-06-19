import { NextResponse } from "next/server";
import { createServerSupabaseClient, requireAdminApiToken } from "../../../_server";

const supabase = createServerSupabaseClient();

type RouteContext = {
  params: Promise<{ id: string }>;
};

type ActionBody = {
  action?: string;
  notes?: string;
  amount?: number | string | null;
  tracking_number?: string | null;
  problem_type?: string | null;
};

type ProblemCase = {
  problem_case_id: string;
  purchase_item_id: string;
  problem_type: string;
  workflow_state: string;
  notes: string | null;
};

export async function POST(request: Request, context: RouteContext) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const { id } = await context.params;
  const body = (await request.json().catch(() => ({}))) as ActionBody;
  const action = String(body.action || "").trim();

  if (!action) {
    return NextResponse.json({ error: "Action is required." }, { status: 400 });
  }

  try {
    const problemCase = await fetchProblemCase(id);
    if (!problemCase) {
      return NextResponse.json({ error: "Order problem episode not found." }, { status: 404 });
    }

    const result = actionUpdate(action, body, problemCase);
    const now = new Date().toISOString();
    const updates = {
      ...result.caseUpdates,
      updated_at: now,
    };

    const { data, error } = await supabase
      .from("order_problem_cases")
      .update(updates)
      .eq("problem_case_id", id)
      .select("*")
      .limit(1);
    if (error) throw new Error(`order_problem_cases update: ${error.message}`);

    if (result.purchaseStatus) {
      const { error: itemError } = await supabase
        .from("purchase_items")
        .update({ current_status: result.purchaseStatus })
        .eq("item_id", problemCase.purchase_item_id);
      if (itemError) throw new Error(`purchase_items update: ${itemError.message}`);
    }

    const eventRow = {
      problem_case_id: id,
      event_type: action,
      event_source: "operator",
      message: result.message,
      amount: result.amount,
      currency: result.amount === null ? null : "USD",
      tracking_number: result.trackingNumber,
      raw_json: body,
    };
    const { data: eventData, error: eventError } = await supabase
      .from("order_problem_events")
      .insert(eventRow)
      .select("problem_event_id,event_type,event_source,event_at,message,amount,currency,tracking_number,created_at")
      .limit(1);
    if (eventError) throw new Error(`order_problem_events insert: ${eventError.message}`);

    return NextResponse.json({ case: (data ?? [])[0] ?? null, event: (eventData ?? [])[0] ?? null });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Order problem action failed." },
      { status: 500 },
    );
  }
}

async function fetchProblemCase(id: string): Promise<ProblemCase | null> {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select("problem_case_id,purchase_item_id,problem_type,workflow_state,notes")
    .eq("problem_case_id", id)
    .limit(1);
  if (error) throw new Error(`order_problem_cases lookup: ${error.message}`);
  return ((data ?? [])[0] ?? null) as ProblemCase | null;
}

function actionUpdate(action: string, body: ActionBody, problemCase: ProblemCase) {
  const now = new Date().toISOString();
  const amount = parseAmount(body.amount);
  const trackingNumber = cleanText(body.tracking_number);
  const notes = appendNotes(problemCase.notes, body.notes);
  const base: Record<string, unknown> = {};
  if (notes !== problemCase.notes) base.notes = notes;

  switch (action) {
    case "update_problem_type": {
      const problemType = cleanProblemType(body.problem_type);
      return result({
        ...base,
        problem_type: problemType,
      }, null, `Updated episode type to ${problemType}.`, amount, trackingNumber);
    }
    case "mark_return_needed":
      return result({
        ...base,
        problem_type: "return_needed",
        workflow_state: "return_needed",
        return_needed_at: now,
        next_action: "Open or continue return/refund follow-up.",
        episode_kind: "return_request",
        opened_reason: "manual",
        source_artifact_type: "manual",
      }, "return_pending", "Marked return needed.", amount, trackingNumber);
    case "mark_return_opened":
      return result({
        ...base,
        workflow_state: "return_opened",
        ebay_return_opened_at: now,
        next_action: "Wait for seller response.",
        episode_kind: "return_request",
        opened_reason: "manual",
        source_artifact_type: "manual",
      }, "return_opened", "Marked return opened in eBay.", amount, trackingNumber);
    case "mark_seller_messaged":
      return result({
        ...base,
        workflow_state: "seller_message_needs_response",
        needs_response: true,
        seller_message_last_at: now,
        next_action: "Respond to seller in eBay.",
      }, null, "Marked seller message needing response.", amount, trackingNumber);
    case "mark_operator_responded":
      return result({
        ...base,
        workflow_state: "waiting_on_seller",
        needs_response: false,
        operator_responded_at: now,
        next_action: "Wait for seller response.",
      }, null, "Marked operator response completed in eBay.", amount, trackingNumber);
    case "mark_partial_refund_offered":
      return result({
        ...base,
        workflow_state: "partial_refund_offered",
        partial_refund_amount: amount,
        partial_refund_offered_at: now,
        next_action: "Review partial refund offer.",
      }, null, "Marked partial refund offered.", amount, trackingNumber);
    case "mark_partial_refund_accepted":
      return result({
        ...base,
        workflow_state: "partial_refund_accepted",
        partial_refund_amount: amount,
        partial_refund_accepted_at: now,
        next_action: "Confirm partial refund posts.",
      }, null, "Marked partial refund accepted.", amount, trackingNumber);
    case "mark_label_available":
      return result({
        ...base,
        workflow_state: "label_received",
        label_available_at: now,
        ...(trackingNumber ? { return_tracking_number: trackingNumber } : {}),
        next_action: "Ship item back to seller.",
      }, null, "Marked return label available.", amount, trackingNumber);
    case "mark_return_shipped":
      return result({
        ...base,
        workflow_state: "return_shipped",
        return_shipped_at: now,
        ...(trackingNumber ? { return_tracking_number: trackingNumber } : {}),
        next_action: "Wait for seller to receive return.",
      }, null, "Marked return shipped.", amount, trackingNumber);
    case "mark_seller_received_return":
      return result({
        ...base,
        workflow_state: "seller_received_return",
        seller_received_return_at: now,
        return_tracking_delivered_at: now,
        refund_due_at: now,
        next_action: "Wait for refund.",
      }, null, "Marked seller received return.", amount, trackingNumber);
    case "mark_refund_pending":
      return result({
        ...base,
        workflow_state: "refund_pending",
        refund_due_at: now,
        next_action: "Confirm refund received.",
      }, cancellationPurchaseStatus(problemCase), "Marked refund pending.", amount, trackingNumber);
    case "mark_refund_received":
      return result({
        ...base,
        workflow_state: "resolved_refunded",
        is_open: false,
        actual_refund_amount: amount,
        refund_received_at: now,
        closed_at: now,
        resolved_reason: "refund_received",
        next_action: null,
      }, cancellationPurchaseStatus(problemCase), "Marked refund received and resolved.", amount, trackingNumber);
    case "mark_missing_item_pending":
      return result({
        ...base,
        problem_type: "missing_items",
        workflow_state: "replacement_pending",
        replacement_promised_at: now,
        next_action: "Wait for missing/replacement item.",
        episode_kind: "item_not_received",
        opened_reason: "manual",
        source_artifact_type: "manual",
      }, null, "Marked missing item / replacement pending.", amount, trackingNumber);
    case "mark_replacement_shipped":
      return result({
        ...base,
        problem_type: "missing_items",
        workflow_state: "replacement_shipped",
        replacement_shipped_at: now,
        replacement_tracking_number: trackingNumber,
        next_action: "Monitor replacement tracking and confirm receipt.",
      }, null, "Marked replacement shipped.", amount, trackingNumber);
    case "mark_missing_item_received":
      return result({
        ...base,
        workflow_state: "resolved_received_item",
        is_open: false,
        replacement_received_at: now,
        closed_at: now,
        resolved_reason: "replacement_received",
        next_action: null,
      }, "delivered", "Marked missing item delivered and returned to receiving flow.", amount, trackingNumber);
    case "mark_escalation_available":
      return result({
        ...base,
        workflow_state: "escalation_available",
        escalation_available_at: now,
        next_action: "Escalate in eBay if seller has not resolved.",
      }, null, "Marked escalation available.", amount, trackingNumber);
    case "mark_escalated":
      return result({
        ...base,
        workflow_state: "escalated",
        escalated_at: now,
        next_action: "Wait for eBay case decision.",
      }, null, "Marked escalated in eBay.", amount, trackingNumber);
    case "close_no_refund":
      return result({
        ...base,
        workflow_state: "closed_no_refund",
        is_open: false,
        closed_at: now,
        resolved_reason: "no_refund",
        next_action: null,
      }, null, "Closed order problem episode with no refund.", amount, trackingNumber);
    case "close_resolve":
      return result({
        ...base,
        workflow_state: "closed_no_action",
        is_open: false,
        closed_at: now,
        resolved_reason: "operator_closed",
        next_action: null,
      }, null, "Closed order problem episode.", amount, trackingNumber);
    default:
      throw new Error(`Unsupported action: ${action}`);
  }
}

function cleanProblemType(value: unknown) {
  const text = cleanText(value);
  const allowed = new Set([
    "not_as_listed",
    "buyer_choice",
    "missing_items",
    "cancelled_refund_followup",
    "late_delivery_candidate",
    "carrier_exception_candidate",
    "stale_tracking_candidate",
    "return_needed",
  ]);
  if (!text || !allowed.has(text)) {
    throw new Error("Unsupported episode type.");
  }
  return text;
}

function result(
  caseUpdates: Record<string, unknown>,
  purchaseStatus: string | null,
  message: string,
  amount: number | null,
  trackingNumber: string | null,
) {
  return { caseUpdates, purchaseStatus, message, amount, trackingNumber };
}

function cancellationPurchaseStatus(problemCase: ProblemCase) {
  return problemCase.problem_type === "cancelled_refund_followup" ? "cancelled" : null;
}

function parseAmount(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function cleanText(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function appendNotes(existing: string | null, next: string | undefined) {
  const text = cleanText(next);
  if (!text) return existing;
  if (!existing) return text;
  return `${existing}\n${text}`;
}
