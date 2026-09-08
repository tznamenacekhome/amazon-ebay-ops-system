-- MBOP-only sourcing evidence. No purchase/workflow rows are modified.
begin;
create table public.sourcing_declined_ebay_offers (
  ebay_legacy_item_id text primary key check (ebay_legacy_item_id ~ '^[0-9]+$'),
  declined_offer_amount numeric(12,2) not null check (declined_offer_amount > 0),
  currency text not null default 'USD' check (currency = 'USD'),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);
alter table public.sourcing_declined_ebay_offers enable row level security;
revoke all on public.sourcing_declined_ebay_offers from public, anon, authenticated;
grant select, insert, update on public.sourcing_declined_ebay_offers to service_role;

-- Atomic maximum: retries/concurrent syncs must never erase a higher decline.
create function public.record_sourcing_declined_offers(offers jsonb) returns void
language sql security invoker set search_path = pg_catalog, public as $$
  insert into public.sourcing_declined_ebay_offers (ebay_legacy_item_id, declined_offer_amount)
  select ebay_legacy_item_id, max(declined_offer_amount)
  from jsonb_to_recordset(offers) as x(ebay_legacy_item_id text, declined_offer_amount numeric)
  group by ebay_legacy_item_id
  on conflict (ebay_legacy_item_id) do update set
    declined_offer_amount = greatest(sourcing_declined_ebay_offers.declined_offer_amount, excluded.declined_offer_amount),
    last_seen_at = now();
$$;
revoke all on function public.record_sourcing_declined_offers(jsonb) from public, anon, authenticated;
grant execute on function public.record_sourcing_declined_offers(jsonb) to service_role;
comment on table public.sourcing_declined_ebay_offers is
  'Highest observed buyer-declined USD item offer per eBay listing. Absence from later API responses never clears evidence. Not a complete offer history.';
commit;
