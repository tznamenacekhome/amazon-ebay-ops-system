-- Read-only aggregate of the authoritative purchase view; no source writes.
set lock_timeout = '2s';
set statement_timeout = '10s';
create function public.purchase_delivery_stats() returns jsonb
language sql stable security invoker set search_path = '' as $$
  with items as (
    -- Shipment joins may repeat an item; count purchased units only once.
    select distinct v.item_id, v.current_status, v.quantity, v.unit_cost
    from public.vw_purchases_dashboard v
    join public.purchase_items p on p.item_id = v.item_id
    where p.exclude_from_purchase_reporting is not true
      and v.current_status in ('no_tracking','shipped_no_tracking','awaiting_carrier_scan',
        'in_transit','partially_delivered','multi_package_in_transit','available_for_pickup',
        'out_for_delivery','exception','delivered')
  ), totals as (
    select current_status = 'delivered' as delivered,
      sum(coalesce(quantity,0)) as units,
      round(sum(coalesce(unit_cost,0) * coalesce(quantity,0)),2) as dollars,
      sum(case when unit_cost is null then coalesce(quantity,0) else 0 end) as unpriced
    from items group by current_status = 'delivered'
  )
  select jsonb_build_object(
    'notDelivered', coalesce((select jsonb_build_object('units',units,'purchaseDollars',dollars,'unpricedUnits',unpriced) from totals where not delivered), '{"units":0,"purchaseDollars":0,"unpricedUnits":0}'::jsonb),
    'deliveredNotReceived', coalesce((select jsonb_build_object('units',units,'purchaseDollars',dollars,'unpricedUnits',unpriced) from totals where delivered), '{"units":0,"purchaseDollars":0,"unpricedUnits":0}'::jsonb)
  );
$$;
revoke all on function public.purchase_delivery_stats() from public, anon, authenticated;
grant execute on function public.purchase_delivery_stats() to service_role;
notify pgrst, 'reload schema';
reset lock_timeout;
reset statement_timeout;
