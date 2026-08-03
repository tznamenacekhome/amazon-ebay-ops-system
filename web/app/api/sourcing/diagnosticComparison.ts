type JsonRecord = Record<string, unknown>;

export type DiagnosticComparisonRow = {
  key: string;
  label: string;
  amazon: string | null;
  ebay: string | null;
  evidence: string | null;
  kind: "identity" | "evidence" | "context";
  ruleFamily?: string;
  evidenceSource?: string;
};

export type DiagnosticComparison = {
  version: "diagnostic_comparison_v2";
  recommendation: string | null;
  hardBlocks: string[];
  warnings: string[];
  evidenceSummary: string | null;
  rows: DiagnosticComparisonRow[];
};

export function buildDiagnosticComparison({
  opportunity,
  seed,
  candidate,
  diagnostics,
}: {
  opportunity: JsonRecord;
  seed: JsonRecord;
  candidate: JsonRecord;
  diagnostics: unknown;
}): DiagnosticComparison {
  const rawEbay = objectValue(candidate.raw_ebay_json);
  const aspects = itemSpecifics(rawEbay.localizedAspects);
  const staticRules = objectValue(objectValue(diagnostics).static_rules);
  const numeric = objectValue(staticRules.numeric_identity ?? objectValue(diagnostics).numeric_identity);
  const titleOverlap = objectValue(staticRules.title_overlap ?? objectValue(diagnostics).title_overlap);
  const platformRule = objectValue(staticRules.platform_rule ?? objectValue(diagnostics).platform_rule);
  const regionRule = objectValue(staticRules.region ?? objectValue(diagnostics).region);
  const editionRule = objectValue(staticRules.edition_version ?? objectValue(diagnostics).edition_version);
  const categoryRule = objectValue(staticRules.category ?? objectValue(diagnostics).category);
  const incompleteRule = objectValue(staticRules.incomplete_product ?? objectValue(diagnostics).incomplete_product);
  const digitalRule = objectValue(staticRules.digital_download ?? objectValue(diagnostics).digital_download);
  const recommendation = textValue(objectValue(diagnostics).recommendation ?? staticRules.recommendation);
  const hardBlocks = stringArray(staticRules.hard_blocks ?? objectValue(diagnostics).hard_blocks);
  const warnings = stringArray(staticRules.warnings ?? objectValue(diagnostics).warnings ?? objectValue(diagnostics).flags)
    .filter((value) => !value.startsWith("Blocked:"));
  const amazonTitle = firstText(seed.amazon_title, opportunity.amazon_title);
  const amazonSystem = firstText(seed.system, objectValue(seed.raw_context_json).inferred_system, platformRule.amazon_system);
  const amazonImage = firstText(seed.amazon_image_url, opportunity.amazon_image_url);
  const asin = firstText(opportunity.asin, seed.asin);
  const amazonEdition = firstText(editionRule.amazon, editionRule.amazon_edition, objectValue(seed.raw_context_json).edition);
  const amazonRegion = firstText(regionRule.amazon, objectValue(seed.raw_context_json).region);

  return {
    version: "diagnostic_comparison_v2",
    recommendation,
    hardBlocks,
    warnings,
    evidenceSummary: evidenceSummary(diagnostics, titleOverlap),
    rows: [
      identityRow("core_game_identity", "Core Game", "core_game_identity", amazonTitle, textValue(candidate.ebay_title), sharedTokensText(titleOverlap)),
      identityRow("installment_number", "Installment / Sequel", "numeric_installment", identityText(numeric, "amazon"), identityText(numeric, "ebay"), numericExplanation(numeric)),
      identityRow("platform_system", "Platform", "platform", amazonSystem, textValue(aspects.Platform ?? platformRule.ebay_system), formatDiagnosticValue(platformRule.result)),
      identityRow("edition_version", "Edition / Version", "edition_version", amazonEdition, textValue(editionRule.ebay), formatDiagnosticValue(editionRule.result)),
      identityRow("region", "Region", "region", amazonRegion, textValue(aspects["Region Code"] ?? aspects.Region ?? regionRule.ebay), formatDiagnosticValue(regionRule.result)),
      identityRow("package_bundle_contents", "Package Contents", "completeness", firstText(objectValue(seed.raw_context_json).package_contents, "Standard physical software expected"), formatDiagnosticValue(aspects.Features ?? aspects["Custom Bundle"] ?? aspects.Bundle), "Package or bundle evidence"),
      identityRow("completeness", "Completeness", "completeness", "Complete physical software expected", formatDiagnosticValue(incompleteRule.result), formatDiagnosticValue(incompleteRule.reason)),
      identityRow("digital_physical", "Digital vs Physical", "digital_physical", "Physical resale expected", formatDiagnosticValue(digitalRule.result), formatDiagnosticValue(digitalRule.reason)),
      identityRow("category_product_type", "Category / Product Type", "category_product_type", null, formatDiagnosticValue(categoryName(rawEbay) ?? categoryRule.ebay), formatDiagnosticValue(categoryRule.result)),
      identityRow("seller_listing_photo_consistency", "Seller Listing / Photos", "seller_listing_photo_consistency", amazonImage, imageCount(rawEbay), "Photos available for operator review"),
      evidenceRow("amazon_title", "Amazon Title", "amazon_title", amazonTitle),
      evidenceRow("ebay_title", "eBay Title", "ebay_title", textValue(candidate.ebay_title)),
      evidenceRow("ebay_game_name", "eBay Game Name", "ebay_game_name", formatDiagnosticValue(aspects["Game Name"])),
      evidenceRow("ebay_item_specifics", "eBay Item Specifics", "ebay_item_specifics", itemSpecificSummary(aspects)),
      evidenceRow("ebay_description", "Description", "ebay_description", formatDiagnosticValue(rawEbay.description ?? rawEbay.shortDescription)),
      evidenceRow("photos", "Photos", "primary_image", imageCount(rawEbay)),
      evidenceRow("category", "Category", "category", formatDiagnosticValue(categoryName(rawEbay) ?? categoryRule.ebay)),
      evidenceRow("platform_metadata", "Platform Metadata", "platform_metadata", formatDiagnosticValue(aspects.Platform ?? platformRule.ebay_system)),
      evidenceRow("amazon_catalog_metadata", "Amazon Catalog Metadata", "amazon_catalog_metadata", amazonCatalogSummary(seed, platformRule, editionRule, regionRule)),
      contextRow("final_recommendation", "Final recommendation", null, recommendation, "Backend scoring recommendation"),
      contextRow("hard_blocks", "Hard-block reasons", null, hardBlocks.join("; ") || null, "Backend hard blocks"),
      contextRow("warnings", "Warnings", null, warnings.join("; ") || null, "Backend warnings"),
      contextRow("confidence_summary", "Confidence/evidence summary", null, evidenceSummary(diagnostics, titleOverlap), "Backend diagnostics"),
      contextRow("opportunity_context", "Opportunity context", asin, textValue(candidate.ebay_item_id), "ASIN and eBay identity"),
    ],
  };
}

