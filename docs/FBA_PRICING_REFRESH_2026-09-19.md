# FBA Pricing Refresh Deployment - 2026-09-19

## Incident

The Send to Amazon `Update Pricing` action started production scheduler run
`d20051b7-0bb9-40ab-8022-b603af9aefe6`. The run requested live Keepa offers
for every eligible ASIN. Its first 20-ASIN request consumed 240 tokens and drove
the token balance negative. It reached only 25 of 115 ASINs and then waited for
token replenishment, which made the UI continue to report that pricing was
running.

The task was stopped at `2026-09-19T20:15:46Z`. The scheduler run was closed as
`cancelled`, and its running job was closed as `failed`, with an operator message
that it was replaced by the lightweight pricing refresh. This cleanup changed
telemetry only.

## Repair

Commit `50bd6d179b5f7e2d2b8f28dc257d92344dc3e97e` changes
`integrations/fba_pricing_keepa_until_complete.py` so the normal FBA pricing
group requests Keepa statistics without offer/stock enrichment. The default
token estimate is one token per ASIN. The `--offers` option remains available
for an explicitly requested diagnostic run and is no longer part of the normal
button path.

Two regression tests verify that the default command omits `--offers` and
`--only-live-offers`, while an explicit offer count still enables those flags.
The tests, Python compilation, and `git diff --check` passed.

## Deployment

- Scheduler task definition: `mbop-scheduler-task:103`
- Source commit: `50bd6d179b5f7e2d2b8f28dc257d92344dc3e97e`
- Image digest: `sha256:0ed3f676b82f5d325048684e23aff0d4ab2aeebadff599f7ad5e37953da6e3f1`
- Replacement ECS task: `081c9b61c84e457eb1c928290f82a0db`
- Replacement scheduler run: `2a03d374-8cb7-4ec8-ad86-0f9eef84030e`
- Trigger: `mbop-web-on-demand-fba-pricing-recovery`

No EventBridge schedule or cadence was changed. The existing web on-demand path
selects the latest scheduler task revision, so a web deployment was not needed.

## Production verification

The replacement run started at `2026-09-19T20:17:51.899614Z` and finished at
`2026-09-19T20:42:24.799091Z`, a runtime of 1,472.899 seconds. ECS exited zero
and scheduler telemetry records the overall run and both jobs as `ok`.

- Keepa FBA prep pricing: 115 distinct ASIN snapshots captured, 115 rows
  updated, no error. The request logs contain stats/history/rating parameters
  and no offer parameter.
- Amazon Product Fees estimates: 111 successful cache rows across 107 distinct
  ASINs, no error. Multiple rows can exist for an ASIN at different prices.
- The Keepa snapshots were captured from `2026-09-19T20:19:22Z` through
  `2026-09-19T20:39:27Z`.

The run wrote only pricing snapshots, fee-estimate cache rows, and scheduler
telemetry. It did not change FBA shipment state, purchase history, received
quantities, inventory workflow state, or scheduler cadence.
