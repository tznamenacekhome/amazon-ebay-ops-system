import { createServerSupabaseClient } from "../../_server";

const CUSTOMER_RETURN_SELECT =
  "amazon_fba_customer_return_row_id,amazon_report_run_id,source_row_number,marketplace_id," +
  "amazon_order_id,merchant_order_id,return_date,seller_sku,sku,fnsku,asin,product_name,title," +
  "quantity,fulfillment_center_id,detailed_disposition,reason,status,license_plate_number," +
  "customer_comments,raw_row_json,imported_at,updated_at";

const REIMBURSEMENT_SELECT =
  "amazon_fba_reimbursement_row_id,amazon_report_run_id,source_row_number,marketplace_id," +
  "approval_date,reimbursement_id,case_id,amazon_order_id,reason,seller_sku,sku,fnsku,asin," +
  "product_name,title,quantity_reimbursed,amount_total,amount_per_unit,currency,raw_row_json," +
  "imported_at,updated_at";

const CASE_SELECT =
  "amazon_return_recovery_case_id,case_source,workflow_state,decision,reimbursement_review_status," +
  "reimbursement_likelihood,return_reason,return_status,return_disposition,customer_comments," +
  "evidence_summary,lpn,amazon_order_id,merchant_order_id,removal_order_id,removal_shipment_id," +
  "vret_id,ra_number,tracking_number,asin,seller_sku,sku,fnsku,title,quantity,return_date," +
  "raw_evidence_json,created_at,updated_at";

type ServerSupabaseClient = ReturnType<typeof createServerSupabaseClient>;

export type CustomerReturnRow = {
  amazon_fba_customer_return_row_id: string;
  amazon_report_run_id: string | null;
  source_row_number: number | null;
  marketplace_id: string | null;
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
  imported_at: string | null;
  updated_at: string | null;
};

export type ReimbursementRow = {
  amazon_fba_reimbursement_row_id: string;
  amazon_report_run_id: string | null;
  source_row_number: number | null;
  marketplace_id: string | null;
  approval_date: string | null;
  reimbursement_id: string | null;
  case_id: string | null;
  amazon_order_id: string | null;
  reason: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  asin: string | null;
  product_name: string | null;
  title: string | null;
  quantity_reimbursed: number | null;
  amount_total: number | null;
  amount_per_unit: number | null;
  currency: string | null;
  raw_row_json: unknown;
  imported_at: string | null;
  updated_at: string | null;
};

export type ReturnRecoveryCaseRow = {
  amazon_return_recovery_case_id: string;
  case_source: string;
  workflow_state: string;
  decision: string;
  reimbursement_review_status: string;
  reimbursement_likelihood: string;
  return_reason: string | null;
  return_status: string | null;
  return_disposition: string | null;
  customer_comments: string | null;
  evidence_summary: string | null;
  lpn: string | null;
  amazon_order_id: string | null;
  merchant_order_id: string | null;
  removal_order_id: string | null;
  removal_shipment_id: string | null;
  vret_id: string | null;
  ra_number: string | null;
  tracking_number: string | null;
  asin: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  title: string | null;
  quantity: number | null;
  return_date: string | null;
  raw_evidence_json: unknown;
  created_at: string | null;
  updated_at: string | null;
};

