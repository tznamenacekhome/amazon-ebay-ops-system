import type { createServerSupabaseClient } from "./_server";

export type FulfillmentMethod = "FBA" | "MF";
export const FBA_CHANNELS = ["Amazon", "AMAZON", "AMAZON_NA", "AFN", "FBA"];
export const MF_CHANNELS = ["DEFAULT", "MFN", "MF", "FBM", "MERCHANT", "MERCHANT_NA"];

export function fulfillmentMethod(value: string | null | undefined): FulfillmentMethod | null {
  const channel = value?.trim().toUpperCase();
  if (FBA_CHANNELS.some(item => item.toUpperCase() === channel)) return "FBA";
  if (MF_CHANNELS.includes(channel || "")) return "MF";
  return null;
}

export function skuCondition(value: string | null | undefined): string | null {
  const condition = value?.trim().toLowerCase().replace(/[ _-]/g, "");
  if (!condition || condition === "unknown") return null;
  if (["11", "new", "newnew"].includes(condition)) return "new";
  return ({ "1": "usedlikenew", "2": "usedverygood", "3": "usedgood", "4": "usedacceptable" } as Record<string, string>)[condition] || condition;
}

type SkuMapping = { asin: string; seller_sku: string; condition: string | null; fulfillment_method: FulfillmentMethod };

/** An ASIN alone never identifies a seller listing. Unknown or ambiguous mappings stay blank. */
export function resolveListingSku(mappings: SkuMapping[], asin: string, method: FulfillmentMethod, condition?: string | null) {
  const wantedCondition = skuCondition(condition);
  const matches = mappings.filter(row => row.asin === asin && row.fulfillment_method === method &&
    (!wantedCondition || skuCondition(row.condition) === wantedCondition));
  const skus = [...new Set(matches.map(row => row.seller_sku).filter(Boolean))];
  return skus.length === 1 ? skus[0] : null;
}

export async function fetchListingSkuMappings(db: ReturnType<typeof createServerSupabaseClient>, asins: string[], method: FulfillmentMethod) {
  const mappings: SkuMapping[] = [];
  const marketplace = process.env.AMAZON_SP_API_MARKETPLACE_ID || process.env.AMAZON_MARKETPLACE_ID || "ATVPDKIKX0DER";
  for (let offset = 0; offset < asins.length; offset += 100) {
    const chunk = asins.slice(offset, offset + 100);
    const { data, error } = await db.from("amazon_skus")
      .select("asin,seller_sku,condition,fulfillment_channel").eq("marketplace_id", marketplace).in("asin", chunk);
    if (error) throw new Error(`Listing MSKU lookup failed: ${error.message}`);
    for (const row of data || []) {
      if (row.asin && row.seller_sku && fulfillmentMethod(row.fulfillment_channel) === method) {
        mappings.push({ asin: row.asin, seller_sku: row.seller_sku, condition: row.condition, fulfillment_method: method });
      }
    }
    if (method === "MF") {
      const { data: offers, error: offerError } = await db.from("amazon_mf_offers")
        .select("asin,seller_sku,condition,amazon_mf_accounts!inner(marketplace_id,configured)")
        .eq("amazon_mf_accounts.marketplace_id", marketplace).eq("amazon_mf_accounts.configured", true)
        .in("listing_state", ["in_stock", "out_of_stock", "unknown"]).in("asin", chunk);
      if (offerError) throw new Error(`MF listing MSKU lookup failed: ${offerError.message}`);
      for (const row of offers || []) {
        // A SKU currently observed as FBA cannot identify merchant-held stock.
        const otherMethod = (data || []).some(sku => sku.seller_sku === row.seller_sku && fulfillmentMethod(sku.fulfillment_channel) === "FBA");
        if (row.asin && row.seller_sku && !otherMethod) {
          mappings.push({ asin: row.asin, seller_sku: row.seller_sku, condition: row.condition, fulfillment_method: "MF" });
        }
      }
    }
  }
  return mappings;
}
