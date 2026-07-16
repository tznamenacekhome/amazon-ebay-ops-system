-- Canonical shared Supabase migration owned by College Planner.
-- Recovered from supabase_migrations.schema_migrations in the linked shared Supabase project.
-- MBOP is the migration authority for the shared project; do not edit after application.

begin;

alter table college_planner.courses
  add column if not exists catalog_id text,
  add column if not exists catalog_title text,
  add column if not exists catalog_year text,
  add column if not exists catalog_source_url text,
  add column if not exists catalog_external_id text,
  add column if not exists catalog_last_synced_at timestamptz,
  add column if not exists catalog_content_hash text,
  add column if not exists catalog_raw_prerequisite_text text,
  add column if not exists catalog_raw_corequisite_text text,
  add column if not exists catalog_credit_wording text;

comment on column college_planner.courses.description is 'Clean official catalog course description text when imported; schedule and section history remain separate.';

comment on column college_planner.courses.catalog_id is 'Official source catalog identifier, for example Lipscomb catalog catoid 33.';

comment on column college_planner.courses.catalog_title is 'Official title from the imported catalog course entry.';

comment on column college_planner.courses.catalog_year is 'Catalog year for the imported official course description, for example 2026-2027.';

comment on column college_planner.courses.catalog_source_url is 'Official catalog URL used for the imported course description.';

comment on column college_planner.courses.catalog_external_id is 'Stable external course id or anchor from the source catalog, when available.';

comment on column college_planner.courses.catalog_content_hash is 'SHA-256 hash of catalog-owned fields used to skip unchanged description imports.';

comment on column college_planner.courses.catalog_raw_prerequisite_text is 'Prerequisite wording preserved when naturally present in the official course entry.';

comment on column college_planner.courses.catalog_raw_corequisite_text is 'Corequisite wording preserved when naturally present in the official course entry.';

comment on column college_planner.courses.catalog_credit_wording is 'Official catalog credit wording preserved as prose; structured credit fields remain authoritative for planning.';

commit;

