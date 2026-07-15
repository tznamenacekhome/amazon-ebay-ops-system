# eBay Browse Call Optimization Production Validation - 2026-07-15

Scope: read-only report on the latest production `daily_catalog_sourcing` run
with persisted eBay Browse search/detail instrumentation. No sourcing settings,
business rules, schema, or production sourcing data were changed to generate
this report.

Important timing note: this report analyzes the production run that started at
`2026-07-14T07:12:16Z`, immediately after the eBay Browse quota reset whose
next reset was recorded as `2026-07-15T07:00:00Z`.

Primary run analyzed:

- `sourcing_run_id`: `347967a3-f3c8-4794-a8d2-e2419728339b`
- Run type: `daily_catalog_sourcing`
- Coverage cycle: `2aa4afbb-39a5-465f-8f34-2f9180625d1b`
- Started: `2026-07-14T07:12:16.424849Z`
- Completed: `2026-07-14T08:34:23.385577Z`
- Stop reason: `quota_reserve_reached`
- Scheduler run: `cab1a629-ce81-40b0-992a-f4e689620145`
- EventBridge schedule: `mbop-sourcing-catalog`
- ECS task:
  `arn:aws:ecs:us-west-2:297464765814:task/mbop-cluster1/563100e6169349728cecd5a025c67fbf`
- ECS task definition at run time: `mbop-scheduler-task:21`
- Scheduler image:
  `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:bc42711a71e9f13ed95ad5f35fbf8181d117f0ac404730ad3ddc39ff42986f2d`

Baseline/reference reports:

- `docs/ebay_browse_call_efficiency_audit_2026-07-12.md`
- `docs/ebay_browse_call_optimization_production_validation_2026-07-14.md`

## 1. Executive Summary

The optimized production path remained active:

- one platform-aware query per supported ASIN was active
- query variants equaled search calls
- old alias fan-out did not return
- Browse search/detail metrics were persisted under
  `sourcing_runs.raw_summary_json.ebay_search`
- detail reasons and outcomes were persisted
- the run stopped only after spending its full app-counted Browse budget

The run searched far more ASINs than the previous optimized validation:

| Metric | 2026-07-14 Validation | Today's Run | Delta |
| --- | ---: | ---: | ---: |
| Browse calls | 578 | 5,000 | +4,422 |
| Search calls | 142 | 1,200 | +1,058 |
| Detail calls | 436 | 3,800 | +3,364 |
| Searched seeds | 143 | 1,215 | +1,072 |
| Calls / searched seed | 4.04 | 4.12 | +0.08 |
| Search calls / searched seed | 0.99 | 0.99 | flat |
| Detail calls / searched seed | 3.05 | 3.13 | +0.08 |
| Batch-qualifying opportunities | 47 | 466 | +419 |
| Batch opportunities / 1,000 Browse calls | 81.31 | 93.20 | +11.89 |

The largest remaining quota sink is still item detail:

- detail calls were `3,800 / 5,000` app-counted Browse calls (`76.0%`)
- every detail-eligible record carried `game_name_confirmation_needed`
- `2,457` detail records also had `shipping_missing`
- `1,044` detail records (`27.5%`) had no material decision change

Recommendation: **DETAIL-CALL OPTIMIZATION IS STILL THE NEXT HIGH-VALUE PASS**.
The deployed search optimization is holding, but Browse efficiency is now bound
mostly by detail enrichment and Game Name confirmation.

## 2. Run And Coverage State

| Run Metric | Value |
| --- | ---: |
| Source rows loaded | 1,250 |
| Seeds searched | 1,215 |
| Supported search calls | 1,200 |
| Unsourced seeds skipped | 16 |
| Search results returned | 36,412 |
| Stored/scored candidates | 2,911 |
| Batch-qualifying opportunities | 466 |
| App-counted Browse calls | 5,000 |
| Stop reason | `quota_reserve_reached` |

Coverage cycle state after the run:

| Coverage Metric | Value |
| --- | ---: |
| Cycle number | 3 |
| Status | active |
| Total eligible ASINs | 1,537 |
| Searched | 1,215 |
| Remaining | 322 |
| Retryable failed | 35 |
| Completion | 79.05% |
| Total Browse calls | 5,000 |
| Candidates found | 2,979 |
| Qualifying opportunities | 2,979 |

Bucket progress:

| Bucket | Total | Searched | Remaining | Browse Calls | Candidates | Qualifying Opps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sold in last 90 days | 246 | 246 | 0 | 807 | 429 | 429 |
| Purchased, not sent to Amazon | 44 | 44 | 0 | 254 | 210 | 210 |
| Remaining catalog | 1,247 | 925 | 322 | 3,939 | 2,340 | 2,340 |

## 3. Quota Accounting

