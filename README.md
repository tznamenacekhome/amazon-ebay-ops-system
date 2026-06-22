# Midnight Blue Operations Platform

MBOP is the internal operations platform for Midnight Blue Enterprises, LLC.

The system automates and supports:

- eBay buyer purchase ingestion
- inbound shipment tracking and carrier updates
- purchase data review and cleanup
- receiving workflow
- Send to Amazon prep and FBA shipment tracking
- Amazon inventory, listing, planning, finance, and valuation visibility
- Keepa and Informed read-only repricing intelligence
- inventory reconciliation and business value dashboarding
- sourcing opportunity discovery, matching, and availability cleanup

## Architecture

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend uses API routes only and must not recalculate landed cost, inventory value, or repricing recommendations.

Capacity guardrails for Supabase billing limits, Disk IO Budget, and recovery are documented in `docs/supabase_capacity.md`. Check that file before adding broad syncs, heavy backfills, raw snapshot storage, or full-table dashboard queries.

## Key Docs

- `AGENTS.md`: project rules for coding agents.
- `CURRENT_STATE.md`: current implemented state and latest validation.
- `DECISIONS.md`: durable architecture and business decisions.
- `KNOWN_ISSUES.md`: active issues, monitor items, and deferred decisions.
- `ROADMAP.md`: prioritized future work.
- `docs/backend_architecture.md`: backend ownership boundaries and integration orchestration.
- `docs/database_schema.md`: high-level schema map.
- `docs/business_rules.md`: canonical business rules.
- `docs/aws/MBOP_AWS_DEPLOYMENT.md`: authoritative AWS production deployment state.
- `docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`: EventBridge/ECS scheduler design, groups, cadence, and telemetry.
- `docs/aws/MBOP_AWS_OPERATIONS_RUNBOOK.md`: deploy, rotate, troubleshoot, and cost-check procedures.

## Sync Orchestration

`run_all_syncs.py` is the Python integration orchestrator. In production, AWS
EventBridge Scheduler launches ECS/Fargate `mbop-scheduler-task:1` runs with
explicit group names documented in `docs/aws/MBOP_AWS_SCHEDULER_PLAN.md`.

The deployed web app image is web-only and does not run scheduler jobs. The
legacy local Windows Task Scheduler path is retired; `run_all_syncs.bat`
remains useful for manual/local development runs and appends output to
`logs/scheduler.log`.

`inventory_source_balance_audit.py` is a secondary control for purchase-source
unit balancing. Run it after FIFO allocator/import backfill work and during
monthly close. `inventory_source_balance_audit.bat` remains a manual local
entry point that appends to `logs/inventory_source_balance_audit.log` and
writes the latest report to `exports/inventory_source_balance_audit.csv`.

## UI Freshness

MBOP screens show a `Last updated` timestamp near their refresh controls. These
timestamps come from `/api/screen-data-freshness`, not direct frontend Supabase
queries. Dashboard uses the oldest required cash/value input so stale Amazon or
YNAB cash data is visible even if another dashboard source refreshed recently.
