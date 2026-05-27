import type { PurchaseRow, PurchaseStats } from "./types";
import { isDelivered, needsAsinReview } from "./utils";

export function getPurchaseStats(
  rows: PurchaseRow[],
  visibleRows: PurchaseRow[]
): PurchaseStats {
  return {
    total: rows.length,
    visible: visibleRows.length,
    needsReview: rows.filter(needsAsinReview).length,
    orderProblems: 0,
    delivered: rows.filter(isDelivered).length,
  };
}
