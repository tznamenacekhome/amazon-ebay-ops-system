export type ReceiptItem = {
  title: string; supplier_sku: string; quantity: string | number; line_total: string | number;
  condition: string; system: string; exclude_from_purchase_reporting: boolean;
};
export type ReceiptData = {
  cost_basis: string;
  supplier: string; order_id: string; order_date: string; currency: string;
  shipping: string | number; tax: string | number; discount: string | number;
  order_total: string | number; notes: string; items: ReceiptItem[]; warnings?: string[];
};
export type ReceiptCosts = {
  subtotal: number; order_total: number;
  items: (ReceiptItem & { landed_total: number; average_unit_cost: number; extra_quantity: number })[];
};
export type ReceiptDraft = {
  id: string; original_filename: string; status: string; created_at: string;
  extracted_data: Partial<ReceiptData> | null; reviewed_data: Partial<ReceiptData> | null;
  extraction_error: string | null; extraction_started_at: string | null; purchase_id: string | null;
};
export const receiptField = "w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900";
export const receiptButton = "rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50";
export const blankReceiptItem = (): ReceiptItem => ({ title: "", supplier_sku: "", quantity: "", line_total: "", condition: "new", system: "", exclude_from_purchase_reporting: false });

export function editableReceipt(draft: ReceiptDraft): ReceiptData {
  const source = draft.reviewed_data || draft.extracted_data || {};
  return {
    cost_basis: source.cost_basis || "itemized",
    supplier: source.supplier ?? "", order_id: source.order_id ?? "", order_date: source.order_date ?? "",
    currency: source.currency ?? "", shipping: source.shipping ?? "", tax: source.tax ?? "",
    discount: source.discount ?? "", order_total: source.order_total ?? "", notes: source.notes ?? "",
    items: source.items?.length ? source.items.map((item) => ({ ...blankReceiptItem(), ...Object.fromEntries(Object.entries(item).map(([key, value]) => [key, value ?? ""])) })) : [blankReceiptItem()],
    warnings: source.warnings || [],
  };
}
