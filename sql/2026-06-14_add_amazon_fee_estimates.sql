-- Amazon Product Fees estimate cache.
--
-- Additive only. Stores read-only SP-API Product Fees v0 estimates so FBA
-- prep can calculate shipment-time profit/ROI without calling Amazon on every
-- page load. Estimates are keyed by ASIN, marketplace, fulfillment channel,
-- and listing price because fees vary by price and fulfillment context.

create table if not exists public.amazon_fee_estimates (
  amazon_fee_estimate_id uuid primary key default gen_random_uuid(),

  asin text not null,
  marketplace_id text not null default 'ATVPDKIKX0DER',
  fulfillment_channel text not null default 'AFN',
  listing_price numeric(14, 2) not null,
  shipping_price numeric(14, 2) not null default 0,
  currency text not null default 'USD',

  total_fees_estimate numeric(14, 2),
  referral_fee_estimate numeric(14, 2),
  fba_fee_estimate numeric(14, 2),
  variable_closing_fee_estimate numeric(14, 2),
  fee_breakdown_json jsonb,
  raw_fee_estimate_json jsonb,

  estimate_status text not null default 'ok',
  status_message text,
  requested_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint amazon_fee_estimates_status_check
    check (estimate_status in ('ok', 'error', 'not_available'))
);

comment on table public.amazon_fee_estimates is
'Cached SP-API Product Fees v0 estimates used for pre-FBA shipment pricing and ROI review.';

create unique index if not exists amazon_fee_estimates_unique_price_uidx
  on public.amazon_fee_estimates (
    asin,
    marketplace_id,
    fulfillment_channel,
    listing_price,
    shipping_price,
    currency
  );

create index if not exists amazon_fee_estimates_asin_updated_idx
  on public.amazon_fee_estimates (asin, updated_at desc);

grant all on table public.amazon_fee_estimates to service_role;
