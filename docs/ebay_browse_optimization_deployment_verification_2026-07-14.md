# eBay Browse Optimization Deployment Verification - 2026-07-14

## Summary

Deployment was necessary. Production `mbop-sourcing-catalog` was still running
`mbop-scheduler-task:20`, whose scheduler image was pushed before the Browse
optimization commit. The schedule has been updated to `mbop-scheduler-task:21`,
which is pinned to a scheduler image built from current repository HEAD.

No sourcing business rules or production data were changed. The only production
change was the EventBridge Scheduler target revision for the daily sourcing
catalog schedule.

## Repository State

- Default branch: `main`
- Repository HEAD: `56a34347dd8eb515161e32ef88bdcd24d92a3fcb`
- Browse optimization commit:
  `f2dfc641da31b4029953f3bc4c8eec390e8cd379`
- HEAD includes the optimization commit: yes
- Uncommitted local files relevant to deployment: none
- Untracked local files excluded from the scheduler image:
  `docs/CODEX_WORKFLOW.md`, `ebay_purchases.py`

The production image was built from a clean `git archive` of HEAD, so untracked
local files were not included.

## Expected Code Verified In Repository

- One query for supported systems:
  `integrations/ebay_sourcing_search.py:261`
- Supported-system query returns one platform-aware query:
  `integrations/ebay_sourcing_search.py:276`
- Unsupported systems are skipped:
  `integrations/ebay_sourcing_search.py:269`
- Default `--max-results-per-asin` is `200`:
  `integrations/ebay_sourcing_search.py:229`
- Search requests use Video Games category `139973`:
  `integrations/ebay_sourcing_search.py:614`
- Fallback search requests also use category `139973`:
  `integrations/ebay_sourcing_search.py:634`
- Pre-detail summary candidate decision:
  `integrations/ebay_sourcing_search.py:100`
- Best Offer pre-filter uses `best_offer_min_ask_percent`:
  `integrations/ebay_sourcing_search.py:371`
- Lazy detail planning:
  `integrations/ebay_sourcing_search.py:440`
- Detail reason counts:
  `integrations/ebay_sourcing_search.py:539`
- Detail call records:
  `integrations/ebay_sourcing_search.py:564`
- Search/detail/retry counting wrapper:
  `integrations/ebay_sourcing_search.py:707`
- Final run aggregation into `raw_summary_json.ebay_search`:
  `integrations/run_daily_catalog_sourcing.py:412`
- Chunk metric aggregation:
  `integrations/run_daily_catalog_sourcing.py:469`

## Production Scheduler Path

- Schedule name: `mbop-sourcing-catalog`
- Schedule group: `default`
- State: `ENABLED`
- Schedule expression: `cron(10 0 ? * * *)`
- Timezone: `America/Los_Angeles`
- Target: `arn:aws:scheduler:::aws-sdk:ecs:runTask`
- ECS cluster:
  `arn:aws:ecs:us-west-2:297464765814:cluster/mbop-cluster1`
- Container: `mbop-scheduler`
- Command override:
  `python run_all_syncs.py --group sourcing-catalog`
- EventBridge Scheduler role:
  `arn:aws:iam::297464765814:role/mbopEventBridgeSchedulerEcsRole`
- CPU override: `1024`
- Memory override: `2048`
- Subnets:
  `subnet-04169524e0f9bdd8b`,
  `subnet-07558cd00060ff69d`,
  `subnet-0acbbc29cdf301200`,
  `subnet-0b2f04002f8b85fa0`
- Security group: `sg-0b05e7760083c5e31`
- Public IP assignment: `ENABLED`
- CloudWatch log group: `/ecs/mbop-scheduler`

## Before Deployment

- Scheduler target task definition:
  `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:20`
- Image:
  `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:2a6eea5d26635662ca1b95b41d9b05a5f1a850bc312ac518feb0b2ebf703850c`
- ECR tag: `scheduler-301412a48193`
- ECR pushed: `2026-07-12T15:30:20.669000-07:00`

The previous image was pushed before optimization commit
`f2dfc641da31b4029953f3bc4c8eec390e8cd379`, which was committed on
`2026-07-12T21:18:51-07:00`.

Conclusion before deployment: production was running an older image.

## Most Recent Production Run Before Deployment

- Sourcing run ID: `6e8d5312-e490-47a9-9018-28dd219e91cd`
- CloudWatch stream:
  `scheduled/mbop-scheduler/f8ef2f5d3ea1417ea394d5718109b62c`
- Searched ASINs: `1,193`
- Logged search lines: `2,287`
- Alias fan-out was active. The first ASIN had three search variants:
  `Wolfenstein II The New Colossus PlayStation 4 PlayStation 4`,
  `wolfenstein ii the new colossus PlayStation 4`, and
  `wolfenstein ii the new colossus ps4`.
