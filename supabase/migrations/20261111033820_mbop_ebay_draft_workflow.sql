-- eBay photo-to-draft work is stored separately from purchases and receiving.
-- The production API uses the service role; no browser Data API access is granted.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'mbop-ebay-draft-photos',
  'mbop-ebay-draft-photos',
  false,
  20971520,
  array['image/jpeg', 'image/png', 'image/webp']::text[]
)
on conflict (id) do update
set name = excluded.name,
    public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create table public.ebay_draft_imports (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  source_name text not null default 'photo folder',
  status text not null default 'needs_group_review'
    check (status in ('needs_group_review', 'in_review', 'complete', 'failed')),
  source_manifest jsonb not null default '{}'::jsonb,
  grouping_summary jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.ebay_listing_drafts (
  id uuid primary key default gen_random_uuid(),
  import_id uuid not null references public.ebay_draft_imports(id) on delete cascade,
  group_key text not null,
  group_name text not null,
  source_item_number text,
  source_item_id uuid references public.purchase_items(item_id) on delete set null,
  grouping_confidence numeric(5,4) check (grouping_confidence between 0 and 1),
  grouping_reason text,
  grouping_confirmed boolean not null default false,
  listing_kind text not null default 'single' check (listing_kind in ('single', 'lot')),
  status text not null default 'draft' check (status in ('draft', 'needs_input', 'ready')),
  marketplace_id text not null default 'EBAY_US',
  title text not null default '',
  category_id text,
  category_name text,
  condition_id text,
  condition_name text,
  condition_notes text not null default '',
  tested_status text not null default 'unknown'
    check (tested_status in ('unknown', 'not_tested', 'working', 'faulty', 'not_applicable')),
  description text not null default '',
  quantity integer not null default 1 check (quantity > 0),
  price numeric(12,2) check (price is null or price >= 0),
  currency text not null default 'USD',
  item_specifics jsonb not null default '{}'::jsonb,
  required_inputs text[] not null default '{}',
  identification_status text not null default 'uncertain'
    check (identification_status in ('uncertain', 'review_required', 'confirmed', 'conflict')),
  identification_evidence jsonb not null default '{}'::jsonb,
  visible_flaws text not null default '',
  included_items text not null default '',
  seller_notes text not null default '',
  price_recommendation jsonb not null default '{}'::jsonb,
  comparable_sales jsonb not null default '[]'::jsonb,
  ai_model text,
  ai_analysis jsonb not null default '{}'::jsonb,
  reviewed_at timestamptz,
  revision integer not null default 1 check (revision > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (import_id, group_key)
);

create table public.ebay_listing_draft_photos (
  id uuid primary key default gen_random_uuid(),
  draft_id uuid not null references public.ebay_listing_drafts(id) on delete cascade,
  original_name text not null,
  relative_path text not null,
  original_sha256 text not null,
  processed_sha256 text not null,
  original_storage_path text not null unique,
  storage_path text not null unique,
  mime_type text not null check (mime_type in ('image/jpeg', 'image/png', 'image/webp')),
  byte_size bigint not null check (byte_size > 0),
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  source_orientation smallint check (source_orientation between 1 and 8),
  rotation_degrees smallint not null default 0 check (rotation_degrees in (0, 90, 180, 270)),
  sort_order integer not null check (sort_order >= 0),
  role text not null default 'unknown'
    check (role in ('hero', 'alternate_angle', 'label', 'included_item', 'flaw', 'unknown')),
  analysis jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (draft_id, original_sha256)
);

create index ebay_listing_drafts_status_updated_idx
  on public.ebay_listing_drafts (status, updated_at desc);
create index ebay_listing_drafts_source_item_idx
  on public.ebay_listing_drafts (source_item_id)
  where source_item_id is not null;
create index ebay_listing_draft_photos_draft_sort_idx
  on public.ebay_listing_draft_photos (draft_id, sort_order);

alter table public.ebay_draft_imports enable row level security;
alter table public.ebay_listing_drafts enable row level security;
alter table public.ebay_listing_draft_photos enable row level security;

revoke all on public.ebay_draft_imports from anon, authenticated;
revoke all on public.ebay_listing_drafts from anon, authenticated;
revoke all on public.ebay_listing_draft_photos from anon, authenticated;
grant all on public.ebay_draft_imports to service_role;
grant all on public.ebay_listing_drafts to service_role;
grant all on public.ebay_listing_draft_photos to service_role;

comment on table public.ebay_draft_imports is
  'Idempotent photo-folder intake sessions for the separate eBay seller listing workflow.';
comment on table public.ebay_listing_drafts is
  'One editable eBay listing review per confirmed photo group; no purchase workflow state is changed.';
comment on table public.ebay_listing_draft_photos is
  'Original and corrected image copies, review order, orientation, and image role for an eBay listing draft.';
