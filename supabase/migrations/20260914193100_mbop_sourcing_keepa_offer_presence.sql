-- MBOP read-only projection: the list only needs whether the offer array is nonempty.
set lock_timeout = '2s';
set statement_timeout = '30s';
create function public.sourcing_keepa_has_offers(public.vw_latest_keepa_product_snapshot)
returns boolean language sql stable parallel safe set search_path = '' as $$
  select case when jsonb_typeof($1.raw_keepa_json->'offers') = 'array'
    then jsonb_array_length($1.raw_keepa_json->'offers') > 0 else false end;
$$;
revoke all on function public.sourcing_keepa_has_offers(public.vw_latest_keepa_product_snapshot) from public,anon,authenticated;
grant execute on function public.sourcing_keepa_has_offers(public.vw_latest_keepa_product_snapshot) to service_role;
notify pgrst, 'reload schema';
reset lock_timeout;
reset statement_timeout;
