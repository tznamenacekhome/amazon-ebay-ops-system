-- Canonical shared Supabase migration owned by College Planner.
-- Recovered from supabase_migrations.schema_migrations in the linked shared Supabase project.
-- MBOP is the migration authority for the shared project; do not edit after application.

-- College Planner MVP schema replacement candidate.
-- This standalone migration is for manual review only.
-- Supabase PostgreSQL is expected to provide gen_random_uuid().
-- Do not apply it together with the archived 60-table initial schema.

begin;

create schema if not exists college_planner;

create or replace function college_planner.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

comment on schema college_planner is 'Dedicated schema for College Planner objects in the shared Supabase project.';

-- ---------------------------------------------------------------------------
-- Stable MVP lookup tables
-- ---------------------------------------------------------------------------

create table if not exists college_planner.source_types (
  code text primary key,
  label text not null,
  description text,
  created_at timestamptz not null default now(),
  constraint source_types_code_format check (code ~ '^[a-z0-9_]+$')
);

create table if not exists college_planner.confidence_levels (
  code text primary key,
  label text not null,
  sort_order integer not null unique,
  created_at timestamptz not null default now()
);

create table if not exists college_planner.user_roles (
  code text primary key,
  label text not null,
  can_edit boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists college_planner.import_statuses (
  code text primary key,
  label text not null,
  is_terminal boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists college_planner.delivery_methods (
  code text primary key,
  label text not null,
  created_at timestamptz not null default now()
);

create table if not exists college_planner.academic_record_statuses (
  code text primary key,
  label text not null,
  affects_earned_credit boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists college_planner.plan_statuses (
  code text primary key,
  label text not null,
  created_at timestamptz not null default now()
);

insert into college_planner.source_types (code, label, description) values
  ('official_catalog', 'Official catalog', 'University catalog or official catalog export'),
  ('official_degree_audit', 'Official degree audit', 'Official student degree audit source'),
  ('advisor_confirmed_exception', 'Advisor-confirmed exception', 'Advisor-approved waiver, exception, or substitution'),
  ('advisor_degree_plan', 'Advisor degree plan', 'Advisor-provided planning document'),
  ('current_published_schedule', 'Current published schedule', 'Current term class schedule'),
  ('transcript', 'Transcript', 'Student transcript or completed coursework source'),
  ('registered_student_schedule', 'Registered student schedule', 'Student registered schedule source'),
  ('major_requirements_document', 'Major requirements document', 'Program-specific requirements document'),
  ('historical_schedule', 'Historical schedule', 'Historical class schedule'),
  ('manual_registration_scenario', 'Manual registration scenario', 'Manually entered registration scenario'),
  ('system_inference', 'System inference', 'Rule-based system inference'),
  ('student_entered_record', 'Student-entered record', 'Student-entered or corrected record')
on conflict (code) do nothing;

insert into college_planner.confidence_levels (code, label, sort_order) values
  ('unknown', 'Unknown', 0),
  ('low', 'Low', 10),
  ('medium', 'Medium', 20),
  ('high', 'High', 30),
  ('official', 'Official', 40)
on conflict (code) do nothing;

insert into college_planner.user_roles (code, label, can_edit) values
  ('owner', 'Owner', true),
  ('editor', 'Editor', true),
  ('viewer', 'Viewer', false),
  ('advisor', 'Advisor', true)
on conflict (code) do nothing;

insert into college_planner.import_statuses (code, label, is_terminal) values
  ('pending', 'Pending', false),
  ('validating', 'Validating', false),
  ('ready', 'Ready', false),
  ('failed', 'Failed', true),
  ('published', 'Published', true),
  ('archived', 'Archived', true)
on conflict (code) do nothing;

insert into college_planner.delivery_methods (code, label) values
  ('in_person', 'In person'),
  ('online', 'Online'),
  ('hybrid', 'Hybrid'),
  ('asynchronous', 'Asynchronous'),
  ('independent_study', 'Independent study'),
  ('study_abroad', 'Study abroad')
on conflict (code) do nothing;

insert into college_planner.academic_record_statuses (code, label, affects_earned_credit) values
  ('completed', 'Completed', true),
  ('in_progress', 'In progress', false),
  ('registered', 'Registered', false),
  ('withdrawn', 'Withdrawn', false),
  ('failed', 'Failed', false),
  ('repeated', 'Repeated', true),
  ('transfer', 'Transfer credit', true),
  ('test_credit', 'Test credit', true)
on conflict (code) do nothing;

insert into college_planner.plan_statuses (code, label) values
  ('draft', 'Draft'),
  ('active', 'Active'),
  ('archived', 'Archived')
on conflict (code) do nothing;

-- ---------------------------------------------------------------------------
-- Users, universities, terms, and provenance
-- ---------------------------------------------------------------------------

create table if not exists college_planner.application_users (
  id uuid primary key default gen_random_uuid(),
  cognito_subject text unique,
  email text,
  display_name text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint application_users_email_lowercase check (email is null or email = lower(email))
);

comment on table college_planner.application_users is 'Future Cognito-linked users for College Planner access control.';

create table if not exists college_planner.universities (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  city text,
  state text,
  country text not null default 'US',
  website_url text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint universities_code_format check (code ~ '^[a-z0-9_]+$')
);

create table if not exists college_planner.academic_years (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  code text not null,
  name text not null,
  starts_on date,
  ends_on date,
  is_current boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint academic_years_unique_code unique (university_id, code),
  constraint academic_year_dates_valid check (starts_on is null or ends_on is null or starts_on <= ends_on)
);

create table if not exists college_planner.academic_terms (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  academic_year_id uuid references college_planner.academic_years(id),
  code text not null,
  name text not null,
  term_kind text not null,
  starts_on date,
  ends_on date,
  is_current boolean not null default false,
  is_historical boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint academic_terms_unique_code unique (university_id, code),
  constraint academic_term_dates_valid check (starts_on is null or ends_on is null or starts_on <= ends_on)
);

create table if not exists college_planner.term_parts (
  id uuid primary key default gen_random_uuid(),
  academic_term_id uuid not null references college_planner.academic_terms(id),
  code text not null,
  name text not null,
  starts_on date,
  ends_on date,
  add_deadline_on date,
  drop_deadline_on date,
  withdraw_deadline_on date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint term_parts_unique_code unique (academic_term_id, code),
  constraint term_part_dates_valid check (starts_on is null or ends_on is null or starts_on <= ends_on)
);

create table if not exists college_planner.source_records (
  id uuid primary key default gen_random_uuid(),
  source_type_code text not null references college_planner.source_types(code),
  source_title text not null,
  source_identity text,
  source_url text,
  source_filename text,
  source_row_number integer,
  file_hash text,
  raw_source_json jsonb,
  confidence_code text references college_planner.confidence_levels(code),
  imported_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint source_records_identity_unique unique (source_type_code, source_identity, file_hash, source_row_number)
);

comment on table college_planner.source_records is 'Row- or document-level provenance for imported and manually confirmed records.';

create table if not exists college_planner.import_batches (
  id uuid primary key default gen_random_uuid(),
  source_type_code text not null references college_planner.source_types(code),
  status_code text not null references college_planner.import_statuses(code),
  source_name text not null,
  idempotency_key text not null unique,
  imported_by_user_id uuid references college_planner.application_users(id),
  source_record_id uuid references college_planner.source_records(id),
  row_count integer not null default 0,
  success_count integer not null default 0,
  warning_count integer not null default 0,
  error_count integer not null default 0,
  imported_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint import_batches_counts_valid check (
    row_count >= 0 and
    success_count >= 0 and
    warning_count >= 0 and
    error_count >= 0 and
    success_count <= row_count and
    warning_count <= row_count and
    error_count <= row_count and
    success_count + error_count <= row_count
  )
);

create table if not exists college_planner.import_files (
  id uuid primary key default gen_random_uuid(),
  import_batch_id uuid not null references college_planner.import_batches(id),
  source_filename text not null,
  file_hash text not null,
  storage_path text,
  content_type text,
  byte_size bigint,
  raw_metadata jsonb,
  created_at timestamptz not null default now(),
  constraint import_files_unique_hash unique (import_batch_id, file_hash)
);

create table if not exists college_planner.import_errors (
  id uuid primary key default gen_random_uuid(),
  import_batch_id uuid not null references college_planner.import_batches(id),
  import_file_id uuid references college_planner.import_files(id),
  source_row_number integer,
  source_identity text,
  severity text not null,
  message text not null,
  raw_source_json jsonb,
  correction_status text not null default 'open',
  corrected_by_user_id uuid references college_planner.application_users(id),
  corrected_at timestamptz,
  created_at timestamptz not null default now(),
  constraint import_errors_severity_valid check (severity in ('info', 'warning', 'error')),
  constraint import_errors_correction_valid check (correction_status in ('open', 'ignored', 'corrected'))
);

-- ---------------------------------------------------------------------------
-- Course catalog, relationships, offerings, and sections
-- ---------------------------------------------------------------------------

create table if not exists college_planner.subjects (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  code text not null,
  name text not null,
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint subjects_unique_code unique (university_id, code)
);

create table if not exists college_planner.courses (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  subject_id uuid not null references college_planner.subjects(id),
  course_number text not null,
  title text not null,
  description text,
  credits_min numeric(4,2) not null,
  credits_max numeric(4,2) not null,
  level text not null,
  is_variable_credit boolean not null default false,
  is_active boolean not null default true,
  retired_at_term_id uuid references college_planner.academic_terms(id),
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint courses_unique_code unique (university_id, subject_id, course_number),
  constraint courses_credit_range check (credits_min >= 0 and credits_max >= credits_min),
  constraint courses_level_valid check (level in ('undergraduate', 'graduate', 'noncredit'))
);

comment on table college_planner.courses is 'Catalog courses; not semester offerings or registration sections.';

create table if not exists college_planner.course_aliases (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  course_id uuid references college_planner.courses(id),
  alias_subject_code text not null,
  alias_course_number text not null,
  alias_title text,
  relationship_type text not null,
  effective_from_term_id uuid references college_planner.academic_terms(id),
  effective_to_term_id uuid references college_planner.academic_terms(id),
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint course_aliases_unique_alias unique (university_id, alias_subject_code, alias_course_number, relationship_type),
  constraint course_alias_relationship_valid check (relationship_type in ('alias', 'replacement', 'equivalent', 'retired'))
);

create table if not exists college_planner.course_relationship_groups (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references college_planner.courses(id),
  relationship_type text not null,
  group_logic text not null default 'all',
  minimum_courses integer,
  minimum_credits numeric(5,2),
  minimum_grade text,
  notes text,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint course_relationship_type_valid check (relationship_type in ('prerequisite', 'corequisite', 'recommended')),
  constraint course_relationship_logic_valid check (group_logic in ('all', 'any', 'minimum'))
);

create table if not exists college_planner.course_relationship_options (
  id uuid primary key default gen_random_uuid(),
  relationship_group_id uuid not null references college_planner.course_relationship_groups(id),
  related_course_id uuid references college_planner.courses(id),
  related_course_tag text,
  option_label text,
  minimum_grade text,
  sort_order integer not null default 0,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint course_relationship_option_target check (num_nonnulls(related_course_id, related_course_tag) = 1)
);

create table if not exists college_planner.course_offerings (
  id uuid primary key default gen_random_uuid(),
  academic_term_id uuid not null references college_planner.academic_terms(id),
  course_id uuid not null references college_planner.courses(id),
  source_record_id uuid references college_planner.source_records(id),
  source_identity text,
  course_notes text,
  raw_source_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint course_offerings_unique_source unique (academic_term_id, course_id, source_identity)
);

create table if not exists college_planner.course_sections (
  id uuid primary key default gen_random_uuid(),
  course_offering_id uuid not null references college_planner.course_offerings(id),
  section_code text not null,
  crn text,
  instructor_name text,
  delivery_method_code text references college_planner.delivery_methods(code),
  location_summary text,
  credits_min numeric(4,2),
  credits_max numeric(4,2),
  capacity integer,
  seats_filled integer,
  seats_available integer,
  requires_instructor_approval boolean not null default false,
  is_honors_only boolean not null default false,
  is_major_only boolean not null default false,
  is_fully_online_only boolean not null default false,
  is_dual_enrollment boolean not null default false,
  is_study_abroad boolean not null default false,
  is_independent_study boolean not null default false,
  notes text,
  restrictions_text text,
  restriction_details jsonb,
  source_record_id uuid references college_planner.source_records(id),
  source_identity text,
  raw_source_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint course_sections_unique_section unique (course_offering_id, section_code),
  constraint course_sections_capacity_valid check (capacity is null or capacity >= 0),
  constraint course_sections_seats_valid check (
    (seats_filled is null or seats_filled >= 0) and
    (seats_available is null or seats_available >= 0)
  ),
  constraint course_sections_credit_range check (
    credits_min is null or credits_max is null or (credits_min >= 0 and credits_max >= credits_min)
  )
);

comment on table college_planner.course_sections is 'Registration sections for a term offering; section restrictions are MVP columns/JSONB until detailed filtering requires a child table.';

create table if not exists college_planner.section_meetings (
  id uuid primary key default gen_random_uuid(),
  course_section_id uuid not null references college_planner.course_sections(id),
  term_part_id uuid references college_planner.term_parts(id),
  meeting_type text not null default 'class',
  day_of_week integer,
  starts_at time,
  ends_at time,
  starts_on date,
  ends_on date,
  location text,
  building text,
  room text,
  is_tba boolean not null default false,
  raw_meeting_text text,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint section_meetings_day_valid check (day_of_week is null or day_of_week between 0 and 6),
  constraint section_meetings_time_valid check (starts_at is null or ends_at is null or starts_at < ends_at),
  constraint section_meetings_date_valid check (starts_on is null or ends_on is null or starts_on <= ends_on)
);

-- ---------------------------------------------------------------------------
-- Catalogs, curricula, programs, and requirements
-- ---------------------------------------------------------------------------

create table if not exists college_planner.university_catalogs (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  academic_year_id uuid references college_planner.academic_years(id),
  code text not null,
  title text not null,
  effective_from_term_id uuid references college_planner.academic_terms(id),
  effective_to_term_id uuid references college_planner.academic_terms(id),
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint university_catalogs_unique_code unique (university_id, code)
);

create table if not exists college_planner.core_curriculum_versions (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  university_catalog_id uuid references college_planner.university_catalogs(id),
  code text not null,
  name text not null,
  total_credits_required numeric(5,2),
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint core_curriculum_versions_unique_code unique (university_id, code)
);

create table if not exists college_planner.degree_programs (
  id uuid primary key default gen_random_uuid(),
  university_id uuid not null references college_planner.universities(id),
  code text not null,
  name text not null,
  degree_type text not null,
  program_type text not null default 'major',
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint degree_programs_unique_code unique (university_id, code),
  constraint degree_programs_type_valid check (program_type in ('major', 'minor', 'certificate', 'concentration'))
);

create table if not exists college_planner.degree_program_versions (
  id uuid primary key default gen_random_uuid(),
  degree_program_id uuid not null references college_planner.degree_programs(id),
  university_catalog_id uuid not null references college_planner.university_catalogs(id),
  core_curriculum_version_id uuid references college_planner.core_curriculum_versions(id),
  code text not null,
  name text not null,
  total_credits_required numeric(5,2),
  minimum_major_credits numeric(5,2),
  minimum_upper_level_credits numeric(5,2),
  residency_credits_required numeric(5,2),
  is_active boolean not null default true,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint degree_program_versions_unique_code unique (degree_program_id, university_catalog_id, code)
);

create table if not exists college_planner.degree_requirement_groups (
  id uuid primary key default gen_random_uuid(),
  degree_program_version_id uuid references college_planner.degree_program_versions(id),
  core_curriculum_version_id uuid references college_planner.core_curriculum_versions(id),
  parent_requirement_group_id uuid references college_planner.degree_requirement_groups(id),
  code text not null,
  name text not null,
  requirement_area text not null,
  group_logic text not null default 'all',
  min_credits numeric(5,2),
  min_courses integer,
  min_grade text,
  allow_double_count boolean not null default false,
  is_required boolean not null default true,
  is_zero_credit boolean not null default false,
  sort_order integer not null default 0,
  rule_config jsonb,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint degree_requirement_groups_scope check (
    num_nonnulls(degree_program_version_id, core_curriculum_version_id) = 1
  ),
  constraint degree_requirement_groups_logic_valid check (group_logic in ('all', 'any', 'minimum', 'sequence')),
  constraint degree_requirement_groups_area_valid check (requirement_area in ('program', 'core', 'elective', 'free_elective', 'non_degree', 'recurring', 'residency'))
);

comment on table college_planner.degree_requirement_groups is 'Flexible requirement areas for program, core, elective, recurring, and residency rules.';

create table if not exists college_planner.degree_requirement_options (
  id uuid primary key default gen_random_uuid(),
  requirement_group_id uuid not null references college_planner.degree_requirement_groups(id),
  option_type text not null,
  label text,
  course_id uuid references college_planner.courses(id),
  course_tag text,
  min_credits numeric(5,2),
  min_courses integer,
  min_grade text,
  upper_level_only boolean not null default false,
  residency_required boolean not null default false,
  may_satisfy_multiple_areas boolean not null default false,
  sort_order integer not null default 0,
  rule_config jsonb,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint degree_requirement_options_type_valid check (option_type in ('course', 'course_list', 'tag', 'credit_minimum', 'course_minimum', 'free_elective', 'non_course', 'recurring')),
  constraint degree_requirement_options_target_valid check (
    case option_type
      when 'course' then course_id is not null and course_tag is null and min_courses is null
      when 'course_list' then course_id is null and course_tag is null
      when 'tag' then course_id is null and course_tag is not null
      when 'credit_minimum' then course_id is null and min_credits is not null
      when 'course_minimum' then course_id is null and min_courses is not null
      when 'free_elective' then course_id is null and course_tag is null
      when 'non_course' then course_id is null and course_tag is null
      when 'recurring' then course_id is null and course_tag is null
      else false
    end
  )
);

create table if not exists college_planner.requirement_option_courses (
  id uuid primary key default gen_random_uuid(),
  requirement_option_id uuid not null references college_planner.degree_requirement_options(id),
  course_id uuid not null references college_planner.courses(id),
  sort_order integer not null default 0,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  constraint requirement_option_courses_unique unique (requirement_option_id, course_id)
);

create table if not exists college_planner.requirement_option_tags (
  id uuid primary key default gen_random_uuid(),
  requirement_option_id uuid not null references college_planner.degree_requirement_options(id),
  tag text not null,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  constraint requirement_option_tags_unique unique (requirement_option_id, tag)
);

-- ---------------------------------------------------------------------------
-- Students, academic records, plans, and exceptions
-- ---------------------------------------------------------------------------

create table if not exists college_planner.student_profiles (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references college_planner.application_users(id),
  university_id uuid not null references college_planner.universities(id),
  display_name text not null,
  student_identifier text,
  start_term_id uuid references college_planner.academic_terms(id),
  expected_graduation_term_id uuid references college_planner.academic_terms(id),
  catalog_year_id uuid references college_planner.academic_years(id),
  primary_program_version_id uuid references college_planner.degree_program_versions(id),
  concentration_label text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint student_profiles_owner_display_unique unique (owner_user_id, display_name)
);

comment on table college_planner.student_profiles is 'Private student planning profile owned by an application user.';

create table if not exists college_planner.student_access_grants (
  id uuid primary key default gen_random_uuid(),
  student_profile_id uuid not null references college_planner.student_profiles(id),
  user_id uuid not null references college_planner.application_users(id),
  role_code text not null references college_planner.user_roles(code),
  granted_by_user_id uuid references college_planner.application_users(id),
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint student_access_grants_unique_active unique (student_profile_id, user_id, role_code)
);

create table if not exists college_planner.student_programs (
  id uuid primary key default gen_random_uuid(),
  student_profile_id uuid not null references college_planner.student_profiles(id),
  degree_program_version_id uuid not null references college_planner.degree_program_versions(id),
  concentration_label text,
  program_role text not null default 'primary',
  declared_on date,
  ended_on date,
  source_record_id uuid references college_planner.source_records(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint student_programs_role_valid check (program_role in ('primary', 'secondary_major', 'minor', 'concentration', 'certificate')),
  constraint student_programs_unique_role unique (student_profile_id, degree_program_version_id, program_role)
);

create table if not exists college_planner.student_academic_records (
  id uuid primary key default gen_random_uuid(),
  student_profile_id uuid not null references college_planner.student_profiles(id),
  status_code text not null references college_planner.academic_record_statuses(code),
  course_id uuid references college_planner.courses(id),
  academic_term_id uuid references college_planner.academic_terms(id),
  external_institution_name text,
  external_course_code text,
  external_course_title text,
  external_credit_type text,
  grade text,
  credits_attempted numeric(4,2),
  credits_earned numeric(4,2),
  is_repeat boolean not null default false,
  repeated_record_id uuid references college_planner.student_academic_records(id),
  confirmation_status text not null default 'unconfirmed',
  confidence_code text references college_planner.confidence_levels(code),
  manually_corrected boolean not null default false,
  source_record_id uuid references college_planner.source_records(id),
  notes text,
  created_by_user_id uuid references college_planner.application_users(id),
  updated_by_user_id uuid references college_planner.application_users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint student_academic_records_credit_valid check (
    (credits_attempted is null or credits_attempted >= 0) and
    (credits_earned is null or credits_earned >= 0)
  ),
  constraint student_academic_records_confirmation_valid check (confirmation_status in ('unconfirmed', 'student_confirmed', 'advisor_confirmed', 'system_proposed', 'corrected'))
);

comment on table college_planner.student_academic_records is 'Private student coursework history, registrations, transfer credit, test credit, and planned placeholders if needed.';

create table if not exists college_planner.degree_plans (
  id uuid primary key default gen_random_uuid(),
  student_profile_id uuid not null references college_planner.student_profiles(id),
  name text not null,
  status_code text not null references college_planner.plan_statuses(code),
  planned_graduation_term_id uuid references college_planner.academic_terms(id),
  is_primary boolean not null default false,
  advisor_reviewed boolean not null default false,
  advisor_reviewed_at timestamptz,
  notes text,
  created_by_user_id uuid references college_planner.application_users(id),
  updated_by_user_id uuid references college_planner.application_users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint degree_plans_unique_name unique (student_profile_id, name)
);

create table if not exists college_planner.planned_terms (
  id uuid primary key default gen_random_uuid(),
  degree_plan_id uuid not null references college_planner.degree_plans(id),
  academic_term_id uuid references college_planner.academic_terms(id),
  sequence_number integer not null,
  label text not null,
  target_term_kind text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint planned_terms_unique_sequence unique (degree_plan_id, sequence_number)
);

create table if not exists college_planner.planned_courses (
  id uuid primary key default gen_random_uuid(),
  planned_term_id uuid not null references college_planner.planned_terms(id),
  course_id uuid references college_planner.courses(id),
  requirement_group_id uuid references college_planner.degree_requirement_groups(id),
  student_academic_record_id uuid references college_planner.student_academic_records(id),
  planned_credits numeric(4,2),
  is_locked boolean not null default false,
  is_placeholder boolean not null default false,
  alternate_course_ids jsonb,
  student_notes text,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on column college_planner.planned_courses.alternate_course_ids is 'MVP placeholder for alternate courses; normalize later when alternative planning needs richer behavior.';

create table if not exists college_planner.requirement_exceptions (
  id uuid primary key default gen_random_uuid(),
  student_profile_id uuid not null references college_planner.student_profiles(id),
  requirement_group_id uuid references college_planner.degree_requirement_groups(id),
  original_course_id uuid references college_planner.courses(id),
  substitute_course_id uuid references college_planner.courses(id),
  exception_type text not null,
  status_code text not null default 'pending',
  advisor_note text,
  approved_by_user_id uuid references college_planner.application_users(id),
  approved_at timestamptz,
  source_record_id uuid references college_planner.source_records(id),
  confidence_code text references college_planner.confidence_levels(code),
  explanation text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint requirement_exceptions_type_valid check (exception_type in ('waiver', 'substitution', 'override', 'advisor_confirmation')),
  constraint requirement_exceptions_status_valid check (status_code in ('pending', 'approved', 'rejected', 'superseded'))
);

-- ---------------------------------------------------------------------------
-- Justified MVP indexes
-- ---------------------------------------------------------------------------

create index if not exists idx_application_users_email on college_planner.application_users (email);

create unique index if not exists idx_academic_years_one_current_per_university on college_planner.academic_years (university_id) where is_current;

create index if not exists idx_academic_terms_university_current on college_planner.academic_terms (university_id, is_current, starts_on);

create unique index if not exists idx_academic_terms_one_current_per_university on college_planner.academic_terms (university_id) where is_current;

create index if not exists idx_term_parts_term on college_planner.term_parts (academic_term_id);

create index if not exists idx_source_records_type_identity on college_planner.source_records (source_type_code, source_identity);

create index if not exists idx_import_batches_status on college_planner.import_batches (status_code, created_at desc);

create index if not exists idx_import_errors_batch_severity on college_planner.import_errors (import_batch_id, severity);

create index if not exists idx_subjects_university on college_planner.subjects (university_id, code);

create index if not exists idx_courses_subject_number on college_planner.courses (subject_id, course_number);

create index if not exists idx_courses_university_active on college_planner.courses (university_id, is_active);

create index if not exists idx_course_relationship_groups_course on college_planner.course_relationship_groups (course_id, relationship_type);

create index if not exists idx_course_offerings_term on college_planner.course_offerings (academic_term_id);

create index if not exists idx_course_offerings_course on college_planner.course_offerings (course_id);

create index if not exists idx_course_sections_offering on college_planner.course_sections (course_offering_id);

create index if not exists idx_course_sections_source_identity on college_planner.course_sections (source_identity);

create index if not exists idx_section_meetings_section on college_planner.section_meetings (course_section_id, day_of_week, starts_at);

create unique index if not exists idx_section_meetings_unique_pattern on college_planner.section_meetings (
  course_section_id,
  coalesce(term_part_id, '00000000-0000-0000-0000-000000000000'::uuid),
  meeting_type,
  coalesce(day_of_week, -1),
  coalesce(starts_at, '00:00'::time),
  coalesce(ends_at, '00:00'::time),
  coalesce(starts_on, '0001-01-01'::date),
  coalesce(ends_on, '0001-01-01'::date),
  coalesce(location, '')
);

create index if not exists idx_degree_program_versions_program_catalog on college_planner.degree_program_versions (degree_program_id, university_catalog_id);

create index if not exists idx_requirement_groups_program on college_planner.degree_requirement_groups (degree_program_version_id, sort_order);

create index if not exists idx_requirement_groups_core on college_planner.degree_requirement_groups (core_curriculum_version_id, sort_order);

create index if not exists idx_requirement_options_group on college_planner.degree_requirement_options (requirement_group_id, sort_order);

create index if not exists idx_requirement_option_courses_course on college_planner.requirement_option_courses (course_id);

create index if not exists idx_student_profiles_owner on college_planner.student_profiles (owner_user_id);

create index if not exists idx_student_access_grants_user on college_planner.student_access_grants (user_id, revoked_at);

create unique index if not exists idx_student_access_grants_one_active_owner on college_planner.student_access_grants (student_profile_id) where role_code = 'owner' and revoked_at is null;

create index if not exists idx_student_academic_records_student_status on college_planner.student_academic_records (student_profile_id, status_code);

create unique index if not exists idx_student_academic_records_unique_source on college_planner.student_academic_records (student_profile_id, source_record_id) where source_record_id is not null;

create index if not exists idx_degree_plans_student_status on college_planner.degree_plans (student_profile_id, status_code);

create unique index if not exists idx_degree_plans_one_active_primary on college_planner.degree_plans (student_profile_id) where is_primary and status_code = 'active';

-- ---------------------------------------------------------------------------
-- updated_at triggers only for mutable MVP tables
-- ---------------------------------------------------------------------------

create trigger set_application_users_updated_at before update on college_planner.application_users for each row execute function college_planner.set_updated_at();

create trigger set_universities_updated_at before update on college_planner.universities for each row execute function college_planner.set_updated_at();

create trigger set_academic_years_updated_at before update on college_planner.academic_years for each row execute function college_planner.set_updated_at();

create trigger set_academic_terms_updated_at before update on college_planner.academic_terms for each row execute function college_planner.set_updated_at();

create trigger set_term_parts_updated_at before update on college_planner.term_parts for each row execute function college_planner.set_updated_at();

create trigger set_source_records_updated_at before update on college_planner.source_records for each row execute function college_planner.set_updated_at();

create trigger set_import_batches_updated_at before update on college_planner.import_batches for each row execute function college_planner.set_updated_at();

create trigger set_subjects_updated_at before update on college_planner.subjects for each row execute function college_planner.set_updated_at();

create trigger set_courses_updated_at before update on college_planner.courses for each row execute function college_planner.set_updated_at();

create trigger set_course_offerings_updated_at before update on college_planner.course_offerings for each row execute function college_planner.set_updated_at();

create trigger set_course_sections_updated_at before update on college_planner.course_sections for each row execute function college_planner.set_updated_at();

create trigger set_section_meetings_updated_at before update on college_planner.section_meetings for each row execute function college_planner.set_updated_at();

create trigger set_university_catalogs_updated_at before update on college_planner.university_catalogs for each row execute function college_planner.set_updated_at();

create trigger set_core_curriculum_versions_updated_at before update on college_planner.core_curriculum_versions for each row execute function college_planner.set_updated_at();

create trigger set_degree_programs_updated_at before update on college_planner.degree_programs for each row execute function college_planner.set_updated_at();

create trigger set_degree_program_versions_updated_at before update on college_planner.degree_program_versions for each row execute function college_planner.set_updated_at();

create trigger set_degree_requirement_groups_updated_at before update on college_planner.degree_requirement_groups for each row execute function college_planner.set_updated_at();

create trigger set_degree_requirement_options_updated_at before update on college_planner.degree_requirement_options for each row execute function college_planner.set_updated_at();

create trigger set_student_profiles_updated_at before update on college_planner.student_profiles for each row execute function college_planner.set_updated_at();

create trigger set_student_access_grants_updated_at before update on college_planner.student_access_grants for each row execute function college_planner.set_updated_at();

create trigger set_student_programs_updated_at before update on college_planner.student_programs for each row execute function college_planner.set_updated_at();

create trigger set_student_academic_records_updated_at before update on college_planner.student_academic_records for each row execute function college_planner.set_updated_at();

create trigger set_degree_plans_updated_at before update on college_planner.degree_plans for each row execute function college_planner.set_updated_at();

create trigger set_planned_terms_updated_at before update on college_planner.planned_terms for each row execute function college_planner.set_updated_at();

create trigger set_planned_courses_updated_at before update on college_planner.planned_courses for each row execute function college_planner.set_updated_at();

create trigger set_requirement_exceptions_updated_at before update on college_planner.requirement_exceptions for each row execute function college_planner.set_updated_at();

commit;

