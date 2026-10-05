import { createServerSupabaseClient } from "../_server";

export type KeepaFulfillment = "fba" | "mf" | null;

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

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function booleanValue(value: unknown): boolean | null {
  if (value === true || value === false) return value;
  if (value === 1 || value === "1" || String(value).toLowerCase() === "true") return true;
  if (value === 0 || value === "0" || String(value).toLowerCase() === "false") return false;
  return null;
}
