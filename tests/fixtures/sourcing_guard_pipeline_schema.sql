-- Disposable-only reduced fixture schema, not a production migration.
-- Mirrors release-input columns from purchase_items and the FBA shipment SQL.
create table if not exists public.purchase_items (
  item_id uuid primary key default gen_random_uuid(), asin text, quantity integer,
  current_status text, marketplace text, exclude_from_purchase_reporting boolean
);
create table if not exists public.fba_shipments (
  fba_shipment_id uuid primary key default gen_random_uuid(), shipment_code text,
  workflow_status text, amazon_status_normalized text
);
create table if not exists public.fba_shipment_items (
  fba_shipment_item_id uuid primary key default gen_random_uuid(),
  fba_shipment_id uuid references public.fba_shipments,
  item_id uuid references public.purchase_items, quantity integer, included boolean,
  outbound_remaining_quantity integer, received_quantity integer, available_quantity integer
);
