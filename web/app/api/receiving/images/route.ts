import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../_server";
import { amazonListingImageUrl, ebayImageUrl, ebayLegacyItemId, imageUrl } from "./imageUrls";

const supabase = createServerSupabaseClient();

export async function GET(request: Request) {
  const itemId = new URL(request.url).searchParams.get("item_id");
  if (!itemId || !/^[0-9a-f-]{36}$/i.test(itemId)) {
    return NextResponse.json({ error: "A valid item_id is required" }, { status: 400 });
  }
  const { data: item, error } = await supabase.from("purchase_items")
    .select("asin,supplier_listing_url,supplier_sku,raw_import_json")
    .eq("item_id", itemId).single();
  if (error || !item) return NextResponse.json({ error: "Purchase item unavailable" }, { status: 404 });

  const legacyId = ebayLegacyItemId(item);
  const asin = typeof item.asin === "string" && /^[A-Z0-9]{10}$/i.test(item.asin) ? item.asin.toUpperCase() : null;
  // Only exact identifiers for this detail item; never hydrate images for the queue.
  const [ebay, amazon] = await Promise.all([
    (async () => {
      const importedImage = ebayImageUrl(item.raw_import_json);
      if (importedImage || !legacyId) return importedImage;
      const { data, error } = await supabase.from("sourcing_ebay_candidates")
        .select("ebay_image_url").eq("ebay_legacy_item_id", legacyId)
        .not("ebay_image_url", "is", null).order("last_seen_at", { ascending: false }).limit(1);
      if (error) console.warn("Receiving eBay image lookup failed", error.message);
      return imageUrl(data?.[0]?.ebay_image_url);
    })(),
    (async () => {
      if (!asin) return null;
      const { data, error } = await supabase.from("vw_latest_amazon_listing_snapshot")
        .select("raw_listing_json").eq("asin", asin).limit(5);
      if (error) console.warn("Receiving Amazon image lookup failed", error.message);
      for (const row of data ?? []) {
        const url = amazonListingImageUrl(row.raw_listing_json);
        if (url) return url;
      }
      const seed = await supabase.from("sourcing_seed_asins").select("amazon_image_url").eq("asin", asin).limit(1);
      if (seed.error) console.warn("Receiving Amazon seed image lookup failed", seed.error.message);
      return imageUrl(seed.data?.[0]?.amazon_image_url) || `https://images-na.ssl-images-amazon.com/images/P/${asin}.01._SL500_.jpg`;
    })(),
  ]);
  return NextResponse.json({ ebay, amazon }, { headers: { "Cache-Control": "private, no-store" } });
}
