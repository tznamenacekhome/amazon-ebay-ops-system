-- Allow the daily Amazon-to-eBay coverage workflow to retain explicit
-- provenance when a selected, freshly eligible wholesale ASIN is its source.
alter table public.sourcing_seed_asins
  drop constraint if exists sourcing_seed_asins_source_mode_check;

alter table public.sourcing_seed_asins
  add constraint sourcing_seed_asins_source_mode_check check (source_mode in (
    'recent_sales',
    'full_listings',
    'wholesale_catalog',
    '1_recently_sold',
    '2_purchased_not_sent',
    '3_catalog_remaining'
  ));

comment on column public.sourcing_seed_asins.source_mode is
'Primary ASIN-discovery provenance. wholesale_catalog uses selected compatible wholesale matches with fresh shared New-condition eligibility; coverage priority remains separate.';
