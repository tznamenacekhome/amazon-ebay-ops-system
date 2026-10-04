-- Allow an immutable source file to be replayed by a newer parser version.
-- Exact retries remain idempotent within the same parser version.
alter table public.wholesale_imports
  drop constraint wholesale_imports_supplier_id_effective_date_file_sha256_key;
alter table public.wholesale_imports
  add constraint wholesale_imports_source_parser_unique
  unique (supplier_id, effective_date, file_sha256, parser_version);

create or replace function public.wholesale_apply_import(p_payload jsonb, p_replaces_import_id uuid default null)
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
      and file_sha256 = p_payload->>'file_sha256'
      and parser_version = p_payload->>'parser_version';
  if found then
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

