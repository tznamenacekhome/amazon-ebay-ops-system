alter table fba_shipments
  add column if not exists amazon_status_raw text,
  add column if not exists amazon_status_normalized text,
  add column if not exists fulfillment_center_id text,
  add column if not exists destination_fulfillment_center_id text,
  add column if not exists carrier_name text,
  add column if not exists tracking_number text,
  add column if not exists carrier_tracking_url text,
  add column if not exists carrier_pickup_at timestamptz,
  add column if not exists carrier_delivery_eta date,
  add column if not exists carrier_delivered_at timestamptz,
  add column if not exists amazon_checked_in_at timestamptz,
  add column if not exists amazon_receiving_started_at timestamptz,
  add column if not exists amazon_closed_at timestamptz,
  add column if not exists all_units_available_at timestamptz,
  add column if not exists units_sent integer,
  add column if not exists units_expected integer,
  add column if not exists units_received integer,
  add column if not exists units_available integer,
  add column if not exists units_reserved integer,
  add column if not exists units_unfulfillable integer,
  add column if not exists units_missing integer,
  add column if not exists fba_availability_pct numeric,
  add column if not exists cost_sent numeric,
  add column if not exists outbound_remaining_cost numeric,
  add column if not exists amazon_received_cost numeric,
  add column if not exists amazon_available_cost numeric,
  add column if not exists attention_flags jsonb not null default '[]'::jsonb,
  add column if not exists raw_amazon_shipment_json jsonb,
  add column if not exists raw_tracking_json jsonb,
  add column if not exists last_amazon_sync_at timestamptz,
  add column if not exists last_inventory_availability_sync_at timestamptz,
  add column if not exists updated_at timestamptz not null default now();

alter table fba_shipment_items
  add column if not exists seller_sku text,
  add column if not exists fnsku text,
  add column if not exists expected_quantity integer,
  add column if not exists received_quantity integer,
  add column if not exists available_quantity integer,
  add column if not exists reserved_quantity integer,
  add column if not exists unfulfillable_quantity integer,
  add column if not exists missing_quantity integer,
  add column if not exists outbound_remaining_quantity integer,
  add column if not exists cost_sent numeric,
  add column if not exists outbound_remaining_cost numeric,
  add column if not exists amazon_received_cost numeric,
  add column if not exists amazon_available_cost numeric,
  add column if not exists raw_amazon_item_json jsonb,
  add column if not exists availability_last_checked_at timestamptz,
  add column if not exists updated_at timestamptz not null default now();

create table if not exists fba_shipment_events (
  fba_shipment_event_id uuid primary key default gen_random_uuid(),
  fba_shipment_id uuid not null references fba_shipments(fba_shipment_id) on delete cascade,
  event_type text not null,
  event_source text not null,
  event_at timestamptz not null,
  fulfillment_center_id text,
  raw_event_json jsonb,
  created_at timestamptz not null default now(),
  unique (fba_shipment_id, event_type, event_source, event_at)
);

create index if not exists idx_fba_shipments_status
  on fba_shipments(amazon_status_normalized, workflow_status);

create index if not exists idx_fba_shipments_carrier_eta
  on fba_shipments(carrier_delivery_eta);

create index if not exists idx_fba_shipments_fulfillment_center
  on fba_shipments(fulfillment_center_id);

create index if not exists idx_fba_shipments_last_sync
  on fba_shipments(last_amazon_sync_at);

create index if not exists idx_fba_shipment_items_asin
  on fba_shipment_items(asin);

create index if not exists idx_fba_shipment_items_seller_sku
  on fba_shipment_items(seller_sku);

create index if not exists idx_fba_shipment_events_shipment
  on fba_shipment_events(fba_shipment_id, event_at);

grant all on table public.fba_shipment_events to service_role;
