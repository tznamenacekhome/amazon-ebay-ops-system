import type { PurchaseRow } from "./types";

export function formatDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "2-digit",
  });
}

export function formatMoney(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

export function rowKey(row: PurchaseRow) {
  return row.item_id || row.purchase_id || row.supplier_order_id || "";
}

export function amazonAsinUrl(asin: string) {
  return `https://www.amazon.com/dp/${asin}`;
}

export function amazonSearchUrl(title: string) {
  return `https://www.amazon.com/s?k=${encodeURIComponent(title)}`;
}

export function ebayOrderUrl(orderId?: string | null) {
  if (!orderId) return "";
  return `https://order.ebay.com/ord/show?orderId=${orderId}#/`;
}

export function getPrimaryTitle(row: PurchaseRow) {
  return row.amazon_title || row.ebay_title || row.title || "Untitled item";
}

export function getEbayTitle(row: PurchaseRow) {
  return row.ebay_title || "";
}

export function getShipmentStatus(row: PurchaseRow) {
  return row.normalized_status || row.shipment_status || row.current_status || "";
}

export function isDelivered(row: PurchaseRow) {
  const status = getShipmentStatus(row).toLowerCase();
  return !!row.delivered_date || status === "delivered";
}
