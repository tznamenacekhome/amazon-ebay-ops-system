# November 13, 2026 outstanding changes release

## Included work

- Amazon shipping reconciliation retries previously imported orders without complete costs, reserves bounded historical backlog capacity, rotates continuation cursors, preserves valid evidence, and retries transient Veeqo failures. The shared shipping helper validates USD label evidence and allocates order costs once across items. Profitability repair preserves existing COGS and fees. The read-only audit command produces unit-level reconciliation evidence.
- Scheduler orchestration adds the shipping-only group and shipping-specific telemetry counters. System Health displays queue status, verified empty queues, unresolved costs, failures, and backlog age. The implementation and earlier production recovery are documented in `docs/sales_shipping_reconciliation.md` and `docs/aws/RELEASE_2026-11-07_SALES_SHIPPING_RECONCILIATION.md`.
- Historical recovery evidence under `artifacts/shipping-reconciliation` includes before/after unit records, CSV output, task references, image references, schedule comparisons, and source hashes. These records describe the earlier recovery and are retained as historical evidence.
- List on Amazon renames FBA Shipments to Batches Listed. The screen shows the latest 100 FBA and MF batches, including drafts and pending exports, with quantities, status, export/completion dates, and Open controls. Opening a batch restores its method and saved selection in Prep Queue. FBA shipment tracking appears below the batch table.
- Purchase intake documentation reflects editable ASIN/sell-price suggestions from existing Amazon records, internal platform/condition metadata, and the USD-only draft workflow.

## Verification

- `npm.cmd run build` passed, including TypeScript and page generation.
- 32 Python tests passed across shipping reconciliation, profitability fees, and scheduler diagnostics.
- Existing listing batch selection, API fixture, and InventoryLab export checks passed.
- Deployment uses the repository AWS web and scheduler scripts. Web runtime verification requires the authenticated production browser after ECS reaches a stable deployment.

## Deployment scope

Deploy the web image for batch history and System Health. Deploy the scheduler image for the committed shipping worker and orchestration, scoped to the `mbop-amazon-sales-recent-` schedules. Existing recovery evidence documents an earlier scheduler deployment of this worker. This release records the implementation in Git and publishes an image tied to the release commit. No database migration is required.