| Quota Metric | Value |
| --- | ---: |
| Starting Browse quota count | 0 |
| Starting Browse quota remaining | 5,000 |
| Starting Browse quota limit | 5,000 |
| Ending Browse quota remaining | 670 |
| App-counted Browse calls | 5,000 |
| App-counted vs stored Analytics delta | 670 |
| Browse quota reset | `2026-07-15T07:00:00Z` |

This run reintroduced a quota reconciliation discrepancy. MBOP's internal
counter reached the 5,000-call budget and the final chunk stopped as
`ebay_out_of_quota`, but the stored eBay Analytics ending snapshot still showed
`670` remaining. Treat the `670` difference as unresolved until the next quota
accounting pass compares:

- app `api_call_count`
- `search_call_count`
- `detail_call_count`
- failed/retry counters
- eBay Analytics after enough delay for reporting freshness

The discrepancy did not prevent correct operational stopping. The job stopped
instead of continuing to spend calls after the app-side budget was exhausted.

## 4. Search Query Analysis

| Search Metric | Value |
| --- | ---: |
| Seed rows requested across chunks | 1,250 |
| Seeds searched | 1,215 |
| Search calls | 1,200 |
| Query variants | 1,200 |
| Search calls / searched seed | 0.99 |
| Search calls / supported searched ASIN | 1.00 |
| Search results returned | 36,412 |
| Search results / search call | 30.34 |
| Stored candidates | 2,911 |
| Stored candidates / searched seed | 2.40 |
| Duplicate summary items skipped | 15 |

Confirmation:

- One-query-per-supported-ASIN: confirmed by `1,200` query variants for
  `1,200` search calls.
- Alias fan-out: not observed in persisted counters.
- Unsupported/unsourced seeds: `16` skipped.
- Search chunking: 25 chunks were attempted; the final chunk stopped with
  `ebay_out_of_quota`.

Chunk behavior:

| Chunk Metric | Value |
| --- | ---: |
| Chunks | 25 |
| Requested seeds | 1,250 |
| Searched seeds | 1,215 |
| Search calls | 1,200 |
| Detail calls | 3,800 |
| App-counted calls | 5,000 |
| Rate-limited/out-of-quota chunks | 1 |
| Highest-detail chunk | offset `250`, 253 detail calls |
| Final chunk | offset `1200`, 16 search calls, 63 detail calls |

## 5. Candidate Category And Shipping

Stored candidate category evidence:

| Category Observation | Count |
| --- | ---: |
| `139973 Video Games` | 2,850 |
| `139973 Jeux vidéo` | 6 |
| Category not exposed in raw audit query | 55 |
| Total stored candidates | 2,911 |

Among stored candidates whose raw payload exposed a category in this audit
query, `2,856 / 2,856` were category `139973`. The 55 missing-category rows
were not proven category leaks; the category field was simply not available in
the stored raw shape used by this report query.

Shipping evidence:

| Shipping Metric | Value |
| --- | ---: |
| Stored candidates with shipping cost | 2,908 / 2,911 |
| Detail records with `shipping_missing` reason | 2,457 |
| Shipping-missing detail records with missing data resolved | 2,456 |
| Shipping-missing detail records retained | 1,928 |
| Shipping-missing detail records that changed decision/economics | 2,454 |

Shipping enrichment remained highly effective, but expensive.

## 6. Detail Call Analysis

Unique Browse item-detail HTTP calls: `3,800`.

Detail records: `3,801`. One eligible detail was served from the run-level
detail cache (`duplicate_detail_calls_prevented_count = 1`), so records exceed
HTTP detail calls by one.

Detail reasons can overlap, so reason counts sum above unique detail calls.

| Detail Reason | Calls |
| --- | ---: |
| `shipping_missing` | 2,457 |
| `platform_confirmation_needed` | 98 |
| `game_name_confirmation_needed` | 3,801 |
| `region_confirmation_needed` | 0 |
| `edition_confirmation_needed` | 0 |
| `type_or_format_confirmation_needed` | 0 |
| `description_needed` | 0 |
| `quantity_confirmation_needed` | 0 |
| `combined_shipping_evaluation_needed` | 0 |

Detail reason outcomes:

| Detail Reason | Calls | Missing Data Resolved | Changed Decision | Retained |
| --- | ---: | ---: | ---: | ---: |
| `shipping_missing` | 2,457 | 2,456 | 2,454 | 1,928 |
| `platform_confirmation_needed` | 98 | 96 | 95 | 47 |
| `game_name_confirmation_needed` | 3,801 | 3,782 | 2,757 | 2,992 |

Overall detail outcomes:

| Detail Outcome | Count | Percent |
| --- | ---: | ---: |
| Detail successes | 3,801 | 100.0% of detail records |
| Missing data resolved | 3,782 | 99.5% |
| Missing data not resolved | 19 | 0.5% |
| Changed sourcing decision/economics | 2,757 | 72.5% |
| No decision change | 1,044 | 27.5% |
| Candidate retained after detail | 2,992 | 78.7% |
| Candidate rejected after detail | 809 | 21.3% |

