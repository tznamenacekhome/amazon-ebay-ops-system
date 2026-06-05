import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseServiceRoleKey);

const PAGE_SIZE_MAX = 500;
const STALE_TRACKING_ORDER_AGE_DAYS = 14;
const STALE_TRACKING_LOOKBACK_DAYS = 90;

type ProblemQuery = {
  searchText: string;
  stage: string;
  page: number;
  pageSize: number;
};

type DashboardRow = {
  item_id: string;
  purchase_id: string;
  order_date: string | null;
  supplier: string | null;
  supplier_order_id: string | null;
  title: string | null;
  system: string | null;
  asin: string | null;
  sell_price: number | null;
  target_price?: number | null;
  unit_cost: number | null;
  quantity: number | null;
  current_status: string | null;
  tracking_number: string | null;
  supplier_listing_url: string | null;
  carrier: string | null;
  delivery_status: string | null;
  estimated_delivery_date: string | null;
  delivered_date: string | null;
};

type ProblemCase = {
  problem_case_id: string;
  purchase_item_id: string;
  purchase_id: string | null;
  supplier: string | null;
  supplier_order_id: string | null;
  problem_source: string;
  problem_type: string;
  workflow_state: string;
  priority: string | null;
  is_open: boolean;
  needs_response: boolean;
  next_action: string | null;
  next_action_due_at: string | null;
  first_detected_at: string | null;
  last_detected_at: string | null;
  escalation_available_at: string | null;
  ebay_return_id: string | null;
  ebay_inquiry_id: string | null;
  ebay_case_id: string | null;
  ebay_return_state: string | null;
  ebay_return_status: string | null;
  ebay_current_type: string | null;
  ebay_action_url: string | null;
  expected_refund_amount: number | null;
  actual_refund_amount: number | null;
  partial_refund_amount: number | null;
  refund_currency: string | null;
  replacement_tracking_number: string | null;
  notes: string | null;
};

type ProblemSeed = {
  item_id: string;
  purchase_id: string | null;
  supplier: string | null;
  supplier_order_id: string | null;
  problem_source: string;
  problem_type: string;
  workflow_state: string;
  next_action: string;
};

type DynamicQueryResult = {
  data?: Array<Record<string, unknown>> | null;
  count?: number | null;
  error?: { message: string } | null;
};

type DynamicQuery = PromiseLike<DynamicQueryResult> & {
  select: (columns: string, options?: { count?: "exact"; head?: boolean }) => DynamicQuery;
  eq: (column: string, value: string | boolean) => DynamicQuery;
  in: (column: string, values: string[]) => DynamicQuery;
  not: (column: string, operator: string, value: string) => DynamicQuery;
  lt: (column: string, value: string) => DynamicQuery;
  lte: (column: string, value: string) => DynamicQuery;
  gte: (column: string, value: string) => DynamicQuery;
  or: (filters: string) => DynamicQuery;
  order: (column: string, options?: { ascending?: boolean; nullsFirst?: boolean }) => DynamicQuery;
  range: (from: number, to: number) => DynamicQuery;
  limit: (count: number) => DynamicQuery;
};

