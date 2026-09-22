-- Additive, read-only exact-date expected-arrival aggregates; no purchase/source writes.
set lock_timeout = '2s';
set statement_timeout = '10s';

create function public.purchase_daily_delivery_stats(
  p_start_date date default (current_timestamp at time zone 'America/Los_Angeles')::date,
  p_day_count integer default 7
) returns jsonb
language sql stable security invoker set search_path = '' as $$
  with days as (
    select p_start_date + day_offset as due_date
    from generate_series(0, greatest(least(p_day_count, 31), 1) - 1) as day_offset
  ), candidates as (
    select v.item_id, v.quantity, v.unit_cost,
      coalesce(
        -- Carrier ETA is a date-only value: preserve its UTC calendar date.
        (v.estimated_delivery_date at time zone 'UTC')::date,
        case when e.eta ~ '^\d{4}-\d{2}-\d{2}' then left(e.eta, 10)::date end,
        pi.expected_delivery
      ) as eta
    from public.vw_purchases_dashboard v
    join public.purchase_items pi on pi.item_id = v.item_id
    join public.purchases p on p.purchase_id = v.purchase_id
    left join lateral (
      select jsonb_path_query_first(
        p.raw_import_json,
        '$.**.EstimatedDeliveryTimeMax'
      ) #>> '{}' as eta
    ) e on true
    where pi.exclude_from_purchase_reporting is not true
      and v.current_status in (
        'no_tracking', 'shipped_no_tracking', 'awaiting_carrier_scan',
        'in_transit', 'partially_delivered', 'multi_package_in_transit',
        'available_for_pickup', 'out_for_delivery', 'exception'
      )
  ), items as (
    -- Count each purchase item once, and use the latest ETA if joins repeat it.
    select item_id, quantity, unit_cost, max(eta) as eta
    from candidates
    group by item_id, quantity, unit_cost
  ), totals as (
    select
      days.due_date,
      coalesce(sum(items.quantity), 0) as units,
      round(coalesce(sum(coalesce(items.unit_cost, 0) * coalesce(items.quantity, 0)), 0), 2) as dollars,
      coalesce(sum(case when items.unit_cost is null then items.quantity else 0 end), 0) as unpriced
    from days
    left join items on items.eta = days.due_date
    group by days.due_date
  )
  select jsonb_build_object(
    'startDate', p_start_date,
    'days', jsonb_agg(
      jsonb_build_object(
        'dueDate', due_date,
        'units', units,
        'purchaseDollars', dollars,
        'unpricedUnits', unpriced
      ) order by due_date
    )
  )
  from totals;
$$;

revoke all on function public.purchase_daily_delivery_stats(date, integer)
  from public, anon, authenticated;
grant execute on function public.purchase_daily_delivery_stats(date, integer)
  to service_role;

notify pgrst, 'reload schema';
reset lock_timeout;
reset statement_timeout;
