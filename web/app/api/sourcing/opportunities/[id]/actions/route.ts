import { NextRequest, NextResponse } from "next/server";
import { supabase } from "../../../_supabase";
import { buildListingSnapshot } from "../../../matchingIntelligence";
import { requireAdminApiToken } from "../../../../_server";

const actionStatus: Record<string, string> = {
  block_asin: "dismissed",
  dismiss: "dismissed",
  watch: "watching",
  purchased: "purchased_pending_match",
  snooze_roi: "roi_snoozed",
};

const actionRecordType: Record<string, string> = {
  block_asin: "dismissed",
  dismiss: "dismissed",
  watch: "watching",
  purchased: "purchased",
  snooze_roi: "roi_snoozed",
};

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const adminError = requireAdminApiToken(request);
  if (adminError) return adminError;

  const { id } = await params;
  const body = await request.json();
  const actionType = String(body.actionType ?? "");
  const notes = body.notes ? String(body.notes) : null;
  const imageClues = Array.isArray(body.imageClues)
    ? body.imageClues.map((value: unknown) => String(value)).filter(Boolean)
    : [];
  const reason = body.reason ? String(body.reason) : actionType === "block_asin" ? "asin_blocked" : null;
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
    blockedAsin: actionType === "block_asin",
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

  if (actionType === "block_asin") {
    const { error: blockError } = await supabase.from("sourcing_blocked_asins").upsert(
      {
        asin: String(opportunity.asin ?? "").toUpperCase(),
        reason,
        notes,
        source_opportunity_id: id,
        source_action_id: action.action_id,
        blocked_by: request.headers.get("x-amzn-oidc-identity") ?? "mbop",
        updated_at: new Date().toISOString(),
      },
      { onConflict: "asin" },
    );
    if (blockError) {
      return NextResponse.json({ error: `Block ASIN failed: ${blockError.message}` }, { status: 500 });
    }
  }

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

  const updatePayload = {
    status: newStatus,
    latest_listing_snapshot_id: snapshot.listing_snapshot_id,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from("sourcing_opportunities")
    .update(updatePayload)
    .eq("opportunity_id", id)
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const relatedEbayIds = ebayIdentityValues(opportunity);
  if (relatedEbayIds.length) {
    await supabase
      .from("sourcing_opportunities")
      .update(updatePayload)
      .eq("asin", opportunity.asin)
      .in("ebay_item_id", relatedEbayIds);
  }

  if (actionType === "block_asin") {
    await supabase
      .from("sourcing_opportunities")
      .update(updatePayload)
      .eq("asin", opportunity.asin)
      .in("status", ["open", "rejected", "watching", "roi_snoozed"]);
  }

  return NextResponse.json({ opportunity: data });
}

function numberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ebayIdentityValues(opportunity: {
  ebay_item_id?: string | null;
  sourcing_ebay_candidates?: { ebay_legacy_item_id?: string | null } | null;
}) {
  const values = [
    opportunity.ebay_item_id,
    opportunity.sourcing_ebay_candidates?.ebay_legacy_item_id,
    legacyEbayItemId(opportunity.ebay_item_id),
  ];
  return [...new Set(values.map((value) => String(value ?? "").trim()).filter(Boolean))];
}

function legacyEbayItemId(value: string | null | undefined) {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) return null;
  if (/^\d+$/.test(trimmed)) return trimmed;
  if (trimmed.startsWith("v1|")) return trimmed.split("|")[1] || null;
  return null;
}
