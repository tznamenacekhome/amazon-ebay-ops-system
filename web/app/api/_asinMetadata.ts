type SupabaseClient = {
  from: (table: string) => any;
};

export type AsinMetadata = {
  asin: string;
  amazonTitle: string | null;
  targetPrice: number | null;
};

export function normalizeAsin(value: unknown) {
  const text = String(value ?? "").trim().toUpperCase();
  return /^[A-Z0-9]{10}$/.test(text) ? text : "";
}

export async function resolveAsinMetadata(
  supabase: SupabaseClient,
  asinValue: unknown
): Promise<AsinMetadata | null> {
  const asin = normalizeAsin(asinValue);
  if (!asin) return null;

  const [
    manualMatch,
    keepaSnapshot,
    amazonSku,
    latestSale,
  ] = await Promise.all([
    fetchManualMatchMetadata(supabase, asin),
    fetchKeepaMetadata(supabase, asin),
    fetchAmazonSkuMetadata(supabase, asin),
    fetchLatestSalePrice(supabase, asin),
  ]);

  return {
    asin,
    amazonTitle:
      cleanText(manualMatch.amazonTitle) ||
      cleanText(keepaSnapshot.amazonTitle) ||
      cleanText(amazonSku.amazonTitle),
    targetPrice: highestMoney([
      manualMatch.targetPrice,
      latestSale,
      keepaSnapshot.keepaAvg90Price,
      keepaSnapshot.keepaCurrentPrice,
      amazonSku.listingPrice,
    ]),
  };
}

async function fetchManualMatchMetadata(supabase: SupabaseClient, asin: string) {
  const { data, error } = await supabase
    .from("manual_item_matches")
    .select("amazon_title,target_price,updated_at")
    .eq("asin", asin)
    .order("updated_at", { ascending: false, nullsFirst: false })
    .limit(1);

  if (error) {
    console.warn("Manual ASIN metadata lookup failed", error.message);
    return { amazonTitle: null, targetPrice: null };
  }

  const row = data?.[0] ?? {};
  return {
    amazonTitle: cleanText(row.amazon_title),
    targetPrice: toMoney(row.target_price),
  };
}

async function fetchKeepaMetadata(supabase: SupabaseClient, asin: string) {
  const { data, error } = await supabase
    .from("vw_latest_keepa_product_snapshot")
    .select("title,buy_box_price_avg90_cents,buy_box_price_current_cents,new_fba_price_current_cents,new_price_current_cents")
    .eq("asin", asin)
    .limit(1);

  if (error) {
    console.warn("Keepa ASIN metadata lookup failed", error.message);
    return { amazonTitle: null, keepaAvg90Price: null, keepaCurrentPrice: null };
  }

  const row = data?.[0] ?? {};
  return {
    amazonTitle: cleanText(row.title),
    keepaAvg90Price: centsToDollars(row.buy_box_price_avg90_cents),
    keepaCurrentPrice:
      centsToDollars(row.buy_box_price_current_cents) ??
      centsToDollars(row.new_fba_price_current_cents) ??
      centsToDollars(row.new_price_current_cents),
  };
}

async function fetchAmazonSkuMetadata(supabase: SupabaseClient, asin: string) {
  const { data, error } = await supabase
    .from("amazon_skus")
    .select("product_name,listing_price,updated_at")
    .eq("asin", asin)
    .order("updated_at", { ascending: false, nullsFirst: false })
    .limit(1);

  if (error) {
    console.warn("Amazon SKU ASIN metadata lookup failed", error.message);
    return { amazonTitle: null, listingPrice: null };
  }

  const row = data?.[0] ?? {};
  return {
    amazonTitle: cleanText(row.product_name),
    listingPrice: toMoney(row.listing_price),
  };
}

async function fetchLatestSalePrice(supabase: SupabaseClient, asin: string) {
  const { data, error } = await supabase
    .from("amazon_sales_profitability")
    .select("quantity,sale_price,amazon_order_id")
    .eq("asin", asin)
    .eq("data_status", "complete")
    .not("sale_price", "is", null)
    .gt("quantity", 0)
    .order("amazon_order_id", { ascending: false, nullsFirst: false })
    .limit(25);

  if (error) {
    console.warn("Amazon sale ASIN metadata lookup failed", error.message);
    return null;
  }

  const prices = (data ?? []).map((row: Record<string, unknown>) => {
    const salePrice = toMoney(row.sale_price);
    const quantity = toMoney(row.quantity);
    return salePrice !== null && quantity !== null && quantity > 0
      ? roundMoney(salePrice / quantity)
      : null;
  });
  return highestMoney(prices);
}

function cleanText(value: unknown) {
  const text = String(value ?? "").trim();
  return text || null;
}

function toMoney(value: unknown) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? roundMoney(parsed) : null;
}

function centsToDollars(value: unknown) {
  const cents = toMoney(value);
  return cents !== null && cents > 0 ? roundMoney(cents / 100) : null;
}

function highestMoney(values: Array<number | null | undefined>) {
  const valid = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value) && value > 0);
  return valid.length ? roundMoney(Math.max(...valid)) : null;
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}
