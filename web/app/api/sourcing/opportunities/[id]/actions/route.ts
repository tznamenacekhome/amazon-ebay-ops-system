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
  inventory_snooze: "inventory_snoozed",
};

const actionRecordType: Record<string, string> = {
  block_asin: "dismissed",
  dismiss: "dismissed",
  watch: "watching",
  purchased: "purchased",
  snooze_roi: "roi_snoozed",
  inventory_snooze: "inventory_snoozed",
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
  const inventoryBaselineUnits = integerOrNull(body.inventoryBaselineUnits);
  const inventoryRepresentAtUnits = inventoryBaselineUnits === null ? null : representAtUnits(inventoryBaselineUnits);
  const myQuantity = integerOrNull(body.myQuantity);
  const myPipelineQuantity = integerOrNull(body.myPipelineQuantity);
  const myPurchasedQuantity = integerOrNull(body.myPurchasedQuantity);
  const myReceivedQuantity = integerOrNull(body.myReceivedQuantity);
  const myOutboundQuantity = integerOrNull(body.myOutboundQuantity);
  const diagnosticsFeedback = normalizeLegacyDiagnosticsFeedback(body.diagnosticsFeedback);
  const matchingFeedback = normalizeMatchingFeedback(body.diagnosticsFeedback);
  const newStatus = actionStatus[actionType];

  if (!actionRecordType[actionType]) {
    return NextResponse.json({ error: "Unsupported sourcing action." }, { status: 400 });
  }
  if (actionType === "dismiss" && !reason) {
    return NextResponse.json({ error: "Dismiss requires a reason." }, { status: 400 });
  }
  if (actionType === "inventory_snooze" && (!inventoryBaselineUnits || inventoryBaselineUnits < 1)) {
    return NextResponse.json({ error: "Wait for sell-through requires at least one in-stock or pipeline unit." }, { status: 400 });
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

  const diagnosticComparison = safeDiagnosticComparison({
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
    inventorySnooze: actionType === "inventory_snooze" ? {
      baselineUnits: inventoryBaselineUnits,
      representAtUnits: inventoryRepresentAtUnits,
      sellThroughPercent: 10,
      inStockUnits: myQuantity,
      pipelineUnits: myPipelineQuantity,
      purchasedNotReceivedUnits: myPurchasedQuantity,
      receivedNotSentUnits: myReceivedQuantity,
      outboundToAmazonUnits: myOutboundQuantity,
    } : undefined,
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

  if (actionType === "dismiss" && reason === "sales_velocity_too_low") {
    const suppressionError = await upsertSalesVelocitySuppression({
      opportunity,
      action,
    });
    if (suppressionError) {
      return NextResponse.json({ error: suppressionError }, { status: 500 });
    }
  }

  const event = actionType === "inventory_snooze"
    ? "roi_snoozed"
    : actionRecordType[actionType] === "purchased"
      ? "purchased"
      : actionRecordType[actionType];
  let snapshotId: string | null = null;
  try {
    snapshotId = await persistActionSnapshot({
      action,
      opportunity,
      event,
      reason,
      notes,
      imageClues,
      rawActionContext,
      required: actionType !== "watch",
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Sourcing action snapshot failed." },
      { status: 500 },
    );
  }

  if (snapshotId) {
    await persistImmediateMatchingExample({
      action,
      opportunity,
      snapshotId,
      reason,
      actionType,
      notes,
      rawActionContext,
    });
  }

  if (!newStatus) {
    return NextResponse.json({ opportunity });
  }

  const updatePayload: Record<string, unknown> = {
    status: newStatus,
    updated_at: new Date().toISOString(),
  };
  if (snapshotId) updatePayload.latest_listing_snapshot_id = snapshotId;

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
      .in("status", ["open", "rejected", "watching", "roi_snoozed", "inventory_snoozed"]);
  }

  if (actionType === "inventory_snooze") {
    await supabase
      .from("sourcing_opportunities")
      .update(updatePayload)
      .eq("asin", opportunity.asin)
      .in("status", ["open", "rejected", "watching", "roi_snoozed", "inventory_snoozed"]);
  }

  return NextResponse.json({ opportunity: data });
}

function safeDiagnosticComparison({
  opportunity,
  candidate,
  seed,
  diagnostics,
}: {
  opportunity: Record<string, unknown>;
  candidate: Record<string, unknown>;
  seed: Record<string, unknown>;
  diagnostics: unknown;
}) {
  try {
    return buildDiagnosticComparison({ opportunity, candidate, seed, diagnostics });
  } catch (error) {
    console.warn("Sourcing action diagnostic comparison failed", error);
    return {
      version: "unavailable",
      rows: [],
      summary: {
        matchingFields: 0,
        conflictingFields: 0,
        unknownFields: 0,
      },
    };
  }
}

async function persistActionSnapshot({
  action,
  opportunity,
  event,
  reason,
  notes,
  imageClues,
  rawActionContext,
  required,
}: {
  action: Record<string, unknown>;
  opportunity: Record<string, unknown>;
  event: string;
  reason: string | null;
  notes: string | null;
  imageClues: string[];
  rawActionContext: Record<string, unknown>;
  required: boolean;
}) {
  const { data: snapshot, error: snapshotError } = await supabase
    .from("sourcing_listing_snapshots")
    .insert(buildListingSnapshot({
      opportunity,
      candidate: (opportunity.sourcing_ebay_candidates ?? {}) as Record<string, unknown>,
      seed: (opportunity.sourcing_seed_asins ?? {}) as Record<string, unknown>,
      event,
      actionId: textOrNull(action.action_id),
      rawContext: {
        ...rawActionContext,
        dismissReason: reason,
        notes,
        imageClues,
      },
    }))
    .select("listing_snapshot_id")
    .single();

  if (snapshotError) {
    if (required) throw new Error(snapshotError.message);
    console.warn("Optional sourcing action snapshot failed", snapshotError.message);
    return null;
  }

  const snapshotId = textOrNull(snapshot?.listing_snapshot_id);
  if (!snapshotId) return null;

  await supabase
    .from("sourcing_actions")
    .update({ listing_snapshot_id: snapshotId })
    .eq("action_id", action.action_id);

  return snapshotId;
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

async function upsertSalesVelocitySuppression({
  opportunity,
  action,
}: {
  opportunity: Record<string, unknown>;
  action: Record<string, unknown>;
}) {
  const seed = objectRecord(opportunity.sourcing_seed_asins);
  const asin = textOrNull(opportunity.asin)?.toUpperCase();
  if (!asin) return "Sales velocity suppression requires an ASIN.";

  const settings = await latestSourcingSettings();
  const lookbackDays = Math.max(1, Math.floor(numberOrNull(settings?.sales_lookback_days) ?? 90));
  const requiredVelocity = roundNumber(1 / Math.max(lookbackDays / 30, 1), 4);
  const currentVelocity = numberOrNull(seed.monthly_velocity);
  const now = new Date().toISOString();
  const payload = {
    asin,
    source_action_id: action.action_id,
    dismissed_at: now,
    velocity_at_dismissal: currentVelocity,
    metric_window_days: lookbackDays,
    required_velocity: requiredVelocity,
    current_velocity: currentVelocity,
    status: "active",
    last_evaluated_at: now,
    reactivated_at: null,
    reason_code: "sales_velocity_too_low",
    raw_context_json: {
      opportunityId: opportunity.opportunity_id,
      sourcingRunId: opportunity.sourcing_run_id,
      seedId: opportunity.seed_id,
      inventoryNeedLevel: seed.inventory_need_level ?? null,
      monthsOfSupply: seed.months_of_supply ?? null,
    },
    updated_at: now,
  };
  const existing = await supabase
    .from("sourcing_sales_velocity_suppressions")
    .select("suppression_id")
    .eq("asin", asin)
    .eq("status", "active")
    .maybeSingle();
  if (existing.error) return `Sales velocity suppression lookup failed: ${existing.error.message}`;
  const { error } = existing.data?.suppression_id
    ? await supabase
      .from("sourcing_sales_velocity_suppressions")
      .update(payload)
      .eq("suppression_id", existing.data.suppression_id)
    : await supabase
      .from("sourcing_sales_velocity_suppressions")
      .insert({ ...payload, created_at: now });
  return error ? `Sales velocity suppression failed: ${error.message}` : null;
}

async function latestSourcingSettings() {
  const { data, error } = await supabase
    .from("sourcing_settings")
    .select("sales_lookback_days")
    .order("created_at", { ascending: false })
    .limit(1);
  if (error) throw new Error(`Sourcing settings: ${error.message}`);
  return data?.[0] ?? null;
}

function roundNumber(value: number, digits: number) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function integerOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : null;
}

function representAtUnits(baselineUnits: number) {
  const soldUnitsRequired = Math.max(1, Math.ceil(baselineUnits * 0.1));
  return Math.max(0, baselineUnits - soldUnitsRequired);
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
