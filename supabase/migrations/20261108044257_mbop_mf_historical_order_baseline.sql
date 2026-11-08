-- First-seen historical shipments cannot consume newly counted stock on a later non-shipping update.
create or replace function public.mbop_mf_apply_order(p_account uuid,p_item jsonb) returns void language plpgsql security invoker set search_path=public as $$
declare old public.amazon_mf_order_items; rowid uuid; q integer; shippedq integer; base integer:=0; demand integer; source_at timestamptz; start_at timestamptz;
begin
 select tracking_started_at into strict start_at from public.amazon_mf_accounts where id=p_account for update;
 if p_item->>'marketplace_id' is distinct from (select marketplace_id from public.amazon_mf_accounts where id=p_account)
 or p_item->>'fulfillment_channel'<>'MFN' then raise exception 'MF account/marketplace/channel mismatch';end if;
 source_at:=(p_item->>'source_updated_at')::timestamptz;
 if source_at is null then raise exception 'Source timestamp required';end if;
 q:=(p_item->>'ordered')::integer;shippedq:=(p_item->>'shipped')::integer;
 if q is null or shippedq is null or q<0 or shippedq<0 then raise exception 'Valid order quantities required';end if;
 select * into old from public.amazon_mf_order_items where account_id=p_account and amazon_order_id=p_item->>'amazon_order_id' and amazon_order_item_id=p_item->>'amazon_order_item_id';
 insert into public.amazon_mf_order_observations(account_id,amazon_order_id,amazon_order_item_id,source_updated_at,fingerprint,outcome,ordered,shipped,order_status)
 values(p_account,p_item->>'amazon_order_id',p_item->>'amazon_order_item_id',source_at,md5(p_item::text),
 case when source_at<old.source_updated_at then 'stale_ignored' when source_at=old.source_updated_at and old.source_payload is distinct from p_item then 'timestamp_conflict' else 'observed' end,q,shippedq,p_item->>'status') on conflict do nothing;
 if old.id is not null then
  if source_at<old.source_updated_at then return;end if;
  if source_at=old.source_updated_at then
    if old.source_payload is distinct from p_item then update public.amazon_mf_order_items set anomaly='Conflicting observations at identical source timestamp' where id=old.id;end if;
    return;
  end if;
  if old.seller_sku is distinct from p_item->>'seller_sku' or old.condition<>public.mbop_mf_condition(p_item->>'condition') or old.asin is distinct from p_item->>'asin' then
   update public.amazon_mf_order_items set anomaly='Order product identity changed; reconciliation required' where id=old.id;return;
  end if;
  base:=old.baseline_shipped;
  if source_at<start_at then base:=greatest(base,shippedq);end if;
 elsif source_at<start_at or (p_item->>'purchased_at')::timestamptz<start_at then base:=shippedq;
 end if;
 demand:=case when p_item->>'status' in ('Canceled','Shipped','Unfulfillable') then 0 else (p_item->>'unfulfilled')::integer end;
 if demand is null or demand<0 then raise exception 'Unfulfilled quantity required';end if;
 insert into public.amazon_mf_order_items(account_id,amazon_order_id,amazon_order_item_id,seller_sku,asin,title,condition,order_status,ordered,shipped,baseline_shipped,reservation_demand,source_updated_at,purchased_at,replacement_for,source_payload,anomaly)
 values(p_account,p_item->>'amazon_order_id',p_item->>'amazon_order_item_id',p_item->>'seller_sku',p_item->>'asin',p_item->>'title',public.mbop_mf_condition(p_item->>'condition'),p_item->>'status',q,greatest(shippedq,coalesce(old.shipped,0)),base,demand,source_at,(p_item->>'purchased_at')::timestamptz,coalesce(p_item->'replacement_for','[]'),p_item,
 case when old.id is null and base>0 and source_at>=start_at then 'Pre-tracking order first observed fulfilled; shipment timing requires reconciliation' when shippedq<old.shipped then 'Amazon shipped quantity decreased; physical stock was not restored' when shippedq+ demand>q then 'Fulfilled plus unfulfilled exceeds ordered quantity' when old.anomaly like 'Pre-tracking order first observed fulfilled%' then old.anomaly end)
 on conflict(account_id,amazon_order_id,amazon_order_item_id) do update set order_status=excluded.order_status,ordered=excluded.ordered,shipped=excluded.shipped,baseline_shipped=excluded.baseline_shipped,reservation_demand=excluded.reservation_demand,
 source_updated_at=excluded.source_updated_at,observed_at=now(),source_payload=excluded.source_payload,anomaly=excluded.anomaly returning id into rowid;
 if shippedq>greatest(coalesce(old.shipped,base),base) then
  insert into public.amazon_mf_shipment_events(order_item_id,cumulative_shipped,quantity,source_updated_at) values(rowid,shippedq,shippedq-greatest(coalesce(old.shipped,base),base),source_at) on conflict do nothing;
 end if;
 perform public.mbop_mf_allocate(p_account);
end $$;

