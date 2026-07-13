# eBay Browse Call Efficiency Audit

Date: 2026-07-12

Scope: read-only audit of why MBOP sourcing is consuming roughly 4-6 eBay Browse calls per searched ASIN. No production sourcing behavior was changed.

`CODEX_PROMPTING_GUIDE_v3.md` was not present in this repository.

## Executive Summary

The high calls-per-ASIN are real. In the monitored production ECS run `97224694-8db6-43fe-bbc5-ec49c5d7ba82`, MBOP searched 248 ASINs and stored `api_call_count = 1498`, or 6.04 counted Browse calls per searched ASIN. eBay Developer Analytics started at 3,500/5,000 used with 1,500 remaining and ended at 0 remaining, so the external quota burn matches the application metric closely.

The main driver is not ASIN re-searching inside the coverage cycle. The run generated 666 eBay search-query variants for the 248 searched ASINs, averaging 2.69 search calls per ASIN. The larger driver is item-detail shipping enrichment: the remaining inferred 832 counted Browse calls were detail calls made for search results whose item summaries did not include buyer-ZIP shipping. That is 3.35 detail calls per ASIN and 55.5% of counted calls.

Duplicate candidate listings across aliases were present but small in this run: cycle item candidate totals summed to 2,015 while the run stored 2,009 unique candidate rows, a difference of 6 rows. Alias fan-out still matters, but shipping-detail enrichment is the larger quota sink.

The run stopped with `ebay_rate_limited` after eBay returned persistent 429s on the 249th ASIN. The retry helper attempted the failed request 6 times, but the current `api_call_count` does not count retry attempts or the final failed request. That makes the stored metric useful for business-level budget accounting, but incomplete as an HTTP-attempt diagnostic.

## Monitored Run Metrics

Run:

- `sourcing_run_id`: `97224694-8db6-43fe-bbc5-ec49c5d7ba82`
- ECS task: `scheduled/mbop-scheduler/f084634e056e4e8bb9f0745a605046d2`
- Started: `2026-07-12 23:40:19 UTC`
- Completed: `2026-07-13 00:05:54 UTC`
- Status: `completed`
- Stop reason: `ebay_rate_limited`
- Starting Browse quota: 3,500 used / 5,000 limit / 1,500 remaining
- Ending Browse quota remaining: 0
- App-counted Browse calls: 1,498
- ASINs searched: 248
- Calls per searched ASIN: 6.04
- Candidate rows stored: 2,009
- Opportunity rows scored: 2,009
- Seeds with stored candidates: 222
- Searched cycle bucket: 248 from `1_recently_sold`
- Remaining cycle items: 1,331, including 2 retryable failed rows

Opportunity status split for this run:

| Status | Type | Rows |
| --- | --- | ---: |
| rejected | `no_profitable_source_found` | 1,870 |
| rejected | `best_offer` | 22 |
| rejected | `watch` | 11 |
| watching | `no_profitable_source_found` | 11 |
| watching | `best_offer` | 6 |
| dismissed | `buy_now` | 7 |
| dismissed | `best_offer` | 4 |
| dismissed | `auction` | 1 |
| dismissed | `no_profitable_source_found` | 74 |
| purchased_pending_match | `auction` | 3 |

The final log line `Opportunities found: 1` is the selected batch count, not the total scoring output. The run wrote and scored 2,009 opportunity rows.

## Search, Detail, and Retry Breakdown

Measured query generation from the exact `search_queries_for_seed` function against the 248 searched seeds:

| Query variants per ASIN | ASIN count |
| ---: | ---: |
| 1 | 30 |
| 2 | 22 |
| 3 | 192 |
| 4 | 4 |

Totals:

- Search-query calls: 666
- Average search-query calls per ASIN: 2.69
- App-counted total calls: 1,498
- Inferred item-detail enrichment calls: 832
- Average detail calls per ASIN: 3.35
- Stored detail-enriched candidate rows: 365
- Stored candidates missing shipping: 0

The detail-call count is inferred as:

```text
1498 app-counted Browse calls - 666 search-query variants = 832 detail calls
```

The stored `raw_ebay_json ? 'rawSearchSummary'` count is only 365 because detail calls can happen before candidate filtering and run-level dedupe. This means a detail call can be spent for a listing that later does not become a stored unique candidate row.

Retry observations:

