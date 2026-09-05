import { NextResponse } from "next/server";
import {
  buildQueueRow,
  fetchCasesForReturns,
  fetchCustomerReturnRows,
  fetchRecentReimbursementRows,
  fetchSalesContextForReturns,
  getReturnRecoverySupabaseClient,
  queueRowMatchesWorkflowFilter,
  queueRowMatchesSearch,
  summarizeQueue,
} from "./data";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const query = url.searchParams.get("q") ?? url.searchParams.get("search") ?? "";
    const workflow = url.searchParams.get("workflow") ?? "open";
    const limit = clampLimit(url.searchParams.get("limit"));
    const supabase = getReturnRecoverySupabaseClient();

    const [customerReturns, reimbursements] = await Promise.all([
      fetchCustomerReturnRows(supabase),
      fetchRecentReimbursementRows(supabase),
    ]);
    const uniqueCustomerReturns = dedupeCustomerReturnRows(customerReturns);
    const [salesContext, cases] = await Promise.all([
      fetchSalesContextForReturns(supabase, uniqueCustomerReturns),
      fetchCasesForReturns(supabase, uniqueCustomerReturns),
    ]);

    const allRows = uniqueCustomerReturns.map((row) =>
      buildQueueRow(row, reimbursements, salesContext, cases),
    );
    const filteredRows = allRows
      .filter((row) => queueRowMatchesWorkflowFilter(row, workflow))
      .filter((row) => queueRowMatchesSearch(row, query));
    const rows = filteredRows.slice(0, limit);

    return NextResponse.json({
      generated_at: new Date().toISOString(),
      query,
      workflow,
      limit,
      summary: summarizeQueue(filteredRows, allRows),
      rows,
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to load Amazon return recovery queue",
      },
      { status: 500 },
    );
  }
}

function dedupeCustomerReturnRows<T extends {
  amazon_fba_customer_return_row_id: string;
  amazon_order_id: string | null;
  return_date: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  asin: string | null;
  quantity: number | null;
  license_plate_number: string | null;
}>(rows: T[]) {
  const byIdentity = new Map<string, T>();
  for (const row of rows) {
    const key = customerReturnIdentity(row);
    if (!byIdentity.has(key)) byIdentity.set(key, row);
  }
  return [...byIdentity.values()];
}

function customerReturnIdentity(row: {
  amazon_fba_customer_return_row_id: string;
  amazon_order_id: string | null;
  return_date: string | null;
  seller_sku: string | null;
  sku: string | null;
  fnsku: string | null;
  asin: string | null;
  quantity: number | null;
  license_plate_number: string | null;
}) {
  const durableParts = [
    row.license_plate_number,
    row.amazon_order_id,
    row.asin,
    row.seller_sku ?? row.sku,
    row.fnsku,
    row.return_date,
    row.quantity,
  ].map((value) => String(value ?? "").trim().toUpperCase());
  if (durableParts.some(Boolean)) return durableParts.join("|");
  return row.amazon_fba_customer_return_row_id;
}

function clampLimit(value: string | null) {
  const number = Number(value ?? 250);
  if (!Number.isFinite(number)) return 250;
  return Math.min(500, Math.max(1, Math.round(number)));
}
