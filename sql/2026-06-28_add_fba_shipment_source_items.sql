create table if not exists public.fba_shipment_source_items (
  fba_shipment_source_item_id uuid primary key default gen_random_uuid(),
  fba_shipment_id uuid not null references public.fba_shipments(fba_shipment_id) on delete cascade,
  source_type text not null,
  source_row_id uuid not null,
  amazon_return_recovery_case_id uuid references public.amazon_return_recovery_cases(amazon_return_recovery_case_id) on delete restrict,
  quantity integer not null default 1 check (quantity > 0),
  asin text not null,
  amazon_title text,
  seller_sku text,
  fnsku text,
  observed_condition text,
  workflow_state_at_save text,
  unit_cost numeric,
  target_price numeric,
  included boolean not null default true,
  expected_quantity integer,
  received_quantity integer,
  available_quantity integer,
  reserved_quantity integer,
  unfulfillable_quantity integer,
  missing_quantity integer,
  outbound_remaining_quantity integer,
  cost_sent numeric,
  outbound_remaining_cost numeric,
  amazon_received_cost numeric,
  amazon_available_cost numeric,
  raw_source_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint fba_shipment_source_items_source_type_check
    check (source_type in ('amazon_return_recovery')),
  constraint fba_shipment_source_items_return_case_required_check
    check (
      source_type <> 'amazon_return_recovery'
      or amazon_return_recovery_case_id is not null
    ),
  unique (fba_shipment_id, source_type, source_row_id)
);

create index if not exists idx_fba_shipment_source_items_shipment_id
  on public.fba_shipment_source_items(fba_shipment_id);

create index if not exists idx_fba_shipment_source_items_source
  on public.fba_shipment_source_items(source_type, source_row_id);

create index if not exists idx_fba_shipment_source_items_return_case
  on public.fba_shipment_source_items(amazon_return_recovery_case_id);

create index if not exists idx_fba_shipment_source_items_asin
  on public.fba_shipment_source_items(asin);

grant all on table public.fba_shipment_source_items to service_role;