function identityRow(
  key: string,
  label: string,
  ruleFamily: string,
  amazon: unknown,
  ebay: unknown,
  evidence: unknown,
): DiagnosticComparisonRow {
  return { key, label, ruleFamily, amazon: formatDiagnosticValue(amazon), ebay: formatDiagnosticValue(ebay), evidence: formatDiagnosticValue(evidence), kind: "identity" };
}

function evidenceRow(key: string, label: string, evidenceSource: string, value: unknown): DiagnosticComparisonRow {
  return { key, label, evidenceSource, amazon: null, ebay: formatDiagnosticValue(value), evidence: null, kind: "evidence" };
}

function contextRow(key: string, label: string, amazon: unknown, ebay: unknown, evidence: unknown): DiagnosticComparisonRow {
  return { key, label, amazon: formatDiagnosticValue(amazon), ebay: formatDiagnosticValue(ebay), evidence: formatDiagnosticValue(evidence), kind: "context" };
}

function objectValue(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function textValue(value: unknown): string | null {
  return formatDiagnosticValue(value);
}

function firstText(...values: unknown[]): string | null {
  for (const value of values) {
    const text = textValue(value);
    if (text) return text;
  }
  return null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item ?? "").trim()).filter(Boolean) : [];
}

function itemSpecifics(value: unknown): JsonRecord {
  const output: JsonRecord = {};
  if (!Array.isArray(value)) return output;
  for (const row of value) {
    const record = objectValue(row);
    const name = textValue(record.name);
    if (!name) continue;
    const valueText = textValue(record.value ?? record.values);
    if (valueText) output[name] = valueText;
  }
  return output;
}

function categoryName(rawEbay: JsonRecord): string | null {
  const categories = rawEbay.categories;
  if (Array.isArray(categories)) {
    const first = objectValue(categories[0]);
    return textValue(first.categoryName ?? first.categoryId);
  }
  return textValue(rawEbay.categoryPath ?? rawEbay.categoryId);
}

