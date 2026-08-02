# Sourcing Best Offer Rejection Cleanup

Date: 2026-08-02

## Summary

Several Best Offer sourcing rows were incorrectly excluded from Replenishment review. The scorer classified them as `best_offer`, but the final status gate still required the full asking price to pass profitability. That meant offers with a valid suggested offer amount could remain `status = rejected`.

## Code Changes

- Updated `integrations/score_sourcing_opportunities.py` so rows classified as `buy_now`, `multi_unit`, `best_offer`, or `auction` become `open` when matching rules pass.
- Updated `integrations/sourcing_decision_trace.py` so current-open rows do not retain exclusion reasons, and stale `status = rejected` alone is not labeled as operator history.
- Expanded `integrations/reprocess_recent_rejected_sourcing_decisions.py` with:
  - `--days`
  - `--only-generic-fallback`
  - `--only-stale-reason`
  - `--promote-valid`
  - `--promotions-only`
  - retry/backoff for Supabase chunk reads/writes
- Added regression coverage for valid Best Offer rows scoring as `open`.

## Production Data Changes

First cleanup pass, generic fallback only:

- `783` last-7-days generic rejected rows updated
- `2` rows promoted to `open`
- second non-deduped pass updated `1,161` additional generic rejected rows
- `1` additional row promoted to `open`
- final generic fallback readback: `0` rows remaining

Broad last-7-days rejection cleanup:

- `12,591` rejected rows checked
- stale/generic/false `duplicate_history` reasons cleared
- final precise-reason readback before Best Offer scoring fix:
  - `11,457` profitability
  - `908` region/location
  - `164` historical exact negative
  - `54` numeric installment mismatch
  - `8` wrong platform

Best Offer scoring fix reprocess:

- dry-run found `2,720` rows that current rules now deem valid/open
- promoted those `2,720` rows to `open`
- final readback after promotion:
  - `9,871` rejected rows remain from the last 7 days
  - `0` current-valid opportunities remain rejected
  - remaining reasons:
    - `8,737` profitability
    - `908` region/location
    - `164` historical exact negative
    - `54` numeric installment mismatch
    - `8` wrong platform

## Artifacts

- `tmp/sourcing_rejected_decision_trace_dry_run_20260802213401.json`
- `tmp/sourcing_rejected_decision_trace_write_20260802215839.json`
- `tmp/sourcing_rejected_decision_trace_dry_run_20260802220528.json`
- `tmp/sourcing_rejected_decision_trace_dry_run_20260802224617.json`
- `tmp/sourcing_rejected_decision_trace_write_20260802225447.json`
- `tmp/sourcing_rejected_decision_trace_dry_run_20260802230635.json`

## Verification

- Python compile passed for changed sourcing modules.
- Focused unit tests passed:
  - `tests.test_sourcing_progressive_batches`
  - `tests.test_sourcing_decision_trace`

## Deployment Note

The scoring code runs in the scheduler image for production sourcing jobs. Deploying the scheduler image is required so future sourcing runs do not recreate the Best Offer exclusion issue.

## Deployment

Committed fix:

- `03f6559 Fix best offer sourcing eligibility`

Scheduler deployment:

- image tag: `scheduler-03f6559004ea`
- image digest: `sha256:871abff71ca6508df712406a77a2750314527fbedc0bb00690398f06afd7196f`
- task definition: `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:58`

EventBridge schedule update:

- schedule: `mbop-sourcing-catalog`
- previous task definition: `mbop-scheduler-task:56`
- new task definition: `mbop-scheduler-task:58`
- schedule expression preserved: `cron(10 0 ? * * *)`
- timezone preserved: `America/Los_Angeles`
- command preserved: `python run_all_syncs.py --group sourcing-catalog`
