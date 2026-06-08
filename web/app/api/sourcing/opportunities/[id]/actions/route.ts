import { NextRequest, NextResponse } from "next/server";
import { supabase } from "../../../_supabase";

const actionStatus: Record<string, string> = {
  dismiss: "dismissed",
  watch: "watching",
  purchased: "purchased_pending_match",
  snooze_roi: "roi_snoozed",
};

const actionRecordType: Record<string, string> = {
  dismiss: "dismissed",
  watch: "watching",
  purchased: "purchased",
  snooze_roi: "roi_snoozed",
};

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.json();
  const actionType = String(body.actionType ?? "");
  const notes = body.notes ? String(body.notes) : null;
  const reason = body.reason ? String(body.reason) : null;
  const requiredMaxLandedCost = numberOrNull(body.requiredMaxLandedCost);
  const requiredRoiPercent = numberOrNull(body.requiredRoiPercent);
  const expectedPurchaseCost = numberOrNull(body.expectedPurchaseCost);
  const newStatus = actionStatus[actionType];

  if (!newStatus) {
    return NextResponse.json({ error: "Unsupported sourcing action." }, { status: 400 });
  }
  if (actionType === "dismiss" && !reason) {
    return NextResponse.json({ error: "Dismiss requires a reason." }, { status: 400 });
  }

  const { data: opportunity, error: opportunityError } = await supabase
    .from("sourcing_opportunities")
    .select("opportunity_id,sourcing_run_id,candidate_id,asin,ebay_item_id,status")
    .eq("opportunity_id", id)
    .single();
  if (opportunityError) {
    return NextResponse.json({ error: opportunityError.message }, { status: 500 });
  }

  const { error: actionError } = await supabase.from("sourcing_actions").insert({
    opportunity_id: id,
    candidate_id: opportunity.candidate_id,
    asin: opportunity.asin,
    ebay_item_id: opportunity.ebay_item_id,
    action_type: actionRecordType[actionType],
    dismiss_reason: reason,
    notes,
    required_max_landed_cost: requiredMaxLandedCost,
    required_roi_percent: requiredRoiPercent,
    expected_purchase_cost: expectedPurchaseCost,
  });
  if (actionError) return NextResponse.json({ error: actionError.message }, { status: 500 });

  const { data, error } = await supabase
    .from("sourcing_opportunities")
    .update({
      status: newStatus,
      updated_at: new Date().toISOString(),
    })
    .eq("opportunity_id", id)
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ opportunity: data });
}

function numberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
