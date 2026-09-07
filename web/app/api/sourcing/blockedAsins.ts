import { supabase } from "./_supabase";

// Query only the ASINs on this request, and fail closed if eligibility cannot
// be checked. A stored Watch/open row never overrides an ASIN-level block.
export async function fetchBlockedAsins(asins: string[]): Promise<Set<string>> {
  const unique = [...new Set(asins.map((asin) => asin.trim().toUpperCase()).filter(Boolean))];
  const blocked = new Set<string>();
  for (let offset = 0; offset < unique.length; offset += 100) {
    const { data, error } = await supabase.from("sourcing_blocked_asins")
      .select("asin").in("asin", unique.slice(offset, offset + 100));
    if (error) throw new Error(`Could not verify sourcing ASIN eligibility: ${error.message}`);
    for (const row of data ?? []) blocked.add(String(row.asin).trim().toUpperCase());
  }
  return blocked;
}

export async function excludeBlockedOpportunities<T extends { asin: string }>(rows: T[]): Promise<T[]> {
  const blocked = await fetchBlockedAsins(rows.map((row) => row.asin));
  return rows.filter((row) => !blocked.has(row.asin.trim().toUpperCase()));
}
