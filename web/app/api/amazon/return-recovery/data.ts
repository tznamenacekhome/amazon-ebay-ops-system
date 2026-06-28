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
  "received_at,inspected_at,closed_at,raw_evidence_json,created_at,updated_at";

const SALES_ORDER_SELECT =
  "amazon_order_id,purchase_date,order_status,fulfillment_channel,order_total_amount,order_total_currency";

const SALES_ORDER_ITEM_SELECT =
  "amazon_order_item_id,amazon_order_id,asin,seller_sku,title,quantity_ordered,quantity_shipped," +
  "item_price_amount,item_price_currency";

const SALES_PROFITABILITY_SELECT =
  "amazon_order_id,amazon_order_item_id,asin,seller_sku,title,quantity,sale_price," +
  "amazon_fees_excluding_fulfillment,fulfillment_cost,fulfillment_cost_source,cogs,cogs_source," +
  "net_profit,roi,data_status,calculated_at";

const SALES_FINANCIAL_EVENT_SELECT =
  "amazon_order_id,amazon_order_item_id,event_type,posted_date,amount,currency,fee_type,charge_type";

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

export type SalesOrderRow = {
  amazon_order_id: string;
  purchase_date: string | null;
  order_status: string | null;
  fulfillment_channel: string | null;
  order_total_amount: number | null;
  order_total_currency: string | null;
};

export type SalesOrderItemRow = {
  amazon_order_item_id: string;
  amazon_order_id: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity_ordered: number | null;
  quantity_shipped: number | null;
  item_price_amount: number | null;
  item_price_currency: string | null;
};

export type SalesProfitabilityRow = {
  amazon_order_id: string;
  amazon_order_item_id: string;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity: number | null;
  sale_price: number | null;
  amazon_fees_excluding_fulfillment: number | null;
  fulfillment_cost: number | null;
  fulfillment_cost_source: string | null;
  cogs: number | null;
  cogs_source: string | null;
  net_profit: number | null;
  roi: number | null;
  data_status: string | null;
  calculated_at: string | null;
};

export type SalesFinancialEventRow = {
  amazon_order_id: string | null;
  amazon_order_item_id: string | null;
  event_type: string | null;
  posted_date: string | null;
  amount: number | null;
  currency: string | null;
  fee_type: string | null;
  charge_type: string | null;
};

export type SalesContext = {
  orders: SalesOrderRow[];
  items: SalesOrderItemRow[];
  profitability: SalesProfitabilityRow[];
  financialEvents: SalesFinancialEventRow[];
};

export type OriginalSaleFinancialImpact = {
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
  received_at: string | null;
  inspected_at: string | null;
  closed_at: string | null;
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
  original_sale: OriginalSaleFinancialImpact;
  case_id: string | null;
  workflow_state: string;
  decision: string;
  inspection: InspectionEvidence;
};

