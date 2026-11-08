# MF listing batches, phase 1

The existing `/fba` URL remains compatible. Its navigation and preparation heading are **List on Amazon**. Purchase review, receiving, ASIN matching and cached pricing remain separate workflows.

Choose FBA or MF before saving a draft/export. ASIN checkboxes control eligible purchase allocations; individual checkboxes and quantities retain source identity. New selections default to all eligible quantities. Reopening a saved draft restores its exact quantity map, including exclusions. Save draft explicitly before leaving. Export freezes that batch's selection; use New selection for another export.

MF references use `MF YYYY-MM-DD hh:mm AM/PM`, for example `MF 2026-01-17 05:42 PM`. The editable InventoryLab wall time uses the existing business timezone, `America/Los_Angeles`; the stable internal UUID is independent of this reference. Correct IL reference updates the external reference without regenerating the export. Each completion retains its reference at confirmation time.

Export uses the existing InventoryLab columns and backend weighted-cost rules. The exact CSV text and per-source allocation snapshots are persisted. Re-export downloads that text. It never creates inventory or consumes the Received queue.

After export, **Mark listed** opens the exported allocations. Pending quantities start checked. Uncheck unlisted allocations or reduce quantities, then confirm actual Amazon MSKUs. A unique MF mapping for the same ASIN and condition is prefilled when available; ambiguous/unknown mappings require operator capture from InventoryLab/Amazon. No synthetic MSKU is generated. Closing this panel never saves.

`mbop_complete_mf_listing` locks the batch and source rows in a stable order. In one PostgreSQL transaction it validates pending quantities, records completion, creates merchant-held cost lots, moves included purchase quantities to Listed, and leaves the remainder Received. Partial quantities clone all purchase/receipt fields into a listed child linked to the original; the original remains the actionable remainder. Original snapshots and purchase IDs remain in `amazon_listing_allocations`. Changed ASIN, condition, cost or stock requires reconciliation instead of consuming stale source data.

Request UUIDs and unique completion/allocation keys make retries idempotent. Concurrent submissions cannot create duplicate lots. Completed batches reject new completion attempts. Transaction errors roll back every allocation, including purchase changes.

Merchant lots have manual confirmation and no Amazon verification timestamp. The existing inventory projection uses `home_amazon_mfn_listed` for MF-marked listed items, rather than treating them as sold or outbound FBA. The scheduler's unchanged-source check includes merchant lot creation. This phase does not sync Amazon availability, sell through MF stock, handle returns, or transfer MF stock to FBA.

FBA saves retain the existing shipment API, row splitting, return-recovery routing and historical tables. New UI saves also record method/reference/selection history; old clients and historical shipment records remain compatible. Historical FBA records remain in the FBA Shipments tab. MF return-recovery intake is excluded from this phase.

## Database deployment

Migration: `supabase/migrations/20261108035549_mbop_amazon_listing_batches.sql`.
MBOP project: `amazon-ebay-ops` / `froeucjkcepuhgwisped`. All new objects belong to MBOP's `public` schema. RLS is enabled; only the server service role can access the new tables/functions. No College Planner object or applied migration is altered.

Use the repository's linked migration workflow, after verifying the target and reconciling **every** shared ledger entry:

```powershell
supabase migration list --linked
supabase db push --linked --dry-run
supabase migration list --linked
supabase db push --linked
```

## Focused checks

```powershell
node web/app/fba/listingBatch.test.mjs
node web/app/fba/listingBatchApi.test.mjs
node web/app/fba/inventoryLabExport.test.mjs
.venv/Scripts/python.exe tests/test_mf_listing_batches.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_mf_inventory_projection.py
.venv/Scripts/python.exe -m unittest discover -s tests -p test_amazon_fba_shipment_inventory.py
cd web
npm.cmd run build
```

The transaction suite starts an isolated disposable PostgreSQL 17 Docker container, publishes no port, applies the real migration over minimal workflow fixtures, and removes the container. It tests partial/full completion, original cost/receipt preservation, concurrent retries, immutable re-export, rollback across allocations, stale competing batches, missing MSKUs, draft zeroes, and existing FBA history behavior. It never changes production inventory.

The API fixture checks validate selected allocation snapshots, exact CSV persistence, MF reference formatting, exclusion of FBA-only SKU mappings, draft zeroes, rejected stale/invalid selections, and immutable re-export without preparation reads.
