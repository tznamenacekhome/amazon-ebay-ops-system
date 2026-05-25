create table if not exists fba_shipments (
  fba_shipment_id uuid primary key default gen_random_uuid(),
  shipment_code text not null unique,
  workflow_status text not null default 'finalized',
  notes text,
  created_at timestamptz not null default now(),
  finalized_at timestamptz
);

create table if not exists fba_shipment_items (
  fba_shipment_item_id uuid primary key default gen_random_uuid(),
  fba_shipment_id uuid not null references fba_shipments(fba_shipment_id) on delete cascade,
  item_id uuid not null references purchase_items(item_id) on delete restrict,
  quantity integer not null default 1 check (quantity > 0),
  asin text not null,
  amazon_title text,
  system text,
  unit_cost numeric,
  target_price numeric,
  included boolean not null default true,
  created_at timestamptz not null default now(),
  unique (fba_shipment_id, item_id)
);

create index if not exists idx_fba_shipment_items_item_id
  on fba_shipment_items(item_id);

create index if not exists idx_fba_shipment_items_shipment_id
  on fba_shipment_items(fba_shipment_id);

insert into fba_shipments (
  shipment_code,
  workflow_status,
  notes,
  finalized_at
)
values (
  'legacy_listed_no_shipment_id',
  'historical',
  'Historical Listed items imported before MBOP FBA shipment tracking; real Amazon shipment IDs were not backfilled.',
  now()
)
on conflict (shipment_code) do nothing;

insert into fba_shipment_items (
  fba_shipment_id,
  item_id,
  quantity,
  asin,
  amazon_title,
  system,
  unit_cost,
  target_price,
  included
)
select
  fs.fba_shipment_id,
  pi.item_id,
  coalesce(pi.quantity, 1),
  pi.asin,
  pi.amazon_title,
  pi.system,
  pi.unit_cost,
  pi.target_price,
  true
from purchase_items pi
cross join fba_shipments fs
where fs.shipment_code = 'legacy_listed_no_shipment_id'
  and pi.current_status = 'listed'
  and pi.asin is not null
  and not exists (
    select 1
    from fba_shipment_items fsi
    where fsi.item_id = pi.item_id
  );
