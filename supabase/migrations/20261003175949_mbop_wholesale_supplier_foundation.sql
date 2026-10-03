-- MBOP Phase 1 only. Additive, server-only supplier catalog/history.
-- No purchase, sourcing, marketplace, receiving or College Planner objects change.
create table public.wholesale_suppliers (
  supplier_id uuid primary key default gen_random_uuid(),
  supplier_key text not null unique check (length(supplier_key) between 1 and 100),
  name text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.wholesale_suppliers (supplier_key, name)
values ('royal-electronics', 'Royal Electronics, Inc.');

create table public.wholesale_imports (
  import_id uuid primary key default gen_random_uuid(),
  supplier_id uuid not null references public.wholesale_suppliers(supplier_id),
  effective_date date not null,
  date_source text not null check (date_source in ('supplier_document', 'operator_parameter')),
  original_filename text not null,
  file_sha256 text not null check (file_sha256 ~ '^[0-9a-f]{64}$'),
  parser_version text not null,
  revision integer not null check (revision > 0),
  replaces_import_id uuid references public.wholesale_imports(import_id),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  status text not null check (status in ('completed', 'rejected')),
  summary jsonb not null check (jsonb_typeof(summary) = 'object'),
  warnings jsonb not null default '[]' check (jsonb_typeof(warnings) = 'array'),
  errors jsonb not null default '[]' check (jsonb_typeof(errors) = 'array'),
  source_rows jsonb not null check (jsonb_typeof(source_rows) = 'array'),
  system_counts jsonb not null default '{}',
  imported_at timestamptz not null default now(),
  unique (supplier_id, effective_date, file_sha256),
  unique (supplier_id, effective_date, revision),
  unique (import_id, supplier_id)
);
create index wholesale_imports_latest_idx
  on public.wholesale_imports (supplier_id, effective_date desc, revision desc)
  where status = 'completed';

create table public.wholesale_supplier_products (
  supplier_product_id uuid primary key default gen_random_uuid(),
  supplier_id uuid not null references public.wholesale_suppliers(supplier_id),
  identity_key text not null check (identity_key ~ '^[0-9a-f]{64}$'),
  -- First imported raw identity is immutable through the importer; each observation
  -- holds its own exact identity fields, including later formatting differences.
  raw_title text not null check (length(btrim(raw_title)) > 0),
  raw_system text not null check (length(btrim(raw_system)) > 0),
  raw_identifier text not null check (length(btrim(raw_identifier)) > 0),
  normalized_identifier text not null,
  identifier_type text not null,
  identifier_length integer not null,
  check_digit_valid boolean,
  identifier_status text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (supplier_id, identity_key),
  unique (supplier_product_id, supplier_id)
);

create table public.wholesale_supplier_observations (
  observation_id uuid primary key default gen_random_uuid(),
  supplier_product_id uuid not null,
  supplier_id uuid not null,
  import_id uuid not null,
  raw_title text not null,
  raw_system text not null,
  raw_identifier text not null,
  normalized_identifier text not null,
  identifier_type text not null,
  identifier_length integer not null,
  check_digit_valid boolean,
  identifier_status text not null,
  supplier_price numeric(12,2) not null check (supplier_price >= 0),
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  availability_raw text not null,
  availability_min integer check (availability_min >= 0),
  availability_is_exact boolean,
  source_row_numbers integer[] not null check (cardinality(source_row_numbers) > 0),
  created_at timestamptz not null default now(),
  foreign key (supplier_product_id, supplier_id)
    references public.wholesale_supplier_products(supplier_product_id, supplier_id),
  foreign key (import_id, supplier_id)
    references public.wholesale_imports(import_id, supplier_id),
  unique (supplier_product_id, import_id),
  check ((availability_min is null) = (availability_is_exact is null))
);
create index wholesale_observations_import_idx on public.wholesale_supplier_observations(import_id);

comment on table public.wholesale_supplier_products is
'Supplier-scoped catalog, not purchased inventory. Royal v1 identity: SHA256 of JSON [casefolded whitespace-normalized identifier, SYS, title]. No barcode repair or fuzzy matching.';
comment on table public.wholesale_supplier_observations is
'Immutable supplier quotes. Missing from a later list does not mean zero stock or discontinuation. Absence of USED is not verification of New/sealed condition.';

alter table public.wholesale_suppliers enable row level security;
alter table public.wholesale_imports enable row level security;
alter table public.wholesale_supplier_products enable row level security;
alter table public.wholesale_supplier_observations enable row level security;
revoke all on public.wholesale_suppliers, public.wholesale_imports,
  public.wholesale_supplier_products, public.wholesale_supplier_observations from public, anon, authenticated;
grant select, insert, update on public.wholesale_suppliers to service_role;
grant select, insert on public.wholesale_imports, public.wholesale_supplier_products,
  public.wholesale_supplier_observations to service_role;

-- One transaction, serialized per supplier. A failed write rolls back the entire list.
-- Completed imports and their observations are append-only; corrections are revisions.
create function public.wholesale_apply_import(p_payload jsonb, p_replaces_import_id uuid default null)
returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
  v_supplier public.wholesale_suppliers%rowtype;
  v_existing public.wholesale_imports%rowtype;
  v_current public.wholesale_imports%rowtype;
  v_date date := (p_payload->>'effective_date')::date;
  v_id uuid := gen_random_uuid();
  v_product uuid;
  v_revision integer;
  v_item jsonb;
  v_count integer;
  v_matched integer := 0;
  v_summary jsonb;
begin
  if jsonb_typeof(p_payload->'products') is distinct from 'array'
     or jsonb_typeof(p_payload->'source_rows') is distinct from 'array'
     or jsonb_typeof(p_payload->'errors') is distinct from 'array'
     or jsonb_typeof(p_payload->'summary') is distinct from 'object'
     or length(p_payload::text) > 10000000 then
    raise exception 'Invalid or oversized wholesale payload';
  end if;
  v_count := jsonb_array_length(p_payload->'products');
  if v_count > 5000 or jsonb_array_length(p_payload->'source_rows') > 10000
     or v_date is null or (p_payload->>'status') is null
     or (p_payload->>'status') not in ('completed', 'rejected')
     or (p_payload->>'status' = 'completed'
         and coalesce((p_payload->'summary'->>'rows_encountered')::integer, 0) < 1) then
    raise exception 'Invalid import status, date or row count';
  end if;
  if (p_payload->>'status' = 'completed') <> (jsonb_array_length(p_payload->'errors') = 0) then
    raise exception 'Import status and errors disagree';
  end if;
  select * into strict v_supplier from public.wholesale_suppliers
    where supplier_key = p_payload->>'supplier_key' for update;
  if not v_supplier.is_active then raise exception 'Supplier is inactive'; end if;
  if v_supplier.supplier_key = 'royal-electronics' and p_payload->>'currency' is distinct from 'USD' then
    raise exception 'Royal prices must be USD';
  end if;
  select * into v_existing from public.wholesale_imports
    where supplier_id = v_supplier.supplier_id and effective_date = v_date
      and file_sha256 = p_payload->>'file_sha256';
  if found then
    if v_existing.parser_version <> p_payload->>'parser_version' then
      raise exception 'Identical source already parsed with a different version; explicit reconciliation required';
    end if;
    return jsonb_build_object('import_id', v_existing.import_id, 'status', v_existing.status,
      'already_imported', true, 'summary', v_existing.summary,
      'products_created', 0, 'products_matched', 0, 'observations_created', 0);
  end if;
  select * into v_current from public.wholesale_imports
    where supplier_id = v_supplier.supplier_id and effective_date = v_date and status = 'completed'
    order by revision desc limit 1;
  if v_current.import_id is distinct from p_replaces_import_id then
    raise exception 'Same-date correction requires replaces_import_id of the latest completed import (or null for a new date)';
  end if;
  select coalesce(max(revision), 0) + 1 into v_revision from public.wholesale_imports
    where supplier_id = v_supplier.supplier_id and effective_date = v_date;
  if p_payload->>'status' = 'completed' then
    if (select count(distinct x->>'identity_key') from jsonb_array_elements(p_payload->'products') x) <> v_count then
      raise exception 'Duplicate or missing product identities in import';
    end if;
    select count(*) into v_matched from public.wholesale_supplier_products p
      join jsonb_array_elements(p_payload->'products') x on p.identity_key = x->>'identity_key'
      where p.supplier_id = v_supplier.supplier_id;
  else
    v_count := 0;
  end if;
  v_summary := (p_payload->'summary') || jsonb_build_object(
    'rows_imported', v_count, 'products_created', v_count - v_matched,
    'products_matched', v_matched, 'observations_created', v_count);
  insert into public.wholesale_imports(import_id, supplier_id, effective_date, date_source,
    original_filename, file_sha256, parser_version, revision, replaces_import_id,
    currency, status, summary, warnings, errors, source_rows, system_counts)
  values(v_id, v_supplier.supplier_id, v_date, p_payload->>'date_source',
    p_payload->>'filename', p_payload->>'file_sha256', p_payload->>'parser_version', v_revision,
    p_replaces_import_id, p_payload->>'currency', p_payload->>'status', v_summary,
    p_payload->'warnings', p_payload->'errors', p_payload->'source_rows', p_payload->'system_counts');
  if p_payload->>'status' = 'completed' then
    for v_item in select value from jsonb_array_elements(p_payload->'products') loop
      if v_item->>'currency' is distinct from p_payload->>'currency'
         or v_item->>'raw_title' ~* '\mUSED\M' or v_item->>'raw_system' ~* '\mUSED\M' then
        raise exception 'Invalid accepted product currency or explicit USED marker';
      end if;
      insert into public.wholesale_supplier_products(supplier_id, identity_key, raw_title, raw_system,
        raw_identifier, normalized_identifier, identifier_type, identifier_length, check_digit_valid, identifier_status)
      values(v_supplier.supplier_id, v_item->>'identity_key', v_item->>'raw_title', v_item->>'raw_system',
        v_item->>'raw_identifier', v_item->>'normalized_identifier', v_item->>'identifier_type',
        (v_item->>'identifier_length')::integer, (v_item->>'check_digit_valid')::boolean, v_item->>'identifier_status')
      on conflict (supplier_id, identity_key) do nothing;
      select supplier_product_id into strict v_product from public.wholesale_supplier_products
        where supplier_id = v_supplier.supplier_id and identity_key = v_item->>'identity_key';
      insert into public.wholesale_supplier_observations(supplier_product_id, supplier_id, import_id,
        raw_title, raw_system, raw_identifier, normalized_identifier, identifier_type, identifier_length,
        check_digit_valid, identifier_status, supplier_price, currency, availability_raw,
        availability_min, availability_is_exact, source_row_numbers)
      values(v_product, v_supplier.supplier_id, v_id,
        v_item->>'raw_title', v_item->>'raw_system', v_item->>'raw_identifier',
        v_item->>'normalized_identifier', v_item->>'identifier_type', (v_item->>'identifier_length')::integer,
        (v_item->>'check_digit_valid')::boolean, v_item->>'identifier_status',
        (v_item->>'supplier_price')::numeric, v_item->>'currency', v_item->>'availability_raw',
        (v_item->>'availability_min')::integer, (v_item->>'availability_is_exact')::boolean,
        array(select value::integer from jsonb_array_elements_text(v_item->'source_row_numbers')));
    end loop;
  end if;
  return jsonb_build_object('import_id', v_id, 'status', p_payload->>'status',
    'already_imported', false, 'summary', v_summary,
    'products_created', v_count - v_matched, 'products_matched', v_matched, 'observations_created', v_count);
end;
$$;
revoke all on function public.wholesale_apply_import(jsonb, uuid) from public, anon, authenticated;
grant execute on function public.wholesale_apply_import(jsonb, uuid) to service_role;

-- Read surfaces include correction provenance rather than silently dropping history.
create view public.vw_wholesale_observation_history with (security_invoker = true) as
select o.*, i.effective_date, i.revision, i.original_filename, i.imported_at,
  exists(select 1 from public.wholesale_imports newer
    where newer.supplier_id = i.supplier_id and newer.effective_date = i.effective_date
      and newer.status = 'completed' and newer.revision > i.revision) as is_superseded
from public.wholesale_supplier_observations o
join public.wholesale_imports i on i.import_id = o.import_id
where i.status = 'completed';

create view public.vw_wholesale_supplier_products with (security_invoker = true) as
select p.*, latest.effective_date as last_seen_date,
  current_list.import_id as current_list_import_id,
  current_list.effective_date as current_list_date,
  exists(select 1 from public.wholesale_supplier_observations present
    where present.supplier_product_id = p.supplier_product_id
      and present.import_id = current_list.import_id) as present_in_latest_list,
  to_jsonb(latest) as latest_observation
from public.wholesale_supplier_products p
left join lateral (
  select h.* from public.vw_wholesale_observation_history h
  where h.supplier_product_id = p.supplier_product_id and not h.is_superseded
  order by h.effective_date desc, h.revision desc limit 1
) latest on true
left join lateral (
  select i.import_id, i.effective_date from public.wholesale_imports i
  where i.supplier_id = p.supplier_id and i.status = 'completed'
  order by i.effective_date desc, i.revision desc limit 1
) current_list on true;

revoke all on public.vw_wholesale_observation_history, public.vw_wholesale_supplier_products
  from public, anon, authenticated;
grant select on public.vw_wholesale_observation_history, public.vw_wholesale_supplier_products to service_role;