- `integrations/ebay_sourcing_search.py` uses `MAX_HTTP_RETRIES = 6`.
- On the final failed request, CloudWatch showed 5 backoff sleeps and then `eBay Browse returned 429 after 6 attempts`.
- The current metric increments once after a successful search wrapper call and once per detail enrichment completion. It does not increment per HTTP retry attempt.
- The final persistent 429 request did not increment `api_call_count`.
- eBay quota moved from 1,500 remaining to 0 remaining, while MBOP stored 1,498 calls. Treat that 2-call difference as measurement noise from failed/retried requests and quota endpoint timing.

## Static Call-Site Inventory

### `integrations/ebay_sourcing_search.py`

Primary sourcing discovery consumer.

Calls:

- OAuth refresh token: `POST /identity/v1/oauth2/token`
- Browse search: `GET /buy/browse/v1/item_summary/search`
- Browse item detail: `GET /buy/browse/v1/item/{item_id}`

Behavior:

- Builds multiple keyword queries per ASIN from Amazon title plus platform aliases.
- Uses buyer contextual ZIP header.
- Search filters: new condition, US/CA location, US delivery, fixed price or auction.
- Calls item detail when a search summary lacks shipping cost.
- Upserts candidates with `on_conflict="ebay_item_id"`.
- Dedupe in memory by `ebay_item_id` inside one script invocation.
- No persistent search-query cache.
- No persistent item-detail cache.
- No per-query candidate count metric.
- No explicit search-vs-detail-vs-retry metric.

### `integrations/run_daily_catalog_sourcing.py`

Unified daily coverage-cycle runner.

Calls:

- Reads eBay Developer Analytics quota through `ebay_api_limits.fetch_browse_quota()`.
- Executes `ebay_sourcing_search.py` in chunks.
- Scores candidates after each chunk.
- Writes run, batch, quota, and coverage-cycle metrics.

Behavior:

- Uses live remaining `buy.browse` quota as the default budget.
- Fetches pending/retryable ASINs from one durable coverage cycle.
- Does not re-search already searched ASINs in the active cycle.
- Per-cycle-item `browse_calls_used` is rounded per chunk, which lost fidelity in this run: run `api_call_count` was 1,498, while cycle-item `browse_calls_used` summed to 1,438.

### `integrations/run_sourcing_workflow.py`

Legacy/progressive on-demand runner.

Calls:

- Also executes `ebay_sourcing_search.py`.
- Also reads Browse quota through `ebay_api_limits.py`.

Behavior:

- Still useful for older recent-sales/full-listings workflows.
- The current daily and UI flow uses `run_daily_catalog_sourcing.py`.

### `integrations/run_daily_sourcing_discovery.py`

Compatibility wrapper.

Calls:

- Executes `integrations/run_daily_catalog_sourcing.py`.

### `integrations/refresh_sourcing_listing_availability.py`

Separate availability refresh consumer in the `sourcing-catalog` scheduler group.

Calls:

- OAuth refresh token.
- Browse item detail: `GET /buy/browse/v1/item/{item_id}`

Behavior:

- Checks open/watch/ROI-snoozed opportunities.
- Has in-process per-run dedupe by `ebay_item_id`.
- No persisted cache across scheduler runs.
- Default scheduler invocation checks up to 250 opportunities.

### `integrations/ebay_sync_buyer_purchases.py`

Purchase ingestion enrichment consumer, separate from sourcing discovery.

Calls:

- Browse legacy detail: `GET /buy/browse/v1/item/get_item_by_legacy_id`

Behavior:

- Used only when existing system and title-derived system are missing.
- Has in-process `ITEM_ASPECT_CACHE`.
- Core purchase ingestion uses eBay Trading API and does not depend on Browse.

### `integrations/ebay_api_limits.py`

Quota visibility, not Browse sourcing itself.

Calls:

- OAuth client credentials token.
- Developer Analytics: `GET /developer/analytics/v1_beta/rate_limit/`

Behavior:

- Reads `buy.browse` limit/count/remaining/reset.
- Does not consume Browse quota itself.

## Alias Effectiveness Findings

The current alias strategy searches the original cleaned Amazon title and platform-specific aliases. It is intentionally platform-aware, which is correct for video games. The observed distribution is heavily concentrated at 3 queries per ASIN:

