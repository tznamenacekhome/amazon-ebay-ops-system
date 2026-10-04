-- Automated Royal price-list intake and operator-facing failure notifications.
-- Additive only: no purchase, receiving, accounting, or College Planner objects change.
alter table public.wholesale_imports drop constraint wholesale_imports_date_source_check;
alter table public.wholesale_imports add constraint wholesale_imports_date_source_check
  check (date_source in ('supplier_document', 'supplier_filename', 'operator_parameter'));

create table public.wholesale_email_ingestions (
  ingestion_id uuid primary key default gen_random_uuid(),
  supplier_id uuid references public.wholesale_suppliers(supplier_id),
  mailbox text not null,
  graph_message_id text not null,
  internet_message_id text,
  sender_address text not null,
  subject text,
  received_at timestamptz not null,
  status text not null default 'discovered' check (status in
    ('discovered','processing','retry','completed','duplicate','rejected','failed')),
  attempt_count integer not null default 0,
  next_retry_at timestamptz,
  last_attempt_at timestamptz,
  source_type text check (source_type in ('attachment','secure_link')),
  source_name text,
  source_host text,
  file_sha256 text check (file_sha256 is null or file_sha256 ~ '^[0-9a-f]{64}$'),
  effective_date date,
  wholesale_import_id uuid references public.wholesale_imports(import_id),
  enrichment_run_id uuid references public.wholesale_enrichment_runs(enrichment_run_id),
  error_code text,
  error_summary text,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (mailbox, graph_message_id)
);
create index wholesale_email_ingestions_queue_idx on public.wholesale_email_ingestions
  (status, next_retry_at, received_at);
create index wholesale_email_ingestions_import_idx on public.wholesale_email_ingestions
  (wholesale_import_id) where wholesale_import_id is not null;

create table public.mbop_notifications (
  notification_id uuid primary key default gen_random_uuid(),
  dedupe_key text not null unique,
  severity text not null check (severity in ('info','warning','error')),
  category text not null,
  title text not null,
  message text not null,
  href text,
  occurrence_count integer not null default 1,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  read_at timestamptz,
  resolved_at timestamptz,
  created_at timestamptz not null default now()
);
create index mbop_notifications_unread_idx on public.mbop_notifications
  (last_seen_at desc) where read_at is null and resolved_at is null;

alter table public.wholesale_email_ingestions enable row level security;
alter table public.mbop_notifications enable row level security;
revoke all on public.wholesale_email_ingestions, public.mbop_notifications from public, anon, authenticated;
grant select, insert, update on public.wholesale_email_ingestions, public.mbop_notifications to service_role;

comment on table public.wholesale_email_ingestions is
'Read-only Microsoft Graph message checkpoint and sanitized Royal import provenance. Download URLs, tokens, and attachment bytes are never stored.';
comment on table public.mbop_notifications is
'Deduplicated operational notifications surfaced by the MBOP application bell.';
