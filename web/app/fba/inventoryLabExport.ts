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

/** Validate every selected source row; never average or substitute its cost/date. */
export function inventoryLabExportRows(groups: ExportGroup[], quantities: Record<string, string>): string[][] {
  const rows: string[][] = [];
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
    if (!sku) missing.push("MSKU");
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
    rows.push([asin, sku!, title!, group.system || "", detail.unit_cost!.toFixed(2),
      group.sell_price!.toFixed(2), String(quantity), date, supplier!]);
  }
  if (issues.length) throw new Error(`Export blocked. Complete the required fields for every selected unit: ${issues.join("; ")}.`);
  if (!rows.length) throw new Error("Select at least one unit to export.");
  return rows;
}