export type ReturnRecoveryEventRow = {
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

export type QueueRow = {
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

export function getReturnRecoverySupabaseClient() {
  return createServerSupabaseClient();
}

export async function fetchCustomerReturnRows(supabase: ServerSupabaseClient) {
  const { data, error } = await supabase
    .from("amazon_fba_customer_return_rows")
    .select(CUSTOMER_RETURN_SELECT)
    .order("return_date", { ascending: false, nullsFirst: false })
    .order("imported_at", { ascending: false, nullsFirst: false })
    .limit(1000);

  if (error) throw new Error(`amazon_fba_customer_return_rows: ${error.message}`);
  return (data ?? []) as unknown as CustomerReturnRow[];
}

export async function fetchCustomerReturnRow(supabase: ServerSupabaseClient, id: string) {
  const { data, error } = await supabase
    .from("amazon_fba_customer_return_rows")
    .select(CUSTOMER_RETURN_SELECT)
    .eq("amazon_fba_customer_return_row_id", id)
    .maybeSingle();

  if (error) throw new Error(`amazon_fba_customer_return_rows: ${error.message}`);
  return data as unknown as CustomerReturnRow | null;
}

export async function fetchRecentReimbursementRows(supabase: ServerSupabaseClient) {
  const { data, error } = await supabase
    .from("amazon_fba_reimbursement_rows")
    .select(REIMBURSEMENT_SELECT)
    .order("approval_date", { ascending: false, nullsFirst: false })
    .order("imported_at", { ascending: false, nullsFirst: false })
    .limit(1000);

  if (error) throw new Error(`amazon_fba_reimbursement_rows: ${error.message}`);
  return (data ?? []) as unknown as ReimbursementRow[];
}

export async function fetchCasesAndEventsForReturn(
  supabase: ServerSupabaseClient,
  row: CustomerReturnRow,
) {
  const casesById = new Map<string, ReturnRecoveryCaseRow>();
  const amazonOrderId = cleanText(row.amazon_order_id);
  const lpn = cleanText(row.license_plate_number);

  for (const query of [
    amazonOrderId ? { column: "amazon_order_id", value: amazonOrderId } : null,
    lpn ? { column: "lpn", value: lpn } : null,
  ]) {
    if (!query) continue;
    const { data, error } = await supabase
      .from("amazon_return_recovery_cases")
      .select(CASE_SELECT)
      .eq(query.column, query.value)
      .limit(25);

    if (error) throw new Error(`amazon_return_recovery_cases: ${error.message}`);
    for (const caseRow of (data ?? []) as unknown as ReturnRecoveryCaseRow[]) {
      casesById.set(caseRow.amazon_return_recovery_case_id, caseRow);
    }
  }

  const cases = Array.from(casesById.values());
  const caseIds = cases.map((caseRow) => caseRow.amazon_return_recovery_case_id);
  if (!caseIds.length) return { cases, events: [] as ReturnRecoveryEventRow[] };

  const { data, error } = await supabase
    .from("amazon_return_recovery_events")
    .select(
      "amazon_return_recovery_event_id,amazon_return_recovery_case_id,event_type,event_source," +
        "event_at,message,notes,raw_event_json,created_at",
    )
    .in("amazon_return_recovery_case_id", caseIds)
    .order("event_at", { ascending: false });

  if (error) throw new Error(`amazon_return_recovery_events: ${error.message}`);
  return { cases, events: (data ?? []) as unknown as ReturnRecoveryEventRow[] };
}

export function buildQueueRow(
  row: CustomerReturnRow,
  reimbursements: ReimbursementRow[],
): QueueRow {
  const evidence = matchReimbursements(row, reimbursements);
  const amountTotal = evidence.reduce((total, reimbursement) => {
    const amount = toOptionalNumber(reimbursement.amount_total);
    return amount === null ? total : total + amount;
  }, 0);
  const currency =
    evidence.find((reimbursement) => cleanText(reimbursement.currency))?.currency ?? null;

  return {
    id: row.amazon_fba_customer_return_row_id,
    return_date: dateOnly(row.return_date),
    title: cleanText(row.title) ?? cleanText(row.product_name) ?? "(Untitled Amazon return)",
    asin: normalizeIdentifier(row.asin),
    seller_sku: cleanText(row.seller_sku),
    sku: cleanText(row.sku),
    fnsku: cleanText(row.fnsku),
    lpn: cleanText(row.license_plate_number),
    return_reason: cleanText(row.reason),
    return_disposition: cleanText(row.detailed_disposition),
    return_status: cleanText(row.status),
    customer_comments: cleanText(row.customer_comments),
    amazon_order_id: cleanText(row.amazon_order_id),
    merchant_order_id: cleanText(row.merchant_order_id),
    quantity: toOptionalNumber(row.quantity),
    reimbursement_status: evidence.length ? "Evidence found" : "No linked evidence",
    reimbursement_count: evidence.length,
    reimbursement_amount_total: evidence.length ? roundMoney(amountTotal) : null,
    reimbursement_currency: currency,
    latest_reimbursement_approval_date:
      evidence.map((item) => dateOnly(item.approval_date)).filter(Boolean).sort().reverse()[0] ??
      null,
  };
}

export function matchReimbursements(
  row: CustomerReturnRow,
  reimbursements: ReimbursementRow[],
) {
  const orderId = normalizeIdentifier(row.amazon_order_id);
  if (!orderId) return [];

  return reimbursements.filter((reimbursement) => {
    if (normalizeIdentifier(reimbursement.amazon_order_id) !== orderId) return false;

    const returnIdentifiers = productIdentifiers(row);
    const reimbursementIdentifiers = productIdentifiers(reimbursement);
    if (!returnIdentifiers.length || !reimbursementIdentifiers.length) return true;

    return returnIdentifiers.some((identifier) => reimbursementIdentifiers.includes(identifier));
  });
}

export function queueRowMatchesSearch(row: QueueRow, query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;

  return [
    row.lpn,
    row.amazon_order_id,
    row.asin,
    row.seller_sku,
    row.sku,
    row.fnsku,
    row.title,
    row.return_reason,
    row.return_disposition,
    row.return_status,
    row.customer_comments,
  ].some((value) => cleanText(value)?.toLowerCase().includes(needle));
}

export function summarizeQueue(rows: QueueRow[], allRows: QueueRow[]) {
  return {
    total_customer_returns: allRows.length,
    filtered_customer_returns: rows.length,
    with_reimbursement_evidence: rows.filter((row) => row.reimbursement_count > 0).length,
    without_reimbursement_evidence: rows.filter((row) => row.reimbursement_count === 0).length,
    with_customer_comments: rows.filter((row) => Boolean(cleanText(row.customer_comments))).length,
  };
}

function productIdentifiers(row: {
  seller_sku?: string | null;
  sku?: string | null;
  fnsku?: string | null;
  asin?: string | null;
}) {
  return Array.from(
    new Set(
      [row.seller_sku, row.sku, row.fnsku, row.asin]
        .map((value) => normalizeIdentifier(value))
        .filter((value): value is string => Boolean(value)),
    ),
  );
}

function cleanText(value: unknown) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function normalizeIdentifier(value: unknown) {
  return cleanText(value)?.toUpperCase() ?? null;
}

function toOptionalNumber(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function dateOnly(value?: string | null) {
  if (!value) return null;
  const match = value.match(/^\d{4}-\d{2}-\d{2}/);
  return match?.[0] ?? null;
}
