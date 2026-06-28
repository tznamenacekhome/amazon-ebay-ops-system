import { NextResponse } from "next/server";
import {
  buildQueueRow,
  fetchCustomerReturnRows,
  fetchRecentReimbursementRows,
  getReturnRecoverySupabaseClient,
  queueRowMatchesSearch,
  summarizeQueue,
} from "./data";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const query = url.searchParams.get("q") ?? url.searchParams.get("search") ?? "";
    const limit = clampLimit(url.searchParams.get("limit"));
    const supabase = getReturnRecoverySupabaseClient();

    const [customerReturns, reimbursements] = await Promise.all([
      fetchCustomerReturnRows(supabase),
      fetchRecentReimbursementRows(supabase),
    ]);

    const allRows = customerReturns.map((row) => buildQueueRow(row, reimbursements));
    const filteredRows = allRows.filter((row) => queueRowMatchesSearch(row, query));
    const rows = filteredRows.slice(0, limit);

    return NextResponse.json({
      generated_at: new Date().toISOString(),
      query,
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

function clampLimit(value: string | null) {
  const number = Number(value ?? 250);
  if (!Number.isFinite(number)) return 250;
  return Math.min(500, Math.max(1, Math.round(number)));
}
