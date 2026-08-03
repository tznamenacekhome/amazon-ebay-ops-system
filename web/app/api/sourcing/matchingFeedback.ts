const VERSION = "matching_feedback_v2";

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
  version: typeof VERSION;
  allAssumptionsCorrect: boolean;
  failedRuleFamilies: string[];
  evidenceSources: string[];
  legacyIncorrectRows: string[];
  note: string | null;
};

export function normalizeMatchingFeedback(value: unknown): MatchingFeedback {
  let record = objectRecord(value);
  const nested = objectRecord(record.matchingFeedback);
  if (Object.keys(nested).length) record = nested;

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
  const normalizedEvidenceSources = allAssumptionsCorrect
    ? []
    : unique([
        ...normalizeValues(record.evidenceSources, evidenceSources),
        ...evidenceSourcesForLegacyRows,
        ...evidenceSourcesForFailures,
      ]);

  return {
    version: VERSION,
    allAssumptionsCorrect,
    failedRuleFamilies,
    evidenceSources: normalizedEvidenceSources,
    legacyIncorrectRows: allAssumptionsCorrect ? [] : legacyIncorrectRows,
    note: typeof record.note === "string" && record.note.trim() ? record.note.trim() : null,
  };
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
