import { NextRequest, NextResponse } from "next/server";
import { supabase } from "../../../_supabase";
import { buildDiagnosticComparison } from "../../../diagnosticComparison";
import { buildListingSnapshot } from "../../../matchingIntelligence";
import { normalizeMatchingFeedback } from "../../../matchingFeedback";
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
  mark_valid_match: "confirmed_valid_match",
  confirm_exclusion: "confirmed_exclusion",
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
  const diagnosticsFeedback = normalizeLegacyDiagnosticsFeedback(body.diagnosticsFeedback);
  const matchingFeedback = normalizeMatchingFeedback(body.diagnosticsFeedback);
  const newStatus = actionStatus[actionType];

  if (!actionRecordType[actionType]) {
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

  const diagnosticComparison = buildDiagnosticComparison({
    opportunity: opportunity as Record<string, unknown>,
    candidate: (opportunity.sourcing_ebay_candidates ?? {}) as Record<string, unknown>,
    seed: (opportunity.sourcing_seed_asins ?? {}) as Record<string, unknown>,
    diagnostics: opportunity.matching_diagnostics_json,
  });

  const rawActionContext = {
    actionType,
    blockedAsin: actionType === "block_asin",
    previousStatus: opportunity.status,
    newStatus: newStatus ?? opportunity.status,
    requiredMaxLandedCost,
    requiredRoiPercent,
    expectedPurchaseCost,
    imageClues,
    diagnosticsFeedback,
    matchingFeedback,
    diagnosticComparison,
    diagnosticVersion: diagnosticComparison.version,
    evidenceSource: reason === "seller_listing_mismatch" ? "image_conflict" : undefined,
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

  await persistImmediateMatchingExample({
    action,
    opportunity,
    snapshotId: snapshot.listing_snapshot_id,
    reason,
    actionType,
    notes,
    rawActionContext,
  });

  if (!newStatus) {
    return NextResponse.json({ opportunity });
  }

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

function normalizeLegacyDiagnosticsFeedback(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {
      allAssumptionsCorrect: false,
      incorrectRows: [],
      note: null,
    };
  }
  const record = value as Record<string, unknown>;
  const allAssumptionsCorrect = record.allAssumptionsCorrect === true;
  const incorrectRows = Array.isArray(record.incorrectRows)
    ? record.incorrectRows.map((row) => String(row)).filter(Boolean)
    : Array.isArray(record.legacyIncorrectRows)
      ? record.legacyIncorrectRows.map((row) => String(row)).filter(Boolean)
    : [];
  return {
    allAssumptionsCorrect,
    incorrectRows: allAssumptionsCorrect ? [] : incorrectRows,
    note: typeof record.note === "string" && record.note.trim() ? record.note.trim() : null,
  };
}

async function persistImmediateMatchingExample({
  action,
  opportunity,
  snapshotId,
  reason,
  actionType,
  notes,
  rawActionContext,
}: {
  action: Record<string, unknown>;
  opportunity: Record<string, unknown>;
  snapshotId: string;
  reason: string | null;
  actionType: string;
  notes: string | null;
  rawActionContext: Record<string, unknown>;
}) {
  const label = immediateLabel(actionType, reason);
  if (!label) return;
  const candidate = objectRecord(opportunity.sourcing_ebay_candidates);
  const seed = objectRecord(opportunity.sourcing_seed_asins);
  const rawEbay = objectRecord(candidate.raw_ebay_json);
  const now = new Date().toISOString();
  const { error } = await supabase.from("matching_intelligence_examples").insert(
    {
      source_table: "sourcing_actions",
      source_id: textOrNull(action.action_id),
      source_detail: textOrNull(action.action_type),
      source_weight: label.match_label === "match" ? 7 : 8,
      listing_snapshot_id: snapshotId,
      opportunity_id: textOrNull(opportunity.opportunity_id),
      candidate_id: textOrNull(opportunity.candidate_id),
      action_id: textOrNull(action.action_id),
      asin: textOrNull(opportunity.asin),
      amazon_title: seed.amazon_title ?? null,
      amazon_image_url: seed.amazon_image_url ?? null,
      amazon_system: seed.system ?? null,
      ebay_item_id: candidate.ebay_item_id ?? opportunity.ebay_item_id ?? null,
      ebay_legacy_item_id: candidate.ebay_legacy_item_id ?? legacyEbayItemId(textOrNull(candidate.ebay_item_id ?? opportunity.ebay_item_id)),
      ebay_title: candidate.ebay_title ?? null,
      ebay_primary_image_url: candidate.ebay_image_url ?? null,
      ebay_item_specifics_json: Array.isArray(rawEbay.localizedAspects) ? rawEbay.localizedAspects : null,
      ebay_condition: candidate.condition ?? null,
      ebay_category: ebayCategory(rawEbay),
      ebay_seller_username: candidate.seller_username ?? null,
      detected_system: seed.system ?? null,
      operator_action: textOrNull(action.action_type),
      dismiss_reason: label.dismiss_reason,
      dismissal_note: notes,
      match_label: label.match_label,
      label_type: label.label_type,
      confidence: label.confidence,
      evidence_strength: label.evidence_strength,
      raw_context_json: rawActionContext,
      created_at: now,
      reviewed_at: now,
      rebuilt_at: now,
    },
  );
  if (error) console.warn("Immediate matching-intelligence example insert failed", error.message);
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textOrNull(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function immediateLabel(actionType: string, reason: string | null) {
  if (actionType === "mark_valid_match") {
    return { match_label: "match", label_type: "positive_identity", dismiss_reason: null, confidence: 1, evidence_strength: "high" };
  }
  if (actionType === "confirm_exclusion") {
    return { match_label: "non_match", label_type: "negative_identity", dismiss_reason: reason || "wrong_product", confidence: 1, evidence_strength: "high" };
  }
  if (actionType === "dismiss" && reason === "seller_listing_mismatch") {
    return { match_label: "non_match", label_type: "negative_identity", dismiss_reason: reason, confidence: 1, evidence_strength: "high" };
  }
  return null;
}

function ebayCategory(raw: unknown) {
  if (!raw || typeof raw !== "object") return null;
  const categories = (raw as { categories?: unknown }).categories;
  if (Array.isArray(categories) && categories[0] && typeof categories[0] === "object") {
    return String((categories[0] as { categoryName?: unknown }).categoryName ?? "") || null;
  }
  return String((raw as { categoryPath?: unknown }).categoryPath ?? "") || null;
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