export async function GET(request: Request) {
  const query = parseProblemQuery(new URL(request.url));

  try {
    await seedDerivedProblemCases();
    const cases = suppressDerivedCandidatesCoveredByEbayCase(
      await fetchCases(query.stage === "resolved"),
    );
    const itemIds = cases.map((row) => row.purchase_item_id);
    const [dashboardRows, itemMeta] = await Promise.all([
      fetchDashboardRows(itemIds),
      fetchItemMeta(itemIds),
    ]);
    const dashboardByItemId = new Map(dashboardRows.map((row) => [row.item_id, row]));
    const itemMetaById = new Map(itemMeta.map((row) => [row.item_id, row]));

    const mergedRows = cases
      .map((problemCase) => mergeProblemCase(problemCase, dashboardByItemId, itemMetaById))
      .filter((row): row is ReturnType<typeof mergeProblemCase> & object => Boolean(row))
      .filter((row) => matchesStage(row, query.stage))
      .filter((row) => matchesSearch(row, query.searchText))
      .sort(compareProblemRows);

    const total = mergedRows.length;
    const rangeStart = (query.page - 1) * query.pageSize;
    const pagedRows = mergedRows.slice(rangeStart, rangeStart + query.pageSize);

    return NextResponse.json({
      rows: pagedRows,
      total,
      page: query.page,
      pageSize: query.pageSize,
      stats: {
        total,
        visible: total,
        needsReview: 0,
        orderProblems: total,
        delivered: 0,
      },
      summary: summarizeProblemRows(mergedRows),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load order problems" },
      { status: 500 },
    );
  }
}

function suppressDerivedCandidatesCoveredByEbayCase(cases: ProblemCase[]) {
  const supplierOrdersWithEbayCases = new Set(
    cases
      .filter((row) => row.is_open)
      .filter((row) => row.problem_source === "ebay_return_sync" || row.problem_source === "ebay_inquiry_sync")
      .map((row) => row.supplier_order_id)
      .filter((orderId): orderId is string => Boolean(orderId)),
  );

  if (supplierOrdersWithEbayCases.size === 0) return cases;

  return cases.filter((row) => {
    if (row.problem_source !== "derived_order_problem") return true;
    if (!row.supplier_order_id) return true;
    return !supplierOrdersWithEbayCases.has(row.supplier_order_id);
  });
}

function parseProblemQuery(url: URL): ProblemQuery {
  const page = Math.max(Number(url.searchParams.get("page") || "1"), 1);
  const pageSize = Math.min(
    Math.max(Number(url.searchParams.get("pageSize") || "100"), 25),
    PAGE_SIZE_MAX,
  );

  return {
    searchText: (url.searchParams.get("search") || "").trim(),
    stage: url.searchParams.get("stage") || "open",
    page,
    pageSize,
  };
}

async function seedDerivedProblemCases() {
  const candidateRows = await fetchDerivedCandidateRows();
  const initialSeeds = dedupeSeeds(candidateRows.map(candidateSeedForRow).filter(Boolean) as ProblemSeed[]);
  const resolvedKeys = await fetchResolvedProblemKeys();
  const seeds = initialSeeds.filter((seed) => !isAlreadyResolved(seed, resolvedKeys));
  await closeResolvedDerivedCandidates(seeds);
  if (seeds.length === 0) return;

  const itemIds = seeds.map((seed) => seed.item_id);
  const existingRows = await fetchOpenCasesForItems(itemIds);
  const existingByItemId = new Map(existingRows.map((row) => [row.purchase_item_id, row]));
  const now = new Date().toISOString();

  const inserts: Record<string, unknown>[] = [];

  for (const seed of seeds) {
    const existing = existingByItemId.get(seed.item_id);
    if (existing) {
      const { error } = await supabase
        .from("order_problem_cases")
        .update({ last_detected_at: now, updated_at: now })
        .eq("problem_case_id", existing.problem_case_id);
      if (error) throw new Error(`order_problem_cases update: ${error.message}`);
      continue;
    }

    inserts.push({
      purchase_item_id: seed.item_id,
      purchase_id: seed.purchase_id,
      supplier: seed.supplier ?? "eBay",
      supplier_order_id: seed.supplier_order_id,
      problem_source: seed.problem_source,
      problem_type: seed.problem_type,
      workflow_state: seed.workflow_state,
      priority: "normal",
      is_open: true,
      needs_response: false,
      next_action: seed.next_action,
      first_detected_at: now,
      last_detected_at: now,
    });
  }

  if (inserts.length === 0) return;

  const { data, error } = await supabase
    .from("order_problem_cases")
    .insert(inserts)
    .select("problem_case_id,workflow_state,problem_type");
  if (error) throw new Error(`order_problem_cases insert: ${error.message}`);

  const eventRows = ((data ?? []) as Array<{ problem_case_id: string; workflow_state: string; problem_type: string }>).map((row) => ({
    problem_case_id: row.problem_case_id,
    event_type: "derived_candidate_detected",
    event_source: "system",
    message: `Derived order problem detected: ${row.workflow_state} / ${row.problem_type}`,
  }));

  if (eventRows.length > 0) {
    const { error: eventError } = await supabase.from("order_problem_events").insert(eventRows);
    if (eventError) throw new Error(`order_problem_events insert: ${eventError.message}`);
  }
}

type ResolvedProblemKeys = {
  itemIds: Set<string>;
  supplierOrderIds: Set<string>;
  detailByItemId: Map<string, ResolvedProblemDetail>;
  detailBySupplierOrderId: Map<string, ResolvedProblemDetail>;
};

type ResolvedProblemDetail = {
  ebay_return_id: string | null;
  ebay_inquiry_id: string | null;
  ebay_case_id: string | null;
  ebay_action_url: string | null;
};

async function fetchResolvedProblemKeys(): Promise<ResolvedProblemKeys> {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select("purchase_item_id,supplier_order_id,ebay_return_id,ebay_inquiry_id,ebay_case_id,ebay_action_url")
    .eq("is_open", false)
    .in("workflow_state", ["resolved_refunded", "resolved_received_item"]);
  if (error) throw new Error(`order_problem_cases resolved lookup: ${error.message}`);

  const detailByItemId = new Map<string, ResolvedProblemDetail>();
  const detailBySupplierOrderId = new Map<string, ResolvedProblemDetail>();
  for (const row of data ?? []) {
    const detail = {
      ebay_return_id: row.ebay_return_id,
      ebay_inquiry_id: row.ebay_inquiry_id,
      ebay_case_id: row.ebay_case_id,
      ebay_action_url: row.ebay_action_url,
    };
    if (row.purchase_item_id && !detailByItemId.has(row.purchase_item_id)) {
      detailByItemId.set(row.purchase_item_id, detail);
    }
    if (row.supplier_order_id && !detailBySupplierOrderId.has(row.supplier_order_id)) {
      detailBySupplierOrderId.set(row.supplier_order_id, detail);
    }
  }

  return {
    itemIds: new Set((data ?? []).map((row) => row.purchase_item_id).filter(Boolean)),
    supplierOrderIds: new Set((data ?? []).map((row) => row.supplier_order_id).filter(Boolean)),
    detailByItemId,
    detailBySupplierOrderId,
  };
}

function isAlreadyResolved(seed: ProblemSeed, resolvedKeys: ResolvedProblemKeys) {
  return resolvedKeys.itemIds.has(seed.item_id);
}

async function closeResolvedDerivedCandidates(seeds: ProblemSeed[]) {
  const activeSeedItemIds = new Set(seeds.map((seed) => seed.item_id));
  const existingDerivedCases = await fetchOpenDerivedCandidateCases();
  const now = new Date().toISOString();
  const resolvedCases = existingDerivedCases.filter((row) => !activeSeedItemIds.has(row.purchase_item_id));

  for (const problemCase of resolvedCases) {
    const { error } = await supabase
      .from("order_problem_cases")
      .update({
        is_open: false,
        workflow_state: "closed_no_action",
        closed_at: now,
        updated_at: now,
        notes: "Closed automatically because the purchase no longer matches an order-problem candidate rule.",
      })
      .eq("problem_case_id", problemCase.problem_case_id);
    if (error) throw new Error(`order_problem_cases close resolved derived candidate: ${error.message}`);
  }
}

async function fetchDerivedCandidateRows() {
  const [pastEta, stale, statusRows] = await Promise.all([
    queryDashboard()
      .lt("estimated_delivery_date", todayDateString())
      .not("current_status", "in", "(delivered,received,listed,cancelled,return_opened)"),
    queryDashboard()
      .in("current_status", ["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"])
      .lte("order_date", daysAgoDateString(STALE_TRACKING_ORDER_AGE_DAYS))
      .gte("order_date", daysAgoDateString(STALE_TRACKING_LOOKBACK_DAYS)),
    queryDashboard().in("current_status", ["exception", "return_pending", "return_opened", "cancelled"]),
  ]);

  const rows = [...rowsOrThrow(pastEta, "past ETA"), ...rowsOrThrow(stale, "stale tracking"), ...rowsOrThrow(statusRows, "status")];
  const byItemId = new Map<string, DashboardRow>();
  for (const row of rows as DashboardRow[]) {
    if (row.item_id) byItemId.set(row.item_id, row);
  }
  return Array.from(byItemId.values());
}

function queryDashboard() {
  return dynamicFrom("vw_purchases_dashboard")
    .select(
      [
        "item_id",
        "purchase_id",
        "order_date",
        "supplier",
        "supplier_order_id",
        "title",
        "system",
        "asin",
        "sell_price",
        "target_price:sell_price",
        "unit_cost",
        "quantity",
        "current_status",
        "tracking_number",
        "supplier_listing_url",
        "carrier",
        "delivery_status",
        "estimated_delivery_date",
        "delivered_date",
      ].join(","),
    )
    .limit(1000);
}

function rowsOrThrow(result: DynamicQueryResult, label: string) {
  if (result.error) throw new Error(`${label}: ${result.error.message}`);
  return result.data ?? [];
}

function candidateSeedForRow(row: DashboardRow): ProblemSeed | null {
  const status = normalizeStatus(row.current_status);
  if (!row.item_id) return null;

  if (status === "return_pending") {
    return seed(row, "receiving_return_pending", "return_needed", "return_needed", "Open or continue return/refund follow-up.");
  }
  if (status === "return_opened") {
    return seed(row, "manual", "return_needed", "return_opened", "Review eBay return/case status.");
  }
  if (status === "cancelled") {
    return seed(row, "manual", "cancelled_refund_followup", "refund_pending", "Confirm refund received.");
  }
  if (status === "exception") {
    return seed(row, "derived_order_problem", "carrier_exception_candidate", "candidate", "Review carrier exception and contact seller/carrier if needed.");
  }
  if (["no_tracking", "shipped_no_tracking", "awaiting_carrier_scan"].includes(status)) {
    return seed(row, "derived_order_problem", "stale_tracking_candidate", "candidate", "Check eBay order details and ask seller for a usable shipment update.");
  }
  return seed(row, "derived_order_problem", "late_delivery_candidate", "candidate", "Delivery estimate has passed; check tracking and seller communication.");
}

function seed(row: DashboardRow, problemSource: string, problemType: string, workflowState: string, nextAction: string): ProblemSeed {
  return {
    item_id: row.item_id,
    purchase_id: row.purchase_id ?? null,
    supplier: row.supplier ?? "eBay",
    supplier_order_id: row.supplier_order_id ?? null,
    problem_source: problemSource,
    problem_type: problemType,
    workflow_state: workflowState,
    next_action: nextAction,
  };
}

function dedupeSeeds(seeds: ProblemSeed[]) {
  return Array.from(new Map(seeds.map((seed) => [seed.item_id, seed])).values());
}

async function fetchOpenCasesForItems(itemIds: string[]) {
  const rows: ProblemCase[] = [];
  for (const chunk of chunks(itemIds, 500)) {
    const { data, error } = await supabase
      .from("order_problem_cases")
      .select("*")
      .in("purchase_item_id", chunk)
      .eq("is_open", true);
    if (error) throw new Error(`order_problem_cases lookup: ${error.message}`);
    rows.push(...((data ?? []) as ProblemCase[]));
  }
  return rows;
}

async function fetchOpenDerivedCandidateCases() {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select("problem_case_id,purchase_item_id")
    .eq("is_open", true)
    .eq("problem_source", "derived_order_problem")
    .eq("workflow_state", "candidate");
  if (error) throw new Error(`order_problem_cases derived lookup: ${error.message}`);
  return (data ?? []) as Array<{ problem_case_id: string; purchase_item_id: string }>;
}

async function fetchCases(includeClosed: boolean) {
  let query = supabase
    .from("order_problem_cases")
    .select("*");

  if (!includeClosed) {
    query = query.eq("is_open", true);
  }

  const { data, error } = await query;
  if (error) throw new Error(`order_problem_cases: ${error.message}`);
  return (data ?? []) as ProblemCase[];
}

async function fetchDashboardRows(itemIds: string[]) {
  const rows: DashboardRow[] = [];
  for (const chunk of chunks(itemIds, 500)) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select(
        [
          "item_id",
          "purchase_id",
          "order_date",
          "supplier",
          "supplier_order_id",
          "title",
          "system",
          "asin",
          "sell_price",
          "target_price:sell_price",
          "unit_cost",
          "quantity",
          "current_status",
          "tracking_number",
          "supplier_listing_url",
          "carrier",
          "delivery_status",
          "estimated_delivery_date",
          "delivered_date",
        ].join(","),
      )
      .in("item_id", chunk);
    if (error) throw new Error(`vw_purchases_dashboard: ${error.message}`);
    rows.push(...((data ?? []) as unknown as DashboardRow[]));
  }
  return rows;
}

