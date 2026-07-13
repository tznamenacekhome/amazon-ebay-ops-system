# eBay Browse Call Optimization Production Validation

Date: 2026-07-14

Scope: read-only validation of the first production daily sourcing run after the
eBay Browse quota reset. No code, schema, settings, sourcing behavior, or
production data were changed.

Primary run analyzed:

- `sourcing_run_id`: `6e8d5312-e490-47a9-9018-28dd219e91cd`
- Run type: `daily_catalog_sourcing`
- Coverage cycle: `dd2f604c-2651-44f3-925f-60de361d36bd`
- Started: `2026-07-13T07:11:20Z`
- Completed: `2026-07-13T08:57:21Z`
- Stop reason: `quota_reserve_reached`
- Scheduler telemetry job: `Daily catalog sourcing`
- Scheduler command: `integrations/run_daily_sourcing_discovery.py`
- Scheduler window: `2026-07-13T07:10:36Z` to `2026-07-13T08:47:12Z`
- CloudWatch log stream:
  `scheduled/mbop-scheduler/f8ef2f5d3ea1417ea394d5718109b62c`

Baseline:

- `docs/ebay_browse_call_efficiency_audit_2026-07-12.md`
- Baseline run: `97224694-8db6-43fe-bbc5-ec49c5d7ba82`

## Executive Summary

The optimization did **not** run in production as implemented. CloudWatch logs
confirm the scheduler still used the pre-optimization alias fan-out search path:
the run logged `2,287` eBay search lines for `1,193` searched ASINs, and the
first ASINs used three variants such as:

```text
Wolfenstein II The New Colossus PlayStation 4 PlayStation 4
wolfenstein ii the new colossus PlayStation 4
wolfenstein ii the new colossus ps4
```

Browse throughput improved materially, but this was not because the intended
one-query/category-filter/detail-diagnostics implementation was active. The
production run also did not persist the new `raw_summary_json.ebay_search`
diagnostics that were added for this validation. Detail-call reasons and
per-detail outcomes were missing from the completed run record.

Observed Browse usage did decrease by ASIN:

- Baseline app-counted usage: `1,498` calls / `248` ASINs = `6.04` calls/ASIN.
- Latest app-counted usage: `5,000` calls / `1,193` ASINs = `4.19` calls/ASIN.
- Latest external eBay Analytics usage: `4,140` calls / `1,193` ASINs =
  `3.47` calls/ASIN.

Sourcing quality improved in raw actionable volume: the latest run produced
`210` batch-qualifying opportunities versus `1` in the audited baseline. That is
a large improvement, but it is not a clean recall/precision proof because the
run still admitted non-video-game categories into stored candidates.

The most important finding: the production scheduler appears to be running an
older scheduler image or task revision. The Video Games category filter was not
fully active in the production path that ran. Stored candidate payloads included
rows from
Postcards, Collectible Ads, Video Game Merchandise, Manuals, Posters, Magnets,
Controllers, Strategy Guides, and other non-software categories. Candidate
category distribution showed `7,013` rows in category `139973 Video Games` and
`2,006` rows outside category `139973`.

What is now consuming the most Browse quota: discovery item-detail calls remain
the largest app-counted consumer. CloudWatch logged `2,287` search calls; with
`5,000` app-counted Browse calls, that implies `2,713` app-counted detail calls.
The post-run availability refresh then checked `150` unique eBay items.

Recommendation: **NEEDS ANOTHER OPTIMIZATION PASS**.

## Baseline Comparison

Two after values are shown where they differ:

- App-counted calls: `sourcing_runs.api_call_count`.
- Analytics calls: eBay Developer Analytics quota delta.

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Browse calls, app-counted | 1,498 | 5,000 | +3,502 |
| Browse calls, Analytics delta | ~1,500 | 4,140 | +2,640 |
| Search calls | 666 inferred | 2,287 CloudWatch | +1,621 |
| Detail calls | 832 inferred | 2,713 app-inferred | +1,881 |
| Calls / ASIN, app-counted | 6.04 | 4.19 | -1.85 (-30.6%) |
| Calls / ASIN, Analytics delta | ~6.05 | 3.47 | -2.58 (-42.6%) |
| Search calls / ASIN | 2.69 | 1.92 | -0.77 (-28.8%) |
| Detail calls / ASIN | 3.35 | 2.27 app-inferred | -1.08 (-32.1%) |
| ASINs searched | 248 | 1,193 | +945 |
| Search results returned | Not persisted | Not persisted | Unknown |
| Candidates after summary filtering | 2,009 stored | 9,033 stored | +7,024 |
| Candidates sent to detail | Not persisted | Not persisted | Unknown |
| Batch-qualifying opportunities | 1 | 210 | +209 |
| Batch-qualifying opportunities / 1,000 Analytics calls | 0.67 | 50.72 | +50.05 |

