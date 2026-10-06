import { createServerSupabaseClient } from "../_server";

export type KeepaFulfillment = "fba" | "mf" | null;
export type KeepaPriceSource = "buy_box" | "fba" | "mf" | "new" | "used_only" | "no_data";
export type KeepaCurrentPriceContext = {
  price: number | null;
  label: string;
  source: KeepaPriceSource;
  fulfillment: KeepaFulfillment;
  isBuyBox: boolean;
};

type SnapshotRow = {
  asin: string | null;
  keepa_stats: unknown;
};

export async function fetchBuyBoxFulfillmentByAsin(
  supabase: ReturnType<typeof createServerSupabaseClient>,
  values: Array<string | null | undefined>,
) {
  const asins = Array.from(new Set(values.filter(Boolean).map(value => String(value).toUpperCase())));
  const result = new Map<string, KeepaFulfillment>();

  for (let index = 0; index < asins.length; index += 200) {
    const { data, error } = await supabase
      .from("vw_latest_keepa_product_snapshot")
      .select("asin,keepa_stats:raw_keepa_json->stats")
      .in("asin", asins.slice(index, index + 200));
    if (error) throw new Error(`Keepa fulfillment snapshots: ${error.message}`);

    for (const row of (data ?? []) as SnapshotRow[]) {
      const asin = row.asin?.toUpperCase();
      if (!asin) continue;
      const stats = objectValue(row.keepa_stats);
      result.set(asin, booleanValue(stats.buyBoxIsFBA) === true ? "fba" : booleanValue(stats.buyBoxIsFBA) === false ? "mf" : null);
    }
  }

  return result;
}

export function fulfillmentForAsin(
  byAsin: Map<string, KeepaFulfillment>,
  asin: unknown,
) {
  return asin ? byAsin.get(String(asin).toUpperCase()) ?? null : null;
}

export function currentPriceContext(row: Record<string, unknown> | null | undefined): KeepaCurrentPriceContext {
  const raw = objectValue(row?.raw_keepa_json);
  const stats = objectValue(raw.stats);
  const buyBoxIsUsed = booleanValue(stats.buyBoxIsUsed);
  const buyBoxIsFba = booleanValue(stats.buyBoxIsFBA);
  const buyBox = buyBoxIsUsed === true ? null : cents(row?.buy_box_price_current_cents);
  const lowFba = cents(row?.new_fba_price_current_cents) ?? lowestLiveNewOfferPrice(raw, true);
  const lowMf = statsCents(stats, "current", 7) ?? lowestLiveNewOfferPrice(raw, false);
  const lowNew = cents(row?.new_price_current_cents);
  const used = statsCents(stats, "current", 2);
  if (buyBox !== null) return { price: buyBox, label: "Buy Box", source: "buy_box",
    fulfillment: buyBoxIsFba === true ? "fba" : buyBoxIsFba === false ? "mf" : null, isBuyBox: true };
  if (lowFba !== null) return { price: lowFba, label: "Low FBA New", source: "fba", fulfillment: "fba", isBuyBox: false };
  if (lowMf !== null) return { price: lowMf, label: "Low MF New", source: "mf", fulfillment: "mf", isBuyBox: false };
  if (lowNew !== null) return { price: lowNew, label: "Low New", source: "new", fulfillment: null, isBuyBox: false };
  const usedOnly = used !== null || buyBoxIsUsed === true;
  return { price: null, label: usedOnly ? "Used Only" : "No Data",
    source: usedOnly ? "used_only" : "no_data", fulfillment: null, isBuyBox: false };
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function booleanValue(value: unknown): boolean | null {
  if (value === true || value === false) return value;
  if (value === 1 || value === "1" || String(value).toLowerCase() === "true") return true;
  if (value === 0 || value === "0" || String(value).toLowerCase() === "false") return false;
  return null;
}

function cents(value: unknown) {
  const parsed = Number(value);
  return value === null || value === undefined || !Number.isFinite(parsed) || parsed < 0 ? null : parsed / 100;
}

function statsCents(stats: Record<string, unknown>, period: string, index: number) {
  const values = stats[period];
  return Array.isArray(values) ? cents(values[index]) : null;
}

function lowestLiveNewOfferPrice(raw: Record<string, unknown>, isFba: boolean) {
  const offers = raw.offers;
  if (!Array.isArray(offers)) return null;
  let lowest: number | null = null;
  for (const value of offers) {
    const offer = objectValue(value);
    if (Number(offer.condition) !== 1 || booleanValue(offer.isFBA) !== isFba || offer.isShippable === false) continue;
    const history = offer.offerCSV;
    if (!Array.isArray(history) || history.length < 3) continue;
    const price = cents(history[history.length - 2]);
    const shipping = cents(history[history.length - 1]);
    if (price === null || shipping === null) continue;
    const landed = price + shipping;
    lowest = lowest === null ? landed : Math.min(lowest, landed);
  }
  return lowest;
}
