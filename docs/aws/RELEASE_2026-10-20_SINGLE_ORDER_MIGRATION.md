# Manual Amazon order lookup migration — October 20, 2026

## Overnight catch-up, local night October 19–20

The October 18–19 pass was already completed and was not repeated. The pending
October 19–20 pass was caught up after the workstation reconnected on October 20.
Supported task status showed no competing active MBOP checkout worker. Repository
instructions were reread; no additional `.agents` skill files or completed record
for this night were found. The checkout started clean at `cf902df`, with origin/main
ahead/behind 0/0 after fetch. Web revision 188 remained COMPLETED, running 1/1,
pending 0, build `93740307e3d9`, and its ALB target was healthy. No pending batch
required a maintenance deployment. The newly authorized notice fix below is a
separate batch; no unrelated changes or migration SQL are included.

## Developer notice fix

Amazon's [deprecation schedule](https://developer-docs.amazon/sp-api/docs/sp-api-deprecations)
removes Orders v0 on March 27, 2027. This is a planned retirement, not evidence of
an immediate outage. Scheduled sales ingestion was migrated on October 18.
Caller inspection found the optional `--order-id` path still used v0 getOrder
and a separate getOrderItems call. No other Amazon single-order callers were found.

Following the [migration guide](https://developer-docs.amazon/sp-api/docs/orders-api-migration-guide)
and [getOrder reference](https://developer-docs.amazon/sp-api/reference/getorder-3):

- Single-order reads now use `/orders/2026-01-01/orders/{orderId}`, requesting only
  FULFILLMENT, PROCEEDS and CANCELLATION. IDs are URL-escaped; blank IDs, mismatched
  response IDs and missing item collections fail safely.
- `--order-id` uses the existing 2026 projection, embedded items and missing-value
  preservation. It makes no separate item request. Existing operational tables,
  cutoff, dry-run default, apply behavior and scheduled search remain unchanged.
- The item helper retains its normalized compatibility envelope using the new
  getOrder response. Obsolete nonempty pagination tokens fail explicitly rather
  than silently returning duplicate items. Provider failures retain existing
  error handling; retry/auth behavior is unchanged.
- Buyer/recipient/package datasets are not requested; unsolicited personal fields
  are removed by the existing explicit projection before persistence. No roles,
  credentials, permissions, schema, or shared migration ledger changes are needed.

Unused legacy list_orders/iter_orders helpers remain outside this authorized
single-order batch; no production caller uses them. This is not a claim that all
legacy text has been removed from the client.

## Validation and delivery

`python -m unittest tests.test_amazon_orders_2026 tests.test_revseller_model_migration tests.test_amazon_sales_profitability_fees`
passed 23 tests. Coverage includes unchanged scheduled search/pagination, manual
and scheduled apply destinations, embedded items without extra requests, retained
known fields versus explicit zero, unsolicited PII removal, malformed/mismatched
responses, rejected legacy tokens, and provider failure with no writes.
`git diff --check` passed.

Build with `scripts/deploy-scheduler.ps1`, using revision 145 as the base and a
nonmatching schedule prefix to register without retargeting workloads. Verify a
bounded read-only ECS canary against the new revision before updating only
`mbop-amazon-sales-recent-*` with `scripts/update-scheduler-schedules.ps1`.
Compare captured schedules and task configuration; preserve all fields except
the intended image/task revision. Web, sourcing and purchase enrichment do not
need redeployment. Rollback only the two sales schedules to revision 145.

Deployment receipt follows after production verification.
