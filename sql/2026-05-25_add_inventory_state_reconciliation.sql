-- Unified Inventory State + Inventory Reconciliation foundation.
--
-- This is an additive, derived inventory layer. It does not replace workflow
-- ownership in purchases, purchase_items, receiving, FBA shipment preparation,
-- or Amazon SP-API snapshot tables.

create table if not exists public.inventory_positions (
  inventory_position_id uuid primary key default gen_random_uuid(),

  -- Optional links back to authoritative workflow/source records.
  purchase_item_id uuid references public.purchase_items(item_id) on delete set null,
  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  fba_shipment_id uuid references public.fba_shipments(fba_shipment_id) on delete set null,
  fba_shipment_item_id uuid references public.fba_shipment_items(fba_shipment_item_id) on delete set null,

  source_system text not null default 'mbop',
  source_table text,
  source_id uuid,
  external_reference_type text,
  external_reference_id text,

  -- Product identity.
  asin text,
  seller_sku text,
  fnsku text,
  title text,
  system text,

  -- Position quantity and value. Cost basis must come from backend data.
  quantity integer not null check (quantity > 0),
  unit_cost numeric(12, 4),
  total_cost numeric(14, 4),
  currency text not null default 'USD',

  -- Normalized state dimensions. Do not collapse these into one status.
  inventory_state text not null,
  physical_location text not null,
  marketplace_intent text not null default 'undecided',
  listing_channel text not null default 'none',
  operational_status text not null,
  condition_disposition text not null default 'new',

  -- Reconciliation and audit metadata.
  reconciliation_status text not null default 'not_checked',
  needs_reconciliation boolean not null default false,
  last_reconciled_at timestamptz,
  derived_from text not null default 'workflow_projection',
  derivation_version text not null default 'inventory_state_v1',
  effective_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint inventory_positions_inventory_state_check
    check (inventory_state in (
      'purchased_not_shipped',
      'shipped_not_delivered',
      'delivered_not_received',
      'received_unassigned',
      'received_assigned_amazon_not_sent',
      'home_amazon_mfn_listed',
      'outbound_to_amazon',
      'amazon_fba_inbound_receiving',
      'amazon_fba_sellable',
      'amazon_fba_reserved',
      'amazon_fba_unsellable_damaged',
      'amazon_fba_stranded',
      'removed_from_amazon_home',
      'transferred_to_ebay',
      'home_ebay_resale_listed',
      'home_ebay_personal_listed',
      'sold_amazon',
      'sold_ebay',
      'return_pending',
      'return_opened',
      'cancelled_refund_follow_up',
      'disposed_donated_lost'
    )),

  constraint inventory_positions_physical_location_check
    check (physical_location in (
      'supplier',
      'in_transit_to_me',
      'home',
      'in_transit_to_amazon',
      'amazon_fba',
      'buyer',
      'disposed',
      'unknown'
    )),

  constraint inventory_positions_marketplace_intent_check
    check (marketplace_intent in (
      'amazon_fba',
      'amazon_mfn',
      'ebay_resale',
      'ebay_personal',
      'return_to_supplier',
      'undecided',
      'none'
    )),

  constraint inventory_positions_listing_channel_check
    check (listing_channel in ('amazon', 'ebay', 'none')),

  constraint inventory_positions_operational_status_check
    check (operational_status in (
      'purchased',
      'shipped',
      'delivered',
      'received',
      'ready_to_list',
      'listed',
      'sold',
      'return_pending',
      'return_opened',
      'cancelled',
      'needs_review',
      'removed',
      'transferred',
      'disposed',
      'lost'
    )),

  constraint inventory_positions_condition_disposition_check
    check (condition_disposition in (
      'new',
      'damaged',
      'restricted',
      'unsellable',
      'personal',
      'business_supply',
      'lost',
      'donated',
      'unknown'
    )),

  constraint inventory_positions_reconciliation_status_check
    check (reconciliation_status in (
      'not_checked',
      'matched',
      'mismatch',
      'missing_external',
      'missing_internal',
      'needs_review',
      'ignored'
    ))
);

comment on table public.inventory_positions is
'Derived current inventory positions for MBOP. Workflow tables remain authoritative; this layer normalizes location, marketplace intent, listing channel, operational state, and disposition for reconciliation.';

comment on column public.inventory_positions.inventory_state is
'Explicit operational inventory state label. State dimensions are also stored separately and should be used for filtering/reconciliation.';

create index if not exists inventory_positions_purchase_item_idx
  on public.inventory_positions (purchase_item_id);

create index if not exists inventory_positions_amazon_sku_idx
  on public.inventory_positions (amazon_sku_id);

create index if not exists inventory_positions_asin_idx
  on public.inventory_positions (asin);

create index if not exists inventory_positions_seller_sku_idx
  on public.inventory_positions (seller_sku);

