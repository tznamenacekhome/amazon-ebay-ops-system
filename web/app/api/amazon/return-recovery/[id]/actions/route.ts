import { NextResponse } from "next/server";
import { requireAdminApiToken } from "../../../../_server";
import {
  fetchCasesAndEventsForReturn,
  fetchCustomerReturnRow,
  findBestCase,
  getReturnRecoverySupabaseClient,
  inspectionFromCase,
  type CustomerReturnRow,
  type ReturnRecoveryCaseRow,
} from "../../data";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

type ActionBody = {
  action?: string;
  observed_condition?: string | null;
  notes?: string | null;
  decision?: string | null;
};

const DECISIONS = new Set([
  "needs_review",
  "send_back_to_amazon",
  "sell_on_ebay",
  "dispose_donate",
]);

const OBSERVED_CONDITIONS = new Set([
  "not_recorded",
  "new",
  "used",
  "damaged",
  "missing_parts",
  "wrong_item",
]);

export async function POST(request: Request, context: RouteContext) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const { id } = await context.params;
  const body = (await request.json().catch(() => ({}))) as ActionBody;
  const action = cleanText(body.action) ?? "record_inspection";

  if (!["record_inspection", "open_case_review"].includes(action)) {
    return NextResponse.json({ error: `Unsupported action: ${action}` }, { status: 400 });
  }

  try {
    const supabase = getReturnRecoverySupabaseClient();
    const customerReturn = await fetchCustomerReturnRow(supabase, id);
    if (!customerReturn) {
      return NextResponse.json({ error: "Amazon customer return row not found." }, { status: 404 });
    }

    const caseData = await fetchCasesAndEventsForReturn(supabase, customerReturn);
    const existingCase = findBestCase(customerReturn, caseData.cases);
    const recoveryCase = existingCase ?? await createRecoveryCase(supabase, customerReturn);
    const previousInspection = inspectionFromCase(recoveryCase);
    const previousDecision = recoveryCase.decision;
    const previousWorkflowState = recoveryCase.workflow_state;
    const now = new Date().toISOString();
    const inspection = {
      ...previousInspection,
      observed_condition: cleanObservedCondition(body.observed_condition ?? previousInspection.observed_condition),
      notes: cleanText(body.notes),
      inspected_at: now,
      updated_at: now,
    };
    const decision = cleanDecision(body.decision);
    const workflowState =
      action === "open_case_review" ? "reimbursement_review" : workflowStateForDecision(decision);
    const rawEvidence = mergeRawEvidence(recoveryCase.raw_evidence_json, {
      customer_return_row_id: customerReturn.amazon_fba_customer_return_row_id,
      inspection,
    });

    const { data, error } = await supabase
      .from("amazon_return_recovery_cases")
      .update({
        workflow_state: workflowState,
        decision,
        evidence_summary: evidenceSummary(inspection, decision),
        raw_evidence_json: rawEvidence,
        inspected_at: now,
        updated_at: now,
      })
      .eq("amazon_return_recovery_case_id", recoveryCase.amazon_return_recovery_case_id)
      .select("*")
      .limit(1);
    if (error) throw new Error(`amazon_return_recovery_cases update: ${error.message}`);
    const updatedCase = ((data ?? [])[0] ?? null) as ReturnRecoveryCaseRow | null;

    await appendEvent(supabase, recoveryCase.amazon_return_recovery_case_id, {
      event_type: "inspection_recorded",
      message: "Operator recorded Amazon return inspection.",
      notes: inspection.notes,
      raw_event_json: {
        action,
        inspection,
        previous_inspection: previousInspection,
      },
    });

    if (action === "open_case_review") {
      await appendEvent(supabase, recoveryCase.amazon_return_recovery_case_id, {
        event_type: "case_review_opened",
        message: "Operator opened manual Seller Central case review workflow.",
        notes: inspection.notes,
        raw_event_json: {
          action,
          previous_workflow_state: previousWorkflowState,
          workflow_state: workflowState,
          observed_condition: inspection.observed_condition,
        },
      });
    }

    if (previousDecision !== decision) {
      await appendEvent(supabase, recoveryCase.amazon_return_recovery_case_id, {
        event_type: "disposition_changed",
        message: `Disposition changed from ${formatStatus(previousDecision)} to ${formatStatus(decision)}.`,
        notes: inspection.notes,
        raw_event_json: {
          action,
          previous_decision: previousDecision,
          decision,
          workflow_state: workflowState,
        },
      });
    }

    const refreshed = updatedCase ?? recoveryCase;
    return NextResponse.json({
      case: refreshed,
      inspection: inspectionFromCase(refreshed),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Amazon return action failed." },
      { status: 500 },
    );
  }
}