Notes:

- The latest run began with Browse quota at `0 / 5,000` used and ended with
  `4,140 / 5,000` used, leaving `860`.
- The latest run nevertheless recorded `api_call_count = 5,000` and stopped as
  `quota_reserve_reached`. That means app-counted quota and eBay Analytics quota
  diverged by `860` calls.
- If the Analytics delta is used with the CloudWatch search-call count, inferred
  detail calls are `1,853`, or `1.55` detail calls/ASIN. This conflicts with the
  app-counted inferred detail total of `2,713`, so exact detail totals still need
  the missing instrumentation.
- The run-specific cycle item allocation summed to `4,815` Browse calls across
  the `1,200` seed rows loaded for the run, which also differs from both the app
  run total and Analytics total. Treat the run-level Analytics delta as the best
  external quota measurement for this validation.

## Search Query Analysis

Metrics from the latest run:

| Search Metric | Value |
| --- | ---: |
| Seed rows loaded | 1,200 |
| ASINs searched | 1,193 |
| Retryable failed seed rows | 7 |
| CloudWatch search lines | 2,287 |
| CloudWatch search lines / searched ASIN | 1.92 |
| Stored candidates | 9,033 |
| Stored candidates / searched ASIN | 7.57 |
| ASINs with at least one CloudWatch search line | 1,194 |
| Unique ASINs with query text recoverable from eBay `_skw` URLs | 1,067 |
| ASINs with multiple recovered query strings | 343 |
| Average CloudWatch query length | 36.55 characters |
| Average recovered `_skw` query length | 34.66 characters |

One-query-per-ASIN is **confirmed not active** in this production run.
CloudWatch logged these query-variant counts by ASIN:

| Logged Queries For ASIN | ASIN Count |
| ---: | ---: |
| 1 | 276 |
| 2 | 748 |
| 3 | 165 |
| 4 | 5 |

The log stream also showed the old alias format with duplicated platform terms,
for example `Dragon Quest Builders PlayStation 4 PlayStation 4` and
`dragon quest builders ps4`.

Video Games category filtering is **not confirmed and appears not fully active**.

Candidate category sample:

| Category | Candidate Rows |
| --- | ---: |
| `139973 Video Games` | 7,013 |
| `165266 Other Collectible Ads` | 357 |
| `38583 Video Game Merchandise` | 274 |
| `182180 Toys to Life` | 115 |
| `182174 Manuals, Inserts & Box Art` | 99 |
| `3628 Modern (1970-Now)` | 89 |
| `41511 Posters & Prints` | 74 |
| `476 Refrigerator Magnets` | 73 |
| `117042 Controllers & Attachments` | 73 |
| `60339 2000-Now` | 49 |

Stored candidate rows outside `139973`: `2,006` (`22.2%` of stored candidates).

Search limit `200` is not confirmed. The metric was absent from
`raw_summary_json.ebay_search`, CloudWatch did not log request parameters, and
eBay URL payloads do not preserve the request limit.

Approved suffix usage is partially observed but not validated end-to-end.
Recovered `_skw` strings included approved platform terms such as `Switch`,
`Wii`, `Wii U`, `wiiu`, `3DS`, `PlayStation 2`, `PS2`, `PlayStation 3`, `PS3`,
`PlayStation 4`, `PS4`, `PlayStation 5`, `PS5`, `PlayStation Vita`, `Xbox 360`,
`X360`, `XB360`, `Xbox One`, `XB1`, `Series X`, and `Series S`. Because multiple
queries were recovered for many ASINs, this does not prove the optimized
one-query path ran.

Weak query examples from recovered `_skw` strings:

| ASIN | Query | Example Stored Candidate |
| --- | --- | --- |
| `B004M8M30G` | `cars ps3` | Tamiya Spray Paints for RC car bodies |
| `B000Q4SREG` | `mysims Wii` | Barbie dollhouse miniature DVD/Blu-Ray/Wii item |
| `B0056C2LIG` | `Wii Play` | Ringling Bros Circus Wii listing |
| `B000QL0T36` | `dirt ps3` | Dirt stickers/posters/ads |
| `B002EZH804` | `avatar ps3` | Modded avatars / promo art / lenticular cards |

