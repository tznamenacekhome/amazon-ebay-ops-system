create table if not exists manual_item_matches (
  match_id uuid primary key default gen_random_uuid(),
  normalized_title text not null,
  compact_title text not null,
  system text not null,
  asin text not null,
  amazon_title text,
  target_price numeric,
  source_purchase_item_id uuid references purchase_items(item_id) on delete set null,
  source_title text,
  match_source text not null default 'manual_ui',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (normalized_title, system)
);

create index if not exists idx_manual_item_matches_compact_system
  on manual_item_matches (compact_title, system);

create index if not exists idx_manual_item_matches_asin
  on manual_item_matches (asin);
