import type { createServerSupabaseClient } from "../_server";
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
  if (typeof basis.supplier !== "string" || !basis.supplier.trim()) return null;
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

type BasisRow = { asin: string | null; seller_sku: string | null; sku?: string | null;
  amazon_order_id: string | null; raw_evidence_json?: unknown };
type Source = Record<string, unknown>;
const text = (value: unknown): string => typeof value === "string" ? value.trim() : "";
const number = (value: unknown): number | null => value === null || value === undefined || value === "" ||
  !Number.isFinite(Number(value)) ? null : Number(value);

/** Resolve every requested return in bounded batches; never guess by ASIN alone. */
export async function resolveReturnPurchaseBases<T extends BasisRow>(
  db: ReturnType<typeof createServerSupabaseClient>, rows: T[],
): Promise<Array<T & { raw_evidence_json: unknown }>> {
  const pending = rows.filter(row => !returnPurchaseBasis({ ...row, raw_evidence_json: row.raw_evidence_json }));
  if (!pending.length) return rows.map(row => ({ ...row, raw_evidence_json: row.raw_evidence_json }));
  const read = async (table: string, columns: string, key: string, values: string[]): Promise<Source[]> => {
    const result: Source[] = [];
    const ids = [...new Set(values.filter(Boolean))];
    for (let start = 0; start < ids.length; start += 100) {
      for (let offset = 0; ; offset += 1000) {
        const { data, error } = await db.from(table).select(columns).in(key, ids.slice(start, start + 100)).range(offset, offset + 999);
        if (error) throw new Error(`Return purchase lookup (${table}): ${error.message}`);
        result.push(...(data ?? []) as unknown as Source[]);
        if (result.length > 10000) throw new Error("Return purchase lookup exceeded its bounded result limit.");
        if (!data || data.length < 1000) break;
      }
    }
    return result;
  };
  const orderIds = pending.map(row => text(row.amazon_order_id));
  const [allocations, orders, legacy, profits] = await Promise.all([
    read("amazon_sales_cogs_consumption", "amazon_order_id,asin,seller_sku,unit_cogs,source_reference_type,source_reference_id", "amazon_order_id", orderIds),
    read("amazon_sales_orders", "amazon_order_id,purchase_date", "amazon_order_id", orderIds),
    read("inventorylab_active_inventory_backfill", "inventorylab_active_inventory_backfill_id,seller_sku,asin,active_cost_per_unit,active_date_purchased,active_supplier,source_file,source_row_number", "seller_sku", pending.map(row => text(row.seller_sku ?? row.sku))),
    read("amazon_sales_profitability", "amazon_order_id,asin,seller_sku,cogs,quantity", "amazon_order_id", orderIds),
  ]);
  const [items, otherSources] = await Promise.all([
    read("purchase_items", "item_id,purchase_id,asin,unit_cost", "item_id", allocations.filter(a => a.source_reference_type === "purchase_item").map(a => text(a.source_reference_id))),
    read("non_ebay_purchase_cogs_sources", "non_ebay_purchase_cogs_source_id,asin,msku,unit_cost,order_date,supplier,supplier_order_number", "non_ebay_purchase_cogs_source_id", allocations.filter(a => a.source_reference_type === "non_ebay_purchase_cogs_source").map(a => text(a.source_reference_id))),
  ]);
  const purchases = await read("purchases", "purchase_id,order_date,supplier,supplier_order_id", "purchase_id", items.map(item => text(item.purchase_id)));
  return rows.map(row => {
    if (returnPurchaseBasis({ ...row, raw_evidence_json: row.raw_evidence_json })) return { ...row, raw_evidence_json: row.raw_evidence_json };
    const sku = text(row.seller_sku ?? row.sku);
    const matches = (value: Source) => value.amazon_order_id === row.amazon_order_id && value.asin === row.asin && value.seller_sku === sku;
    const links = allocations.filter(matches);
    const saleDate = text(orders.find(order => order.amazon_order_id === row.amazon_order_id)?.purchase_date).slice(0, 10);
    const candidates: Source[] = [];
    const add = (value: Source) => {
      const basis = { ...value, verified: true, asin: row.asin, seller_sku: sku, automatic: true };
      const validated = returnPurchaseBasis({ ...row, raw_evidence_json: { purchase_basis: basis } });
      if (validated?.supplier && (!saleDate || validated.purchaseDate <= saleDate)) candidates.push(basis);
    };
    const legacyFor = (cost: number | null) => {
      // Without a sale date, a catalog snapshot cannot establish chronology.
      if (!saleDate) return;
      for (const source of legacy.filter(source => source.seller_sku === sku && source.asin === row.asin &&
        (cost === null || Math.abs((number(source.active_cost_per_unit) ?? -1) - cost) < 0.0001))) {
        add({ unit_cost: number(source.active_cost_per_unit), purchase_date: source.active_date_purchased,
          supplier: source.active_supplier, source: "inventorylab_exact_sku",
          source_reference_id: source.inventorylab_active_inventory_backfill_id,
          source_file: source.source_file, source_row: source.source_row_number });
      }
    };
    let unresolvedAllocation = false;
    for (const link of links) {
      const before = candidates.length;
      if (link.source_reference_type === "purchase_item") {
        const item = items.find(item => item.item_id === link.source_reference_id && item.asin === row.asin);
        const purchase = purchases.find(purchase => purchase.purchase_id === item?.purchase_id);
        if (item && purchase) add({ unit_cost: number(link.unit_cogs), purchase_date: purchase.order_date,
          supplier: purchase.supplier, supplier_order_id: purchase.supplier_order_id,
          source: "original_sale_purchase_allocation", source_reference_id: item.item_id });
      } else if (link.source_reference_type === "non_ebay_purchase_cogs_source") {
        const source = otherSources.find(source => source.non_ebay_purchase_cogs_source_id === link.source_reference_id &&
          source.asin === row.asin && (!source.msku || source.msku === sku));
        if (source) add({ unit_cost: number(link.unit_cogs), purchase_date: source.order_date, supplier: source.supplier,
          supplier_order_id: source.supplier_order_number, source: "original_sale_non_ebay_allocation", source_reference_id: link.source_reference_id });
      } else if (link.source_reference_type === "inventorylab_legacy_valuation") legacyFor(number(link.unit_cogs));
      if (before === candidates.length) unresolvedAllocation = true;
    }
    if (!links.length && sku && row.asin) {
      const profit = profits.filter(matches);
      const knownCosts = profit.flatMap(p => number(p.cogs) !== null && (number(p.quantity) ?? 0) > 0 ? [Number(p.cogs) / Number(p.quantity)] : []);
      if (new Set(knownCosts).size <= 1) legacyFor(knownCosts[0] ?? null);
    }
    const unique = new Map(candidates.map(b => [JSON.stringify([b.unit_cost, b.purchase_date, b.supplier, b.supplier_order_id ?? null]), b]));
    // Conflicting source lots need review; one ASIN can have many different costs.
    const basis = !unresolvedAllocation && unique.size === 1 ? [...unique.values()][0] : null;
    const raw = row.raw_evidence_json && typeof row.raw_evidence_json === "object" ? row.raw_evidence_json : {};
    return { ...row, raw_evidence_json: basis ? { ...raw, purchase_basis: basis } : raw };
  });
}
