set role service_role;
insert into public.inbound_shipment_items(item_id,resolution_status,received_verified,quantity_received_from_package)
values ('00000000-0000-0000-0000-000000000001','open',false,1);
insert into public.purchase_items(item_id,purchase_id,quantity,unit_cost,current_status)
values ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002',1,26.07,'return_opened');
insert into public.order_problem_cases(problem_case_id,purchase_item_id,purchase_id,workflow_state,is_open,refund_received_at,refund_currency)
values ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','resolved_refunded',false,now(),'USD');

do $$ begin
  begin
    perform public.mbop_record_refunded_inventory_recovery('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000003',10,'refunded_replacement_received','Partial must fail');
    raise exception 'Partial refund unexpectedly accepted';
  exception when raise_exception then
    if sqlerrm = 'Partial refund unexpectedly accepted' then raise; end if;
  end;
end $$;
select public.mbop_record_refunded_inventory_recovery('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000003',26.07,'refunded_replacement_received','Correct item received after full refund');
do $$ begin
  if not exists(select 1 from public.purchase_items where unit_cost=0 and current_status='delivered' and received_date is null) then raise exception 'Not ready for Receiving'; end if;
  if not exists(select 1 from public.purchase_item_refund_recoveries where original_unit_cost=26.07 and refund_amount=26.07 and quantity=1) then raise exception 'Original accounting not preserved'; end if;
  if not exists(select 1 from public.inbound_shipment_items where resolution_status='open' and quantity_received_from_package=0 and not received_verified) then raise exception 'Wrong-item package quantity blocked new Receiving'; end if;
end $$;
-- Replayed buyer/return/shipment sync must not put the item back in returns or add cost.
update public.purchase_items set unit_cost=26.07,manual_unit_cost_override=false,current_status='return_opened';
do $$ begin
  if not exists(select 1 from public.purchase_items where unit_cost=0 and current_status='delivered' and manual_unit_cost_override) then raise exception 'Sync overwrote recovery'; end if;
end $$;
-- Existing Receiving and FBA transitions must remain available.
update public.purchase_items set current_status='received',received_date=current_date;
update public.purchase_items set current_status='return_opened';
do $$ begin
  if not exists(select 1 from public.purchase_items where current_status='received') then raise exception 'Stale return overrode Receiving'; end if;
end $$;
update public.purchase_items set current_status='listed';
select public.mbop_record_refunded_inventory_recovery('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000003',26.07,'refunded_replacement_received','Retry');
do $$ begin
  if (select count(*) from public.order_problem_events) <> 1 or (select count(*) from public.purchase_item_refund_recoveries) <> 1 then raise exception 'Retry duplicated accounting'; end if;
  if not exists(select 1 from public.purchase_items where current_status='listed') then raise exception 'Retry reset FBA status'; end if;
end $$;
-- New problem episodes must still work for this inventory.
insert into public.order_problem_cases(problem_case_id,purchase_item_id,purchase_id,workflow_state,is_open)
values ('00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','return_needed',true);
update public.purchase_items set current_status='return_pending';
update public.purchase_items set current_status='return_opened';
do $$ begin
  if not exists(select 1 from public.purchase_items where current_status='return_opened' and unit_cost=0) then raise exception 'New return was blocked'; end if;
  if has_table_privilege('anon','public.purchase_item_refund_recoveries','select') or has_function_privilege('authenticated','public.mbop_record_refunded_inventory_recovery(uuid,uuid,numeric,text,text,timestamptz)','execute') then raise exception 'Recovery exposed to clients'; end if;
end $$;
reset role;
select 'Refund recovery tests passed' as result;
