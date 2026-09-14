export type PlatformRelationship = "match" | "compatible" | "wrong" | "unknown";
export type PlatformRelationshipFeedback = {
  field: "platform";
  operatorRelationship: PlatformRelationship;
  compatiblePlatforms?: { amazon: string[]; ebay: string[] };
};

export function amazonListingUrl(asin: string | null | undefined) {
  return asin && /^[A-Z0-9]{10}$/.test(asin) ? `https://www.amazon.com/dp/${asin}` : null;
}
export function ebayListingUrl(itemId: string | null | undefined) {
  if (!itemId) return null;
  const numeric = /^\d+$/.test(itemId) ? itemId : /^v1\|(\d+)\|\d+$/.exec(itemId)?.[1];
  return numeric ? `https://www.ebay.com/itm/${numeric}` : null;
}
export function normalizePlatformRelationships(value: unknown): PlatformRelationshipFeedback[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > 1) throw new Error("Only one platform relationship may be submitted.");
  return value.map(item => {
    if (!item || item.field !== "platform" || !["match", "compatible", "wrong", "unknown"].includes(item.operatorRelationship)) {
      throw new Error("Choose a valid platform relationship.");
    }
    const result: PlatformRelationshipFeedback = {field: "platform", operatorRelationship: item.operatorRelationship};
    if (item.compatiblePlatforms !== undefined) {
      const supports = (values: unknown) => {
        if (!Array.isArray(values) || values.length > 8 || values.some(v => typeof v !== "string" || !v.trim() || v.length > 100)) {
          throw new Error("Platform support must be a list of up to eight names per side.");
        }
        return [...new Set(values.map((v: string) => v.trim()))];
      };
      result.compatiblePlatforms = {amazon: supports(item.compatiblePlatforms?.amazon), ebay: supports(item.compatiblePlatforms?.ebay)};
    }
    return result;
  });
}

// Explicit review-sample policy only. Never imported by matching/routing code.
export function adjudicationExclusion(row: {asin: string; ebayLegacyItemId: string}) {
  return row.asin === "B072JZB85B" && row.ebayLegacyItemId === "233733278405"
    ? "not useful as exact single-product validation sample; mixed/random lot intentionally left as-is"
    : null;
}
