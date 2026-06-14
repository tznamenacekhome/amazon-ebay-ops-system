import { NextResponse } from "next/server";
import { supabase } from "../_supabase";

type ExampleRow = {
  asin: string | null;
  amazon_title: string | null;
  ebay_title: string | null;
  match_label: string | null;
  label_type: string | null;
  dismiss_reason: string | null;
  dismissal_note: string | null;
  listing_snapshot_id: string | null;
  raw_context_json: Record<string, unknown> | null;
  source_table: string | null;
  ebay_seller_username: string | null;
  created_at: string | null;
};

type ActionRow = {
  action_type: string | null;
  dismiss_reason: string | null;
  notes: string | null;
  opportunity_id: string | null;
  created_at: string | null;
};

type PurchaseMatchRow = {
  opportunity_id: string | null;
  match_id: string | null;
};

type SellerRow = {
  seller_status: string | null;
  seller_username: string | null;
  seller_trust_score: number | null;
  product_condition_return_count: number | null;
  opportunity_count: number | null;
  purchase_conversion_count: number | null;
};

export async function GET() {
  const [examplesResult, snapshotsResult, sellersResult, actionsResult, purchaseMatchesResult] = await Promise.all([
    supabase
      .from("matching_intelligence_examples")
      .select("asin,amazon_title,ebay_title,match_label,label_type,dismiss_reason,dismissal_note,listing_snapshot_id,raw_context_json,source_table,ebay_seller_username,created_at")
      .order("created_at", { ascending: false })
      .limit(5000),
    supabase
      .from("sourcing_listing_snapshots")
      .select("listing_snapshot_id,snapshot_event")
      .limit(5000),
    supabase
      .from("sourcing_seller_intelligence")
      .select("seller_status,seller_username,seller_trust_score,product_condition_return_count,opportunity_count,purchase_conversion_count")
      .order("seller_trust_score", { ascending: true })
      .limit(500),
    supabase
      .from("sourcing_actions")
      .select("action_type,dismiss_reason,notes,opportunity_id,created_at")
      .order("created_at", { ascending: false })
      .limit(5000),
    supabase
      .from("sourcing_purchase_matches")
      .select("opportunity_id,match_id")
      .limit(5000),
  ]);

  if (examplesResult.error) return NextResponse.json({ error: examplesResult.error.message }, { status: 500 });
  if (snapshotsResult.error) return NextResponse.json({ error: snapshotsResult.error.message }, { status: 500 });
  if (sellersResult.error) return NextResponse.json({ error: sellersResult.error.message }, { status: 500 });
  if (actionsResult.error) return NextResponse.json({ error: actionsResult.error.message }, { status: 500 });
  if (purchaseMatchesResult.error) return NextResponse.json({ error: purchaseMatchesResult.error.message }, { status: 500 });

  const examples = (examplesResult.data ?? []) as ExampleRow[];
  const sellers = (sellersResult.data ?? []) as SellerRow[];
  const actions = (actionsResult.data ?? []) as ActionRow[];
  const purchaseMatches = (purchaseMatchesResult.data ?? []) as PurchaseMatchRow[];
  const snapshots = snapshotsResult.data ?? [];
  const purchaseMatchedOpportunityIds = new Set(
    purchaseMatches.map((row) => row.opportunity_id).filter(Boolean),
  );
  const examplesMissingNotes = examples.filter(
    (row) =>
      row.source_table === "sourcing_actions" &&
      row.dismiss_reason &&
      !["no_longer_available"].includes(row.dismiss_reason) &&
      !String(row.dismissal_note ?? "").trim(),
  );

  return NextResponse.json({
    refreshedAt: new Date().toISOString(),
    summary: {
      exampleCount: examples.length,
      snapshotCount: snapshots.length,
      sellerCount: sellers.length,
      examplesWithNotes: examples.filter((row) => String(row.dismissal_note ?? "").trim()).length,
      examplesWithSnapshots: examples.filter((row) => row.listing_snapshot_id).length,
      reviewedOpportunityCount: new Set(actions.map((row) => row.opportunity_id).filter(Boolean)).size,
      actionCount: actions.length,
      missingDismissalNotes: examplesMissingNotes.length,
      purchasedOrOfferedCount: actions.filter((row) => ["purchased", "offer_made"].includes(String(row.action_type ?? ""))).length,
      purchasedOrOfferedMatchedCount: actions.filter(
        (row) =>
          ["purchased", "offer_made"].includes(String(row.action_type ?? "")) &&
          row.opportunity_id &&
          purchaseMatchedOpportunityIds.has(row.opportunity_id),
      ).length,
    },
    countsByLabel: countBy(examples, (row) => row.match_label ?? "unknown"),
    countsByLabelType: countBy(examples, (row) => row.label_type ?? "unknown"),
    countsByDismissReason: countBy(examples.filter((row) => row.dismiss_reason), (row) => row.dismiss_reason ?? "unknown"),
    dismissalReasonStats: dismissalStats(actions),
    countsByImageClue: imageClueStats(examples),
    countsBySourcingAction: countBy(actions, (row) => row.action_type ?? "unknown"),
    countsBySource: countBy(examples, (row) => row.source_table ?? "unknown"),
    countsBySnapshotEvent: countBy(snapshots, (row) => String(row.snapshot_event ?? "unknown")),
    countsBySellerStatus: countBy(sellers, (row) => row.seller_status ?? "unknown"),
    recentNotes: examples
      .filter((row) => row.dismiss_reason && String(row.dismissal_note ?? "").trim())
      .slice(0, 25)
      .map((row) => ({
        reason: row.dismiss_reason,
        note: row.dismissal_note,
        label: row.match_label,
        source: row.source_table,
        createdAt: row.created_at,
      })),
    sellersToWatch: sellers
      .filter((row) => ["avoid", "watch"].includes(String(row.seller_status ?? "")))
      .slice(0, 25)
      .map((row) => ({
        sellerUsername: row.seller_username,
        status: row.seller_status,
        trustScore: row.seller_trust_score,
        productConditionReturns: row.product_condition_return_count,
        opportunities: row.opportunity_count,
        purchases: row.purchase_conversion_count,
      })),
    nearMisses: nearMisses(examples).slice(0, 50),
  });
}

