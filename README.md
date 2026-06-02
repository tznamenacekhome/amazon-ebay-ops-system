# Midnight Blue Operations Platform

MBOP is the internal operations platform for Midnight Blue Enterprises, LLC.

The system automates and supports:

- eBay buyer purchase ingestion
- inbound shipment tracking and carrier updates
- purchase data review and cleanup
- receiving workflow
- Amazon FBA shipment prep
- Amazon inventory, listing, planning, finance, and valuation visibility
- Keepa and Informed read-only repricing intelligence
- inventory reconciliation and business value dashboarding

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

## Local Sync

`run_all_syncs.py` is the local integration orchestrator. It runs eBay, EasyPost, RevSeller, Amazon, Informed, YNAB, guarded Keepa refresh, and daily business value snapshot jobs.

`run_all_syncs.bat` appends scheduler output to `logs/scheduler.log`.

`inventory_source_balance_audit.py` is a secondary control for purchase-source
unit balancing. Run it after FIFO allocator/import backfill work and during
monthly close. The local monthly scheduler entry point is
`inventory_source_balance_audit.bat`, which appends to
`logs/inventory_source_balance_audit.log` and writes the latest report to
`exports/inventory_source_balance_audit.csv`.

## UI Freshness

MBOP screens show a `Last updated` timestamp near their refresh controls. These
timestamps come from `/api/screen-data-freshness`, not direct frontend Supabase
queries. Dashboard uses the oldest required cash/value input so stale Amazon or
YNAB cash data is visible even if another dashboard source refreshed recently.
