-- Non-eBay purchase COGS source table.
--
-- This table stores supplier purchase rows that did not originate in the eBay
-- buyer-purchase workflow. It is a COGS/source-data table for sales-order
-- profitability and must not write to purchases or purchase_items.

create table if not exists public.non_ebay_purchase_cogs_sources (
  non_ebay_purchase_cogs_source_id uuid primary key default gen_random_uuid(),

  source_system text not null default 'google_sheets',
  source_document_id text not null,
  source_document_title text,
  source_sheet_name text not null,
  source_row_number integer not null,

  fulfillment_channel text not null default 'Prep-Center',

  order_date date,
  supplier text,
  asin text not null,
  supplier_order_number text,
  msku text,
  description text,
  size_color text,
  bundles integer,
  quantity integer,
  received_by_prep_center_quantity integer,
  damaged_quantity integer,
  unit_cost numeric(14, 4),
  list_price numeric(14, 2),
  notes text,
  expiration_date date,
  tracking text,
  remarks text,

  raw_row_json jsonb,
  imported_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint non_ebay_purchase_cogs_sources_quantity_check
    check (quantity is null or quantity >= 0),
  constraint non_ebay_purchase_cogs_sources_received_check
    check (received_by_prep_center_quantity is null or received_by_prep_center_quantity >= 0),
  constraint non_ebay_purchase_cogs_sources_damaged_check
    check (damaged_quantity is null or damaged_quantity >= 0),
  constraint non_ebay_purchase_cogs_sources_unit_cost_check
    check (unit_cost is null or unit_cost >= 0),

  unique (source_document_id, source_sheet_name, source_row_number)
);

create index if not exists non_ebay_purchase_cogs_sources_asin_idx
  on public.non_ebay_purchase_cogs_sources (asin);

create index if not exists non_ebay_purchase_cogs_sources_order_date_idx
  on public.non_ebay_purchase_cogs_sources (order_date desc);

create index if not exists non_ebay_purchase_cogs_sources_fulfillment_idx
  on public.non_ebay_purchase_cogs_sources (fulfillment_channel);

create index if not exists non_ebay_purchase_cogs_sources_supplier_idx
  on public.non_ebay_purchase_cogs_sources (supplier);

grant all on table public.non_ebay_purchase_cogs_sources to service_role;