create index if not exists inventory_positions_state_idx
  on public.inventory_positions (
    inventory_state,
    physical_location,
    marketplace_intent,
    listing_channel,
    operational_status,
    condition_disposition
  );

create index if not exists inventory_positions_reconciliation_idx
  on public.inventory_positions (needs_reconciliation, reconciliation_status);

create table if not exists public.inventory_movements (
  inventory_movement_id uuid primary key default gen_random_uuid(),
  inventory_position_id uuid references public.inventory_positions(inventory_position_id) on delete set null,
  purchase_item_id uuid references public.purchase_items(item_id) on delete set null,
  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  fba_shipment_id uuid references public.fba_shipments(fba_shipment_id) on delete set null,
  fba_shipment_item_id uuid references public.fba_shipment_items(fba_shipment_item_id) on delete set null,

  movement_type text not null,
  quantity integer not null check (quantity > 0),

  from_inventory_state text,
  to_inventory_state text,
  from_physical_location text,
  to_physical_location text,
  from_marketplace_intent text,
  to_marketplace_intent text,
  from_listing_channel text,
  to_listing_channel text,
  from_operational_status text,
  to_operational_status text,
  from_condition_disposition text,
  to_condition_disposition text,

  unit_cost numeric(12, 4),
  total_cost numeric(14, 4),
  currency text not null default 'USD',

  source_system text not null default 'mbop',
  source_table text,
  source_id uuid,
  external_reference_type text,
  external_reference_id text,
  notes text,
  raw_context_json jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),

  constraint inventory_movements_movement_type_check
    check (movement_type in (
      'purchase_created',
      'supplier_shipped',
      'delivered_to_me',
      'received_verified',
      'assigned_to_amazon',
      'listed_amazon_mfn',
      'fba_shipment_created',
      'fba_inbound_receiving',
      'fba_sellable',
      'fba_reserved',
      'fba_unsellable',
      'fba_stranded',
      'removed_from_amazon',
      'transferred_to_ebay',
      'listed_ebay_resale',
      'listed_ebay_personal',
      'sold_amazon',
      'sold_ebay',
      'return_pending',
      'return_opened',
      'cancelled',
      'disposed',
      'lost',
      'donated',
      'manual_adjustment',
      'reconciliation_adjustment'
    ))
);

comment on table public.inventory_movements is
'Append-only audit trail for inventory state/location/marketplace transitions. Existing workflow tables still own their own transitions; this table records normalized inventory movement projections.';

create index if not exists inventory_movements_position_idx
  on public.inventory_movements (inventory_position_id);

create index if not exists inventory_movements_purchase_item_idx
  on public.inventory_movements (purchase_item_id);

create index if not exists inventory_movements_amazon_sku_idx
  on public.inventory_movements (amazon_sku_id);

create index if not exists inventory_movements_occurred_at_idx
  on public.inventory_movements (occurred_at desc);

create index if not exists inventory_movements_type_idx
  on public.inventory_movements (movement_type);

create table if not exists public.inventory_reconciliation_events (
  inventory_reconciliation_event_id uuid primary key default gen_random_uuid(),
  reconciliation_type text not null,
  external_source text,
  external_snapshot_id uuid,
  external_snapshot_captured_at timestamptz,
  status text not null default 'completed',
  started_at timestamptz not null default now(),
  completed_at timestamptz,

  internal_positions_scanned integer not null default 0,
  external_rows_scanned integer not null default 0,
  matched_count integer not null default 0,
  mismatch_count integer not null default 0,
  missing_internal_count integer not null default 0,
  missing_external_count integer not null default 0,
  needs_review_count integer not null default 0,

  notes text,
  raw_summary_json jsonb,
  created_at timestamptz not null default now(),

  constraint inventory_reconciliation_events_type_check
    check (reconciliation_type in (
      'amazon_fba_inventory',
      'amazon_listing',
      'ebay_inventory',
      'manual',
      'scheduled'
    )),

  constraint inventory_reconciliation_events_status_check
    check (status in ('started', 'completed', 'failed', 'partial'))
);

comment on table public.inventory_reconciliation_events is
'Run-level reconciliation records comparing MBOP projected inventory positions to external inventory sources such as Amazon FBA snapshots.';

create index if not exists inventory_reconciliation_events_type_idx
  on public.inventory_reconciliation_events (reconciliation_type, started_at desc);

create index if not exists inventory_reconciliation_events_status_idx
  on public.inventory_reconciliation_events (status, started_at desc);

