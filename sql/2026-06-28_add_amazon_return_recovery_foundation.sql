-- Amazon Return Recovery foundation.
--
-- This is an additive Amazon-side workflow for FBA removals and customer
-- returns returned to the business. It intentionally stays separate from
-- purchases, purchase_items, receiving, Order Problems, and FBA shipment prep.
-- Report row tables preserve Amazon evidence; recovery cases are the local
-- operator workflow surface.

create table if not exists public.amazon_return_recovery_cases (
  amazon_return_recovery_case_id uuid primary key default gen_random_uuid(),

  case_source text not null default 'amazon_report',
  workflow_state text not null default 'needs_inspection',
  decision text not null default 'needs_review',
  reimbursement_review_status text not null default 'not_reviewed',
  reimbursement_likelihood text not null default 'unknown',

  return_reason text,
  return_status text,
  return_disposition text,
  customer_comments text,
  evidence_summary text,

  lpn text,
  amazon_order_id text,
  merchant_order_id text,
  removal_order_id text,
  removal_shipment_id text,
  vret_id text,
  ra_number text,
  tracking_number text,

  asin text,
  seller_sku text,
  sku text,
  fnsku text,
  title text,
  quantity integer not null default 1 check (quantity > 0),

  fulfillment_center_id text,
  process_date date,
  return_date date,
  received_at timestamptz,
  inspected_at timestamptz,
  closed_at timestamptz,

  raw_evidence_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint amazon_return_recovery_cases_source_check
    check (case_source in (
      'amazon_customer_return_report',
      'amazon_reimbursement_report',
      'amazon_removal_order_report',
      'amazon_removal_shipment_report',
      'operator_scan',
      'manual',
      'amazon_report'
    )),

  constraint amazon_return_recovery_cases_workflow_state_check
    check (workflow_state in (
      'needs_inspection',
      'inspected',
      'decision_needed',
      'ready_to_send_back_to_amazon',
      'ready_for_ebay_listing',
      'disposed_donated',
      'reimbursement_review',
      'case_prepared',
      'reimbursement_pending',
      'reimbursement_received',
      'closed_no_reimbursement',
      'closed'
    )),

  constraint amazon_return_recovery_cases_decision_check
    check (decision in (
      'needs_review',
      'send_back_to_amazon',
      'sell_on_ebay',
      'dispose_donate'
    )),

  constraint amazon_return_recovery_cases_reimbursement_status_check
    check (reimbursement_review_status in (
      'not_reviewed',
      'not_reimbursement_worthy',
      'needs_review',
      'case_prepared',
      'case_opened',
      'reimbursement_pending',
      'reimbursed',
      'denied',
      'closed'
    )),

  constraint amazon_return_recovery_cases_likelihood_check
    check (reimbursement_likelihood in (
      'unknown',
      'unlikely',
      'possible',
      'likely',
      'confirmed'
    ))
);

comment on table public.amazon_return_recovery_cases is
'Amazon-side workflow cases for FBA customer returns and removals returned to the business. This table must not write to purchases, purchase_items, receiving, Order Problems, or FBA shipment prep workflow rows.';

create index if not exists amazon_return_recovery_cases_state_idx
  on public.amazon_return_recovery_cases (workflow_state, decision, reimbursement_review_status);

create index if not exists amazon_return_recovery_cases_lpn_idx
  on public.amazon_return_recovery_cases (lpn)
  where lpn is not null;

create index if not exists amazon_return_recovery_cases_tracking_idx
  on public.amazon_return_recovery_cases (tracking_number)
  where tracking_number is not null;

create index if not exists amazon_return_recovery_cases_order_idx
  on public.amazon_return_recovery_cases (amazon_order_id)
  where amazon_order_id is not null;

create index if not exists amazon_return_recovery_cases_asin_idx
  on public.amazon_return_recovery_cases (asin)
  where asin is not null;

create index if not exists amazon_return_recovery_cases_seller_sku_idx
  on public.amazon_return_recovery_cases (seller_sku)
  where seller_sku is not null;

create index if not exists amazon_return_recovery_cases_fnsku_idx
  on public.amazon_return_recovery_cases (fnsku)
  where fnsku is not null;

create index if not exists amazon_return_recovery_cases_removal_order_idx
  on public.amazon_return_recovery_cases (removal_order_id)
  where removal_order_id is not null;

