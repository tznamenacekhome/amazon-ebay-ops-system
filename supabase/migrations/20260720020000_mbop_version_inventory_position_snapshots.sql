alter table public.inventory_positions
  add column if not exists is_current boolean not null default true,
  add column if not exists snapshot_token text;

create index if not exists inventory_positions_current_idx
  on public.inventory_positions (is_current, derivation_version, snapshot_token);

create or replace function public.replace_inventory_positions_current(
  positions jsonb,
  position_derivation_version text default 'inventory_state_v1',
  new_snapshot_token text default null
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted_count integer := 0;
  snapshot text := coalesce(new_snapshot_token, gen_random_uuid()::text);
begin
  update public.inventory_reconciliation_event_items
     set resolution_status = 'deferred'
   where resolution_status = 'open';

  insert into public.inventory_positions (
    purchase_item_id,
    amazon_sku_id,
    fba_shipment_id,
    fba_shipment_item_id,
    source_system,
    source_table,
    source_id,
    external_reference_type,
    external_reference_id,
    asin,
    seller_sku,
    fnsku,
    title,
    system,
    quantity,
    unit_cost,
    total_cost,
    currency,
    inventory_state,
    physical_location,
    marketplace_intent,
    listing_channel,
    operational_status,
    condition_disposition,
    reconciliation_status,
    needs_reconciliation,
    last_reconciled_at,
    derived_from,
    derivation_version,
    effective_at,
    is_current,
    snapshot_token
  )
  select
    purchase_item_id,
    amazon_sku_id,
    fba_shipment_id,
    fba_shipment_item_id,
    coalesce(source_system, 'mbop'),
    source_table,
    source_id,
    external_reference_type,
    external_reference_id,
    asin,
    seller_sku,
    fnsku,
    title,
    system,
    quantity,
    unit_cost,
    total_cost,
    coalesce(currency, 'USD'),
    inventory_state,
    physical_location,
    coalesce(marketplace_intent, 'undecided'),
    coalesce(listing_channel, 'none'),
    operational_status,
    coalesce(condition_disposition, 'new'),
    coalesce(reconciliation_status, 'not_checked'),
    coalesce(needs_reconciliation, false),
    last_reconciled_at,
    coalesce(derived_from, 'workflow_projection'),
    coalesce(derivation_version, position_derivation_version),
    coalesce(effective_at, now()),
    true,
    snapshot
  from jsonb_to_recordset(positions) as row_data (
    purchase_item_id uuid,
    amazon_sku_id uuid,
    fba_shipment_id uuid,
    fba_shipment_item_id uuid,
    source_system text,
    source_table text,
    source_id uuid,
    external_reference_type text,
    external_reference_id text,
    asin text,
    seller_sku text,
    fnsku text,
    title text,
    system text,
    quantity integer,
    unit_cost numeric(12, 4),
    total_cost numeric(14, 4),
    currency text,
    inventory_state text,
    physical_location text,
    marketplace_intent text,
    listing_channel text,
    operational_status text,
    condition_disposition text,
    reconciliation_status text,
    needs_reconciliation boolean,
    last_reconciled_at timestamptz,
    derived_from text,
    derivation_version text,
    effective_at timestamptz
  );

  get diagnostics inserted_count = row_count;

  update public.inventory_positions
     set is_current = false,
         updated_at = now()
   where derivation_version = position_derivation_version
     and is_current = true
     and coalesce(snapshot_token, '') <> snapshot;

  return inserted_count;
end;
$$;

comment on column public.inventory_positions.is_current is
'True for rows in the latest derived inventory snapshot. Historical snapshots are retained instead of deleted to avoid scheduled reconciliation delete timeouts.';

comment on column public.inventory_positions.snapshot_token is
'Opaque token identifying one inventory reconciliation snapshot refresh.';

comment on function public.replace_inventory_positions_current(jsonb, text, text) is
'Inserts a new derived inventory_positions snapshot and retires older current rows without deleting referenced history.';

revoke all on function public.replace_inventory_positions_current(jsonb, text, text) from public;
grant execute on function public.replace_inventory_positions_current(jsonb, text, text) to service_role;

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
where is_current = true
group by
  inventory_state,
  physical_location,
  marketplace_intent,
  listing_channel,
  operational_status,
  condition_disposition,
  reconciliation_status,
  needs_reconciliation;

grant select on public.vw_inventory_position_summary to service_role;
