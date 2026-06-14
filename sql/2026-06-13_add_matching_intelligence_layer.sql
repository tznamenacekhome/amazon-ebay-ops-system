-- MBOP Matching Intelligence Layer foundation.
--
-- Additive only. Sourcing remains advisory and marketplace integrations remain
-- read-only. These tables preserve evidence and derived labels for future
-- matching diagnostics; they do not replace sourcing, purchases, receiving,
-- order problems, or Amazon workflow ownership.

alter table public.sourcing_actions
  add column if not exists raw_action_context jsonb,
  add column if not exists listing_snapshot_id uuid;

alter table public.sourcing_opportunities
  add column if not exists initial_listing_snapshot_id uuid,
  add column if not exists latest_listing_snapshot_id uuid,
  add column if not exists seller_trust_status text,
  add column if not exists seller_trust_score numeric(8, 4),
  add column if not exists matching_diagnostics_json jsonb;

create table if not exists public.sourcing_listing_snapshots (
  listing_snapshot_id uuid primary key default gen_random_uuid(),

  -- Source/event links. Nullable because some snapshots may be built from
  -- historical evidence where only one side is still available.
  opportunity_id uuid references public.sourcing_opportunities(opportunity_id) on delete set null,
  candidate_id uuid references public.sourcing_ebay_candidates(candidate_id) on delete set null,
  action_id uuid references public.sourcing_actions(action_id) on delete set null,
  sourcing_run_id uuid references public.sourcing_runs(sourcing_run_id) on delete set null,

  snapshot_event text not null,
  snapshot_source text not null default 'mbop',

  -- Amazon context.
  asin text,
  amazon_title text,
  amazon_system text,
  amazon_image_url text,
  target_sale_price numeric(14, 2),
  target_sale_price_source text,

  -- eBay identity and listing context.
  ebay_item_id text,
  ebay_legacy_item_id text,
  ebay_title text,
  ebay_subtitle text,
  ebay_description text,
  ebay_condition text,
  ebay_condition_id text,
  ebay_category text,
  ebay_category_id text,
  ebay_category_path text,
  ebay_item_specifics_json jsonb,
  ebay_primary_image_url text,
  ebay_image_urls jsonb,
  ebay_listing_url text,

  -- Pricing/availability.
  price numeric(14, 2),
  shipping_cost numeric(14, 2),
  landed_cost numeric(14, 2),
  shipping_is_separate boolean,
  quantity_available integer,
  buying_options jsonb,
  listing_status text,

  -- Seller and location context.
  seller_username text,
  seller_feedback_score integer,
  seller_feedback_percentage numeric(8, 4),
  seller_status text,
  item_location_country text,
  ships_to_configured_zip boolean,

  raw_ebay_json jsonb,
  raw_context_json jsonb,
  captured_at timestamptz not null default now(),
  created_at timestamptz not null default now(),

  constraint sourcing_listing_snapshots_event_check
    check (snapshot_event in (
      'opportunity_created',
      'dismissed',
      'watching',
      'purchased',
      'offer_made',
      'roi_snoozed',
      'availability_refresh',
      'backfill'
    ))
);

comment on table public.sourcing_listing_snapshots is
'Point-in-time evidence snapshots for sourced eBay listings that became MBOP opportunities or received operator/system actions.';

create index if not exists sourcing_listing_snapshots_opportunity_idx
  on public.sourcing_listing_snapshots (opportunity_id, captured_at desc);

create index if not exists sourcing_listing_snapshots_candidate_idx
  on public.sourcing_listing_snapshots (candidate_id, captured_at desc);

create index if not exists sourcing_listing_snapshots_ebay_item_idx
  on public.sourcing_listing_snapshots (ebay_legacy_item_id, ebay_item_id);

create index if not exists sourcing_listing_snapshots_seller_idx
  on public.sourcing_listing_snapshots (seller_username, captured_at desc);

