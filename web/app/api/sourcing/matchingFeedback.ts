const VERSION = "matching_feedback_v3";

const ruleFamilies = new Set([
  "core_game_identity",
  "numeric_installment",
  "platform",
  "edition_version",
  "region",
  "completeness",
  "digital_physical",
  "category_product_type",
  "seller_listing_photo_consistency",
  "other",
]);

const evidenceSources = new Set([
  "amazon_title",
  "ebay_title",
  "ebay_game_name",
  "ebay_item_specifics",
  "amazon_catalog_metadata",
  "ebay_description",
  "primary_image",
  "additional_images",
  "category",
  "platform_metadata",
  "other",
]);

const legacyRuleFamily: Record<string, string> = {
  core_game_identity: "core_game_identity",
  platform_system: "platform",
  installment_number: "numeric_installment",
  numeric_installment: "numeric_installment",
  edition_version: "edition_version",
  region: "region",
  package_bundle_contents: "completeness",
  completeness: "completeness",
  digital_physical: "digital_physical",
  category: "category_product_type",
  format_type: "category_product_type",
  seller_listing_photo_consistency: "seller_listing_photo_consistency",
};

const legacyEvidenceSource: Record<string, string[]> = {
  full_title: ["amazon_title", "ebay_title"],
  game_name: ["ebay_game_name"],
  platform_system: ["platform_metadata"],
  category: ["category"],
  format_type: ["ebay_item_specifics"],
  release_year: ["ebay_item_specifics"],
  package_bundle_contents: ["ebay_item_specifics"],
  seller_listing_photo_consistency: ["primary_image", "additional_images"],
  item_location: ["other"],
};

const familyEvidenceDefaults: Record<string, string[]> = {
  core_game_identity: ["amazon_title", "ebay_title", "ebay_game_name"],
  numeric_installment: ["amazon_title", "ebay_title", "ebay_item_specifics"],
  platform: ["amazon_title", "ebay_title", "platform_metadata", "ebay_item_specifics"],
  edition_version: ["amazon_title", "ebay_title", "ebay_item_specifics"],
  region: ["ebay_item_specifics", "category"],
  completeness: ["ebay_title", "ebay_item_specifics", "ebay_description", "primary_image", "additional_images"],
  digital_physical: ["ebay_title", "ebay_item_specifics", "ebay_description", "category"],
  category_product_type: ["category", "ebay_item_specifics", "ebay_title"],
  seller_listing_photo_consistency: ["primary_image", "additional_images", "ebay_title"],
  other: ["other"],
};

export type MatchingFeedback = {
  version: typeof VERSION | "matching_feedback_v2";
  allAssumptionsCorrect: boolean;
  failedRuleFamilies: string[];
  evidenceSources: string[];
  legacyIncorrectRows: string[];
  note: string | null;
  pairVerdict: "correct" | "incorrect" | "unsure" | "not_provided";
  corrections: Array<{ field: string; side: "amazon" | "ebay"; scope: "pair" | "asin"; state: string; value: string | null; note: string | null; before?: unknown }>;
  availableEvidenceSources: string[];
  evidenceProvenance: "explicit" | "legacy_mixed";
};

export function normalizeMatchingFeedback(value: unknown): MatchingFeedback {
  let record = objectRecord(value);
  const nested = objectRecord(record.matchingFeedback);
  if (Object.keys(nested).length) record = nested;
  const current = record.version === VERSION;

  const allAssumptionsCorrect = record.allAssumptionsCorrect === true;
  const legacyIncorrectRows = unique([
    ...stringList(record.legacyIncorrectRows),
    ...stringList(record.incorrectRows),
  ]);
  const failedRuleFamilies = allAssumptionsCorrect
    ? []
    : unique([
        ...normalizeValues(record.failedRuleFamilies, ruleFamilies),
        ...legacyIncorrectRows
          .map((row) => legacyRuleFamily[row] ?? (legacyEvidenceSource[row] ? "" : "other"))
          .filter(Boolean),
      ]);
  const evidenceSourcesForFailures = failedRuleFamilies.flatMap((family) => familyEvidenceDefaults[family] ?? ["other"]);
  const evidenceSourcesForLegacyRows = legacyIncorrectRows.flatMap((row) => legacyEvidenceSource[row] ?? []);
  const normalizedEvidenceSources = allAssumptionsCorrect && !current
    ? []
    : unique([
        ...normalizeValues(record.evidenceSources, evidenceSources),
        ...(current ? [] : evidenceSourcesForLegacyRows),
        ...(current ? [] : evidenceSourcesForFailures),
      ]);

  return {
    version: current ? VERSION : "matching_feedback_v2",
    allAssumptionsCorrect,
    failedRuleFamilies,
    evidenceSources: normalizedEvidenceSources,
    legacyIncorrectRows: allAssumptionsCorrect ? [] : legacyIncorrectRows,
    note: typeof record.note === "string" && record.note.trim() ? record.note.trim() : null,
    pairVerdict: ["correct", "incorrect", "unsure"].includes(String(record.pairVerdict)) ? record.pairVerdict as "correct" | "incorrect" | "unsure" : "not_provided",
    corrections: normalizeCorrections(record.corrections),
    availableEvidenceSources: normalizeValues(record.availableEvidenceSources, evidenceSources),
    evidenceProvenance: current ? "explicit" : "legacy_mixed",
  };
}

