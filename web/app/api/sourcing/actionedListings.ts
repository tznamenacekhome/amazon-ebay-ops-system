import { supabase } from "./_supabase";

type Listing = {
  asin: string;
  ebay_item_id?: string | null;
  status?: string | null;
  sourcing_ebay_candidates?: { ebay_item_id?: string | null; ebay_legacy_item_id?: string | null } | null;
};

// Browse IDs retain variation identity. A bare legacy ID denotes the parent.
export function listingActionKey(value: string | null | undefined): string | null {
  const id = value?.trim();
  if (!id) return null;
  if (/^\d+$/.test(id)) return `v1|${id}|0`;
  return /^v1\|\d+\|\d+$/.test(id) ? id : null;
}

function rowListingKey(row: Listing) {
  return listingActionKey(row.ebay_item_id) ?? listingActionKey(row.sourcing_ebay_candidates?.ebay_item_id) ??
    listingActionKey(row.sourcing_ebay_candidates?.ebay_legacy_item_id);
}

const activeStatuses = new Set(["open", "rejected", "watching"]);
const decisionActions = ["purchased", "dismiss", "dismissed", "confirmed_exclusion", "confirm_exclusion", "confirmed_valid_match", "mark_valid_match"];

export async function excludeActionedListings<T extends Listing>(rows: T[]): Promise<T[]> {
  const keys = [...new Set(rows.filter(row => activeStatuses.has(row.status ?? "")).map(rowListingKey).filter((key): key is string => Boolean(key)))];
  const purchased = new Set<string>();
  const latestByPair = new Map<string, string>();
  for (let offset = 0; offset < keys.length; offset += 75) {
    const aliases = keys.slice(offset, offset + 75).flatMap(key => key.endsWith("|0") ? [key, key.split("|")[1]] : [key]);
    for (let start = 0; ; start += 1000) {
      const { data, error } = await supabase.from("sourcing_actions")
        .select("action_id,asin,ebay_item_id,action_type,created_at")
        .in("ebay_item_id", aliases)
        .in("action_type", decisionActions)
        .order("created_at", { ascending: false }).order("action_id", { ascending: false })
        .range(start, start + 999);
      if (error) throw new Error(`Could not verify sourcing listing actions: ${error.message}`);
      for (const action of data ?? []) {
        const key = listingActionKey(action.ebay_item_id);
        if (!key) continue;
        if (action.action_type === "purchased") purchased.add(key);
        // Only explicit queue decisions supersede a dismissal; notes, watches,
        // price edits, and unrelated feedback do not silently resurrect it.
        if (!["dismiss", "dismissed", "confirmed_exclusion", "confirm_exclusion", "confirmed_valid_match", "mark_valid_match"].includes(action.action_type)) continue;
        const pair = `${String(action.asin).toUpperCase()}|${key}`;
        if (!latestByPair.has(pair)) latestByPair.set(pair, action.action_type);
      }
      if ((data ?? []).length < 1000) break;
    }
  }
  return rows.filter(row => {
    // Keep purchase and dismissed history visible in their own views. Never
    // mark a duplicate ASIN as purchased: that would corrupt purchase matching.
    if (!activeStatuses.has(row.status ?? "")) return true;
    const key = rowListingKey(row);
    if (!key) return true;
    if (purchased.has(key)) return false;
    const action = latestByPair.get(`${row.asin.toUpperCase()}|${key}`);
    return !action || ["confirmed_valid_match", "mark_valid_match"].includes(action);
  });
}
