-- Disposable PostgreSQL fixture only. Never load these fixture tables in production.
create role anon;
create role authenticated;
create role service_role bypassrls;
create table public.purchase_items (
  item_id uuid primary key, purchase_id uuid, quantity integer, unit_cost numeric,
  current_status text, manual_unit_cost_override boolean, received_date date,
  exclude_from_purchase_reporting boolean default false, exclusion_reason text, notes text
);
create table public.order_problem_cases (
  problem_case_id uuid primary key, purchase_item_id uuid, purchase_id uuid,
  workflow_state text, is_open boolean, refund_received_at timestamptz,
  actual_refund_amount numeric, refund_currency text, replacement_received_at timestamptz,
  notes text, updated_at timestamptz
);
create table public.inbound_shipment_items (
  item_id uuid, resolution_status text, resolved_at timestamptz, resolution_reason text,
  resolved_by text, received_verified boolean, quantity_received_from_package integer
);
create table public.order_problem_events (
  problem_case_id uuid,event_type text,event_source text,event_at timestamptz,
  message text,amount numeric,currency text,raw_json jsonb
);
grant usage on schema public to service_role;
grant all on all tables in schema public to service_role;

-- Migration is concatenated here by the test command before the assertions below.
