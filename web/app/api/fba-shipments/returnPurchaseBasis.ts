// Verified source evidence is server-owned metadata on the recovery case.
// Do not infer a purchase from ASIN alone or substitute the return date.
export function returnPurchaseBasis(row: {
  asin: string | null;
  seller_sku: string | null;
  sku?: string | null;
  raw_evidence_json: unknown;
}): { unitCost: number; purchaseDate: string; supplier: string | null; supplierOrderId: string | null } | null {
  const raw = row.raw_evidence_json as { purchase_basis?: Record<string, unknown> } | null;
  const basis = raw?.purchase_basis;
  if (!basis || basis.asin !== row.asin || basis.seller_sku !== (row.seller_sku ?? row.sku)) return null;
  if (basis.verified !== true || typeof basis.unit_cost !== "number" ||
      !Number.isFinite(basis.unit_cost) || basis.unit_cost < 0) return null;
  const date = basis.purchase_date;
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
      !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date) return null;
  return {
    unitCost: basis.unit_cost,
    purchaseDate: date,
    supplier: typeof basis.supplier === "string" ? basis.supplier : null,
    supplierOrderId: typeof basis.supplier_order_id === "string" ? basis.supplier_order_id : null,
  };
}
