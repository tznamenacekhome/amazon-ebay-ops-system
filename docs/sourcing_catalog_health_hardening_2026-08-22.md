# Sourcing Catalog Health Hardening - 2026-08-22

## Summary

System Health showed `Sourcing Catalog` as delayed even though the daily
catalog sourcing workflow was doing useful work. Production telemetry and
CloudWatch showed the EventBridge/ECS schedule was running, but the
`sourcing-catalog` scheduler group ended in `degraded` state because two
nonblocking jobs exited nonzero after transient Supabase failures.

Schedule:

- EventBridge Scheduler: `mbop-sourcing-catalog`
- ECS task group: `sourcing-catalog`
- Command: `python run_all_syncs.py --group sourcing-catalog`
- CloudWatch log group: `/ecs/mbop-scheduler`
- 2026-08-22 task stream:
  `scheduled/mbop-scheduler/14f832c464b048588bd8f67648cd97a3`

## Root Cause

CloudWatch confirmed two transient Supabase failures in the 2026-08-22 run:

- `Daily catalog sourcing` failed at `2026-08-22T08:19:01Z` in
  `integrations/run_daily_catalog_sourcing.py:create_new_cycle` with Postgres
  error `57014`, `canceling statement due to statement timeout`.
- `Matching intelligence refresh` failed at `2026-08-22T08:21:53Z` while
  `integrations/score_sourcing_opportunities.py` fetched
  `sourcing_ebay_candidates`; Supabase/Cloudflare returned `521 Web server is
  down`, surfaced by the Python client as `JSON could not be generated`.

The first failure happened after the daily sourcing run had searched ASINs and
written candidates/opportunities. The sourcing run row was marked `completed`
by scoring, but its opportunity batch remained `running`, showing that post-run
summary/finalization work did not complete cleanly.

## Changes

- Added transient Supabase retries around sourcing workflow finalization reads,
  batch writes, and run-summary updates in
  `integrations/run_sourcing_workflow.py`.
- Added transient Supabase retries around active coverage-cycle lookup and new
  cycle creation in `integrations/run_daily_catalog_sourcing.py`.
- Added transient Supabase retries around paginated sourcing seed/candidate
  fetches in `integrations/score_sourcing_opportunities.py`.
- Added transient Supabase retries around Matching Intelligence rebuild
  bulk deletes/inserts and validation reads in
  `integrations/build_matching_intelligence_examples.py`.
- Updated System Health group config so `Daily catalog sourcing` appears in the
  `Sourcing Catalog` drawer alongside `Sourcing listing availability` and
  `Matching intelligence refresh`.

## Validation

Local validation:

- `python -m py_compile` for changed sourcing and matching scripts.
- `npm.cmd run build` for the Next.js app and API route typing.

Production verification requires scheduler and web deployment:

- Scheduler deployment registers a new `mbop-scheduler-task` revision and the
  `mbop-sourcing-catalog` schedule must be updated to that revision.
- Web deployment updates `mbop-web-service` so System Health shows the daily
  catalog job in the group drawer.
- Final behavioral confirmation should come from the next
  `mbop-sourcing-catalog` run in System Health and CloudWatch.
