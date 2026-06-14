-- Matching Intelligence receiving outcome capture.
--
-- Additive only. Receiving remains the workflow owner for physical item
-- verification; Matching Intelligence consumes these rows as labeled evidence.

create table if not exists public.matching_intelligence_receiving_outcomes (
  receiving_outcome_id uuid primary key default gen_random_uuid(),
  purchase_item_id uuid not null references public.purchase_items(item_id) on delete cascade,
  purchase_id uuid references public.purchases(purchase_id) on delete set null,

  outcome text not null,
  condition_issue text,
  image_clues jsonb not null default '[]'::jsonb,
  notes text,

  quantity_expected integer,
  quantity_received integer,
  marketplace text,
  asin text,
  amazon_title text,
  ebay_title text,
  system text,
  supplier_order_id text,
  ebay_item_id text,
  ebay_listing_url text,

  raw_context_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint matching_intelligence_receiving_outcomes_outcome_check
    check (outcome in (
      'correct_item',
      'wrong_item',
      'wrong_condition',
      'packaging_issue',
      'incomplete_item',
      'listed_successfully'
    )),

  constraint matching_intelligence_receiving_outcomes_condition_check
    check (
      condition_issue is null
      or condition_issue in (
        'wrong_product',
        'wrong_platform',
        'wrong_edition_version',
        'non_north_american_version',
        'incomplete_product',
        'missing_shrink_wrap',
        'suspected_reseal',
        'packaging_damage',
        'other'
      )
    )
);

comment on table public.matching_intelligence_receiving_outcomes is
'Receiving-owned item verification outcomes consumed by Matching Intelligence as explicit labeled evidence.';

create index if not exists matching_intelligence_receiving_outcomes_item_idx
  on public.matching_intelligence_receiving_outcomes (purchase_item_id, created_at desc);

create index if not exists matching_intelligence_receiving_outcomes_outcome_idx
  on public.matching_intelligence_receiving_outcomes (outcome, condition_issue);

create unique index if not exists matching_intelligence_receiving_outcomes_item_latest_uidx
  on public.matching_intelligence_receiving_outcomes (purchase_item_id);

grant all on table public.matching_intelligence_receiving_outcomes to service_role;