- 192 of 248 searched ASINs had 3 variants.
- Only 30 had 1 variant.
- Only 4 had 4 variants.

The query variants often include redundant platform terms:

```text
Trivial Pursuit Playstation 3 PlayStation 3
trivial pursuit PlayStation 3
trivial pursuit ps3
```

This redundancy is useful for recall, but it is not adaptive. MBOP runs every alias even when the first query already returns enough candidates with shipping. Because exact per-query candidate yield is not persisted, the current data cannot prove which aliases are low-value at scale without log parsing or a diagnostic metric.

## Detail-Call Usefulness Findings

Detail enrichment is currently the largest quota consumer in discovery.

The good news: stored candidates had complete shipping in this run.

- Stored candidate rows: 2,009
- Stored rows with `shipping_cost is null`: 0
- Stored rows with detail payload marker: 365

The bad news: the app inferred 832 detail calls, but only 365 stored unique candidates retained detail-enriched payloads. The missing difference is likely a mix of:

- detail calls for candidates later filtered out by `is_allowed_candidate`
- detail calls for duplicate listings already returned by another query
- detail calls for results that are not persisted because another row for the same `ebay_item_id` already won

This is the best optimization target because it can reduce calls without sacrificing ASIN coverage.

## Duplicate and Caching Findings

Run-level duplicate findings:

- Candidate hits summed from coverage-cycle items: 2,015
- Unique stored candidate rows: 2,009
- Observed duplicate hit difference: 6

Current dedupe/caching:

- `ebay_sourcing_search.py` dedupes by `ebay_item_id` only after detail enrichment and candidate mapping.
- Candidate upsert is by `ebay_item_id`, not by `(run_id, seed_id, ebay_item_id)`.
- There is no persistent cache for query results.
- There is no persistent cache for item-detail shipping enrichment.
- `refresh_sourcing_listing_availability.py` dedupes item detail checks in memory for one run.
- `ebay_sync_buyer_purchases.py` caches legacy Browse item details in memory for one process.

The small duplicate count means alias overlap among stored candidates was not the main cause in this particular run. However, deduping before detail enrichment could still save detail calls when the same listing appears under multiple aliases or when a candidate is filtered after detail.

## Retry and Overlap Findings

The coverage-cycle design is working: it did not repeatedly search the same ASIN within the active cycle. The run searched the first 248 `1_recently_sold` ASINs and left the rest pending or retryable.

The retry system is operationally safe but diagnostically blurry:

- Backoff exists for 429.
- Persistent 429 stops the run as `ebay_rate_limited`.
- Retry attempts are not counted separately.
- Failed final calls are not counted in `api_call_count`.
- Search/detail endpoint labels are not persisted.

The `sourcing-catalog` scheduler group also runs availability refresh after daily catalog sourcing. If discovery spends the full remaining Browse budget, availability refresh and buyer purchase Browse enrichments may be starved until the next reset. This is documented behavior, but the current default reserve is 0.

## Metrics Gaps

Add diagnostic-only fields or logs before changing behavior:

- `search_call_count`
- `detail_call_count`
- `retry_http_attempt_count`
- `rate_limited_http_attempt_count`
- `shipping_missing_summary_count`
- `detail_calls_filtered_out_count`
- `detail_calls_duplicate_item_count`
- `query_variant_count`
- per-query result count and stored candidate count
- per-query "had enough candidates before next alias" signal
- exact per-cycle-item Browse calls, not rounded chunk allocation

The highest-value single metric is a per-chunk JSON summary with search calls, detail calls, and query variants. It would explain quota burn immediately without changing sourcing behavior.

## Prioritized Optimizations

### 1. Make detail enrichment lazy and bounded

Current behavior enriches every search result missing shipping before scoring and before final dedupe/filtering.

Recommended behavior:

- First map/filter/dedupe search summaries.
- Only detail-enrich candidates that remain plausible after cheap filters.
- Cap detail enrichment per ASIN, for example top 3-5 cheapest plausible results.
- Leave unknown-shipping candidates visible but not profit-scored, matching current business rules.

Estimated savings from this run:

- Detail calls were 832 of 1,498 counted calls.
- If bounded detail enrichment cuts detail calls by 50%, total calls fall to about 1,082, or 4.36 calls/ASIN.
- If it cuts detail calls by 70%, total calls fall to about 916, or 3.69 calls/ASIN.
- Savings: about 28-39% of daily Browse quota in similar runs.