function dismissalStats(actions: ActionRow[]) {
  const byReason = new Map<string, { key: string; count: number; withNotes: number }>();
  for (const row of actions) {
    if (!row.dismiss_reason) continue;
    const key = row.dismiss_reason;
    const current = byReason.get(key) ?? { key, count: 0, withNotes: 0 };
    current.count += 1;
    if (String(row.notes ?? "").trim()) current.withNotes += 1;
    byReason.set(key, current);
  }
  return [...byReason.values()]
    .map((row) => ({
      ...row,
      withoutNotes: row.count - row.withNotes,
      noteRate: row.count ? Math.round((row.withNotes / row.count) * 1000) / 10 : 0,
    }))
    .sort((left, right) => right.count - left.count || left.key.localeCompare(right.key));
}

function imageClueStats(examples: ExampleRow[]) {
  const clues: string[] = [];
  for (const example of examples) {
    const context = example.raw_context_json;
    const action = context && typeof context === "object" ? context.action : null;
    const rawActionContext =
      action && typeof action === "object" && !Array.isArray(action)
        ? (action as Record<string, unknown>).raw_action_context
        : null;
    if (rawActionContext && typeof rawActionContext === "object" && !Array.isArray(rawActionContext)) {
      const imageClues = (rawActionContext as Record<string, unknown>).imageClues;
      if (Array.isArray(imageClues)) clues.push(...imageClues.map(String));
    }
  }
  return countBy(clues, (row) => row);
}

function nearMisses(examples: ExampleRow[]) {
  const positivesByAsin = new Map<string, ExampleRow[]>();
  for (const row of examples) {
    if (row.match_label !== "match" || !row.asin) continue;
    positivesByAsin.set(row.asin, [...(positivesByAsin.get(row.asin) ?? []), row]);
  }

  const results = [];
  for (const row of examples) {
    if (!row.asin || !["non_match", "condition_problem"].includes(String(row.match_label ?? ""))) continue;
    const candidateTokens = titleTokens(row.ebay_title);
    if (candidateTokens.size === 0) continue;
    let bestScore = 0;
    let bestPositive: ExampleRow | null = null;
    for (const positive of positivesByAsin.get(row.asin) ?? []) {
      const score = jaccard(candidateTokens, titleTokens(positive.ebay_title));
      if (score > bestScore) {
        bestScore = score;
        bestPositive = positive;
      }
    }
    if (bestScore >= 0.55) {
      results.push({
        asin: row.asin,
        amazonTitle: row.amazon_title,
        rejectedTitle: row.ebay_title,
        positiveTitle: bestPositive?.ebay_title ?? null,
        reason: row.dismiss_reason,
        label: row.match_label,
        similarity: Math.round(bestScore * 1000) / 10,
        note: row.dismissal_note,
        createdAt: row.created_at,
      });
    }
  }
  return results.sort((left, right) => right.similarity - left.similarity);
}

function titleTokens(value: string | null) {
  const stop = new Set(["new", "sealed", "game", "video", "nintendo", "playstation", "ps2", "ps3", "ps4", "ps5", "xbox", "one", "switch", "wii", "u"]);
  return new Set(
    String(value ?? "")
      .toLowerCase()
      .match(/[a-z0-9]+/g)
      ?.filter((token) => token.length > 1 && !stop.has(token)) ?? [],
  );
}

function jaccard(left: Set<string>, right: Set<string>) {
  if (!left.size || !right.size) return 0;
  const intersection = [...left].filter((token) => right.has(token)).length;
  const union = new Set([...left, ...right]).size;
  return union ? intersection / union : 0;
}

function countBy<T>(rows: T[], keyFor: (row: T) => string) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = keyFor(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((left, right) => right.count - left.count || left.key.localeCompare(right.key));
}