export function normalizeCorrections(value: unknown): MatchingFeedback["corrections"] {
  if (!Array.isArray(value)) return [];
  if (value.length > 20) throw new Error("At most 20 field corrections can be saved together.");
  const fields = new Set(["coreGame", "installment", "generation", "theme", "platform", "edition", "region", "packageType", "completeness", "digitalPhysical"]);
  return value.map((item) => {
    const row = objectRecord(item);
    if (!fields.has(String(row.field)) || !["amazon", "ebay"].includes(String(row.side)) || !["pair", "asin"].includes(String(row.scope)) || (row.scope === "asin" && row.side !== "amazon")) throw new Error("Invalid correction field, side or scope.");
    if (!["value", "unknown", "explicitly_absent", "not_applicable"].includes(String(row.state))) throw new Error("Choose a correction value or an explicit unknown/absent/not-applicable state.");
    const text = typeof row.value === "string" ? row.value.trim().slice(0, 500) : null;
    if (row.state === "value" && !text) throw new Error("A corrected value is required.");
    return {field: String(row.field), side: row.side as "amazon" | "ebay", scope: row.scope as "pair" | "asin", state: String(row.state), value: row.state === "value" ? text : null, note: typeof row.note === "string" ? row.note.slice(0,500) : null};
  });
}

export function reviewSemantics(action: string, reason: string | null, verdict: MatchingFeedback["pairVerdict"]) {
  const identity = ["wrong_product","wrong_edition_version","wrong_platform","digital_item","incomplete_product","non_north_american_version"];
  const seller = ["listing_error","seller_listing_mismatch"];
  const condition = ["missing_shrink_wrap","suspected_reseal","packaging_damage","packaging_condition_issue","nfr"];
  const business = ["roi_too_low","sales_velocity_too_low","asin_blocked","duplicate_open_asin_opportunity","inventory_snoozed","no_longer_available"];
  const category = identity.includes(reason ?? "") ? "identity" : seller.includes(reason ?? "") ? "seller_listing" : condition.includes(reason ?? "") ? "condition" : business.includes(reason ?? "") ? "business" : "unspecified";
  const pairVerdict = action === "mark_valid_match" ? "correct" : category === "identity" ? "incorrect" : verdict;
  const label = pairVerdict === "correct" ? {match_label:"match",label_type:"positive_identity"} : pairVerdict === "incorrect" ? {match_label:"non_match",label_type:"negative_identity"} : category === "seller_listing" ? {match_label:"non_match",label_type:"negative_identity"} : category === "condition" ? {match_label:"condition_problem",label_type:"condition_issue"} : category === "business" ? {match_label:"valid_match_poor_opportunity",label_type:"business_issue"} : {match_label:"needs_review",label_type:"unknown"};
  return {pairVerdict, category, label, learningScope: "exact_pair"};
}

function normalizeValues(value: unknown, allowed: Set<string>) {
  return stringList(value).map((item) => allowed.has(item) ? item : "other");
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.map(normalizeKey).filter(Boolean);
}

function normalizeKey(value: unknown) {
  return String(value ?? "").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
}

function unique(values: string[]) {
  return [...new Set(values.filter(Boolean))];
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
