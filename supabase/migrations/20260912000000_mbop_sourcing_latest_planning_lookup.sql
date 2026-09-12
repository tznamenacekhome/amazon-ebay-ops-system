-- Bounded, read-only sourcing projection. Reuses the existing (asin, captured_at
-- DESC) index; neither history nor the SKU-level repricing view is changed.
create function public.sourcing_latest_inventory_planning(requested_asins text[])
returns table (
  asin text, snapshot_date date, captured_at timestamptz,
  sales_shipped_last_30_days integer,
  inv_age_91_to_180_days integer, inv_age_181_to_270_days integer,
  inv_age_271_to_365_days integer, inv_age_365_plus_days integer,
  raw_planning_json jsonb
)
language plpgsql stable security invoker
set search_path = pg_catalog, public
set statement_timeout = '8s'
as $$
begin
  if cardinality(requested_asins) > 200 then
    raise exception 'At most 200 ASINs per sourcing planning lookup';
  end if;
  return query
  select p.asin, p.snapshot_date, p.captured_at,
    p.sales_shipped_last_30_days, p.inv_age_91_to_180_days,
    p.inv_age_181_to_270_days, p.inv_age_271_to_365_days,
    p.inv_age_365_plus_days,
    jsonb_build_object(
      'inv-age-31-to-60-days', p.raw_planning_json -> 'inv-age-31-to-60-days',
      'inv-age-61-to-90-days', p.raw_planning_json -> 'inv-age-61-to-90-days',
      'sales-shipped-last-30-days', p.raw_planning_json -> 'sales-shipped-last-30-days'
    )
  from (select distinct upper(btrim(a)) as asin
        from unnest(requested_asins) a where nullif(btrim(a), '') is not null) wanted
  cross join lateral (
    select s.* from public.amazon_inventory_planning_snapshots s
    where s.asin = wanted.asin
    order by s.captured_at desc, s.amazon_inventory_planning_snapshot_id desc
    limit 1
  ) p;
end;
$$;

revoke all on function public.sourcing_latest_inventory_planning(text[]) from public, anon, authenticated;
grant execute on function public.sourcing_latest_inventory_planning(text[]) to service_role;
comment on function public.sourcing_latest_inventory_planning(text[]) is
'Latest planning row per requested ASIN for sourcing age/sales exclusion. Tied captures use descending snapshot ID. No SKU aggregation; only three raw fallback values are returned.';