create index if not exists amazon_return_recovery_cases_removal_shipment_idx
  on public.amazon_return_recovery_cases (removal_shipment_id)
  where removal_shipment_id is not null;

create index if not exists amazon_return_recovery_cases_vret_idx
  on public.amazon_return_recovery_cases (vret_id)
  where vret_id is not null;

create index if not exists amazon_return_recovery_cases_ra_number_idx
  on public.amazon_return_recovery_cases (ra_number)
  where ra_number is not null;

create table if not exists public.amazon_return_recovery_events (
  amazon_return_recovery_event_id uuid primary key default gen_random_uuid(),
  amazon_return_recovery_case_id uuid not null references public.amazon_return_recovery_cases(amazon_return_recovery_case_id) on delete cascade,

  event_type text not null,
  event_source text not null,
  event_at timestamptz not null default now(),
  message text,
  notes text,
  raw_event_json jsonb,
  created_at timestamptz not null default now(),

  constraint amazon_return_recovery_events_source_check
    check (event_source in ('system', 'operator', 'amazon_report', 'tracking', 'manual'))
);

create index if not exists amazon_return_recovery_events_case_event_at_idx
  on public.amazon_return_recovery_events (amazon_return_recovery_case_id, event_at desc);

create table if not exists public.amazon_fba_customer_return_rows (
  amazon_fba_customer_return_row_id uuid primary key default gen_random_uuid(),
  amazon_report_run_id uuid references public.amazon_report_runs(amazon_report_run_id) on delete set null,
  source_row_number integer not null,

  marketplace_id text,
  amazon_order_id text,
  merchant_order_id text,
  return_date date,
  seller_sku text,
  sku text,
  fnsku text,
  asin text,
  product_name text,
  title text,
  quantity integer,
  fulfillment_center_id text,
  detailed_disposition text,
  reason text,
  status text,
  license_plate_number text,
  customer_comments text,

  raw_row_json jsonb not null,
  imported_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (amazon_report_run_id, source_row_number)
);

comment on table public.amazon_fba_customer_return_rows is
'Raw and normalized rows from GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA. Return reason, disposition, status, LPN, and customer comments are preserved for Amazon Return Recovery evidence.';

create index if not exists amazon_fba_customer_return_rows_lpn_idx
  on public.amazon_fba_customer_return_rows (license_plate_number)
  where license_plate_number is not null;

create index if not exists amazon_fba_customer_return_rows_order_idx
  on public.amazon_fba_customer_return_rows (amazon_order_id)
  where amazon_order_id is not null;

create index if not exists amazon_fba_customer_return_rows_asin_idx
  on public.amazon_fba_customer_return_rows (asin)
  where asin is not null;

create index if not exists amazon_fba_customer_return_rows_seller_sku_idx
  on public.amazon_fba_customer_return_rows (seller_sku)
  where seller_sku is not null;

create index if not exists amazon_fba_customer_return_rows_fnsku_idx
  on public.amazon_fba_customer_return_rows (fnsku)
  where fnsku is not null;

create table if not exists public.amazon_fba_reimbursement_rows (
  amazon_fba_reimbursement_row_id uuid primary key default gen_random_uuid(),
  amazon_report_run_id uuid references public.amazon_report_runs(amazon_report_run_id) on delete set null,
  source_row_number integer not null,

  marketplace_id text,
  approval_date date,
  reimbursement_id text,
  case_id text,
  amazon_order_id text,
  reason text,
  seller_sku text,
  sku text,
  fnsku text,
  asin text,
  product_name text,
  title text,
  quantity_reimbursed integer,
  amount_total numeric(14, 2),
  amount_per_unit numeric(14, 4),
  currency text,

  raw_row_json jsonb not null,
  imported_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (amazon_report_run_id, source_row_number)
);

create index if not exists amazon_fba_reimbursement_rows_order_idx
  on public.amazon_fba_reimbursement_rows (amazon_order_id)
  where amazon_order_id is not null;

create index if not exists amazon_fba_reimbursement_rows_asin_idx
  on public.amazon_fba_reimbursement_rows (asin)
  where asin is not null;

create index if not exists amazon_fba_reimbursement_rows_seller_sku_idx
  on public.amazon_fba_reimbursement_rows (seller_sku)
  where seller_sku is not null;

