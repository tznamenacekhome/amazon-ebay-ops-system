import { createServerSupabaseClient } from "../_server";

export const supabase = createServerSupabaseClient();

export const STALE_TRACKING_ORDER_AGE_DAYS = 14;
export const STALE_TRACKING_LOOKBACK_DAYS = 90;

export type DashboardPurchaseRow = {
  item_id: string | null;
  purchase_id: string | null;
  order_date: string | null;
  supplier_order_id: string | null;
  title: string | null;
  amazon_title: string | null;
  system: string | null;
  asin: string | null;
  sell_price: number | null;
  quantity: number | null;
  unit_cost: number | null;
  current_status: string | null;
  estimated_delivery_date: string | null;
  delivered_date: string | null;
  received_date: string | null;
  marketplace: "Amazon" | "eBay" | null;
  exclude_from_purchase_reporting?: boolean | null;
};

export type OrderProblemCaseRow = {
  problem_case_id?: string;
  purchase_item_id?: string | null;
  supplier_order_id?: string | null;
  problem_type: string | null;
  workflow_state: string | null;
  is_open: boolean;
  next_action?: string | null;
  next_action_due_at?: string | null;
  first_detected_at?: string | null;
  last_detected_at?: string | null;
  refund_due_at?: string | null;
  expected_refund_amount?: number | null;
  actual_refund_amount?: number | null;
  updated_at?: string | null;
};

export type InventoryPositionRow = {
  inventory_position_id: string;
  purchase_item_id: string | null;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  system: string | null;
  quantity: number | null;
  unit_cost: number | null;
  total_cost: number | null;
  inventory_state: string | null;
  physical_location: string | null;
  marketplace_intent: string | null;
  operational_status: string | null;
  needs_reconciliation: boolean | null;
  effective_at: string | null;
  updated_at: string | null;
};

export type SalesProfitabilityRow = {
  amazon_order_id: string | null;
  asin: string | null;
  seller_sku: string | null;
  title: string | null;
  quantity: number | null;
  sale_price: number | null;
  amazon_fees_excluding_fulfillment: number | null;
  fulfillment_cost: number | null;
  cogs: number | null;
  net_profit: number | null;
  roi: number | null;
  data_status: string | null;
  calculated_at: string | null;
  updated_at: string | null;
};

export type SalesOrderRow = {
  amazon_order_id: string;
  purchase_date: string | null;
  order_status: string | null;
  number_of_items_shipped: number | null;
  number_of_items_unshipped: number | null;
  order_total_amount: number | null;
  updated_at: string | null;
};

export async function fetchDashboardPurchaseRows() {
  const rows: DashboardPurchaseRow[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("vw_purchases_dashboard")
      .select(
        [
          "item_id",
          "purchase_id",
          "order_date",
          "supplier_order_id",
          "title",
          "system",
          "asin",
          "sell_price",
          "quantity",
          "unit_cost",
          "current_status",
          "estimated_delivery_date",
          "delivered_date",
        ].join(","),
      )
      .range(offset, offset + pageSize - 1);

    if (error) throw new Error(`dashboard purchases: ${error.message}`);
    rows.push(...((data ?? []) as unknown as DashboardPurchaseRow[]));
    if ((data ?? []).length < pageSize) break;
    offset += pageSize;
  }

  return hydrateReportingExclusions(rows);
}

export async function fetchOpenOrderProblemCases() {
  const { data, error } = await supabase
    .from("order_problem_cases")
    .select(
      "problem_case_id,purchase_item_id,supplier_order_id,problem_type,workflow_state,is_open,next_action," +
        "next_action_due_at,first_detected_at,last_detected_at,refund_due_at,expected_refund_amount," +
        "actual_refund_amount,updated_at",
    )
    .eq("is_open", true);

  if (error) {
    console.warn("Dashboard order problem lookup failed", error.message);
    return [] as OrderProblemCaseRow[];
  }

  return (data ?? []) as unknown as OrderProblemCaseRow[];
}

