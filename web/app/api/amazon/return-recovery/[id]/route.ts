import { NextResponse } from "next/server";
import {
  buildQueueRow,
  fetchCasesAndEventsForReturn,
  fetchCustomerReturnRow,
  fetchRecentReimbursementRows,
  fetchSalesContextForReturns,
  getReturnRecoverySupabaseClient,
  matchReimbursements,
} from "../data";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  try {
    const { id } = await context.params;
    const supabase = getReturnRecoverySupabaseClient();
    const customerReturn = await fetchCustomerReturnRow(supabase, id);

    if (!customerReturn) {
      return NextResponse.json(
        { error: "Amazon customer return row not found" },
        { status: 404 },
      );
    }

    const [reimbursements, caseData] = await Promise.all([
      fetchRecentReimbursementRows(supabase),
      fetchCasesAndEventsForReturn(supabase, customerReturn),
    ]);
    const salesContext = await fetchSalesContextForReturns(supabase, [customerReturn]);
    const reimbursementEvidence = matchReimbursements(customerReturn, reimbursements);
    const row = buildQueueRow(customerReturn, reimbursements, salesContext);

    return NextResponse.json({
      generated_at: new Date().toISOString(),
      row,
      original_sale: row.original_sale,
      customer_return: customerReturn,
      reimbursement_evidence: reimbursementEvidence,
      cases: caseData.cases,
      events: caseData.events,
      raw_evidence: {
        customer_return: customerReturn.raw_row_json,
        reimbursements: reimbursementEvidence.map((row) => row.raw_row_json),
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? error.message
            : "Failed to load Amazon return recovery detail",
      },
      { status: 500 },
    );
  }
}