async function fetchItemMeta(itemIds: string[]) {
  const rows: Array<{ item_id: string; amazon_title: string | null; exclude_from_purchase_reporting: boolean | null }> = [];
  for (const chunk of chunks(itemIds, 500)) {
    const { data, error } = await supabase
      .from("purchase_items")
      .select("item_id,amazon_title,exclude_from_purchase_reporting")
      .in("item_id", chunk);
    if (error) throw new Error(`purchase_items: ${error.message}`);
    rows.push(...((data ?? []) as unknown as typeof rows));
  }
  return rows;
}

function mergeProblemCase(
  problemCase: ProblemCase,
  dashboardByItemId: Map<string, DashboardRow>,
  itemMetaById: Map<string, { item_id: string; amazon_title: string | null; exclude_from_purchase_reporting: boolean | null }>,
) {
  const row = dashboardByItemId.get(problemCase.purchase_item_id);
  if (!row) return null;
  const meta = itemMetaById.get(problemCase.purchase_item_id);
  if (meta?.exclude_from_purchase_reporting) return null;

  return {
    ...row,
    ebay_title: row.title,
    amazon_title: meta?.amazon_title ?? null,
    exclude_from_purchase_reporting: false,
    problem_case_id: problemCase.problem_case_id,
    problem_type: problemCase.problem_type,
    problem_source: problemCase.problem_source,
    workflow_state: problemCase.workflow_state,
    problem_priority: problemCase.priority,
    problem_is_open: problemCase.is_open,
    problem_needs_response: problemCase.needs_response,
    problem_next_action: problemCase.next_action,
    problem_next_action_due_at: problemCase.next_action_due_at,
    problem_first_detected_at: problemCase.first_detected_at,
    problem_last_detected_at: problemCase.last_detected_at,
    problem_escalation_available_at: problemCase.escalation_available_at,
    ebay_return_id: problemCase.ebay_return_id,
    ebay_inquiry_id: problemCase.ebay_inquiry_id,
    ebay_case_id: problemCase.ebay_case_id,
    ebay_return_state: problemCase.ebay_return_state,
    ebay_return_status: problemCase.ebay_return_status,
    ebay_current_type: problemCase.ebay_current_type,
    ebay_action_url: problemCase.ebay_action_url,
    expected_refund_amount: problemCase.expected_refund_amount,
    actual_refund_amount: problemCase.actual_refund_amount,
    partial_refund_amount: problemCase.partial_refund_amount,
    refund_currency: problemCase.refund_currency,
    replacement_tracking_number: problemCase.replacement_tracking_number,
    problem_notes: problemCase.notes,
  };
}

