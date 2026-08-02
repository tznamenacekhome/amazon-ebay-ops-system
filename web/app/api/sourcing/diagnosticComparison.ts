type JsonRecord = Record<string, unknown>;

export type DiagnosticComparisonRow = {
  key: string;
  label: string;
  amazon: string | null;
  ebay: string | null;
  evidence: string | null;
};

export type DiagnosticComparison = {
  version: "diagnostic_comparison_v1";
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

  return {
    version: "diagnostic_comparison_v1",
    recommendation,
    hardBlocks,
    warnings,
    evidenceSummary: evidenceSummary(diagnostics, titleOverlap),
    rows: [
      row("core_game_identity", "Core game identity", textValue(seed.amazon_title), textValue(candidate.ebay_title), textValue(titleOverlap.shared_title_tokens)),
      row("full_title", "Full title", textValue(seed.amazon_title), textValue(candidate.ebay_title), "Title evidence"),
      row("platform_system", "Platform/system", textValue(seed.system), textValue(aspects.Platform ?? platformRule.ebay_system), textValue(platformRule.result)),
      row("installment_number", "Installment/sequel number", identityText(numeric, "amazon"), identityText(numeric, "ebay"), textValue(numeric.comparison)),
      row("edition_version", "Edition/version", textValue(editionRule.amazon), textValue(editionRule.ebay), textValue(editionRule.result)),
      row("region", "Region", textValue(regionRule.amazon), textValue(aspects["Region Code"] ?? aspects.Region ?? regionRule.ebay), textValue(regionRule.result)),
      row("game_name", "eBay Game Name item specific", null, textValue(aspects["Game Name"]), "eBay item specific"),
      row("category", "Category", null, textValue(categoryName(rawEbay) ?? categoryRule.ebay), textValue(categoryRule.result)),
      row("format_type", "Format/type", null, textValue(aspects.Format ?? aspects.Type ?? candidate.condition), "eBay item specifics"),
      row("release_year", "Release year", null, textValue(aspects["Release Year"]), "eBay item specific"),
      row("package_bundle_contents", "Package/bundle contents", null, textValue(aspects.Features ?? aspects["Custom Bundle"] ?? aspects.Bundle), "eBay item specifics"),
      row("completeness", "Completeness", null, textValue(incompleteRule.result), textValue(incompleteRule.reason)),
      row("digital_physical", "Digital versus physical", "Physical resale expected", textValue(digitalRule.result), textValue(digitalRule.reason)),
      row("item_location", "Item location", null, textValue(candidate.item_location_country ?? objectValue(rawEbay.itemLocation).country), "eBay item location"),
      row("seller_listing_photo_consistency", "Seller listing/photo consistency", null, imageCount(rawEbay), "Photos available for operator review"),
      row("final_recommendation", "Final recommendation", null, recommendation, "Backend scoring recommendation"),
      row("hard_blocks", "Hard-block reasons", null, hardBlocks.join("; ") || null, "Backend hard blocks"),
      row("warnings", "Warnings", null, warnings.join("; ") || null, "Backend warnings"),
      row("confidence_summary", "Confidence/evidence summary", null, evidenceSummary(diagnostics, titleOverlap), "Backend diagnostics"),
      row("opportunity_context", "Opportunity context", textValue(opportunity.asin), textValue(candidate.ebay_item_id), "ASIN and eBay identity"),
    ],
  };
}

function row(key: string, label: string, amazon: string | null, ebay: string | null, evidence: string | null): DiagnosticComparisonRow {
  return { key, label, amazon, ebay, evidence };
}

function objectValue(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function textValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    const text = value.map((item) => String(item ?? "").trim()).filter(Boolean).join(", ");
    return text || null;
  }
  const text = String(value ?? "").trim();
  return text || null;
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

function evidenceSummary(diagnostics: unknown, titleOverlap: JsonRecord) {
  const recommendation = textValue(objectValue(diagnostics).recommendation);
  const overlap = textValue(titleOverlap.shared_title_tokens);
  return [recommendation ? `Recommendation: ${recommendation}` : null, overlap ? `Shared title tokens: ${overlap}` : null]
    .filter(Boolean)
    .join("; ") || null;
}
