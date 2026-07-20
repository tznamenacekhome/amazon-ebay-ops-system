import type { PurchaseRow } from "./types";
import { cleanMarketplaceTitleForSearch } from "./titleCleaning";

export const OPERATIONAL_STATUS_OPTIONS = [
  { value: "no_tracking", label: "No Tracking" },
  { value: "shipped_no_tracking", label: "Shipped (No Tracking)" },
  { value: "awaiting_carrier_scan", label: "Awaiting Carrier Scan" },
  { value: "in_transit", label: "In Transit" },
  { value: "partially_delivered", label: "Partially Delivered" },
  { value: "multi_package_in_transit", label: "Multi-Package In Transit" },
  { value: "available_for_pickup", label: "Out for Pickup / Pickup Available" },
  { value: "out_for_delivery", label: "Out for Delivery" },
  { value: "delivered", label: "Delivered" },
  { value: "received", label: "Received" },
  { value: "listed", label: "Listed" },
  { value: "exception", label: "Exception" },
  { value: "return_pending", label: "Return Pending" },
  { value: "return_opened", label: "Return Opened" },
  { value: "cancelled", label: "Cancelled" },
] as const;

export type OperationalStatusValue =
  (typeof OPERATIONAL_STATUS_OPTIONS)[number]["value"];

export function formatDate(value?: string | null) {
  if (!value) return "";

  const dateOnlyMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})/);

  if (dateOnlyMatch) {
    const [, year, month, day] = dateOnlyMatch;
    return `${month}/${day}/${year.slice(2)}`;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const year = String(date.getUTCFullYear()).slice(2);

  return `${month}/${day}/${year}`;
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

export function ebayProblemDetailUrl(
  row: Pick<
    PurchaseRow,
    "ebay_action_url" | "ebay_inquiry_id" | "ebay_return_id"
  >
) {
  if (row.ebay_action_url) return row.ebay_action_url;
  if (row.ebay_inquiry_id) {
    return `https://www.ebay.com/ItemNotReceived/${row.ebay_inquiry_id}`;
  }
  if (row.ebay_return_id) {
    return `https://www.ebay.com/rtn/Return/ReturnsDetail?returnId=${row.ebay_return_id}`;
  }
  return "";
}

export function getPrimaryTitle(row: PurchaseRow) {
  return row.amazon_title || row.ebay_title || row.title || "Untitled item";
}

export function getEbayTitle(row: PurchaseRow) {
  return row.ebay_title || "";
}

export function getShipmentStatus(row: PurchaseRow) {
  return (
    row.normalized_status ||
    row.shipment_status ||
    row.carrier_status ||
    row.delivery_status ||
    ""
  );
}

export function getDisplayDeliveryDate(row: PurchaseRow) {
  return isDelivered(row) ? row.delivered_date : row.estimated_delivery_date;
}

export function getDisplayTitleParts(row: PurchaseRow) {
  const hasMatchedAsin = !!row.asin;
  const amazonTitle = row.amazon_title || "";
  const ebayTitle = getEbayTitle(row) || row.title || "";
  const primaryTitle = hasMatchedAsin
    ? amazonTitle || ebayTitle || "Untitled item"
    : ebayTitle || amazonTitle || "Untitled item";
  const showEbaySubtitle = hasMatchedAsin && !!amazonTitle && !!ebayTitle;

  return {
    primaryTitle,
    ebayTitle,
    showEbaySubtitle,
  };
}

export function isDelivered(row: PurchaseRow) {
  return ["delivered", "received", "listed"].includes(
    getOperationalStatus(row).value
  );
}

export function needsAsinReview(row: PurchaseRow) {
  const status = getOperationalStatus(row).value;
  if (["cancelled", "return_opened", "return_pending", "listed"].includes(status)) {
    return false;
  }

  const asin = (row.asin || "").trim().toUpperCase();
  const missingAsin = !asin || asin === "N/A";
  const missingSellPrice =
    row.sell_price === null &&
    row.sell_price !== 0 &&
    row.target_price === null &&
    row.target_price !== 0;
  const missingSystem = !row.system;
  const missingAmazonTitle = !!asin && asin !== "N/A" && !row.amazon_title;

  return missingAsin || missingSellPrice || missingSystem || missingAmazonTitle;
}

export function getOperationalStatus(row: PurchaseRow): {
  value: OperationalStatusValue;
  label: string;
} {
  const itemStatus = normalizeStatus(row.current_status);

  return statusOption(itemStatus as OperationalStatusValue);
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
