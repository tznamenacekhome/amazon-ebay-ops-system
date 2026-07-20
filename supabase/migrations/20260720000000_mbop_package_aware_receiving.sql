alter table public.inbound_shipment_items
  add column if not exists resolution_status text not null default 'open',
  add column if not exists resolved_at timestamptz,
  add column if not exists resolution_reason text,
  add column if not exists resolved_by text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'inbound_shipment_items_resolution_status_check'
      and conrelid = 'public.inbound_shipment_items'::regclass
  ) then
    alter table public.inbound_shipment_items
      add constraint inbound_shipment_items_resolution_status_check
      check (
        resolution_status in (
          'open',
          'received',
          'closed_fully_received_elsewhere',
          'missing',
          'return_pending'
        )
      );
  end if;
end $$;

create index if not exists inbound_shipment_items_resolution_idx
  on public.inbound_shipment_items (resolution_status, resolved_at);

create index if not exists inbound_shipment_items_item_resolution_idx
  on public.inbound_shipment_items (item_id, resolution_status);

comment on column public.inbound_shipment_items.resolution_status is
'Package-level receiving resolution for a purchase item link. Used to close extra seller tracking numbers once ordered units are fully accounted for.';

comment on column public.inbound_shipment_items.resolution_reason is
'Operator/system reason for package link closure, including fully received elsewhere and package-level missing/return outcomes.';
