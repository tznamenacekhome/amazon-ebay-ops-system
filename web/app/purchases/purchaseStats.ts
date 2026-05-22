import type { PurchaseRow, PurchaseStats } from "./types";
import { isDelivered } from "./utils";

export function getPurchaseStats(
  rows: PurchaseRow[],
  visibleRows: PurchaseRow[]
): PurchaseStats {
  return {
    total: rows.length,
    visible: visibleRows.length,
    needsReview: rows.filter((row) => !row.asin).length,
    delivered: rows.filter(isDelivered).length,
  };
}