function imageCount(rawEbay: JsonRecord): string | null {
  const urls = new Set<string>();
  const image = textValue(objectValue(rawEbay.image).imageUrl);
  if (image) urls.add(image);
  for (const key of ["thumbnailImages", "additionalImages"]) {
    const values = rawEbay[key];
    if (!Array.isArray(values)) continue;
    for (const value of values) {
      const url = textValue(objectValue(value).imageUrl);
      if (url) urls.add(url);
    }
  }
  return urls.size ? `${urls.size} image${urls.size === 1 ? "" : "s"} available` : null;
}

function identityText(numeric: JsonRecord, side: "amazon" | "ebay") {
  const identities = objectValue(numeric[`${side}_identity_numbers`]);
  const base = stringArray(numeric[`${side}_base_identities`]);
  const parts = Object.entries(identities).flatMap(([family, values]) =>
    stringArray(values).map((value) => `${family} ${value}`),
  );
  parts.push(...base.map((value) => `${value} base`));
  return parts.join(", ") || null;
}

function numericExplanation(numeric: JsonRecord) {
  const parts = [
    labeledValue("Result", numeric.result),
    labeledValue("Comparison", numeric.comparison),
    labeledValue("Amazon installment identity", identityText(numeric, "amazon")),
    labeledValue("eBay installment identity", identityText(numeric, "ebay")),
    labeledValue("Ignored platform numbers", numeric.ignored_platform_numbers),
    labeledValue("Ignored release years", numeric.ignored_release_years),
    labeledValue("Ignored quantities", numeric.ignored_quantity_numbers),
    labeledValue("Explanation", numeric.reason),
  ].filter(Boolean);
  return parts.join("; ") || null;
}

function sharedTokensText(titleOverlap: JsonRecord) {
  const shared = formatDiagnosticValue(titleOverlap.shared_title_tokens);
  const result = formatDiagnosticValue(titleOverlap.result);
  return [shared ? `Shared title tokens: ${shared}` : null, result ? `Result: ${result}` : null].filter(Boolean).join("; ") || null;
}

function evidenceSummary(diagnostics: unknown, titleOverlap: JsonRecord) {
  const recommendation = textValue(objectValue(diagnostics).recommendation);
  const overlap = formatDiagnosticValue(titleOverlap.shared_title_tokens);
  return [recommendation ? `Recommendation: ${recommendation}` : null, overlap ? `Shared title tokens: ${overlap}` : null]
    .filter(Boolean)
    .join("; ") || null;
}

function itemSpecificSummary(aspects: JsonRecord) {
  const entries = Object.entries(aspects)
    .map(([key, value]) => labeledValue(key, value))
    .filter(Boolean)
    .slice(0, 8);
  return entries.join("; ") || null;
}

function amazonCatalogSummary(seed: JsonRecord, platformRule: JsonRecord, editionRule: JsonRecord, regionRule: JsonRecord) {
  const rawContext = objectValue(seed.raw_context_json);
  const entries = [
    labeledValue("ASIN", seed.asin),
    labeledValue("System", seed.system ?? rawContext.inferred_system ?? platformRule.amazon_system),
    labeledValue("Edition", editionRule.amazon ?? rawContext.edition),
    labeledValue("Region", regionRule.amazon ?? rawContext.region),
    labeledValue("Product group", rawContext.keepa_product_group),
    labeledValue("Category", rawContext.keepa_category_tree),
  ].filter(Boolean);
  return entries.join("; ") || null;
}

function labeledValue(label: string, value: unknown) {
  const text = formatDiagnosticValue(value);
  return text ? `${label}: ${text}` : null;
}

function formatDiagnosticValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") {
    const text = value.trim();
    return text || null;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    const text = value.map(formatDiagnosticValue).filter(Boolean).join(", ");
    return text || null;
  }
  if (typeof value === "object") {
    const record = value as JsonRecord;
    const preferred = [
      labeledValue("Result", record.result),
      labeledValue("Reason", record.reason),
      labeledValue("Summary", record.summary),
      labeledValue("Recommendation", record.recommendation),
      labeledValue("Comparison", record.comparison),
    ].filter(Boolean);
    if (preferred.length) return preferred.join("; ");
    const entries = Object.entries(record)
      .filter(([, item]) => item !== null && item !== undefined)
      .slice(0, 6)
      .map(([key, item]) => labeledValue(labelFromKey(key), item))
      .filter(Boolean);
    return entries.join("; ") || null;
  }
  return String(value);
}

function labelFromKey(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
