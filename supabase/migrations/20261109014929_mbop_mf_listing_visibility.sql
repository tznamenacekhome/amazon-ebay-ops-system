-- MF listing visibility uses current live offers, never inferred physical stock.
alter table public.amazon_mf_offers add column listing_state text not null default 'unknown'
 check(listing_state in ('in_stock','out_of_stock','inactive','unknown'));
create or replace function public.mbop_mf_apply_offer(p_account uuid,p_offer jsonb) returns void language plpgsql security invoker set search_path=public as $$
begin
 perform 1 from public.amazon_mf_accounts where id=p_account for update;
 insert into public.amazon_mf_offers(account_id,seller_sku,asin,title,condition,amazon_quantity,source_updated_at,observed_at,listing_status,brand,sync_run_id,listing_state)
 values(p_account,p_offer->>'seller_sku',p_offer->>'asin',p_offer->>'title',public.mbop_mf_condition(p_offer->>'condition'),(p_offer->>'quantity')::integer,(p_offer->>'source_updated_at')::timestamptz,(p_offer->>'observed_at')::timestamptz,
 array(select jsonb_array_elements_text(coalesce(p_offer->'status','[]'))),p_offer->>'brand',(p_offer->>'run_id')::uuid,coalesce(p_offer->>'listing_state','unknown'))
 on conflict(account_id,seller_sku) do update set asin=excluded.asin,title=excluded.title,condition=excluded.condition,amazon_quantity=excluded.amazon_quantity,
 source_updated_at=excluded.source_updated_at,observed_at=excluded.observed_at,listing_status=excluded.listing_status,brand=excluded.brand,sync_run_id=excluded.sync_run_id,listing_state=excluded.listing_state
 where excluded.observed_at>amazon_mf_offers.observed_at and coalesce(excluded.source_updated_at,'-infinity')>=coalesce(amazon_mf_offers.source_updated_at,'-infinity');
 -- Exact structured brand or explicitly reviewed ASIN from the prior Tilly audit.
 -- DO NOTHING preserves every later operator choice, including Keep MF=false.
 if lower(trim(p_offer->>'brand')) in ('tilly tackers','tilly tacker') or p_offer->>'asin'='B092FLB415' then
 insert into public.amazon_mf_preferences values(p_account,p_offer->>'seller_sku',true,'identified_tilly_default',now()) on conflict do nothing;
 end if;
 update public.amazon_mf_accounts set revision=revision+1,revised_at=now() where id=p_account;
end $$;

create view public.vw_mf_inventory_listings with(security_invoker=true) as
 select v.*,o.listing_state from public.vw_mf_inventory v
 join public.amazon_mf_offers o on o.account_id=v.account_id and o.seller_sku=v.seller_sku and o.condition=v.condition
 join public.amazon_mf_accounts a on a.id=v.account_id
 where o.listing_state in ('in_stock','out_of_stock','unknown')
 and a.offers_success_at is not null and o.observed_at>=a.offers_success_at;
revoke all on public.vw_mf_inventory_listings from public,anon,authenticated;
grant select on public.vw_mf_inventory_listings to service_role;
revoke all on function public.mbop_mf_apply_offer(uuid,jsonb) from public,anon,authenticated;
grant execute on function public.mbop_mf_apply_offer(uuid,jsonb) to service_role;