create table if not exists public.matching_intelligence_examples (
  matching_intelligence_example_id uuid primary key default gen_random_uuid(),

  source_table text not null,
  source_id text not null,
  source_detail text,
  source_weight numeric(8, 4) not null default 1,

  listing_snapshot_id uuid references public.sourcing_listing_snapshots(listing_snapshot_id) on delete set null,
  opportunity_id uuid references public.sourcing_opportunities(opportunity_id) on delete set null,
  candidate_id uuid references public.sourcing_ebay_candidates(candidate_id) on delete set null,
  action_id uuid references public.sourcing_actions(action_id) on delete set null,
  purchase_item_id uuid references public.purchase_items(item_id) on delete set null,
  problem_case_id uuid references public.order_problem_cases(problem_case_id) on delete set null,
  sourcing_purchase_match_id uuid references public.sourcing_purchase_matches(match_id) on delete set null,

  -- Amazon evidence.
  asin text,
  amazon_title text,
  amazon_image_url text,
  amazon_system text,

  -- eBay evidence.
  ebay_item_id text,
  ebay_legacy_item_id text,
  ebay_title text,
  ebay_description text,
  ebay_primary_image_url text,
  ebay_image_urls jsonb,
  ebay_item_specifics_json jsonb,
  ebay_condition text,
  ebay_category text,
  ebay_seller_username text,
  detected_system text,

  -- Operator/system decision evidence.
  operator_action text,
  dismiss_reason text,
  dismissal_note text,
  return_reason text,
  return_notes text,

  match_label text not null,
  label_type text not null,
  confidence numeric(5, 4) not null default 1,
  evidence_strength text not null default 'medium',

  later_purchase_matched boolean not null default false,
  later_received boolean not null default false,
  later_listed boolean not null default false,
  later_sold boolean not null default false,
  later_profit numeric(14, 2),

  raw_context_json jsonb,
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  rebuilt_at timestamptz not null default now(),

  constraint matching_intelligence_examples_label_check
    check (match_label in (
      'match',
      'non_match',
      'condition_problem',
      'valid_match_poor_opportunity',
      'availability_system',
      'needs_review'
    )),

  constraint matching_intelligence_examples_label_type_check
    check (label_type in (
      'positive_identity',
      'negative_identity',
      'condition_issue',
      'business_issue',
      'availability_system',
      'unknown'
    )),

  constraint matching_intelligence_examples_evidence_strength_check
    check (evidence_strength in ('low', 'medium', 'high', 'very_high'))
);

comment on table public.matching_intelligence_examples is
'Rebuildable labeled examples for matching diagnostics and future scoring. Business-only labels must not poison ASIN identity matching.';

create unique index if not exists matching_intelligence_examples_source_uidx
  on public.matching_intelligence_examples (source_table, source_id, coalesce(source_detail, ''));

create index if not exists matching_intelligence_examples_asin_idx
  on public.matching_intelligence_examples (asin);

create index if not exists matching_intelligence_examples_ebay_item_idx
  on public.matching_intelligence_examples (ebay_legacy_item_id, ebay_item_id);

create index if not exists matching_intelligence_examples_label_idx
  on public.matching_intelligence_examples (match_label, label_type);

create index if not exists matching_intelligence_examples_reason_idx
  on public.matching_intelligence_examples (dismiss_reason);

create index if not exists matching_intelligence_examples_seller_idx
  on public.matching_intelligence_examples (ebay_seller_username);

create table if not exists public.sourcing_seller_intelligence (
  seller_intelligence_id uuid primary key default gen_random_uuid(),
  seller_username text not null unique,

  purchase_count integer not null default 0,
  unit_count integer not null default 0,
  return_count integer not null default 0,
  product_condition_return_count integer not null default 0,
  wrong_product_return_count integer not null default 0,
  wrong_platform_return_count integer not null default 0,
  wrong_edition_return_count integer not null default 0,
  non_na_return_count integer not null default 0,
  incomplete_product_return_count integer not null default 0,
  missing_shrink_wrap_return_count integer not null default 0,
  suspected_reseal_return_count integer not null default 0,
  packaging_damage_return_count integer not null default 0,
  item_not_received_count integer not null default 0,
  refund_delay_count integer not null default 0,
  seller_cancelled_count integer not null default 0,

  average_roi numeric(12, 4),
  median_roi numeric(12, 4),
  offers_made integer not null default 0,
  offers_accepted integer not null default 0,
  offer_acceptance_rate numeric(8, 4),
  average_offer_discount numeric(8, 4),
  total_profit numeric(14, 2),
  opportunity_count integer not null default 0,
  purchase_conversion_count integer not null default 0,
  purchase_conversion_rate numeric(8, 4),

  seller_trust_score numeric(8, 4),
  seller_status text not null default 'normal',
  status_reason text,
  raw_metrics_json jsonb,
  calculated_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint sourcing_seller_intelligence_status_check
    check (seller_status in ('trusted', 'normal', 'watch', 'avoid'))
);

comment on table public.sourcing_seller_intelligence is
'Derived seller intelligence for sourcing diagnostics. Avoid status is advisory only until hide-by-default is explicitly enabled.';

create index if not exists sourcing_seller_intelligence_status_idx
  on public.sourcing_seller_intelligence (seller_status, seller_trust_score);

grant all on table public.sourcing_listing_snapshots to service_role;
grant all on table public.matching_intelligence_examples to service_role;
grant all on table public.sourcing_seller_intelligence to service_role;
