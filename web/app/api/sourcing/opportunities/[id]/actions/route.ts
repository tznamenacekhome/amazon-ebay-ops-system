import { NextRequest, NextResponse } from "next/server";
import { supabase } from "../../../_supabase";
import { buildListingSnapshot } from "../../../matchingIntelligence";

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
  const imageClues = Array.isArray(body.imageClues)
    ? body.imageClues.map((value: unknown) => String(value)).filter(Boolean)
    : [];
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
    .select(
      `
      *,
      sourcing_ebay_candidates (*),
      sourcing_seed_asins (*)
      `,
    )
    .eq("opportunity_id", id)
    .single();
  if (opportunityError) {
    return NextResponse.json({ error: opportunityError.message }, { status: 500 });
  }

  const rawActionContext = {
    actionType,
    previousStatus: opportunity.status,
    newStatus,
    requiredMaxLandedCost,
    requiredRoiPercent,
    expectedPurchaseCost,
    imageClues,
  };

  const { data: action, error: actionError } = await supabase.from("sourcing_actions").insert({
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
    raw_action_context: rawActionContext,
  }).select("*").single();
  if (actionError) return NextResponse.json({ error: actionError.message }, { status: 500 });

  const event = actionRecordType[actionType] === "purchased" ? "purchased" : actionRecordType[actionType];
  const { data: snapshot, error: snapshotError } = await supabase
    .from("sourcing_listing_snapshots")
    .insert(buildListingSnapshot({
      opportunity: opportunity as Record<string, unknown>,
      candidate: (opportunity.sourcing_ebay_candidates ?? {}) as Record<string, unknown>,
      seed: (opportunity.sourcing_seed_asins ?? {}) as Record<string, unknown>,
      event,
      actionId: action.action_id,
      rawContext: {
        ...rawActionContext,
        dismissReason: reason,
        notes,
        imageClues,
      },
    }))
    .select("listing_snapshot_id")
    .single();
  if (snapshotError) return NextResponse.json({ error: snapshotError.message }, { status: 500 });

  await supabase
    .from("sourcing_actions")
    .update({ listing_snapshot_id: snapshot.listing_snapshot_id })
    .eq("action_id", action.action_id);

  const { data, error } = await supabase
    .from("sourcing_opportunities")
    .update({
      status: newStatus,
      latest_listing_snapshot_id: snapshot.listing_snapshot_id,
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