Detail calls are still useful most of the time, but the absolute volume is the
main reason the run can only cover about 1,200 supported searches per 5,000-call
day.

## 7. Summary Filtering

| Summary Filter Metric | Count |
| --- | ---: |
| Search results returned | 36,412 |
| Non-economic summary filtered | 17,343 |
| Profitability summary filtered | 15,229 |
| Duplicate items skipped | 15 |
| Detail-eligible records | 3,801 |
| Stored candidates after final filters | 2,911 |

The pre-detail filters avoided tens of thousands of possible detail calls. The
best-case avoided-detail estimate from profitability filtering alone is
`15,229` calls, before considering the separate non-economic summary filters.

The detailed split inside `summary_filtered_count` is still not persisted, so
category/accessory/digital/platform/edition/region/seller sub-reasons cannot be
reported separately from this run.

## 8. Opportunity Quality

Opportunity type by scored rows:

| Opportunity Type | Rows |
| --- | ---: |
| Buy Now | 224 |
| Best Offer | 851 |
| Auction | 20 |
| Multi-unit | 24 |
| Watch | 38 |
| No profitable source found | 1,754 |

Workflow/status by scored rows:

| Status | Rows |
| --- | ---: |
| Open | 466 |
| Rejected | 2,422 |
| Purchased pending match | 6 |
| Watching | 7 |
| Dismissed | 10 |

Actionable batch:

| Metric | Value |
| --- | ---: |
| Batch ID | `4227fe3e-0193-4e26-9ee2-d297c3989e0b` |
| Batch-qualifying opportunities | 466 |
| Batch opportunities / searched seed | 0.383 |
| Batch opportunities / 1,000 Browse calls | 93.20 |

The optimized run produced materially more actionable opportunities per 1,000
Browse calls than the first optimized validation run.

## 9. Scheduler Result

The `Daily catalog sourcing` job completed successfully:

| Scheduler Field | Value |
| --- | --- |
| Scheduler group | `sourcing-catalog` |
| Scheduler run status | `failed` |
| Daily sourcing job status | `ok` |
| Daily sourcing runtime | 5,024.201 seconds |
| Follow-up availability job | `ok` |
| Follow-up Keepa sourcing opportunities job | `ok` |
| Group failure cause | `Matching intelligence refresh failed with exit code 1` |

The sourcing job itself did not fail. The overall scheduler group was marked
failed because the later `Matching intelligence refresh` job failed after
sourcing and availability completed.

## 10. Remaining Optimization Opportunities

| Rank | Opportunity | Expected Browse Savings | Complexity | Sourcing Risk |
| ---: | --- | --- | --- | --- |
| 1 | Reduce Game Name detail calls for high-confidence title/platform/category matches. | Potentially part of 3,801 detail records. | Medium | Medium |
| 2 | Skip detail when the summary row is already economically impossible even with best-case shipping. | Additional savings inside 2,457 shipping-missing overlap. | Medium | Low |
| 3 | Persist summary-filter sub-reason counters. | No direct savings, but needed to target the 17,343 non-economic rejects. | Low | Low |
| 4 | Reconcile app-counted calls vs eBay Analytics after reporting delay. | No direct savings, but resolves the 670-call discrepancy. | Medium | Low |
| 5 | Add a confidence gate for detail when category, title, platform, and pricing are already decisive. | Could reduce the 1,044 no-decision-change records. | Medium | Medium |
| 6 | Keep run-level detail caching and consider short-lived persistent detail cache. | Small within this run (`1` duplicate prevented), more useful across reruns. | Medium | Low |

## 11. Recommendation

**NEEDS ANOTHER DETAIL-CALL OPTIMIZATION PASS**

The search-side optimization is stable. The run covered 1,215 seeds and
generated 466 batch opportunities while preserving one-query-per-supported-ASIN
behavior. The next efficiency gain is not search query reduction; it is reducing
item-detail calls, especially calls made only to confirm Game Name when the
summary evidence is already strong.

Also investigate quota reconciliation. The job made the right operational stop,
but MBOP stored 5,000 app-counted calls against an ending eBay Analytics
remaining value of 670. That discrepancy should be measured again after
Analytics has had time to settle.

Sources used:

- Supabase `sourcing_runs`
- Supabase `sourcing_coverage_cycles`
- Supabase `sourcing_coverage_cycle_items`
- Supabase `sourcing_opportunity_batches`
- Supabase `sourcing_opportunity_batch_items`
- Supabase `sourcing_ebay_candidates`
- Supabase `sourcing_opportunities`
- Supabase `scheduler_runs`
- Supabase `scheduler_run_jobs`
- AWS ECS task definition `mbop-scheduler-task:21`

No production sourcing behavior or production data was changed for this report.