create table if not exists public.inventory_reconciliation_event_items (
  inventory_reconciliation_event_item_id uuid primary key default gen_random_uuid(),
  inventory_reconciliation_event_id uuid not null references public.inventory_reconciliation_events(inventory_reconciliation_event_id) on delete cascade,

  inventory_position_id uuid references public.inventory_positions(inventory_position_id) on delete set null,
  purchase_item_id uuid references public.purchase_items(item_id) on delete set null,
  amazon_sku_id uuid references public.amazon_skus(amazon_sku_id) on delete set null,
  fba_shipment_id uuid references public.fba_shipments(fba_shipment_id) on delete set null,
  fba_shipment_item_id uuid references public.fba_shipment_items(fba_shipment_item_id) on delete set null,

  severity text not null default 'info',
  issue_type text not null,
  resolution_status text not null default 'open',

  asin text,
  seller_sku text,
  fnsku text,
  title text,
  system text,

  mbop_quantity integer,
  amazon_total_quantity integer,
  amazon_fulfillable_quantity integer,
  amazon_inbound_quantity integer,
  amazon_reserved_quantity integer,
  amazon_unsellable_quantity integer,
  ebay_quantity integer,

  expected_inventory_state text,
  observed_inventory_state text,
  expected_physical_location text,
  observed_physical_location text,
  expected_marketplace_intent text,
  observed_marketplace_intent text,
  expected_listing_channel text,
  observed_listing_channel text,
  expected_operational_status text,
  observed_operational_status text,
  expected_condition_disposition text,
  observed_condition_disposition text,

  notes text,
  raw_internal_json jsonb,
  raw_external_json jsonb,
  first_seen_at timestamptz not null default now(),
  resolved_at timestamptz,
  created_at timestamptz not null default now(),

  constraint inventory_reconciliation_event_items_severity_check
    check (severity in ('info', 'warning', 'critical')),

  constraint inventory_reconciliation_event_items_issue_type_check
    check (issue_type in (
      'quantity_mismatch',
      'mbop_missing_from_amazon',
      'amazon_unknown_to_mbop',
      'amazon_inbound_discrepancy',
      'amazon_unsellable',
      'amazon_reserved',
      'amazon_stranded_or_suppressed',
      'amazon_removed_needs_home_state',
      'ebay_unknown_to_mbop',
      'ebay_transfer_missing',
      'marketplace_intent_mismatch',
      'listing_channel_mismatch',
      'condition_disposition_mismatch',
      'sku_mapping_missing',
      'asin_mapping_missing',
      'cost_basis_missing',
      'needs_operator_review'
    )),

  constraint inventory_reconciliation_event_items_resolution_check
    check (resolution_status in ('open', 'ignored', 'resolved', 'deferred'))
);

comment on table public.inventory_reconciliation_event_items is
'Item-level reconciliation findings. Used to answer what MBOP believes is owned, what Amazon/eBay believe exists, what is in transition, and what needs operator review.';

create index if not exists inventory_reconciliation_items_event_idx
  on public.inventory_reconciliation_event_items (inventory_reconciliation_event_id);

create index if not exists inventory_reconciliation_items_issue_idx
  on public.inventory_reconciliation_event_items (issue_type, resolution_status);

create index if not exists inventory_reconciliation_items_severity_idx
  on public.inventory_reconciliation_event_items (severity, resolution_status);

create index if not exists inventory_reconciliation_items_asin_idx
  on public.inventory_reconciliation_event_items (asin);

create index if not exists inventory_reconciliation_items_seller_sku_idx
  on public.inventory_reconciliation_event_items (seller_sku);

create or replace view public.vw_inventory_position_summary as
select
  inventory_state,
  physical_location,
  marketplace_intent,
  listing_channel,
  operational_status,
  condition_disposition,
  reconciliation_status,
  needs_reconciliation,
  count(*) as position_count,
  coalesce(sum(quantity), 0) as unit_count,
  coalesce(sum(total_cost), 0) as total_cost
from public.inventory_positions
group by
  inventory_state,
  physical_location,
  marketplace_intent,
  listing_channel,
  operational_status,
  condition_disposition,
  reconciliation_status,
  needs_reconciliation;

create or replace view public.vw_latest_amazon_fba_inventory_snapshot as
select distinct on (seller_sku, marketplace_id)
  *
from public.amazon_fba_inventory_snapshots
order by seller_sku, marketplace_id, captured_at desc;

create or replace view public.vw_open_inventory_reconciliation_items as
select
  rei.*,
  re.reconciliation_type,
  re.external_source,
  re.started_at as reconciliation_started_at,
  re.external_snapshot_captured_at
from public.inventory_reconciliation_event_items rei
join public.inventory_reconciliation_events re
  on re.inventory_reconciliation_event_id = rei.inventory_reconciliation_event_id
where rei.resolution_status = 'open';

grant all on table public.inventory_positions to service_role;
grant all on table public.inventory_movements to service_role;
grant all on table public.inventory_reconciliation_events to service_role;
grant all on table public.inventory_reconciliation_event_items to service_role;

grant select on public.vw_inventory_position_summary to service_role;
grant select on public.vw_latest_amazon_fba_inventory_snapshot to service_role;
grant select on public.vw_open_inventory_reconciliation_items to service_role;
