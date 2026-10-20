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

## Canary correction before rollout

The first read-only ECS canary on revision 146, task
`568f2af3c38d429fa41e303a32f292a1`, exited 1 at response validation. The initial
fixture incorrectly modeled getOrder as an unwrapped Order; the official
[GetOrderResponse schema](https://github.com/amzn/selling-partner-api-models/blob/main/models/orders-api-model/orders_2026-01-01.json)
requires an `order` envelope. The client now unwraps and validates that envelope,
and regression fixtures reflect it, including rejecting bare/missing/null orders.
No database reads/writes occurred and no live schedules had been retargeted.
Revision 146 is not approved for production schedules. The corrected revision
must pass the repeated read-only canary before rollout.

## Deployment receipt

Application commits `63407503f9e6` and corrected `83ec65d47131` were pushed to
origin/main. Both builds used a clean working tree and the documented scheduler
deployment helper, based on revision 145. The nonmatching schedule prefix
updated zero schedules during image registration.

The approved corrected image is
`sha256:16cc9505f6732443540de165d9ebc69e7ba417ed9114845181f700ed6337414d`,
tagged `scheduler-83ec65d47131`, registered as `mbop-scheduler-task:147`.
Read-only ECS canary `71a95707694c48fab9bc79c70aaa3efc` reached STOPPED with
exit 0 and logged:

```text
ORDERS_MANUAL_CANARY_OK api=2026-01-01 orders=1 items=1 database_reads=0 database_writes=0
```

It searched one recent page to choose an order, exercised the actual targeted
fetch/normalization path, and built its order/item rows without constructing a
database client. No raw order payloads or personal fields were logged or saved.
This proves the deployed live lookup and normalization, while persistence and
error gates are covered by the mocked regression tests; no apply canary or broad
sync was necessary for this manual-path change.

Only `mbop-amazon-sales-recent-catchup` and `mbop-amazon-sales-recent-day` were
retargeted from 145 to 147. Both remain ENABLED. Exact before/after comparison
confirmed schedule expressions, timezone, networking, overrides, role, state and
other configuration were retained. Task-definition comparison confirmed image
was the only configured change, accounting for AWS runtime metadata and unordered
compatibility-list ordering. Sourcing remains ENABLED on 143 and purchase
enrichment ENABLED on 144. No web rollout was required; revision 188 remained
healthy with build `93740307e3d9` and a healthy ALB target.

Remote main was verified at corrected application commit `83ec65d47131` before
this documentation-only receipt. The receipt does not require another image
build. The overnight catch-up and developer-notice batch are complete with no
remaining blocker. This does not claim completion of a future scheduled sales
run, or removal of the unused legacy list helpers described above.
