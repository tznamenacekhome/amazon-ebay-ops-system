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
  original_tracking_number?: string | null;
  package_tracking_number?: string | null;
  package_link_id?: string | null;
  package_status?: string | null;
  package_delivered_date?: string | null;
  package_quantity_expected?: number | null;
  package_quantity_received?: number | null;
  package_resolution_status?: string | null;
  package_count?: number | null;
  packages_delivered?: number | null;
  packages_open?: number | null;
  inbound_packages?: InboundPackage[];
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
  notes?: string | null;
  order_status?: string | null;
  seller_shipped?: boolean | null;
  ebay_cancelled?: boolean | null;
  marketplace?: "Amazon" | "eBay" | null;
  exclude_from_purchase_reporting?: boolean | null;
  exclusion_reason?: string | null;
  problem_case_id?: string | null;
  problem_type?: string | null;
  problem_source?: string | null;
  workflow_state?: string | null;
  problem_priority?: string | null;
  problem_is_open?: boolean | null;
  problem_needs_response?: boolean | null;
  problem_next_action?: string | null;
  problem_next_action_due_at?: string | null;
  problem_escalation_available_at?: string | null;
  problem_first_detected_at?: string | null;
  problem_last_detected_at?: string | null;
  ebay_return_id?: string | null;
  ebay_inquiry_id?: string | null;
  ebay_case_id?: string | null;
  ebay_return_state?: string | null;
  ebay_return_status?: string | null;
  ebay_current_type?: string | null;
  ebay_action_url?: string | null;
  expected_refund_amount?: number | null;
  actual_refund_amount?: number | null;
  partial_refund_amount?: number | null;
  refund_currency?: string | null;
  replacement_tracking_number?: string | null;
  return_tracking_number?: string | null;
  problem_return_tracking_carrier?: string | null;
  problem_return_tracking_status?: string | null;
  problem_return_tracking_url?: string | null;
  problem_return_tracking_delivered_at?: string | null;
  problem_return_tracking_last_sync_at?: string | null;
  problem_return_label_printed_at?: string | null;
  problem_notes?: string | null;
  problem_episode_kind?: string | null;
  problem_episode_sequence?: number | null;
  problem_opened_reason?: string | null;
  problem_resolved_reason?: string | null;
  problem_superseded_by_case_id?: string | null;
  problem_source_artifact_type?: string | null;
  problem_return_needed_at?: string | null;
  problem_ebay_return_opened_at?: string | null;
  problem_seller_message_last_at?: string | null;
  problem_operator_responded_at?: string | null;
  problem_partial_refund_offered_at?: string | null;
  problem_partial_refund_accepted_at?: string | null;
  problem_label_available_at?: string | null;
  problem_return_shipped_at?: string | null;
  problem_seller_received_return_at?: string | null;
  problem_refund_due_at?: string | null;
  problem_refund_received_at?: string | null;
  problem_replacement_promised_at?: string | null;
  problem_replacement_shipped_at?: string | null;
  problem_replacement_estimated_delivery_date?: string | null;
  problem_replacement_carrier?: string | null;
  problem_replacement_carrier_status?: string | null;
  problem_replacement_delivered_date?: string | null;
  problem_replacement_tracking_url?: string | null;
  problem_replacement_last_tracking_sync?: string | null;
  problem_replacement_received_at?: string | null;
  problem_escalated_at?: string | null;
  problem_closed_at?: string | null;
  problem_events?: ProblemEvent[];
};

export type InboundPackage = {
  inbound_shipment_id?: string;
  inbound_shipment_item_id?: string | null;
  tracking_number?: string | null;
  carrier?: string | null;
  normalized_status?: string | null;
  carrier_status?: string | null;
  estimated_delivery_date?: string | null;
  delivered_date?: string | null;
  tracking_url?: string | null;
  quantity_expected_in_package?: number | null;
  quantity_received_from_package?: number | null;
  received_verified?: boolean | null;
  resolution_status?: string | null;
  resolution_reason?: string | null;
};

export type ProblemEvent = {
  problem_event_id?: string;
  event_type?: string | null;
  event_source?: string | null;
  event_at?: string | null;
  message?: string | null;
  amount?: number | null;
  currency?: string | null;
  tracking_number?: string | null;
  created_at?: string | null;
};

export type PurchaseStats = {
  total: number;
  visible: number;
  needsReview: number;
  orderProblems: number;
  delivered: number;
};

export type PurchaseSortColumn =
  | "order_date"
  | "supplier_order_id"
  | "item"
  | "asin"
  | "system"
  | "quantity"
  | "unit_cost"
  | "sell_price"
  | "carrier"
  | "eta"
  | "status";

export type PurchaseSortDirection = "asc" | "desc";

export type PurchaseQuery = {
  searchText: string;
  asinFilter: string;
  statusFilter: string;
  sortColumn: PurchaseSortColumn;
  sortDirection: PurchaseSortDirection;
  page: number;
  pageSize: number;
  problemStage?: string;
};

export type PurchasesApiResponse = {
  rows: PurchaseRow[];
  total: number;
  page: number;
  pageSize: number;
  stats: PurchaseStats;
};