export async function fetchInventoryPositions() {
  const rows: InventoryPositionRow[] = [];
  const pageSize = 1000;
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from("inventory_positions")
      .select(
        "inventory_position_id,purchase_item_id,asin,seller_sku,title,system,quantity,unit_cost,total_cost," +
          "inventory_state,physical_location,marketplace_intent,operational_status,needs_reconciliation,effective_at,updated_at",
      )
      .range(offset, offset + pageSize - 1);
    if (error) {
      console.warn("Dashboard inventory positions lookup failed", error.message);
      return rows;
    }
    rows.push(...((data ?? []) as unknown as InventoryPositionRow[]));
    if ((data ?? []).length < pageSize) return rows;
    offset += pageSize;
  }
}

export async function fetchOpenReconciliationItems(limit = 500) {
  const { data, error } = await supabase
    .from("vw_open_inventory_reconciliation_items")
    .select("severity,issue_type,asin,seller_sku,title,system,mbop_quantity,amazon_total_quantity,amazon_unsellable_quantity,created_at,first_seen_at")
    .limit(limit);
  if (error) {
    console.warn("Dashboard reconciliation lookup failed", error.message);
    return [] as Array<Record<string, unknown>>;
  }
  return (data ?? []) as unknown as Array<Record<string, unknown>>;
}

export async function fetchSalesProfitabilityRows() {
  const rows: SalesProfitabilityRow[] = [];
  const pageSize = 1000;
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from("amazon_sales_profitability")
      .select(
        "amazon_order_id,asin,seller_sku,title,quantity,sale_price,amazon_fees_excluding_fulfillment," +
          "fulfillment_cost,cogs,net_profit,roi,data_status,calculated_at,updated_at",
      )
      .range(offset, offset + pageSize - 1);
    if (error) {
      console.warn("Dashboard sales profitability lookup failed", error.message);
      return rows;
    }
    rows.push(...((data ?? []) as unknown as SalesProfitabilityRow[]));
    if ((data ?? []).length < pageSize) return rows;
    offset += pageSize;
  }
}

export async function fetchSalesOrdersSince(startIso: string) {
  const rows: SalesOrderRow[] = [];
  const pageSize = 1000;
  let offset = 0;
  while (true) {
    const { data, error } = await supabase
      .from("amazon_sales_orders")
      .select("amazon_order_id,purchase_date,order_status,number_of_items_shipped,number_of_items_unshipped,order_total_amount,updated_at")
      .gte("purchase_date", startIso)
      .range(offset, offset + pageSize - 1);
    if (error) {
      console.warn("Dashboard sales order lookup failed", error.message);
      return rows;
    }
    rows.push(...((data ?? []) as unknown as SalesOrderRow[]));
    if ((data ?? []).length < pageSize) return rows;
    offset += pageSize;
  }
}

export async function latestTimestamp(table: string, column: string) {
  const { data, error } = await supabase
    .from(table)
    .select(column)
    .order(column, { ascending: false, nullsFirst: false })
    .limit(1);
  if (error) {
    console.warn(`Dashboard timestamp lookup failed for ${table}.${column}`, error.message);
    return null;
  }
  return String(((data ?? []) as unknown as Array<Record<string, unknown>>)[0]?.[column] ?? "") || null;
}

export async function countRows(table: string, filters?: (query: CountQuery) => CountQuery) {
  let query = supabase.from(table).select("*", { count: "exact", head: true }) as unknown as CountQuery;
  if (filters) query = filters(query);
  const result = await query;
  if (result.error) {
    console.warn(`Dashboard count failed for ${table}`, result.error.message);
    return 0;
  }
  return result.count ?? 0;
}

type CountQuery = PromiseLike<{
  count?: number | null;
  error?: { message: string } | null;
}> & {
  eq: (column: string, value: string | boolean) => CountQuery;
  in: (column: string, values: string[]) => CountQuery;
};

