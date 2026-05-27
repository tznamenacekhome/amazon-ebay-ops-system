# Backend Architecture

Last updated: 2026-05-27

## Core Flow

MBOP follows one primary architecture:

Python integrations -> Supabase PostgreSQL -> Next.js API routes -> React frontend

Supabase is the operational source of truth. The frontend never talks directly to Supabase and must render backend/API-provided values rather than rebuilding business logic in React.

## Ownership Boundaries

Purchases, receiving, Amazon FBA shipment prep, inventory reconciliation, repricing advice, and external intelligence are separate domains.

- `purchases` and `purchase_items` own acquired eBay buyer purchase inventory.
- Receiving owns physical verification, received quantities, return-pending decisions, marketplace assignment, received dates, and the transition to `received`.
- Amazon FBA shipment prep owns grouping received Amazon-bound items for export, shipment ID assignment, and moving included units to `listed`.
- Amazon SP-API snapshot tables own read-only Amazon inventory, listing, planning, and finance data.
- Keepa tables own read-only catalog, offer, price-history, sales-rank, and competition intelligence.
- Informed tables own read-only repricer report snapshots and advisory rule/price context.
- YNAB tables own read-only category balance snapshots.
- `inventory_positions` and reconciliation tables are derived and rebuildable; they do not replace workflow ownership.

## Integration Orchestration

`run_all_syncs.py` is the local orchestrator. It currently runs:

- eBay buyer purchases and tracking ingestion
- EasyPost carrier updates
- eBay supplier returns
- RevSeller enrichment
- Amazon FBA inventory
- Amazon listing status
- Amazon inventory planning
- Amazon Finance balances
- Informed Repricer reports
- YNAB Business cash balance
- guarded Keepa active-Amazon stale refresh
- daily business value snapshot

Independent integration failures are collected and reported while later syncs continue running. This prevents one external API failure from blocking unrelated freshness work.

## External API Safety

All external API integrations are read-only unless explicitly documented otherwise.

- Amazon SP-API uses LWA auth and an explicit read-only path allow-list.
- Amazon write endpoints, restricted PII flows, and seller order/customer PII are not used.
- Keepa token-spending calls are never triggered by frontend page loads.
- Informed Listings Management upload/write paths are not used.
- YNAB data is cash/budget context only.

## Backend-Owned Business Logic

Backend/API layers own:

- landed cost and dashboard cost totals
- purchase status filtering and pagination
- receiving validation
- FBA grouping and cost aggregation
- inventory value rollups
- repricing recommendation tiers, buckets, target prices, and reasons
- business value snapshots

Frontend components render API-provided values and manage UI workflow state only.

