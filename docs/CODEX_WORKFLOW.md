Before implementation, review the current MBOP project documentation relevant to this feature, including:

- AGENTS.md
- CURRENT_STATE.md
- DECISIONS.md
- ROADMAP.md
- KNOWN_ISSUES.md
- backend_architecture.md
- database_schema.md
- shared_supabase_migration_ownership.md
- business_rules.md

Also review any subsystem documentation related to this feature before making changes.

SQL change workflow:
- MBOP is the canonical migration authority for the Supabase project shared by
  MBOP and College Planner.
- The MBOP `supabase/migrations` directory must contain the complete migration
  history for the shared project, including migrations that affect College
  Planner.
- College Planner may use the database at runtime, but its repository must not
  independently deploy, repair, remove, rewrite, or create migrations against
  the shared remote ledger.
- Their application tables remain logically separate and must be clearly
  identified by schema, naming convention, and documentation. MBOP operational
  objects live in `public` unless specifically documented otherwise; College
  Planner owns the `college_planner` schema.
- Every migration filename must include its owning application after the
  timestamp: `mbop_...`, `college_planner_...`, or `shared_...`.
- College Planner database changes must be added to the MBOP migration
  directory with a `college_planner_` filename.
- Codex must run `supabase migration list` before every `supabase db push`.
- Before `supabase db push`, reconcile the complete shared migration history.
- Already-applied migrations must never be edited or removed.
- Never delete, revert, or alter a migration owned by the other application.
- Default to giving the operator schema or migration SQL to apply.
- Codex may apply schema SQL directly only when the operator explicitly asks,
  the exact SQL file or command is visible in the repo or prompt, the target
  project/environment is verified first, and the project-documented CLI workflow
  is used.
- Do not apply schema SQL directly to the linked database during normal
  development.
- When an emergency direct application is unavoidable, verify the entire
  migration against the remote schema and immediately reconcile the migration
  ledger in MBOP.
- After SQL is applied by either the operator or Codex, continue implementation
  and verification.
