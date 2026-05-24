export type PurchaseRow = {
  purchase_id?: string;
  item_id?: string;
  supplier_order_id?: string;
  order_date?: string;
  amazon_title?: string | null;
  title?: string | null;
  ebay_title?: string | null;
  asin?: string | null;
  system?: string | null;
  quantity?: number | null;
  unit_cost?: number | null;
  sell_price?: number | null;
  target_price?: number | null;
  tracking_number?: string | null;
  supplier_sku?: string | null;
  supplier_listing_url?: string | null;
  ebay_listing_url?: string | null;
  carrier?: string | null;
  carrier_status?: string | null;
  delivery_status?: string | null;
  shipment_status?: string | null;
  normalized_status?: string | null;
  estimated_delivery_date?: string | null;
  delivered_date?: string | null;
  received_date?: string | null;
  current_status?: string | null;
  order_status?: string | null;
  seller_shipped?: boolean | null;
  ebay_cancelled?: boolean | null;
  marketplace?: "Amazon" | "eBay" | null;
};

export type PurchaseStats = {
  total: number;
  visible: number;
  needsReview: number;
  delivered: number;
};
