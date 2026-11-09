export type StockFilter = "in_stock" | "out_of_stock" | "all";
export function stockFilter(value: string | null): StockFilter {
  if (value === null) return "in_stock";
  if (value === "in_stock" || value === "out_of_stock" || value === "all") return value;
  throw Error("Unknown MF stock filter");
}
/** Quoted PostgREST patterns keep commas/parentheses in real titles/SKUs literal. */
export function listingSearch(value: string) {
  const literal = value.trim().replace(/[\\%_]/g, "\\$&");
  const quoted = `"%${literal.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}%"`;
  return ["seller_sku", "title", "asin"].map(column => `${column}.ilike.${quoted}`).join(",");
}
