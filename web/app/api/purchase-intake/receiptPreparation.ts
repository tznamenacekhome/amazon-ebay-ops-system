import type { SupabaseClient } from "@supabase/supabase-js";
import { normalizeAsin, resolveAsinMetadata } from "../_asinMetadata";
import { normalizeSystem } from "../../purchases/matchingKeys";
import { cleanMarketplaceTitleForSearch } from "../../purchases/titleCleaning";
import { blankReceiptItem, type ReceiptData, type ReceiptItem } from "../../purchases/receiptTypes";

export type ReceiptCharge = { key: string; title: string; amount: string };
const feeNames = /^(packing|packaging|handling|packing fee|packaging fee|handling fee|packing charge|packaging charge|handling charge|shipping handling)$/;
function titleKey(title: string) { return cleanMarketplaceTitleForSearch(title).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
function feeKey(item: ReceiptItem) { return `receipt-fee:${item.supplier_sku || titleKey(item.title)}`; }
export function isReceiptFee(item: ReceiptItem) { return item.exclude_from_purchase_reporting && feeNames.test(titleKey(item.title)); }
function cents(value: unknown): bigint | null {
  const text = String(value ?? "");
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, decimal = ""] = text.split(".");
  return BigInt(whole) * BigInt(100) + BigInt(decimal.padEnd(2, "0"));
}
function dollars(value: bigint) { return `${value / BigInt(100)}.${String(value % BigInt(100)).padStart(2, "0")}`; }

/** Backend-only charge reclassification. Never infer a fee from an arbitrary gap. */
export function prepareReceipt(data: ReceiptData, original: Partial<ReceiptData> | null): ReceiptData {
  const result = structuredClone(data);
  result.currency = result.currency || original?.currency || "USD";
  result.other_charges = result.other_charges ?? "0";
  result.charge_lines = result.charge_lines || [];
  result.items = result.items.map((item) => ({ ...blankReceiptItem(), ...item, condition: item.condition || "new", system: item.system || "", asin: String(item.asin || "").trim().toUpperCase(), sell_price: item.sell_price ?? "" }));
  let fees = cents(result.other_charges);
  if (fees === null) return result; // Cost RPC reports invalid input without discarding edits.
  const remaining: ReceiptItem[] = [];
  const currentFees = new Map<string, ReceiptCharge>();
  for (const item of result.items) {
    const amount = cents(item.line_total);
    if (isReceiptFee(item) && amount !== null && result.cost_basis !== "total_only") {
      const previous = currentFees.get(feeKey(item));
      currentFees.set(feeKey(item), { key: feeKey(item), title: item.title, amount: dollars(amount + (previous ? cents(previous.amount)! : BigInt(0))) });
    } else remaining.push(item);
  }
  for (const charge of currentFees.values()) {
    if (!result.charge_lines.some((existing) => existing.key === charge.key)) {
      result.charge_lines.push(charge); fees += cents(charge.amount)!;
    }
  }
  result.items = remaining;
  // Recover only a positively identified source fee that was removed from the draft.
  const amountFields = [result.order_total, result.shipping, result.tax, result.discount, ...remaining.map((item) => item.line_total)].map(cents);
  if (result.cost_basis !== "total_only" && amountFields.every((amount) => amount !== null)) {
    const [total, shipping, tax, discount, ...merchandise] = amountFields as bigint[];
    let gap = total - shipping - tax + discount - fees - merchandise.reduce((sum, amount) => sum + amount, BigInt(0));
    const originalFees = new Map<string, ReceiptCharge>();
    for (const item of original?.items || []) {
      const amount = cents(item.line_total);
      if (!isReceiptFee(item) || amount === null || amount <= BigInt(0)) continue;
      const previous = originalFees.get(feeKey(item));
      originalFees.set(feeKey(item), { key: feeKey(item), title: item.title, amount: dollars(amount + (previous ? cents(previous.amount)! : BigInt(0))) });
    }
    for (const charge of originalFees.values()) {
      const amount = cents(charge.amount)!;
      if (result.charge_lines.some((existing) => existing.key === charge.key)) continue;
      if (gap >= amount) {
        fees += amount; gap -= amount;
        result.charge_lines.push(charge);
      }
    }
  }
  result.other_charges = dollars(fees);
  return result;
}

type Candidate = { asin: string; title: string; system: string | null };
export function chooseReceiptAsin(item: ReceiptItem, candidates: Candidate[]) {
  const system = normalizeSystem(item.system);
  const exact = candidates.filter((candidate) => titleKey(candidate.title) === titleKey(item.title)
    && ((!system && !normalizeSystem(candidate.system || candidate.title)) || (system && normalizeSystem(candidate.system || candidate.title) === system)));
  const asins = [...new Set(exact.map((candidate) => normalizeAsin(candidate.asin)).filter(Boolean))];
  return asins.length === 1 ? asins[0] : null;
}

/** Reuse known Amazon listings and reviewed matches; never invent an ASIN. */
export async function matchReceiptItems(db: SupabaseClient, data: ReceiptData): Promise<ReceiptData> {
  const result = structuredClone(data);
  for (const item of result.items.slice(0, 30)) {
    if (item.exclude_from_purchase_reporting) continue;
    let asin = normalizeAsin(item.asin);
    if (!asin) {
      const words = titleKey(item.title).split(" ").filter((word) => word.length >= 3).slice(0, 2);
      if (!words.length) continue;
      const pattern = `%${words.join("%")}%`;
      const lookups = await Promise.all([
        db.from("amazon_skus").select("asin,product_name").ilike("product_name", pattern).limit(30),
        db.from("amazon_mf_offers").select("asin,title").ilike("title", pattern).limit(30),
        db.from("manual_item_matches").select("asin,source_title,amazon_title,system").ilike("source_title", pattern).limit(30),
      ]);
      const candidates: Candidate[] = [];
      let truncated = false;
      for (let index = 0; index < lookups.length; index++) {
        const lookup = lookups[index];
        if (lookup.error) throw new Error("ASIN lookup is temporarily unavailable. You can enter the ASIN manually or retry.");
        if ((lookup.data || []).length === 30) truncated = true;
        for (const raw of lookup.data || []) {
          const row = raw as unknown as Record<string, string>;
          candidates.push({ asin: row.asin, title: row.product_name || row.title || row.source_title, system: row.system || null });
        }
      }
      asin = truncated ? "" : chooseReceiptAsin(item, candidates) || "";
      item.match_note = asin ? "Matched from existing MBOP Amazon records." : "No unique exact match in MBOP's Amazon records. Enter the ASIN or search Amazon.";
    }
    if (asin) {
      const metadata = await resolveAsinMetadata(db, asin);
      item.asin = asin;
      if (metadata?.amazonTitle) item.amazon_title = metadata.amazonTitle;
      if (item.sell_price === "" && metadata?.targetPrice != null) item.sell_price = metadata.targetPrice;
    }
  }
  return result;
}