type PurchaseItemMetadata = {
  item_id: string;
  exclude_from_purchase_reporting?: boolean | null;
  amazon_title?: string | null;
  marketplace?: "Amazon" | "eBay" | null;
  received_date?: string | null;
};

async function hydrateReportingExclusions(rows: DashboardPurchaseRow[]) {
  const itemIds = rows
    .map((row) => row.item_id)
    .filter((itemId): itemId is string => typeof itemId === "string");

  if (itemIds.length === 0) return rows;

  const itemMetaById = new Map<string, PurchaseItemMetadata>();

  const metadataRows = await fetchPurchaseItemMetadata();
  if (!metadataRows) {
    return rows;
  }

  const wantedItemIds = new Set(itemIds);
  for (const item of metadataRows) {
    if (wantedItemIds.has(item.item_id)) {
      itemMetaById.set(item.item_id, item);
    }
  }

  return rows.map((row) => {
    const meta = row.item_id ? itemMetaById.get(row.item_id) : null;
    return {
      ...row,
      amazon_title: meta?.amazon_title ?? row.amazon_title ?? null,
      marketplace: meta?.marketplace ?? row.marketplace ?? null,
      received_date: meta?.received_date ?? row.received_date ?? null,
      exclude_from_purchase_reporting: Boolean(meta?.exclude_from_purchase_reporting),
    };
  });
}

async function fetchPurchaseItemMetadata() {
  const rows: PurchaseItemMetadata[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const result = await retrySupabaseQuery(() =>
      supabase
      .from("purchase_items")
      .select("item_id,exclude_from_purchase_reporting,amazon_title,marketplace,received_date")
        .range(offset, offset + pageSize - 1),
    );

    if (result.error) {
      console.warn("Dashboard purchase item metadata lookup failed", result.error.message);
      return null;
    }

    rows.push(...((result.data ?? []) as PurchaseItemMetadata[]));
    if ((result.data ?? []).length < pageSize) {
      return rows;
    }

    offset += pageSize;
  }
}

async function retrySupabaseQuery<T>(query: () => PromiseLike<{ data: T[] | null; error: { message: string } | null }>) {
  const maxAttempts = 3;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const result = await query();
    if (!result.error || attempt === maxAttempts) return result;
    await sleep(200 * attempt);
  }

  return query();
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function reportableRows(rows: DashboardPurchaseRow[]) {
  return rows.filter((row) => !row.exclude_from_purchase_reporting);
}

export function normalizeStatus(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
}

export function sumUnits(rows: DashboardPurchaseRow[]) {
  return rows.reduce((total, row) => total + toNumber(row.quantity), 0);
}

export function sumCost(rows: DashboardPurchaseRow[]) {
  return rows.reduce((total, row) => total + toNumber(row.quantity) * toNumber(row.unit_cost), 0);
}

export function ageDays(value: string | null | undefined) {
  const date = Date.parse(String(value || ""));
  if (Number.isNaN(date)) return null;
  return Math.max(0, Math.floor((Date.now() - date) / 86_400_000));
}

export function todayDateString() {
  return new Date().toISOString().slice(0, 10);
}

export function weekEndDateString() {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + 7);
  return date.toISOString().slice(0, 10);
}

export function toNumber(value: unknown) {
  const numberValue = Number(value ?? 0);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

export function dateDaysAgo(days: number) {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString();
}

export function monthKey(value: string | null | undefined) {
  const text = String(value ?? "");
  return text.length >= 7 ? text.slice(0, 7) : null;
}

export function median(values: number[]) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function percentChange(current: number, previous: number | null) {
  if (!previous) return null;
  return ((current - previous) / Math.abs(previous)) * 100;
}

export function hasValidAsin(value: string | null | undefined) {
  return /^[A-Z0-9]{10}$/.test((value ?? "").trim().toUpperCase());
}

export function hasSellPrice(row: DashboardPurchaseRow) {
  return toNumber(row.sell_price) > 0;
}

export function chunks<T>(values: T[], size: number) {
  const output: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    output.push(values.slice(index, index + size));
  }
  return output;
}
