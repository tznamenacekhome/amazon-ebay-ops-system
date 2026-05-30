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