async function createRecoveryCase(
  supabase: ReturnType<typeof getReturnRecoverySupabaseClient>,
  row: CustomerReturnRow,
) {
  const payload = {
    case_source: "amazon_customer_return_report",
    workflow_state: "needs_inspection",
    decision: "needs_review",
    return_reason: cleanText(row.reason),
    return_status: cleanText(row.status),
    return_disposition: cleanText(row.detailed_disposition),
    customer_comments: cleanText(row.customer_comments),
    evidence_summary: "Seeded from Amazon customer return report.",
    lpn: cleanText(row.license_plate_number),
    amazon_order_id: cleanText(row.amazon_order_id),
    merchant_order_id: cleanText(row.merchant_order_id),
    asin: cleanText(row.asin),
    seller_sku: cleanText(row.seller_sku),
    sku: cleanText(row.sku),
    fnsku: cleanText(row.fnsku),
    title: cleanText(row.title) ?? cleanText(row.product_name),
    quantity: Math.max(1, Number(row.quantity ?? 1) || 1),
    fulfillment_center_id: cleanText(row.fulfillment_center_id),
    return_date: row.return_date,
    raw_evidence_json: {
      customer_return_row_id: row.amazon_fba_customer_return_row_id,
      customer_return_raw_row: row.raw_row_json,
    },
  };
  const { data, error } = await supabase
    .from("amazon_return_recovery_cases")
    .insert(payload)
    .select("*")
    .limit(1);
  if (error) throw new Error(`amazon_return_recovery_cases insert: ${error.message}`);
  const recoveryCase = ((data ?? [])[0] ?? null) as ReturnRecoveryCaseRow | null;
  if (!recoveryCase) throw new Error("Amazon return recovery case insert returned no row.");

  await appendEvent(supabase, recoveryCase.amazon_return_recovery_case_id, {
    event_type: "case_created",
    message: "Amazon return recovery case created from customer return row.",
    notes: null,
    raw_event_json: {
      customer_return_row_id: row.amazon_fba_customer_return_row_id,
      amazon_order_id: row.amazon_order_id,
      lpn: row.license_plate_number,
    },
  });

  return recoveryCase;
}

async function appendEvent(
  supabase: ReturnType<typeof getReturnRecoverySupabaseClient>,
  caseId: string,
  row: {
    event_type: string;
    message: string;
    notes: string | null;
    raw_event_json: unknown;
  },
) {
  const { error } = await supabase
    .from("amazon_return_recovery_events")
    .insert({
      amazon_return_recovery_case_id: caseId,
      event_type: row.event_type,
      event_source: "operator",
      message: row.message,
      notes: row.notes,
      raw_event_json: row.raw_event_json,
    });
  if (error) throw new Error(`amazon_return_recovery_events insert: ${error.message}`);
}

function cleanDecision(value: unknown) {
  const decision = cleanText(value) ?? "needs_review";
  if (!DECISIONS.has(decision)) throw new Error("Unsupported disposition decision.");
  return decision;
}

function cleanObservedCondition(value: unknown) {
  const condition = normalizeObservedCondition(value);
  if (!OBSERVED_CONDITIONS.has(condition)) throw new Error("Unsupported observed condition.");
  return condition;
}

function workflowStateForDecision(decision: string) {
  switch (decision) {
    case "send_back_to_amazon":
      return "ready_to_send_back_to_amazon";
    case "sell_on_ebay":
      return "ready_for_ebay_listing";
    case "dispose_donate":
      return "disposed_donated";
    case "needs_review":
    default:
      return "decision_needed";
  }
}

function evidenceSummary(
  inspection: {
    observed_condition: string | null;
  },
  decision: string,
) {
  return [
    `Decision: ${formatStatus(decision)}`,
    inspection.observed_condition ? `condition=${formatStatus(inspection.observed_condition)}` : null,
  ].filter(Boolean).join("; ");
}

function mergeRawEvidence(existing: unknown, patch: Record<string, unknown>) {
  const base =
    existing && typeof existing === "object" && !Array.isArray(existing)
      ? existing as Record<string, unknown>
      : {};
  return { ...base, ...patch };
}

function cleanText(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function normalizeObservedCondition(value: unknown) {
  const text = cleanText(value)?.toLowerCase().replace(/[\s-]+/g, "_") ?? "not_recorded";
  if (["", "not_recorded", "unknown"].includes(text)) return "not_recorded";
  if (["new_sealed", "sealed_new", "new_opened", "opened_new", "used_like_new", "used_good"].includes(text)) {
    return text.startsWith("new") || text.endsWith("_new") ? "new" : "used";
  }
  return text;
}

function formatStatus(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