function matchesStage(row: Record<string, unknown>, stage: string) {
  const workflowState = String(row.workflow_state ?? "");
  const problemType = String(row.problem_type ?? "");
  const needsResponse = Boolean(row.problem_needs_response);

  switch (stage) {
    case "candidates":
      return workflowState === "candidate";
    case "return_needed":
      return workflowState === "return_needed";
    case "return_opened":
      return workflowState === "return_opened";
    case "needs_response":
      return needsResponse || workflowState === "seller_message_needs_response";
    case "waiting_on_seller":
      return ["waiting_on_seller", "label_pending", "partial_refund_offered"].includes(workflowState);
    case "ready_to_ship":
      return workflowState === "label_received";
    case "return_shipped":
      return ["return_shipped", "seller_received_return"].includes(workflowState);
    case "refund_pending":
      return workflowState === "refund_pending";
    case "missing_item_pending":
      return ["replacement_pending", "replacement_shipped"].includes(workflowState) || problemType === "missing_items";
    case "escalation_available":
      return workflowState === "escalation_available";
    case "resolved":
      return workflowState.startsWith("resolved_") || workflowState.startsWith("closed_");
    case "open":
    default:
      return !workflowState.startsWith("resolved_") && !workflowState.startsWith("closed_");
  }
}

function matchesSearch(row: Record<string, unknown>, searchText: string) {
  if (!searchText) return true;
  const needle = searchText.toLowerCase();
  return [
    row.title,
    row.amazon_title,
    row.asin,
    row.system,
    row.supplier_order_id,
    row.tracking_number,
    row.problem_type,
    row.workflow_state,
    row.problem_next_action,
    row.ebay_return_status,
    row.problem_notes,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(needle));
}

