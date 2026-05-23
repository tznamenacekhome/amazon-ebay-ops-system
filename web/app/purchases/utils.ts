import type { PurchaseRow } from "./types";
import { cleanMarketplaceTitleForSearch } from "./titleCleaning";

export const OPERATIONAL_STATUS_OPTIONS = [
  { value: "no_tracking", label: "No Tracking" },
  { value: "shipped_no_tracking", label: "Shipped (No Tracking)" },
  { value: "awaiting_carrier_scan", label: "Awaiting Carrier Scan" },
  { value: "in_transit", label: "In Transit" },
  { value: "available_for_pickup", label: "Out for Pickup / Pickup Available" },
  { value: "out_for_delivery", label: "Out for Delivery" },
  { value: "delivered", label: "Delivered" },
  { value: "exception", label: "Exception" },
  { value: "return_opened", label: "Return Opened" },
  { value: "cancelled", label: "Cancelled" },
] as const;

export type OperationalStatusValue =
  (typeof OPERATIONAL_STATUS_OPTIONS)[number]["value"];

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

export function getAmazonSearchTerm(row: PurchaseRow) {
  const ebayTitle = row.ebay_title || row.title || row.amazon_title || "";
  const searchTerm = cleanMarketplaceTitleForSearch(ebayTitle);

  return searchTerm || ebayTitle || "video game";
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
  return getOperationalStatus(row).value === "delivered";
}

export function getOperationalStatus(row: PurchaseRow): {
  value: OperationalStatusValue;
  label: string;
} {
  const itemStatus = normalizeStatus(row.current_status);
  const carrierStatus = normalizeStatus(
    row.normalized_status ||
      row.shipment_status ||
      row.carrier_status ||
      row.delivery_status
  );

  if (itemStatus === "return_opened") return statusOption("return_opened");
  if (row.ebay_cancelled || itemStatus === "cancelled") {
    return statusOption("cancelled");
  }
  if (carrierStatus === "delivered" || !!row.delivered_date) {
    return statusOption("delivered");
  }
  if (carrierStatus === "exception" || carrierStatus === "return_to_sender") {
    return statusOption("exception");
  }
  if (carrierStatus === "out_for_delivery") return statusOption("out_for_delivery");
  if (carrierStatus === "available_for_pickup") {
    return statusOption("available_for_pickup");
  }
  if (carrierStatus === "in_transit") return statusOption("in_transit");
  if (carrierStatus === "pre_transit" || carrierStatus === "unknown") {
    return statusOption("awaiting_carrier_scan");
  }
  if (row.tracking_number) return statusOption("awaiting_carrier_scan");
  if (row.seller_shipped) return statusOption("shipped_no_tracking");

  return statusOption("no_tracking");
}

function statusOption(value: OperationalStatusValue) {
  const option = OPERATIONAL_STATUS_OPTIONS.find((status) => status.value === value);

  if (!option) return OPERATIONAL_STATUS_OPTIONS[0];

  return option;
}

function normalizeStatus(value?: string | null) {
  if (!value) return "";

  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}
