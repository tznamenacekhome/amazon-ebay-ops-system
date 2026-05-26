-- Read-only Amazon FBA Inventory Planning snapshots.
--
-- Source report type: GET_FBA_INVENTORY_PLANNING_DATA
--
-- This report is Amazon's native aged-inventory / inventory-health view.
-- It provides SKU-level sellable age buckets rather than exact per-unit
-- available-for-sale dates. MBOP uses it for repricing advisor age tiers
-- before attempting more granular ledger inference.
--
-- Amazon planning data is Amazon-specific and must not be written into
-- purchases, purchase_items, receiving, or FBA shipment workflow tables.

create table if not exists public.amazon_report_runs (
  amazon_report_run_id uuid primary key default gen_random_uuid(),

  report_type text not null,
  marketplace_id text not null,
  processing_status text not null default 'created',
  amazon_report_id text,
  amazon_document_id text,

  requested_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  data_start_time timestamptz,
  data_end_time timestamptz,

  rows_imported integer not null default 0,
  failure_reason text,
  raw_report_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.amazon_report_runs is
'Audit table for read-only Amazon SP-API report requests and imports. No Amazon seller order/customer data should be requested for MBOP inventory workflows.';

create index if not exists amazon_report_runs_type_requested_idx
  on public.amazon_report_runs (report_type, requested_at desc);

create index if not exists amazon_report_runs_report_id_idx
  on public.amazon_report_runs (amazon_report_id);

create table if not exists public.amazon_inventory_planning_snapshots (
  amazon_inventory_planning_snapshot_id uuid primary key default gen_random_uuid(),
  amazon_report_run_id uuid references public.amazon_report_runs(amazon_report_run_id) on delete set null,

  captured_at timestamptz not null default now(),
  snapshot_date date,
  marketplace_id text not null,

  seller_sku text not null,
  fnsku text,
  asin text,
  product_name text,
  condition text,

  available_quantity integer,
  pending_removal_quantity integer,

  -- Amazon-native sellable age buckets. These are the preferred first-pass
  -- repricing-advisor age signal for active Amazon FBA inventory.
  inv_age_0_to_90_days integer,
  inv_age_91_to_180_days integer,
  inv_age_181_to_270_days integer,
  inv_age_271_to_365_days integer,
  inv_age_365_plus_days integer,

  currency text,
  estimated_excess_quantity integer,
  estimated_storage_cost_next_month numeric(12, 4),
  estimated_ltsf_next_charge numeric(12, 4),
  recommended_action text,
  healthy_inventory_level integer,
  sales_shipped_last_7_days integer,
  sales_shipped_last_30_days integer,
  sales_shipped_last_60_days integer,
  sales_shipped_last_90_days integer,
  alert text,

  raw_planning_json jsonb not null,
  source text not null default 'amazon_spapi_report_GET_FBA_INVENTORY_PLANNING_DATA',
  created_at timestamptz not null default now()
);

comment on table public.amazon_inventory_planning_snapshots is
'Point-in-time read-only Amazon FBA Inventory Planning report rows. Used for Amazon-native aged-inventory buckets in the repricing advisor.';

create index if not exists amazon_inventory_planning_snapshots_sku_idx
  on public.amazon_inventory_planning_snapshots (seller_sku, marketplace_id, captured_at desc);

create index if not exists amazon_inventory_planning_snapshots_asin_idx
  on public.amazon_inventory_planning_snapshots (asin, captured_at desc);

create index if not exists amazon_inventory_planning_snapshots_snapshot_date_idx
  on public.amazon_inventory_planning_snapshots (snapshot_date desc);

create index if not exists amazon_inventory_planning_snapshots_age_idx
  on public.amazon_inventory_planning_snapshots (
    inv_age_91_to_180_days,
    inv_age_181_to_270_days,
    inv_age_271_to_365_days,
    inv_age_365_plus_days
  );

create or replace view public.vw_latest_amazon_inventory_planning_snapshot as
select distinct on (seller_sku, marketplace_id)
  *
from public.amazon_inventory_planning_snapshots
order by seller_sku, marketplace_id, captured_at desc;

grant all on table public.amazon_report_runs to service_role;
grant all on table public.amazon_inventory_planning_snapshots to service_role;
grant select on public.vw_latest_amazon_inventory_planning_snapshot to service_role;