function compareProblemRows(left: Record<string, unknown>, right: Record<string, unknown>) {
  const leftRank = problemRank(left);
  const rightRank = problemRank(right);
  if (leftRank !== rightRank) return leftRank - rightRank;

  if (leftRank === 2) {
    const leftAge = ageDays(left.order_date);
    const rightAge = ageDays(right.order_date);
    if (leftAge !== rightAge) return rightAge - leftAge;
  }

  const leftDate = Date.parse(
    String(left.problem_next_action_due_at || left.problem_first_detected_at || left.order_date || ""),
  );
  const rightDate = Date.parse(
    String(right.problem_next_action_due_at || right.problem_first_detected_at || right.order_date || ""),
  );
  return (Number.isNaN(leftDate) ? 0 : leftDate) - (Number.isNaN(rightDate) ? 0 : rightDate);
}

function problemRank(row: Record<string, unknown>) {
  const workflowState = String(row.workflow_state ?? "");
  const problemType = String(row.problem_type ?? "");
  const currentStatus = normalizeStatus(String(row.current_status ?? ""));
  const ebayStatus = String(row.ebay_return_status ?? "").toUpperCase();
  const needsResponse = Boolean(row.problem_needs_response);
  const dueAt = Date.parse(String(row.problem_next_action_due_at ?? ""));
  const overdue = !Number.isNaN(dueAt) && dueAt < Date.now();
  const orderAge = ageDays(row.order_date);
  const agedReturnWindowRisk =
    orderAge >= 21 &&
    (
      ["return_needed", "candidate"].includes(workflowState) ||
      ["return_pending", "no_tracking", "shipped_no_tracking", "awaiting_carrier_scan", "in_transit", "exception"].includes(currentStatus) ||
      ["late_delivery_candidate", "stale_tracking_candidate", "carrier_exception_candidate"].includes(problemType)
    );
  const labelProvidedNoCarrierActivity =
    workflowState === "label_received" ||
    (
      workflowState === "return_shipped" &&
      Boolean(row.replacement_tracking_number) &&
      !["in_transit", "delivered"].includes(normalizeStatus(String(row.delivery_status ?? "")))
    );

  if (
    needsResponse ||
    workflowState === "seller_message_needs_response" ||
    ebayStatus.includes("BUYER_RESPONSE") ||
    ebayStatus.includes("BUYER_ACTION")
  ) {
    return 1;
  }
  if (agedReturnWindowRisk) return 2;
  if (labelProvidedNoCarrierActivity) return 3;
  if (overdue) return 4;
  if (workflowState === "escalation_available") return 5;
  if (workflowState === "refund_pending") return 6;
  if (["return_needed", "return_opened", "replacement_pending", "replacement_shipped"].includes(workflowState)) return 7;
  return 8;
}

function summarizeProblemRows(rows: Array<Record<string, unknown>>) {
  const summary: Record<string, number> = {};
  for (const row of rows) {
    const stage = String(row.workflow_state ?? "unknown");
    summary[stage] = (summary[stage] ?? 0) + 1;
  }
  return summary;
}

function normalizeStatus(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function ageDays(value: unknown) {
  const date = Date.parse(String(value || ""));
  if (Number.isNaN(date)) return 0;
  return Math.floor((Date.now() - date) / 86_400_000);
}

function todayDateString() {
  return dateStringDaysAgo(0);
}

function daysAgoDateString(days: number) {
  return dateStringDaysAgo(days);
}

function dateStringDaysAgo(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function chunks<T>(values: T[], size: number) {
  const output: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    output.push(values.slice(index, index + size));
  }
  return output;
}

function dynamicFrom(table: string): DynamicQuery {
  return supabase.from(table) as unknown as DynamicQuery;
}