- `raw_summary_json.ebay_search` was absent.
- Candidate categories included non-`139973` rows.

Conclusion: the last production run did not execute the optimized code path.

## Deployment

- New image tag: `scheduler-56a34347dd8e`
- New image digest:
  `sha256:bc42711a71e9f13ed95ad5f35fbf8181d117f0ac404730ad3ddc39ff42986f2d`
- ECR pushed: `2026-07-13T09:49:47.967000-07:00`
- New task definition:
  `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:21`
- Task definition image:
  `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:bc42711a71e9f13ed95ad5f35fbf8181d117f0ac404730ad3ddc39ff42986f2d`
- Base task CPU: `512`
- Base task memory: `1024`
- Execution role: `arn:aws:iam::297464765814:role/ecsTaskExecutionRole`
- Task role: none
- Log group: `/ecs/mbop-scheduler`
- Log stream prefix: `scheduled`

The EventBridge Scheduler target was updated from `mbop-scheduler-task:20` to
`mbop-scheduler-task:21`. The schedule retained the same command override,
networking, EventBridge role, retry policy, CPU override, memory override, and
timezone schedule.

## After Deployment

- Scheduler target task definition:
  `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:21`
- Scheduler target command:
  `python run_all_syncs.py --group sourcing-catalog`
- Scheduler target CPU override: `1024`
- Scheduler target memory override: `2048`
- Scheduler target cluster:
  `arn:aws:ecs:us-west-2:297464765814:cluster/mbop-cluster1`

Explicit conclusion: production is now configured to run the current optimized
code on the next scheduled `mbop-sourcing-catalog` execution.

## Image Smoke Test

The deployed image was validated locally without consuming eBay Browse quota.

Command result from `mbop-scheduler:scheduler-56a34347dd8e`:

```text
category 139973
query_count 1
query ['halo infinite (Xbox Series X,Series X,Series S)']
max_results_per_asin 200
detail_plan_exists True
metrics_ok True
agg_ok True
```

This proves the image exposes the Video Games category filter, one-query
platform-aware search generation, 200-result default, lazy detail planning,
detail/search/retry metric keys, detail reason tracking, and final run
aggregation keys.

The image also listed the production `sourcing-catalog` group without running
jobs or consuming Browse quota:

```text
Daily catalog sourcing
Sourcing listing availability
Matching intelligence refresh
Keepa sourcing opportunities
```

## Quota Accounting Status

The previous report showed:

- App-counted Browse calls: `5000`
- eBay Analytics Browse calls: `4140`
- Difference: `860`

Current repository code improves accounting by counting search and detail HTTP
attempts in the shared Browse wrapper, tracking retry and rate-limit attempts,
persisting detail-call reasons and outcomes, merging chunk counters into the
final run summary, and setting `api_call_count` from search plus detail calls.

No additional code change was made during this deployment. I did not find a
small, obvious accounting bug that was safer to patch than to document. The
remaining reconciliation question is whether eBay Developer Analytics counts
failed, retried, fallback, or delayed-attribution Browse requests exactly the
same way as MBOP's application counters. The next scheduled run should be used
to compare `raw_summary_json.ebay_search.api_call_count`,
`search_call_count`, `detail_call_count`, retry counts, and eBay Analytics.

## Validation Checklist

- `python tests/test_ebay_sourcing_search.py`: passed, 14 tests
- `python tests/test_sourcing_match_rules.py`: passed, 24 tests
- `python tests/test_sourcing_progressive_batches.py`: passed, 9 tests
- `python tests/test_sourcing_coverage_cycle.py`: passed, 8 tests
- Python compile for sourcing/scheduler modules: passed
- Docker build for scheduler image: passed
- Docker image smoke test without Browse calls: passed
- `python run_all_syncs.py --group sourcing-catalog --list` in container:
  passed
- `npm run build` in `web/`: passed

No validation step triggered a production sourcing run or consumed eBay Browse
quota.

## Next Scheduled Run

The schedule is `cron(10 0 ? * * *)` in `America/Los_Angeles`.

Next scheduled execution after deployment: `2026-07-14 00:10 PT`
(`2026-07-14 07:10 UTC`).

## Follow-Up

After the next scheduled run completes, verify:

- `sourcing_runs.raw_summary_json.ebay_search` exists.
- `searched_seed_count` is close to the intended quota-driven count.
- `search_call_count` is approximately one per searched supported ASIN, plus
  any documented fallback/retry calls.
- `detail_call_count` is materially lower than old detail fan-out behavior.
- Detail reason and outcome counts are populated.
- eBay Analytics Browse usage reconciles against MBOP's application counters.
