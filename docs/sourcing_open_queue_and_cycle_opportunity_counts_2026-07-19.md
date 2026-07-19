# Sourcing Open Queue And Coverage-Cycle Presented Counts

Date: 2026-07-19

## Root Cause

The Replenishment API defaulted to the newest completed sourcing batch when
batch membership existed. That preserved the progressive-batch "new rows"
behavior, but it also meant still-open opportunities from prior completed
batches disappeared from the default Replenishment screen after a newer batch
completed.

No production data needed to be restored. The rows were still present with
their operator action history intact; they were hidden by API scoping.

## Production Read-Only Findings

Read-only audit command:

```powershell
.\.venv\Scripts\python.exe tools\audit_sourcing_open_queue.py
```

Latest completed batch inspected:

- completed at: `2026-07-19T08:15:10.930959+00:00`
- batch: `d1f44c64-2e6e-42ae-b9ed-5fbad8164819`
- run: `9c7401b7-03a3-4906-9f3c-e9094038c94b`
- total presented: `8`

Prior three completed batches inspected:

- unique prior presented opportunities: `102`
- prior opportunities absent from latest batch: `102`
- still open but hidden only by latest-batch scope: `48`
- dismissed among absent prior opportunities: `31`
- no-longer-available dismissals among absent prior opportunities: `2`

Status counts among prior opportunities absent from the latest batch:

- `open`: `48`
- `watching`: `8`
- `purchased_pending_match`: `6`
- `matched_to_purchase`: `9`
- `dismissed`: `31`

Dismiss reason counts included `no_longer_available: 2`; those rows remain
excluded by status and were not reopened.

## Count Definitions

- Raw candidates: eBay candidate rows captured from Browse responses.
- Scored opportunities: rows written to `sourcing_opportunities`, including
  rejected/no-profitable-source rows.
- Batch-qualifying opportunities: open rows selected by the batch builder for
  operator presentation.
- Opportunities Presented: unique `opportunity_id` values in
  `sourcing_opportunity_batch_items` for all completed batches in all runs for a
  coverage cycle. One opportunity counts once per cycle even if rediscovered.
- Currently Open Actionable Opportunities: current API queue rows with
  `status = open`, not ended by availability state, deduped by normalized eBay
  listing identity, and sorted by the existing score/recency/ASIN grouping
  behavior.

## API Changes

`GET /api/sourcing/opportunities` now supports:

- `scope=all_open`: default. Returns open actionable opportunities across
  current and prior runs instead of limiting to the newest batch.
- `scope=new_this_run`: returns opportunities included in the newest completed
  sourcing batch. This preserves the former latest-batch view as an explicit
  operator filter.
- `scope=prior_unreviewed`: returns open opportunities not included in the
  newest completed batch.

The response includes `summary.total` for the full deduped filtered queue and
`summary.returned` for the current page slice. This prevents the default page
limit from implying that only the returned rows exist.

Each opportunity now includes derived presentation metadata where batch history
exists:

- `firstPresentedAt`
- `lastPresentedAt`
- `originatingRunId`
- `latestPresentedRunId`
- `originatingCycleId`
- `latestPresentedCycleId`
- `isNewThisRun`
- `presentationCount`

## Coverage Cycle Changes

`GET /api/sourcing/coverage-cycle` now returns `opportunitiesPresented` for the
active cycle and completed cycle summaries. The value is derived from completed
batch membership, not from raw candidates, rejected scored rows, or the broader
run opportunity count.

The Coverage Cycle UI shows Opportunities Presented in the active cycle cards
and completed-cycle history cards.

## Sorting Behavior

The default queue now combines current and prior open rows before the existing
dedupe/sort pipeline runs. The order remains:

1. Deduplicate exact eBay listings using normalized legacy item ID, item ID, or
   normalized URL.
2. Keep the better row by status rank, score, and recency.
3. Sort by status rank, score descending, then created date descending.
4. Preserve the established ASIN grouping pass over that sorted order.

Newly discovered rows are therefore inserted into the sorted queue according to
the same score/recency/grouping rules instead of being appended or pinned.

## Files Changed

- `web/app/api/sourcing/opportunities/route.ts`
- `web/app/api/sourcing/coverage-cycle/route.ts`
- `web/app/sourcing/page.tsx`
- `web/app/sourcing/useSourcingOpportunities.ts`
- `web/app/sourcing/types.ts`
- `tools/audit_sourcing_open_queue.py`
- `CURRENT_STATE.md`
- `DECISIONS.md`
- `docs/MBOP_Sourcing_Workspace_Architecture.md`
- `docs/database_schema.md`
- `docs/sourcing_progressive_batches_2026-07-11.md`

## Schema Changes

No schema changes were added. The implementation derives counts and metadata
from existing authoritative batch and run tables.

## Validation

Passed:

```powershell
npm.cmd run lint -- app\api\sourcing\opportunities\route.ts app\api\sourcing\coverage-cycle\route.ts app\sourcing\page.tsx app\sourcing\useSourcingOpportunities.ts app\sourcing\types.ts
Set-Location C:\Dev\amazon-ebay-ops-system\web; npm.cmd run build
.\.venv\Scripts\python.exe -m py_compile tools\audit_sourcing_open_queue.py
.\.venv\Scripts\python.exe tests\test_sourcing_progressive_batches.py
.\.venv\Scripts\python.exe tests\test_sourcing_coverage_cycle.py
.\.venv\Scripts\python.exe tests\test_sourcing_match_rules.py
.\.venv\Scripts\python.exe tests\test_ebay_sourcing_search.py
```

Production validation was read-only. No quota-consuming sourcing run was
triggered.

## Caveats

The API still returns a bounded page of opportunities to the frontend, with a
larger backend fetch window before filtering/deduplication. If the open queue
grows beyond that practical window, cursor pagination should become a follow-up.

No sourcing matching, profitability, ROI, Best Offer, auction,
inventory-need, seller-intelligence, external marketplace write, or historical
action behavior was changed.