create index if not exists amazon_fba_reimbursement_rows_fnsku_idx
  on public.amazon_fba_reimbursement_rows (fnsku)
  where fnsku is not null;

create table if not exists public.amazon_fba_removal_order_detail_rows (
  amazon_fba_removal_order_detail_row_id uuid primary key default gen_random_uuid(),
  amazon_report_run_id uuid references public.amazon_report_runs(amazon_report_run_id) on delete set null,
  source_row_number integer not null,

  marketplace_id text,
  removal_order_id text,
  order_type text,
  order_status text,
  requested_quantity integer,
  cancelled_quantity integer,
  disposed_quantity integer,
  shipped_quantity integer,
  in_process_quantity integer,
  removal_fee numeric(14, 2),
  currency text,
  request_date date,
  last_updated_date date,
  seller_sku text,
  sku text,
  fnsku text,
  asin text,
  product_name text,
  title text,
  disposition text,

  raw_row_json jsonb not null,
  imported_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (amazon_report_run_id, source_row_number)
);

create index if not exists amazon_fba_removal_order_detail_rows_removal_order_idx
  on public.amazon_fba_removal_order_detail_rows (removal_order_id)
  where removal_order_id is not null;

create index if not exists amazon_fba_removal_order_detail_rows_asin_idx
  on public.amazon_fba_removal_order_detail_rows (asin)
  where asin is not null;

create index if not exists amazon_fba_removal_order_detail_rows_seller_sku_idx
  on public.amazon_fba_removal_order_detail_rows (seller_sku)
  where seller_sku is not null;

create index if not exists amazon_fba_removal_order_detail_rows_fnsku_idx
  on public.amazon_fba_removal_order_detail_rows (fnsku)
  where fnsku is not null;

create table if not exists public.amazon_fba_removal_shipment_detail_rows (
  amazon_fba_removal_shipment_detail_row_id uuid primary key default gen_random_uuid(),
  amazon_report_run_id uuid references public.amazon_report_runs(amazon_report_run_id) on delete set null,
  source_row_number integer not null,

  marketplace_id text,
  removal_order_id text,
  removal_shipment_id text,
  shipment_date date,
  carrier text,
  tracking_number text,
  shipped_quantity integer,
  seller_sku text,
  sku text,
  fnsku text,
  asin text,
  product_name text,
  title text,
  disposition text,
  fulfillment_center_id text,
  license_plate_number text,
  vret_id text,
  ra_number text,

  raw_row_json jsonb not null,
  imported_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (amazon_report_run_id, source_row_number)
);

create index if not exists amazon_fba_removal_shipment_detail_rows_lpn_idx
  on public.amazon_fba_removal_shipment_detail_rows (license_plate_number)
  where license_plate_number is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_tracking_idx
  on public.amazon_fba_removal_shipment_detail_rows (tracking_number)
  where tracking_number is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_removal_order_idx
  on public.amazon_fba_removal_shipment_detail_rows (removal_order_id)
  where removal_order_id is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_removal_shipment_idx
  on public.amazon_fba_removal_shipment_detail_rows (removal_shipment_id)
  where removal_shipment_id is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_vret_idx
  on public.amazon_fba_removal_shipment_detail_rows (vret_id)
  where vret_id is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_ra_number_idx
  on public.amazon_fba_removal_shipment_detail_rows (ra_number)
  where ra_number is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_asin_idx
  on public.amazon_fba_removal_shipment_detail_rows (asin)
  where asin is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_seller_sku_idx
  on public.amazon_fba_removal_shipment_detail_rows (seller_sku)
  where seller_sku is not null;

create index if not exists amazon_fba_removal_shipment_detail_rows_fnsku_idx
  on public.amazon_fba_removal_shipment_detail_rows (fnsku)
  where fnsku is not null;

grant all on table public.amazon_return_recovery_cases to service_role;
grant all on table public.amazon_return_recovery_events to service_role;
grant all on table public.amazon_fba_customer_return_rows to service_role;
grant all on table public.amazon_fba_reimbursement_rows to service_role;
grant all on table public.amazon_fba_removal_order_detail_rows to service_role;
grant all on table public.amazon_fba_removal_shipment_detail_rows to service_role;
