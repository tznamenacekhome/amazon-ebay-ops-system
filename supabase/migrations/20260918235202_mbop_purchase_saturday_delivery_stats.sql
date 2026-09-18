-- Additive, read-only expected-arrival aggregate; no purchase/source writes.
set lock_timeout = '2s';
set statement_timeout = '10s';
create function public.purchase_saturday_delivery_stats(
  p_today date default (current_timestamp at time zone 'America/Los_Angeles')::date
) returns jsonb
language sql stable security invoker set search_path = '' as $$
  with cutoff as (
    select p_today + ((6 - extract(dow from p_today)::int + 7) % 7) as saturday
  ), candidates as (
    select v.item_id, v.quantity, v.unit_cost,
      coalesce(
        -- Carrier ETA is a date-only value: preserve its UTC calendar date.
        (v.estimated_delivery_date at time zone 'UTC')::date,
        case when e.eta ~ '^\d{4}-\d{2}-\d{2}' then left(e.eta,10)::date end,
        pi.expected_delivery
      ) as eta
    from public.vw_purchases_dashboard v
    join public.purchase_items pi on pi.item_id = v.item_id
    join public.purchases p on p.purchase_id = v.purchase_id
    left join lateral (
      select jsonb_path_query_first(p.raw_import_json,
        '$.**.EstimatedDeliveryTimeMax') #>> '{}' as eta
    ) e on true
    where pi.exclude_from_purchase_reporting is not true
      and v.current_status in ('no_tracking','shipped_no_tracking','awaiting_carrier_scan',
        'in_transit','partially_delivered','multi_package_in_transit','available_for_pickup',
        'out_for_delivery','exception')
  ), items as (
    -- Count each purchase item once, and use the latest ETA if joins repeat it.
    select item_id, quantity, unit_cost, max(eta) as eta
    from candidates group by item_id, quantity, unit_cost
  )
  select jsonb_build_object(
    'throughDate', (select saturday from cutoff),
    'units', coalesce(sum(quantity),0),
    'purchaseDollars', round(coalesce(sum(coalesce(unit_cost,0) * coalesce(quantity,0)),0),2),
    'unpricedUnits', coalesce(sum(case when unit_cost is null then quantity else 0 end),0)
  ) from items where eta <= (select saturday from cutoff);
$$;
revoke all on function public.purchase_saturday_delivery_stats(date) from public, anon, authenticated;
grant execute on function public.purchase_saturday_delivery_stats(date) to service_role;
notify pgrst, 'reload schema';
reset lock_timeout;
reset statement_timeout;
