type JsonRecord = Record<string, unknown>;

export function buildListingSnapshot({
  opportunity,
  candidate,
  seed,
  event,
  actionId,
  rawContext,
}: {
  opportunity: JsonRecord;
  candidate: JsonRecord;
  seed: JsonRecord;
  event: string;
  actionId?: string | null;
  rawContext?: JsonRecord;
}) {
  const raw = objectValue(candidate.raw_ebay_json);
  const seller = objectValue(raw.seller);
  const category = firstCategory(raw);
  return {
    opportunity_id: textOrNull(opportunity.opportunity_id),
    candidate_id: textOrNull(candidate.candidate_id ?? opportunity.candidate_id),
    action_id: actionId ?? null,
    sourcing_run_id: textOrNull(opportunity.sourcing_run_id ?? candidate.sourcing_run_id),
    snapshot_event: event,
    snapshot_source: "sourcing_api",
    asin: textOrNull(opportunity.asin ?? candidate.asin ?? seed.asin),
    amazon_title: textOrNull(seed.amazon_title),
    amazon_system: textOrNull(seed.system),
    amazon_image_url: textOrNull(seed.amazon_image_url),
    target_sale_price: numberOrNull(opportunity.target_sale_price ?? seed.target_sale_price),
    target_sale_price_source: textOrNull(opportunity.target_sale_price_source ?? seed.target_sale_price_source),
    ebay_item_id: textOrNull(candidate.ebay_item_id ?? opportunity.ebay_item_id),
    ebay_legacy_item_id: textOrNull(candidate.ebay_legacy_item_id ?? raw.legacyItemId),
    ebay_title: textOrNull(candidate.ebay_title ?? raw.title),
    ebay_subtitle: textOrNull(raw.subtitle),
    ebay_description: textOrNull(raw.description ?? raw.shortDescription),
    ebay_condition: textOrNull(candidate.condition ?? raw.condition),
    ebay_condition_id: textOrNull(candidate.condition_id ?? raw.conditionId),
    ebay_category: textOrNull(category?.categoryName ?? raw.categoryPath),
    ebay_category_id: textOrNull(category?.categoryId ?? raw.categoryId),
    ebay_category_path: textOrNull(raw.categoryPath),
    ebay_item_specifics_json: Array.isArray(raw.localizedAspects) ? raw.localizedAspects : null,
    ebay_primary_image_url: textOrNull(candidate.ebay_image_url ?? objectValue(raw.image).imageUrl),
    ebay_image_urls: imageUrls(raw),
    ebay_listing_url: textOrNull(candidate.ebay_item_web_url ?? raw.itemWebUrl),
    price: numberOrNull(candidate.price),
    shipping_cost: numberOrNull(candidate.shipping_cost),
    landed_cost: numberOrNull(candidate.landed_cost ?? opportunity.landed_cost),
    shipping_is_separate: typeof candidate.shipping_is_separate === "boolean" ? candidate.shipping_is_separate : null,
    quantity_available: numberOrNull(candidate.available_quantity),
    buying_options: Array.isArray(candidate.buying_options) ? candidate.buying_options : Array.isArray(raw.buyingOptions) ? raw.buyingOptions : null,
    listing_status: textOrNull(candidate.listing_status ?? opportunity.status),
    seller_username: textOrNull(candidate.seller_username ?? seller.username),
    seller_feedback_score: numberOrNull(seller.feedbackScore),
    seller_feedback_percentage: numberOrNull(seller.feedbackPercentage),
    item_location_country: textOrNull(candidate.item_location_country ?? objectValue(raw.itemLocation).country),
    ships_to_configured_zip: hasZipShippingEstimate(raw),
    raw_ebay_json: raw,
    raw_context_json: rawContext ?? {},
  };
}

function objectValue(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function textOrNull(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function numberOrNull(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function firstCategory(raw: JsonRecord) {
  const categories = raw.categories;
  return Array.isArray(categories) && categories[0] && typeof categories[0] === "object"
    ? categories[0] as JsonRecord
    : null;
}

function imageUrls(raw: JsonRecord) {
  const urls: string[] = [];
  const imageUrl = textOrNull(objectValue(raw.image).imageUrl);
  if (imageUrl) urls.push(imageUrl);
  for (const key of ["thumbnailImages", "additionalImages"]) {
    const values = raw[key];
    if (!Array.isArray(values)) continue;
    for (const row of values) {
      const url = textOrNull(objectValue(row).imageUrl);
      if (url) urls.push(url);
    }
  }
  return [...new Set(urls)];
}

function hasZipShippingEstimate(raw: JsonRecord) {
  const options = raw.shippingOptions;
  if (!Array.isArray(options)) return false;
  return options.some((option) => Boolean(textOrNull(objectValue(objectValue(option).shipToLocationUsedForEstimate).postalCode)));
}
