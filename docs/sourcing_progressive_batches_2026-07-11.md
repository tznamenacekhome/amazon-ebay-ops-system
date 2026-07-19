# Sourcing Progressive Quota Batches

Date: 2026-07-11

Update 2026-07-12: daily discovery now runs through
`integrations/run_daily_catalog_sourcing.py`, a unified coverage-cycle runner
that builds one prioritized ASIN queue and spends the usable eBay Browse quota.
The progressive batch tables remain the presentation/history layer for
operator-visible opportunities, and `run_sourcing_workflow.py` remains useful
for legacy/manual compatibility.

## Current Run Semantics Audited

- `/api/sourcing/runs` creates a `sourcing_runs` row and starts an AWS ECS
  scheduler task for `integrations/run_sourcing_workflow.py`.
- Before this change, the runner built seeds, searched a fixed ASIN slice, then
  scored the run once.
- Recent Sales built up to 250 seed ASINs but searched only 50 by default.
- Full Listings built and searched up to 5,000 seed ASINs by default.
- Seeds are stored before eBay search starts and candidates/opportunities retain
  `sourcing_run_id`, `seed_id`, and candidate/opportunity IDs.
- `/api/sourcing/opportunities` previously chose the latest completed run per
  mode and returned open opportunities after backend scoring and API-side
  deduplication.
- `--replace-run` is useful for starting a fresh run, but it is not suitable for
  continuation because it deletes prior seed/opportunity state.
- Dismissed, purchased, unavailable, and blocked rows are excluded through
  existing `sourcing_opportunities.status`, opportunity type, and matching
  diagnostics. The progressive batch selector additionally excludes opportunities
  already assigned to earlier batch items for the same run.
- eBay calls are counted per run/batch by actual Browse search/detail calls.
  The runner reads eBay Developer Analytics before searching and treats the
  remaining `buy.browse` quota as the default daily budget.

`CODEX_PROMPTING_GUIDE_v3.md` was not present in this repository.

## Implemented

- Added durable batch tables:
  - `sourcing_opportunity_batches`
  - `sourcing_opportunity_batch_items`
- Added `--offset` support to `integrations/ebay_sourcing_search.py` so the
  runner can continue through the prioritized seed queue in chunks.
- Changed cloud on-demand sourcing to run `integrations/run_sourcing_workflow.py`
  without a fixed opportunity target. The runner spends the available daily
  eBay Browse quota and collects as many qualifying opportunities as that quota
  can find.
- Added `integrations/run_daily_sourcing_discovery.py` and a
  `run_all_syncs.py` daily `Sourcing opportunity discovery` job in the
  `sourcing-catalog` group.
- Added a progressive loop that:
  - builds the full seed queue for a new run
  - searches seed chunks
  - rescoring after each chunk
  - counts only open Buy Now, Best Offer, auction, and multi-unit opportunities
  - stops at exhausted seeds, explicit manual target, persistent eBay 429, or
    depleted Browse quota
  - persists batch membership and funnel summary
- Added `POST /api/sourcing/runs/[runId]/continue` to start the next batch for
  the same run.
- Updated `/api/sourcing/opportunities` to use completed batches as durable
  presentation history. As of 2026-07-19, completed batches are no longer the
  default Replenishment limiting scope: `All Open` combines still-open
  actionable opportunities across current and prior runs, while `New This Run`
  preserves the newest completed batch view.
- Added a compact Replenishment batch status strip with:
  - batch number
  - current batch count
  - cumulative count
  - seeds searched
  - seeds remaining
  - hard-block count when available
  - stop reason
  - Spend Remaining Quota button
- Updated Sourcing History display language so `ebay_out_of_quota` and
  persistent Browse 429 stops display as `Out of quota` rather than `Failed`.

## Funnel Coverage

The persisted batch funnel currently includes:

- scored opportunities
- valid open opportunities
- opportunities in the current batch
- rejected opportunities
- hard-blocked opportunities
- profitability rejects
- review/watch count

Coverage Cycle `Opportunities Presented` is derived from unique
`sourcing_opportunity_batch_items.opportunity_id` values in completed batches
for the cycle. It is distinct from raw candidates, scored opportunities, and
the current open actionable queue count.

The migration and runner also persist:

- requested opportunity count
- batch/cumulative seed cursor
- seeds remaining
- candidate count
- API calls used
- stop reason

## Follow-Up Gaps

These were intentionally not papered over:

- Seed-level processing states (`pending`, `searched`, `failed`, retry counts)
  are not yet first-class columns.
- Seed exclusion counts for minimum price, stale-stock logic, MFN/FBA
  eligibility, and Keepa snapshot age are not yet persisted in the funnel.
- The eBay daily quota is read live from eBay Developer Analytics. A durable
  quota history table remains a possible follow-up if trend reporting becomes
  useful.
- UI progress while an ECS task is actively running still depends on history
  refresh/polling rather than streaming per-chunk progress.

## Safety Confirmations

- No AI calls were added.
- No model training was added.
- No eBay-to-Amazon sourcing was added.
- No auto-purchase, bid, or Best Offer submission was added.
- Matching, scoring, and batch qualification remain backend-owned.
