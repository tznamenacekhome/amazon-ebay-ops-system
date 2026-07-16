# Supabase Migration Repair: Progressive Sourcing Batches

Date: 2026-07-11

## Cause

`sql/2026-07-11_add_sourcing_progressive_batches.sql` was applied directly to
the linked Supabase project with:

```powershell
npx.cmd --yes supabase@latest db query --linked --file sql\2026-07-11_add_sourcing_progressive_batches.sql
```

That made the remote schema correct, but it did not add a row to
`supabase_migrations.schema_migrations`. The Supabase CLI also reported an
existing unrelated remote-only migration, `20260711030000`, before this repair.

## Canonical Migration Added

The canonical Supabase CLI migration is now:

```text
supabase/migrations/20260711000000_mbop_add_sourcing_progressive_batches.sql
```

It mirrors the committed archive SQL:

```text
sql/2026-07-11_add_sourcing_progressive_batches.sql
```

`.gitignore` was updated so `supabase/migrations/*.sql` is tracked while local
Supabase CLI state remains ignored.

## Remote Schema Verification

Before repairing migration history, the linked remote database was verified for
the progressive sourcing batch objects.

Verified objects:

- `public.sourcing_opportunity_batches`
- `public.sourcing_opportunity_batch_items`

Verified schema details:

- all columns and ordinal positions
- column types and nullability
- defaults, including `gen_random_uuid()`, `now()`, numeric zero defaults,
  `'running'::text`, and `'{}'::jsonb`
- primary keys
- foreign keys to `sourcing_runs`, `sourcing_opportunities`, and batch rows
- unique constraints
- status check constraint
- explicit lookup indexes
- service_role select/insert/update/delete privileges
- table comments
- RLS disabled, matching the migration SQL
- no RLS policies created
- no sourcing batch functions created

## Repair Action

After verification, only the progressive sourcing migration was repaired:

```powershell
npx.cmd --yes supabase@latest migration repair --status applied 20260711000000
```

The repair succeeded and recorded `20260711000000` as applied.

## Final Migration Status

After repair:

```text
local  20260711000000
remote 20260711000000
```

The progressive sourcing batch migration is aligned.

Historical remaining unrelated issue at the time:

```text
remote-only 20260711030000 college_planner_mvp_schema
```

The remote ledger contains the name `college_planner_mvp_schema` and stored
statements for a `college_planner` schema migration. No matching local migration
was found in this repository. It was not repaired, reverted, or replaced because
it is unrelated to MBOP progressive sourcing and was not safely attributable to
this change.

At the time, because of that unrelated remote-only migration,
`supabase db push --dry-run` still reported:

```text
Remote migration versions not found in local migrations directory.
20260711030000
```

## Validation

Passed:

- Python compile for progressive sourcing files
- `python tests/test_sourcing_progressive_batches.py`
- `npm run build` from `web/`

Supabase migration dry-run:

- Progressive migration is repaired and aligned.
- At the time, full project dry-run remained blocked by unrelated remote-only
  `20260711030000`.

## 2026-07-15 Resolution

MBOP is now the canonical migration authority for the shared Supabase project
used by MBOP and College Planner. The actual SQL for College Planner remote
migration `20260711030000` was recovered from
`supabase_migrations.schema_migrations` and stored locally as:

```text
supabase/migrations/20260711030000_college_planner_mvp_schema.sql
```

The later College Planner migration `20260713010000` was also recovered and
stored locally as:

```text
supabase/migrations/20260713010000_college_planner_add_course_catalog_description_metadata.sql
```

Current shared migration ownership rules and object inventory are documented in
`docs/shared_supabase_migration_ownership.md`.