DS/original Xbox/GameCube skip behavior is not confirmed because
`skipped_unsourced_seed_count` was absent from the run summary. The CloudWatch
search lines did not provide enough context to prove those systems were skipped.

## Detail Call Analysis

The latest run did not persist detail-call diagnostics. CloudWatch does allow an
app-counted inference:

```text
5,000 app-counted Browse calls - 2,287 CloudWatch search lines = 2,713 inferred detail calls
```

This is still not a substitute for detail-call diagnostics because it does not
identify which item details were called, why they were called, or whether they
changed the sourcing decision.

| Detail Reason | Calls |
| --- | ---: |
| `shipping_missing` | Not persisted |
| `platform_confirmation_needed` | Not persisted |
| `region_confirmation_needed` | Not persisted |
| `game_name_confirmation_needed` | Not persisted |
| `edition_confirmation_needed` | Not persisted |
| `type_or_format_confirmation_needed` | Not persisted |
| `description_needed` | Not persisted |
| `quantity_confirmation_needed` | Not persisted |
| `combined_shipping_evaluation_needed` | Not persisted |
| `other` | Not persisted |

The following expected counters were all absent or zero:

- `search_call_count`
- `detail_call_count`
- `retry_http_attempt_count`
- `rate_limited_http_attempt_count`
- `detail_reason_counts`
- `detail_reason_breakdown`
- `detail_call_records`
- `detail_calls_missing_data_resolved_count`
- `detail_calls_changed_decision_count`

Because of that, requested fields, returned fields, still-missing fields,
decision changes, retained/rejected detail outcomes, and useful/unnecessary
classifications cannot be measured from this run.

## Shipping Analysis

Stored candidates with non-null `shipping_cost`: `9,033 / 9,033`.

That only proves final stored candidates had shipping. It does not prove how many
Browse item-detail calls were spent to obtain shipping because the run did not
persist `detail_call_count`, `shipping_missing`, or detail outcome records.

Post-run availability refresh did consume Browse item detail calls:

| Availability Refresh Metric | Value |
| --- | ---: |
| Opportunities checked | 250 |
| Unique eBay items checked | 150 |
| Still active | 248 |
| No longer available | 2 |
| Errors | 0 |

Estimated Browse calls spent only by availability refresh: `150`.

Estimated app-counted Browse detail calls during discovery: `2,713`. Most of
those are probably shipping enrichment because this old path detail-enriched
missing-shipping results, but the exact shipping-only count is **not measurable**
without the missing detail reasons.

## Profitability Filter

The latest run's batch funnel recorded:

| Profitability Metric | Value |
| --- | ---: |
| Scored opportunities | 9,033 |
| Profitability rejects | 4,706 |
| Hard-blocked opportunities | 4,039 |
| Review/watch | 44 |
| Valid open opportunities | 210 |

The requested pre-detail split was not persisted:

- regular listing above landed-cost cap
- Best Offer impossible even assuming free shipping
- auction already above max bid

Estimated Browse calls saved by the new pre-detail profitability filter:
**not measurable from this run**.

## Summary Filtering

The latest run did not persist summary-filter reason counters. The run-level
`summary_filtered_count` and `summary_profitability_filtered_count` were absent
or zero in `raw_summary_json.ebay_search`.

Measured downstream scoring categories:

| Downstream Classification | Rows |
| --- | ---: |
| Hard-blocked opportunities | 4,039 |
| Profitability rejects | 4,706 |
| Rejected opportunities | 8,745 |
| Review/watch | 44 |
| Valid open opportunities | 210 |

Requested pre-detail reason split:

| Reason | Count |
| --- | ---: |
| category | Not persisted |
| accessory | Not persisted |
| digital/service | Not persisted |
| incomplete product | Not persisted |
| platform mismatch | Not persisted |
| edition/version mismatch | Not persisted |
| sequel/year mismatch | Not persisted |
| region | Not persisted |
| seller rules | Not persisted |
| profitability | Not persisted |
| duplicate | Not persisted |
| other | Not persisted |

The category payload analysis shows summary filtering was not sufficient:
`2,006` stored candidates were outside eBay category `139973`.

## Detail Call Effectiveness

Detail usefulness cannot be classified because no detail records were persisted.

| Classification | Count | Percent |
| --- | ---: | ---: |
| Useful | Not persisted | Not persisted |
| Unnecessary | Not persisted | Not persisted |

