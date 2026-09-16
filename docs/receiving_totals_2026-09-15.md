# Receiving totals - September 15, 2026

The reported discrepancy was confirmed by bounded production reads: 47 fully delivered units belong to 30 item rows (27 single-unit rows, plus quantities 9, 6 and 5). Receiving includes those rows and one shipped-without-tracking row: 31 rows, not necessarily 31 orders. Package links can also produce multiple receiving rows per item.

The queue label now says `item rows ready to receive`. A separate compact summary shows `Delivered and not received` units and purchase value. `/api/receiving/stats` reuses Purchases' existing `fetchDeliveryStats` helper and `purchase_delivery_stats()` RPC. Both pages therefore use identical status/reporting exclusions, deduplication, quantities and authoritative backend unit costs; no cost calculation is performed in the frontend. Fully delivered totals exclude shipped-without-tracking and partially delivered items even though those may be eligible for receiving.

The summary loads independently of the queue, ignores search filters and refreshes on initial queue load, manual refresh and successful receiving save. Aborted requests cannot overwrite new state. A failed totals request shows its actual error and unavailable totals, not zero; it does not prevent receiving work. Missing costs are disclosed. Existing queue and mutation contracts are unchanged. No migration or production data changes are required.

Validation: existing purchase delivery helper regressions, TypeScript checking, focused lint on the new component/API and `git diff --check` pass.

## Authorized deployment

After explicit operator authorization, deployed web156 from `9308f293bc05` (application change `c79d98f`). Production Docker build and TypeScript passed, including the new `/api/receiving/stats` route. Image digest: `sha256:9940f85e20d7f76e462e319984b0a339d10ec706f5560924172d3ab7f48419ff`. ECS rollout is COMPLETED, desired/running 1, pending 0; the exact new task `83bf97ca45664c86abd4b2142868a0af` is RUNNING and its load-balancer target is healthy. Evidence: `tmp/ops-20260915/web156-deployment.json`.

Browser inventory returned no available apps or browsers, so authenticated production UI click-through is not claimed. Existing npm audit findings were emitted during the build; dependencies were unchanged. This release changes only the web runtime; no migration, scheduler deployment or sourcing rerun accompanied it.