export type InspectionEvidence = {
  observed_condition: string | null;
  sealed_new_status: string | null;
  complete_item: "yes" | "no" | "unknown";
  wrong_item: "yes" | "no" | "unknown";
  notes: string | null;
  inspected_at: string | null;
  updated_at: string | null;
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

export async function fetchCasesForReturns(
  supabase: ServerSupabaseClient,
  rows: CustomerReturnRow[],
) {
  const casesById = new Map<string, ReturnRecoveryCaseRow>();
  const orderIds = uniqueClean(rows.map((row) => row.amazon_order_id));
  const lpns = uniqueClean(rows.map((row) => row.license_plate_number));

  for (const { column, values } of [
    { column: "amazon_order_id", values: orderIds },
    { column: "lpn", values: lpns },
  ]) {
    for (let index = 0; index < values.length; index += 100) {
      const chunk = values.slice(index, index + 100);
      const { data, error } = await supabase
        .from("amazon_return_recovery_cases")
        .select(CASE_SELECT)
        .in(column, chunk);
      if (error) throw new Error(`amazon_return_recovery_cases: ${error.message}`);
      for (const caseRow of (data ?? []) as unknown as ReturnRecoveryCaseRow[]) {
        casesById.set(caseRow.amazon_return_recovery_case_id, caseRow);
      }
    }
  }

  return Array.from(casesById.values());
}

export async function fetchSalesContextForReturns(
  supabase: ServerSupabaseClient,
  rows: CustomerReturnRow[],
): Promise<SalesContext> {
  const orderIds = Array.from(
    new Set(
      rows
        .map((row) => cleanText(row.amazon_order_id))
        .filter((value): value is string => Boolean(value)),
    ),
  );
  if (!orderIds.length) {
    return { orders: [], items: [], profitability: [], financialEvents: [] };
  }

  const [orders, items, profitability, financialEvents] = await Promise.all([
    fetchByOrderIds<SalesOrderRow>(supabase, "amazon_sales_orders", SALES_ORDER_SELECT, orderIds),
    fetchByOrderIds<SalesOrderItemRow>(
      supabase,
      "amazon_sales_order_items",
      SALES_ORDER_ITEM_SELECT,
      orderIds,
    ),
    fetchByOrderIds<SalesProfitabilityRow>(
      supabase,
      "amazon_sales_profitability",
      SALES_PROFITABILITY_SELECT,
      orderIds,
    ),
    fetchByOrderIds<SalesFinancialEventRow>(
      supabase,
      "amazon_sales_financial_events",
      SALES_FINANCIAL_EVENT_SELECT,
      orderIds,
    ),
  ]);

  return { orders, items, profitability, financialEvents };
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
  salesContext: SalesContext = emptySalesContext(),
  cases: ReturnRecoveryCaseRow[] = [],
): QueueRow {
  const evidence = matchReimbursements(row, reimbursements);
  const caseRow = findBestCase(row, cases);
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
    original_sale: buildOriginalSaleFinancialImpact(row, salesContext),
    case_id: caseRow?.amazon_return_recovery_case_id ?? null,
    workflow_state: caseRow?.workflow_state ?? "needs_inspection",
    decision: caseRow?.decision ?? "needs_review",
    inspection: inspectionFromCase(caseRow),
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

export function queueRowMatchesWorkflowFilter(row: QueueRow, filter: string) {
  switch (filter) {
    case "open":
      return !["closed", "disposed_donated"].includes(row.workflow_state);
    case "case_review":
      return row.workflow_state === "reimbursement_review";
    case "needs_review":
      return row.decision === "needs_review" || row.workflow_state === "decision_needed";
    case "send_back_to_amazon":
    case "sell_on_ebay":
    case "dispose_donate":
      return row.decision === filter;
    case "closed":
      return row.workflow_state === "closed";
    case "all":
    default:
      return true;
  }
}

export function summarizeQueue(rows: QueueRow[], allRows: QueueRow[]) {
  return {
    total_customer_returns: allRows.length,
    filtered_customer_returns: rows.length,
    with_reimbursement_evidence: rows.filter((row) => row.reimbursement_count > 0).length,
    without_reimbursement_evidence: rows.filter((row) => row.reimbursement_count === 0).length,
    with_customer_comments: rows.filter((row) => Boolean(cleanText(row.customer_comments))).length,
    needs_inspection: allRows.filter((row) => row.workflow_state === "needs_inspection").length,
    case_review: allRows.filter((row) => row.workflow_state === "reimbursement_review").length,
    needs_review: allRows.filter((row) => row.decision === "needs_review").length,
    send_back_to_amazon: allRows.filter((row) => row.decision === "send_back_to_amazon").length,
    sell_on_ebay: allRows.filter((row) => row.decision === "sell_on_ebay").length,
    dispose_donate: allRows.filter((row) => row.decision === "dispose_donate").length,
    closed: allRows.filter((row) => row.workflow_state === "closed").length,
  };
}

export function findBestCase(row: CustomerReturnRow, cases: ReturnRecoveryCaseRow[]) {
  const orderId = normalizeIdentifier(row.amazon_order_id);
  const lpn = normalizeIdentifier(row.license_plate_number);
  const matching = cases.filter((caseRow) => {
    const caseOrder = normalizeIdentifier(caseRow.amazon_order_id);
    const caseLpn = normalizeIdentifier(caseRow.lpn);
    return (orderId && caseOrder === orderId) || (lpn && caseLpn === lpn);
  });
  return matching.sort((left, right) => {
    const leftUpdated = cleanText(left.updated_at) ?? "";
    const rightUpdated = cleanText(right.updated_at) ?? "";
    return rightUpdated.localeCompare(leftUpdated);
  })[0] ?? null;
}

export function inspectionFromCase(caseRow?: ReturnRecoveryCaseRow | null): InspectionEvidence {
  const raw = asRecord(caseRow?.raw_evidence_json);
  const inspection = asRecord(raw.inspection);
  return {
    observed_condition: cleanText(inspection.observed_condition),
    sealed_new_status: cleanText(inspection.sealed_new_status),
    complete_item: triState(inspection.complete_item),
    wrong_item: triState(inspection.wrong_item),
    notes: cleanText(inspection.notes),
    inspected_at: cleanText(inspection.inspected_at) ?? cleanText(caseRow?.inspected_at),
    updated_at: cleanText(inspection.updated_at),
  };
}

export function buildOriginalSaleFinancialImpact(
  row: CustomerReturnRow,
  salesContext: SalesContext,
): OriginalSaleFinancialImpact {
  const orderId = cleanText(row.amazon_order_id);
  if (!orderId) return missingOriginalSale("No Amazon order ID on customer return row.");

  const order = salesContext.orders.find(
    (candidate) => candidate.amazon_order_id === orderId,
  );
  if (!order) return missingOriginalSale("No matching Amazon sales order found.");

  const orderProfitRows = salesContext.profitability.filter(
    (candidate) => candidate.amazon_order_id === orderId,
  );
  const orderItemRows = salesContext.items.filter(
    (candidate) => candidate.amazon_order_id === orderId,
  );
  const profitMatch = bestProductMatch(row, orderProfitRows);
  const itemMatch = profitMatch
    ? orderItemRows.find((item) => item.amazon_order_item_id === profitMatch.amazon_order_item_id) ??
      bestProductMatch(row, orderItemRows)
    : bestProductMatch(row, orderItemRows);
  const financialEvents = salesContext.financialEvents.filter(
    (event) =>
      event.amazon_order_id === orderId &&
      (!profitMatch?.amazon_order_item_id ||
        !event.amazon_order_item_id ||
        event.amazon_order_item_id === profitMatch.amazon_order_item_id),
  );
  const refund = refundPrincipal(financialEvents);
  const principalAmount = principalCharge(financialEvents);
  const matchBasis = saleMatchBasis(row, profitMatch, itemMatch, orderProfitRows.length);

  if (!profitMatch && orderProfitRows.length > 1) {
    return {
      ...baseOriginalSale(order, itemMatch, null, refund, principalAmount),
      data_status: "multiple_possible",
      confidence: "needs_matching",
      match_basis: matchBasis,
    };
  }

  if (!profitMatch) {
    return {
      ...baseOriginalSale(order, itemMatch, null, refund, principalAmount),
      data_status: "missing_profitability",
      confidence: itemMatch ? "order_only" : "needs_matching",
      match_basis: matchBasis,
    };
  }

  return {
    ...baseOriginalSale(order, itemMatch, profitMatch, refund, principalAmount),
    data_status: "matched",
    confidence: hasProductOverlap(row, profitMatch) ? "high" : "order_only",
    match_basis: matchBasis,
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

function uniqueClean(values: unknown[]) {
  return Array.from(
    new Set(values.map((value) => cleanText(value)).filter((value): value is string => Boolean(value))),
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function triState(value: unknown): "yes" | "no" | "unknown" {
  return value === "yes" || value === "no" ? value : "unknown";
}

async function fetchByOrderIds<T>(
  supabase: ServerSupabaseClient,
  table: string,
  select: string,
  orderIds: string[],
): Promise<T[]> {
  const rows: T[] = [];
  for (let index = 0; index < orderIds.length; index += 100) {
    const chunk = orderIds.slice(index, index + 100);
    const { data, error } = await supabase
      .from(table)
      .select(select)
      .in("amazon_order_id", chunk);
    if (error) throw new Error(`${table}: ${error.message}`);
    rows.push(...((data ?? []) as unknown as T[]));
  }
  return rows;
}

function emptySalesContext(): SalesContext {
  return { orders: [], items: [], profitability: [], financialEvents: [] };
}

function bestProductMatch<T extends { asin?: string | null; seller_sku?: string | null }>(
  row: CustomerReturnRow,
  candidates: T[],
) {
  if (!candidates.length) return null;
  const productMatches = candidates.filter((candidate) => hasProductOverlap(row, candidate));
  if (productMatches.length === 1) return productMatches[0];
  if (productMatches.length > 1) return productMatches[0];
  return candidates.length === 1 ? candidates[0] : null;
}

function hasProductOverlap(
  row: CustomerReturnRow,
  candidate: { asin?: string | null; seller_sku?: string | null },
) {
  const returnIds = productIdentifiers(row);
  const candidateIds = productIdentifiers({
    seller_sku: candidate.seller_sku,
    sku: candidate.seller_sku,
    asin: candidate.asin,
  });
  return returnIds.some((identifier) => candidateIds.includes(identifier));
}

function baseOriginalSale(
  order: SalesOrderRow,
  item: SalesOrderItemRow | null,
  profit: SalesProfitabilityRow | null,
  refund: { amount: number | null; currency: string | null },
  principalAmount: number | null,
) {
  const fulfillmentCost = toOptionalNumber(profit?.fulfillment_cost);
  const refundAmount = refund.amount;

  return {
    order_date: dateOnly(order.purchase_date),
    order_status: cleanText(order.order_status),
    fulfillment_channel: cleanText(order.fulfillment_channel),
    sale_price: toOptionalNumber(profit?.sale_price),
    item_price: toOptionalNumber(item?.item_price_amount),
    principal_amount: principalAmount,
    cogs: toOptionalNumber(profit?.cogs),
    cogs_source: cleanText(profit?.cogs_source),
    amazon_fees_excluding_fulfillment: toOptionalNumber(profit?.amazon_fees_excluding_fulfillment),
    fulfillment_cost: fulfillmentCost,
    fulfillment_cost_source: cleanText(profit?.fulfillment_cost_source),
    original_net_profit: toOptionalNumber(profit?.net_profit),
    roi: toOptionalNumber(profit?.roi),
    refund_amount: refundAmount,
    refund_currency: refund.currency,
    estimated_unrecoverable_fees: null,
    estimated_return_loss: null,
    profitability_status: profitabilityStatus(order, profit, refundAmount),
  };
}

function missingOriginalSale(matchBasis: string): OriginalSaleFinancialImpact {
  return {
    order_date: null,
    order_status: null,
    fulfillment_channel: null,
    sale_price: null,
    item_price: null,
    principal_amount: null,
    cogs: null,
    cogs_source: null,
    amazon_fees_excluding_fulfillment: null,
    fulfillment_cost: null,
    fulfillment_cost_source: null,
    original_net_profit: null,
    roi: null,
    refund_amount: null,
    refund_currency: null,
    estimated_unrecoverable_fees: null,
    estimated_return_loss: null,
    profitability_status: null,
    data_status: "needs_matching",
    confidence: "needs_matching",
    match_basis: matchBasis,
  };
}

function refundPrincipal(events: SalesFinancialEventRow[]) {
  const refundEvents = events.filter(
    (event) =>
      cleanText(event.event_type) === "RefundEventList" &&
      normalizeIdentifier(event.charge_type) === "PRINCIPAL",
  );
  const amount = refundEvents.reduce((total, event) => {
    const value = toOptionalNumber(event.amount);
    return value !== null && value < 0 ? total + Math.abs(value) : total;
  }, 0);
  const currency =
    refundEvents.find((event) => cleanText(event.currency))?.currency ?? null;
  return { amount: amount > 0 ? roundMoney(amount) : null, currency };
}

function principalCharge(events: SalesFinancialEventRow[]) {
  const amount = events.reduce((total, event) => {
    const value = toOptionalNumber(event.amount);
    if (
      normalizeIdentifier(event.charge_type) === "PRINCIPAL" &&
      value !== null &&
      value > 0
    ) {
      return total + value;
    }
    return total;
  }, 0);
  return amount > 0 ? roundMoney(amount) : null;
}

function profitabilityStatus(
  order: SalesOrderRow,
  profit: SalesProfitabilityRow | null,
  refundAmount: number | null,
) {
  if (refundAmount !== null && refundAmount > 0) return "Refund detected";
  if (profit?.data_status === "refunded") return "Refunded";
  if (profit?.data_status === "cancelled") return "Cancelled";
  if (profit?.data_status === "complete") return "Complete";
  if (profit?.data_status) return formatStatus(profit.data_status);
  if (order.order_status) return order.order_status;
  return null;
}

function saleMatchBasis(
  row: CustomerReturnRow,
  profit: SalesProfitabilityRow | null,
  item: SalesOrderItemRow | null,
  profitRowCount: number,
) {
  if (profit && hasProductOverlap(row, profit)) return "Matched by Amazon order ID and product identifier.";
  if (item && hasProductOverlap(row, item)) return "Matched by Amazon order ID and order-item product identifier.";
  if (profit && profitRowCount === 1) return "Matched by Amazon order ID; single profitability row for order.";
  if (profitRowCount > 1) return "Amazon order has multiple profitability rows; product match needed.";
  return "Matched Amazon order header only; profitability row unavailable.";
}

function formatStatus(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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