Useful detail effects that were expected but absent from the run data:

- profitability changed
- shipping changed
- match decision changed
- opportunity type changed

## Opportunity Quality

The latest run produced many more actionable opportunities than the baseline,
but the raw candidate set also contained non-video-game categories, so precision
needs operator review before declaring success.

Opportunity type comparison by scored rows:

| Opportunity Type | Before Rows | After Rows | Delta |
| --- | ---: | ---: | ---: |
| Buy Now | 7 | 106 | +99 |
| Best Offer | 32 | 376 | +344 |
| Auction | 4 | 9 | +5 |
| Multi-unit | 0 | 12 | +12 |
| Watch | 11 | 44 | +33 |
| No profitable source found | 1,955 | 8,486 | +6,531 |

Workflow/status comparison:

| Status | Before Rows | After Rows | Delta |
| --- | ---: | ---: | ---: |
| Open | 0 | 177 | +177 |
| Watching | 17 | 6 | -11 |
| Purchased pending match | 3 | 9 | +6 |
| Dismissed | 86 | 77 | -9 |
| Rejected | 1,903 | 8,764 | +6,861 |

Actionable batch count:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Batch-qualifying opportunities | 1 | 210 | +209 |
| Batch-qualifying opportunities / searched ASIN | 0.004 | 0.176 | +0.172 |
| Batch-qualifying opportunities / 1,000 Analytics calls | 0.67 | 50.72 | +50.05 |

Recall appears improved by volume, but precision is not proven because of the
non-video-game category leakage and missing detail/reason diagnostics.

## Remaining Optimization Opportunities

| Rank | Opportunity | Expected Browse Savings | Complexity | Sourcing Risk |
| ---: | --- | --- | --- | --- |
| 1 | Deploy and point `mbop-sourcing-catalog` at the scheduler image/task revision containing the optimization. | The intended one-query/category-filter/detail-lazy behavior did not run; expected savings should be revalidated after deployment. | Medium | Low |
| 2 | Enforce eBay category `139973` in the production search path and hard-reject non-`139973` summaries before detail. | Up to `2,006` stored candidates from this run were outside category; savings depend on when rejected. | Low to Medium | Low |
| 3 | Fix app-counted Browse budget reconciliation against eBay Analytics. | Prevents stopping with `860` calls still available. Potentially +200 to +250 more ASINs/day at observed actual usage. | Medium | Low |
| 4 | Persist search/detail/retry/detail-reason counters at final run completion. | No direct savings, but required to target detail spend. | Low | Low |
| 5 | Confirm one-query-per-ASIN in production and remove any remaining alias fan-out from the scheduler image. | This run logged `2,287` searches. At one query per `1,193` searched ASINs, search calls would have been about `1,193`, saving roughly `1,094` calls before any detail savings. | Medium | Medium |
| 6 | Keep availability refresh reserve separate from discovery budget. | Availability refresh used `150` item detail checks after discovery. | Low | Low |
| 7 | Add or enforce pre-detail category/accessory/manual/poster filters before shipping detail. | High if current non-game rows are detail-enriched before rejection. | Medium | Low to Medium |

## Recommendation

**NEEDS ANOTHER OPTIMIZATION PASS**

Reasons:

1. The latest production run did not persist the new validation diagnostics under
   `sourcing_runs.raw_summary_json.ebay_search`.
2. CloudWatch proves one-query-per-ASIN was not active; the run still used old
   alias fan-out with up to four queries per ASIN.
3. Video Games category filtering was not fully active in the production path;
   `2,006` stored candidates were outside category `139973`.
4. App-counted Browse usage diverged from eBay Analytics by `860` calls.
5. Detail-reason effectiveness cannot be measured from the run.
6. Throughput and actionable opportunity volume improved, but quality cannot be
   declared stable until category leakage and diagnostics are corrected.

Recommended next step: deploy the scheduler image/task revision that contains
the optimization implementation, verify the `mbop-sourcing-catalog` schedule is
using that revision, then run one more daily cycle after reset and re-run this
validation. This report used Supabase `sourcing_runs`,
`sourcing_coverage_cycles`, `sourcing_opportunity_batches`,
`sourcing_ebay_candidates`, `sourcing_opportunities`, scheduler telemetry
tables, and CloudWatch log stream
`scheduled/mbop-scheduler/f8ef2f5d3ea1417ea394d5718109b62c`. No production
behavior was changed.
