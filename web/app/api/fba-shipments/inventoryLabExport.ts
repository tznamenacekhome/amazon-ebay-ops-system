/** CSV dates must never contain UI placeholders or shift date-only values. */
export function inventoryLabPurchaseDate(value?: string | null): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(value)) return "";
  const dateOnly = value.slice(0, 10);
  const date = new Date(`${dateOnly}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== dateOnly) return "";
  const [year, month, day] = dateOnly.split("-");
  return `${month}/${day}/${year}`;
}

type ExportDetail = {
  item_id: string; asin: string; amazon_title: string | null; seller_sku?: string | null;
  quantity: number; unit_cost: number | null; order_date: string | null; supplier: string | null;
  source_type?: string; source_status?: string | null;
};
type ExportGroup = {
  asin: string; msku: string | null; title: string | null; system: string | null;
  sell_price: number | null; details: ExportDetail[];
};

/** Server only: validate sources first, then merge selected units by ASIN. */
export function inventoryLabExportRows(groups: ExportGroup[], quantities: Record<string, string>): string[][] {
  const merged = new Map<string, { row: string[]; quantity: number; totalCost: number; date: string; suppliers: Set<string> }>();
  const issues: string[] = [];
  for (const group of groups) for (const detail of group.details) {
    const draft = quantities[detail.item_id];
    if (draft === undefined || draft.trim() === "" || Number(draft) === 0) continue;
    const quantity = Number(draft);
    const missing: string[] = [];
    const asin = detail.asin?.trim();
    const sku = (detail.seller_sku || group.msku)?.trim();
    const title = (detail.amazon_title || group.title)?.trim();
    const supplier = detail.supplier?.trim();
    const date = inventoryLabPurchaseDate(detail.order_date);
    if (!/^[A-Z0-9]{10}$/.test(asin)) missing.push("ASIN");
    if (!title) missing.push("title");
    if (detail.unit_cost === null || !Number.isFinite(detail.unit_cost) || detail.unit_cost < 0) missing.push("purchase cost");
    if (group.sell_price === null || !Number.isFinite(group.sell_price) || group.sell_price <= 0) missing.push("list price");
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > detail.quantity) missing.push("valid quantity");
    if (!date) missing.push("purchase date");
    if (!supplier) missing.push("supplier");
    if (detail.source_type === "amazon_return_recovery" && detail.source_status !== "Ready for Send to Amazon") missing.push("eligible return inspection");
    if (missing.length) {
      issues.push(`${asin || detail.item_id}: ${missing.join(", ")}`);
      continue;
    }
    const existing = merged.get(asin);
    if (existing) {
      existing.quantity += quantity;
      existing.totalCost += detail.unit_cost! * quantity;
      if (detail.order_date! < existing.date) existing.date = detail.order_date!;
      existing.suppliers.add(supplier!);
    } else {
      merged.set(asin, { row: [asin, group.msku || sku || "", title!, group.system || "", "",
        group.sell_price!.toFixed(2), "", "", ""], quantity, totalCost: detail.unit_cost! * quantity,
        date: detail.order_date!, suppliers: new Set([supplier!]) });
    }
  }
  if (issues.length) throw new Error(`Export blocked. Complete the required fields for every selected unit: ${issues.join("; ")}.`);
  if (!merged.size) throw new Error("Select at least one unit to export.");
  return [...merged.values()].map(({ row, quantity, totalCost, date, suppliers }) => {
    row[4] = (totalCost / quantity).toFixed(2);
    row[6] = String(quantity);
    row[7] = inventoryLabPurchaseDate(date);
    row[8] = [...suppliers].join(", ");
    return row;
  });
}
