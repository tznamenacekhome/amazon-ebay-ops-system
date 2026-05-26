-- Read-only Informed Repricer report snapshots.
--
-- Source: Informed Repricer Reports API.
--
-- This migration creates additive, Informed-specific snapshot tables for
-- repricing advisory intelligence. MBOP must not use the Informed Listings
-- Management API write/feed path in this feature, and must not write Informed
-- data into purchases, purchase_items, Amazon SP-API tables, Keepa tables, or
-- workflow-owned tables.

create table if not exists public.informed_report_runs (
  informed_report_run_id uuid primary key default gen_random_uuid(),

  report_type text not null,
  report_category text not null default 'listing',
  report_request_id text,
  processing_status text not null default 'created',

  requested_at timestamptz not null default now(),
  completed_at timestamptz,
  report_generated_at timestamptz,
  imported_at timestamptz,

  rows_read integer not null default 0,
  rows_inserted integer not null default 0,
  rows_skipped integer not null default 0,
  missing_asin_count integer not null default 0,
  missing_sku_count integer not null default 0,
  parse_error_count integer not null default 0,

  failure_reason text,
  raw_request_json jsonb,
  raw_status_json jsonb,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint informed_report_runs_category_check
    check (report_category in ('listing', 'rule', 'competition', 'performance', 'template', 'unknown')),

  constraint informed_report_runs_status_check
    check (processing_status in (
      'created',
      'pending',
      'in_progress',
      'complete',
      'imported',
      'error',
      'skipped'
    ))
);

comment on table public.informed_report_runs is
'Audit table for read-only Informed Repricer Reports API requests and imports. Signed download links are intentionally not persisted.';

create index if not exists informed_report_runs_type_requested_idx
  on public.informed_report_runs (report_type, requested_at desc);

create index if not exists informed_report_runs_request_id_idx
  on public.informed_report_runs (report_request_id);

create table if not exists public.informed_listing_snapshots (
  informed_listing_snapshot_id uuid primary key default gen_random_uuid(),
  informed_report_run_id uuid references public.informed_report_runs(informed_report_run_id) on delete set null,

  source_report_type text not null,
  source_row_number integer not null,
  report_generated_at timestamptz,
  imported_at timestamptz not null default now(),

  asin text,
  seller_sku text,
  marketplace text,
  fulfillment_channel text,

  repricing_enabled boolean,
  assigned_rule_name text,
  current_price numeric(12, 4),
  min_price numeric(12, 4),
  max_price numeric(12, 4),
  cost numeric(12, 4),
  buy_box_price numeric(12, 4),
  buy_box_status text,
  buy_box_winner boolean,
  competition_offer_count integer,
  quantity integer,
  listing_status text,

  raw_row_json jsonb not null,
  source text not null default 'informed_reports_api',
  created_at timestamptz not null default now(),

  unique (informed_report_run_id, source_row_number)
);

comment on table public.informed_listing_snapshots is
'Point-in-time read-only Informed Repricer listing/pricing report rows used by MBOP repricing advisor.';

create index if not exists informed_listing_snapshots_run_idx
  on public.informed_listing_snapshots (informed_report_run_id);

create index if not exists informed_listing_snapshots_asin_sku_idx
  on public.informed_listing_snapshots (asin, seller_sku, report_generated_at desc, imported_at desc);

create index if not exists informed_listing_snapshots_sku_idx
  on public.informed_listing_snapshots (seller_sku, report_generated_at desc, imported_at desc);

create index if not exists informed_listing_snapshots_rule_idx
  on public.informed_listing_snapshots (assigned_rule_name, report_generated_at desc);

create table if not exists public.informed_rule_snapshots (
  informed_rule_snapshot_id uuid primary key default gen_random_uuid(),
  informed_report_run_id uuid references public.informed_report_runs(informed_report_run_id) on delete set null,

  source_report_type text not null,
  source_row_number integer not null,
  report_generated_at timestamptz,
  imported_at timestamptz not null default now(),

  rule_name text,
  strategy_type text,
  marketplace text,
  fulfillment_channel text,
  rule_status text,
  min_price_behavior text,
  max_price_behavior text,
  buy_box_behavior text,
  competition_filters jsonb,
  repricing_safeguards jsonb,

  raw_row_json jsonb not null,
  source text not null default 'informed_reports_api',
  created_at timestamptz not null default now(),

  unique (informed_report_run_id, source_row_number)
);

comment on table public.informed_rule_snapshots is
'Point-in-time read-only Informed Repricer rule/settings report rows, populated only if a rule definition report is available.';

create index if not exists informed_rule_snapshots_run_idx
  on public.informed_rule_snapshots (informed_report_run_id);

create index if not exists informed_rule_snapshots_rule_idx
  on public.informed_rule_snapshots (rule_name, marketplace, fulfillment_channel, report_generated_at desc, imported_at desc);

create or replace view public.vw_latest_informed_listing_snapshot as
select distinct on (coalesce(asin, ''), coalesce(seller_sku, ''), coalesce(marketplace, ''))
  *
from public.informed_listing_snapshots
order by
  coalesce(asin, ''),
  coalesce(seller_sku, ''),
  coalesce(marketplace, ''),
  report_generated_at desc nulls last,
  imported_at desc;

create or replace view public.vw_latest_informed_rule_snapshot as
select distinct on (coalesce(rule_name, ''), coalesce(marketplace, ''), coalesce(fulfillment_channel, ''))
  *
from public.informed_rule_snapshots
order by
  coalesce(rule_name, ''),
  coalesce(marketplace, ''),
  coalesce(fulfillment_channel, ''),
  report_generated_at desc nulls last,
  imported_at desc;

grant all on table public.informed_report_runs to service_role;
grant all on table public.informed_listing_snapshots to service_role;
grant all on table public.informed_rule_snapshots to service_role;
grant select on public.vw_latest_informed_listing_snapshot to service_role;
grant select on public.vw_latest_informed_rule_snapshot to service_role;
