import { supabase } from "./_supabase";

type OfferOpportunity = {
  opportunity_type: string | null;
  max_offer_price: number | null;
  sourcing_ebay_candidates?: {
    ebay_item_id: string | null;
    ebay_legacy_item_id: string | null;
    raw_ebay_json: unknown;
  } | null;
};

export function declinedOfferListingId(row: OfferOpportunity): string | null {
  if (row.opportunity_type !== "best_offer") return null;
  const candidate = row.sourcing_ebay_candidates;
  const browseId = candidate?.ebay_item_id ?? "";
  // A parent listing's offer cannot safely suppress a different variation.
  const parts = browseId.split("|");
  if (parts.length === 3 && parts[2] !== "0") return null;
  const raw = candidate?.raw_ebay_json as { price?: { currency?: string; convertedFromCurrency?: string } } | null;
  if (raw?.price?.convertedFromCurrency && raw.price.convertedFromCurrency !== "USD") return null;
  if (raw?.price?.currency && raw.price.currency !== "USD") return null;
  const id = candidate?.ebay_legacy_item_id || (parts.length === 3 ? parts[1] : browseId);
  return /^\d+$/.test(id) ? id : null;
}

export function isDeclinedOfferSuppressed(row: OfferOpportunity, declined: Map<string, number>): boolean {
  const id = declinedOfferListingId(row);
  const amount = id ? declined.get(id) : undefined;
  if (amount === undefined || !Number.isFinite(amount) || amount <= 0) return false;
  // Unknown profitability cannot establish that a higher offer is now viable.
  if (row.max_offer_price === null || !Number.isFinite(row.max_offer_price)) return true;
  // Both amounts are item-only USD; shipping is already reserved by the scorer.
  return Math.round(row.max_offer_price * 100) <= Math.round(amount * 100);
}

export async function excludeDeclinedOffers<T extends OfferOpportunity>(rows: T[]): Promise<T[]> {
  const ids = [...new Set(rows.map(declinedOfferListingId).filter((id): id is string => id !== null))];
  const declined = new Map<string, number>();
  for (let offset = 0; offset < ids.length; offset += 100) {
    const { data, error } = await supabase.from("sourcing_declined_ebay_offers")
      .select("ebay_legacy_item_id,declined_offer_amount").in("ebay_legacy_item_id", ids.slice(offset, offset + 100));
    if (error) throw new Error(`Could not verify declined eBay offers: ${error.message}`);
    for (const row of data ?? []) declined.set(row.ebay_legacy_item_id, Number(row.declined_offer_amount));
  }
  // Presentation-only suppression preserves Watch, matching feedback, and
  // purchase history. Every new run is checked against the same listing record.
  return rows.filter((row) => !isDeclinedOfferSuppressed(row, declined));
}