### 2. Add adaptive alias stopping

Current behavior runs all generated aliases for each ASIN.

Recommended behavior:

- Run the strongest canonical query first.
- If it returns enough unique plausible candidates with shipping, skip short aliases.
- Continue aliases when results are sparse, shipping is missing, or platform confidence is low.

Estimated savings from this run:

- Search variants were 666 calls.
- Reducing search variants by 25% saves about 167 calls.
- Reducing search variants by 40% saves about 266 calls.
- Total calls would fall from 6.04/ASIN to roughly 4.97-5.37/ASIN if detail behavior is unchanged.

### 3. Add a short-lived item-detail cache and dedupe before detail

Current behavior can spend detail calls before knowing whether a listing will be kept.

Recommended behavior:

- Maintain a run-level `seen_detail_item_ids` cache before calling item detail.
- Skip detail for duplicate `itemId` already returned in the same run/chunk.
- Optionally persist a short-lived candidate detail cache keyed by `ebay_item_id` and ZIP/context.
- Reuse existing `sourcing_ebay_candidates.shipping_cost` when a recent row exists and listing is still active enough for advisory scoring.

Estimated savings from this run:

- Stored duplicate candidates were small, about 6 rows.
- The bigger potential is skipping details for filtered-out rows; exact savings require new metrics.
- Conservative expected savings: 2-10% alone, more when combined with lazy detail enrichment.

## Throughput Estimates

Using the monitored run:

- Current observed rate: 6.04 calls/ASIN.
- Full 5,000-call day at this rate: about 827 ASINs/day.
- Current active cycle size: 1,579 ASINs.
- Full cycle at current rate: about 9,535 calls, or 1.9 full 5,000-call days.

With optimizations:

| Scenario | Calls/ASIN | ASINs per 5,000 calls | 1,579-ASIN cycle calls |
| --- | ---: | ---: | ---: |
| Current observed | 6.04 | 827 | 9,537 |
| Detail calls cut 50% | 4.36 | 1,147 | 6,885 |
| Detail calls cut 70% | 3.69 | 1,355 | 5,826 |
| Detail cut 50% + search aliases cut 25% | 3.69 | 1,355 | 5,826 |
| Detail cut 70% + search aliases cut 25% | 3.02 | 1,656 | 4,769 |

These are estimates from one production run. They should be validated after adding search/detail/retry counters.

## Is a Quota Increase Justified?

Yes, but not as the first fix.

A quota increase is justified because MBOP has a legitimate daily coverage-cycle use case, and even a well-optimized video game sourcing scan can consume thousands of Browse calls. However, the current 6.04 calls/ASIN includes avoidable detail enrichment spend and lacks diagnostic counters. Asking eBay for more quota before reducing detail calls would buy capacity but preserve the inefficient pattern.

Recommended position:

1. Implement diagnostic counters.
2. Implement lazy/bounded detail enrichment.
3. Implement adaptive alias stopping.
4. Run at least two production cycles and compare calls/ASIN.
5. Then request quota increase with measured before/after evidence and a clear operational need.

## Implementation Sequence

1. Add diagnostic-only counters to `ebay_sourcing_search.py` and persist them in `sourcing_runs.raw_summary_json.ebay_search`.
2. Fix per-cycle-item call allocation to preserve exact chunk total, or store exact calls only at run/chunk level and stop treating rounded item sums as authoritative.
3. Add pre-detail cheap filtering and run-level detail dedupe.
4. Add a bounded detail policy per ASIN.
5. Add adaptive alias stopping behind a feature flag or CLI option.
6. Re-run one daily coverage cycle and compare:
   - calls/ASIN
   - search calls/ASIN
   - detail calls/ASIN
   - candidates/ASIN
   - open/watch/purchased-pending opportunity yield
7. Revisit eBay quota increase request with measured optimized throughput.

## Bottom Line

MBOP is high because each ASIN gets about 2.69 search queries and about 3.35 item-detail shipping calls. The detail calls are the larger issue. The coverage-cycle queue is preventing same-cycle ASIN repeats, and duplicate stored candidates were minimal in the measured run. The top optimization is to stop detail-enriching every missing-shipping search result before cheap filtering, dedupe, and prioritization.
