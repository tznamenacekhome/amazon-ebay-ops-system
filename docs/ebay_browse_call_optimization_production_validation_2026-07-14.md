# eBay Browse Call Optimization Production Validation - 2026-07-14

Scope: read-only validation of the first production run that actually used the
deployed eBay Browse optimization image. No code, schema, settings, sourcing
behavior, or production data were changed during this investigation.

Important timing note: at validation time, Supabase did not contain a completed
`daily_catalog_sourcing` run after the `2026-07-14T07:00:00Z` Browse quota
reset. The latest completed optimized production run was the manual
leftover-quota run below. It completed the active coverage cycle before that
reset and is still the first run with the new instrumentation and optimized
search path.

Primary run analyzed:

- `sourcing_run_id`: `5ec1f3b0-20f3-4d65-a0a9-09efb19e5daa`
- Run type: `daily_catalog_sourcing`
- Coverage cycle: `dd2f604c-2651-44f3-925f-60de361d36bd`
- Started: `2026-07-14T00:52:22.929912Z`
- Completed: `2026-07-14T01:01:35.889854Z`
- Stop reason: `cycle_completed`
- ECS task:
  `arn:aws:ecs:us-west-2:297464765814:task/mbop-cluster1/97f3b7c91bfb48dbac82a439be6d41fc`
- ECS task definition: `mbop-scheduler-task:21`
- Scheduler image:
  `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:bc42711a71e9f13ed95ad5f35fbf8181d117f0ac404730ad3ddc39ff42986f2d`
- CloudWatch log stream:
  `scheduled/mbop-scheduler/97f3b7c91bfb48dbac82a439be6d41fc`

Baseline:

- `docs/ebay_browse_call_efficiency_audit_2026-07-12.md`
- Baseline run: `97224694-8db6-43fe-bbc5-ec49c5d7ba82`

## 1. Executive Summary

The optimization worked for the behaviors it targeted:

- one platform-aware query per supported ASIN was active
- old alias fan-out was gone
- eBay Video Games category `139973` was active for stored candidates
- `--max-results-per-asin 200` was active
- summary filtering ran before detail enrichment
- detail reasons and outcomes were persisted under
  `sourcing_runs.raw_summary_json.ebay_search`

Browse usage decreased materially:

- app-counted calls per ASIN fell from `6.04` to `4.04`
- search calls per ASIN fell from `2.69` to `0.99`
- detail calls per ASIN fell from `3.35` inferred to `3.05`

Sourcing quality appears better, with caveats:

- stored candidates in the optimized run were `350 / 350` in category `139973`
- the run produced `47` open batch-qualifying opportunities from `143` searched
  ASINs
- the active coverage cycle completed with zero remaining ASINs
- the sample is not perfectly comparable to the baseline because it searched
  the final leftover ASINs in the cycle, mostly catalog remaining rows

What is now consuming the most Browse quota: item detail calls. Detail calls
were `436 / 578` app-counted Browse calls (`75.4%`). The dominant reason was
`game_name_confirmation_needed`, followed by `shipping_missing`.

Recommendation: **NEEDS ANOTHER OPTIMIZATION PASS**. The deployed optimization
is production-safe and should remain active, but detail calls are now the clear
remaining quota sink.

## 2. Baseline Comparison

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Browse calls | 1,498 | 578 | -920 (-61.4%) |
| Search calls | 666 inferred | 142 | -524 (-78.7%) |
| Detail calls | 832 inferred | 436 | -396 (-47.6%) |
| Calls / ASIN | 6.04 | 4.04 | -2.00 (-33.1%) |
| Search calls / ASIN | 2.69 | 0.99 | -1.70 (-63.0%) |
| Detail calls / ASIN | 3.35 | 3.05 | -0.30 (-9.0%) |
| ASINs searched | 248 | 143 | -105 |
| Search results returned | Not persisted | 4,900 | New metric |
| Candidates after summary filtering | 2,009 stored | 350 stored | -1,659 |
| Candidates sent to detail | Not persisted | 437 eligible / 436 HTTP calls | New metric |
| Opportunities produced | 1 batch-qualifying | 47 batch-qualifying | +46 |
| Opportunities / 1,000 Browse calls | 0.67 | 81.31 | +80.64 |

Run-level quota snapshots:

| Quota Metric | Value |
| --- | ---: |
| Starting Browse quota remaining | 710 |
| Ending Browse quota remaining | 130 |
| App-counted Browse calls | 578 |
| eBay Analytics delta | 580 |
| Reconciliation difference | 2 |

The app counter and eBay Analytics were effectively reconciled in this run. The
previous `860`-call divergence did not repeat.

## 3. Search Query Analysis

| Search Metric | Value |
| --- | ---: |
| Seed rows loaded | 143 |
| Supported ASINs searched | 142 |
| Unsourced seeds skipped | 1 |
| Search calls | 142 |
| Query variants | 142 |
| Search calls / supported searched ASIN | 1.00 |
| Search calls / loaded seed | 0.99 |
| Search results returned | 4,900 |
| Search results / search call | 34.51 |
| Stored candidates | 350 |
| Stored candidates / searched ASIN | 2.45 |
| Unique query strings observed in stored detail/candidate records | 76 |
| Average observed query length | 40.03 characters |

Confirmation:

- One-query-per-supported-ASIN: confirmed by `142` query variants for `142`
  supported searched ASINs.
- Original Xbox not searched: confirmed. One run seed had inferred system
  `Xbox` (`B0CFTFG12B`) and the run recorded `skipped_unsourced_seed_count = 1`.
- DS not searched: no DS seed appeared in this run.
- GameCube not searched: no GameCube seed appeared in this run.
- Wii U `(Wii U,wiiu)` suffix: not exercised by this run because no Wii U seed
  appeared.
- Approved platform suffixes: confirmed in CloudWatch examples such as
  `(PlayStation 4,PS4)`, `(Xbox One,XB1)`,
  `(Xbox Series X,Series X,Series S)`, `(Xbox 360,X360,XB360,Xbox360)`,
  `Switch`, `3DS`, `Wii`, and `PC`.
- Video Games category filter: confirmed for stored candidates;
  `350 / 350` stored candidates had primary category `139973 Video Games`.
- Search limit: confirmed in CloudWatch command lines:
  `--max-results-per-asin 200`.

CloudWatch command examples:

```text
python integrations/ebay_sourcing_search.py --run-id 5ec1f3b0-20f3-4d65-a0a9-09efb19e5daa --offset 0 --limit 50 --max-results-per-asin 200 --max-api-calls 710
python integrations/ebay_sourcing_search.py --run-id 5ec1f3b0-20f3-4d65-a0a9-09efb19e5daa --offset 50 --limit 50 --max-results-per-asin 200 --max-api-calls 501
python integrations/ebay_sourcing_search.py --run-id 5ec1f3b0-20f3-4d65-a0a9-09efb19e5daa --offset 100 --limit 43 --max-results-per-asin 200 --max-api-calls 360
```

Potential weak query examples:

| ASIN | Query | Note |
| --- | --- | --- |
| `B0C7SK37D4` | `avatar frontiers of pandora limited edition (Xbox Series X,Series X,Series S)` | Generic word `avatar`, but the full title keeps it usable. |
| `B0935PJSZX` | `skinfix triple lipid boost eye ... (Xbox 360,X360,XB360,Xbox360)` | Bad seed/title data; not a video game title even though it entered the catalog queue. |
| `B0009Z3HYW` | `gun (PlayStation 2,PS2)` | Very short game title; high risk of broad matches. |

The weak-query issue now appears driven more by upstream seed/title quality than
by the eBay query builder.

## 4. Detail Call Analysis

Unique Browse item-detail HTTP calls: `436`.

Detail records: `437`. One eligible detail was served from the run-level detail
cache (`duplicate_detail_calls_prevented_count = 1`), so records exceed HTTP
detail calls by one.

Detail reasons can overlap, so reason counts sum above unique detail calls.

| Detail Reason | Calls |
| --- | ---: |
| `shipping_missing` | 297 |
| `platform_confirmation_needed` | 19 |
| `region_confirmation_needed` | 0 |
| `game_name_confirmation_needed` | 437 |
| `edition_confirmation_needed` | 0 |
| `type_or_format_confirmation_needed` | 0 |
| `description_needed` | 0 |
| `quantity_confirmation_needed` | 0 |
| `combined_shipping_evaluation_needed` | 0 |
| `other` | 0 |

| Detail Reason | Requested Fields | Returned / Populated | Still Missing | Changed Decision | Retained | Rejected |
| --- | --- | --- | --- | ---: | ---: | ---: |
| `shipping_missing` | `shipping_cost`; often `Game Name`; sometimes `Platform` | `shipping_cost` populated 296/297; `Game Name` 294/297; `Platform` 11/11 | `Game Name` still missing on 2 | 297 | 238 | 59 |
| `platform_confirmation_needed` | `localizedAspects.Platform`, `Game Name`; sometimes `shipping_cost` | `Platform` 19/19; `Game Name` 19/19; shipping 11/11 | none | 19 | 7 | 12 |
| `game_name_confirmation_needed` | `localizedAspects.Game Name`; often shipping/platform too | `Game Name` 434/437; shipping 296; platform 19 | `Game Name` still missing on 2 | 329 | 350 | 87 |
| Other listed reasons | none in this run | none | none | 0 | 0 | 0 |

Effectiveness summary:

| Detail Outcome | Count | Percent |
| --- | ---: | ---: |
| Missing data resolved | 436 | 99.8% of detail records |
| Missing data not resolved | 1 | 0.2% |
| Changed sourcing decision/economics | 329 | 75.3% |
| No decision change | 108 | 24.7% |
| Candidate retained after detail | 350 | 80.1% |
| Candidate rejected after detail | 87 | 19.9% |

## 5. Shipping Analysis

| Shipping Metric | Value |
| --- | ---: |
| Stored candidates with shipping | 350 / 350 |
| Detail records with `shipping_missing` reason | 297 |
| Shipping retrieval successes | 296 |
| Shipping retrieval failures | 1 |
| Detail calls spent for shipping-related enrichment | up to 297 |

Estimated Browse calls spent only to obtain shipping: not exactly measurable
because every `shipping_missing` detail call in this run also carried
`game_name_confirmation_needed`. The safe upper bound is `297` calls. The lower
bound is `0` if Game Name confirmation alone would have forced the same calls.

Operationally, shipping enrichment worked: all stored candidates ended with a
non-null shipping cost.

## 6. Profitability Filter

| Profitability Metric | Value |
| --- | ---: |
| Search results returned | 4,900 |
| Summary profitability filtered before detail | 2,226 |
| Other summary/matching filtered before detail | 2,232 |
| Duplicate summary items skipped | 6 |
| Detail-eligible records | 437 |
| Stored candidates after detail/final filters | 350 |

Estimated Browse calls saved by the pre-detail profitability filter:
approximately `2,226` potential detail calls avoided in the best case. The
exact split between regular listings above cap, impossible Best Offers, and
auctions above max bid is not persisted yet.

## 7. Summary Filtering

The run persists total summary filtering, but not the requested detailed reason
split. Available totals:

| Summary Filter Bucket | Count |
| --- | ---: |
| Matching / category / seller / other non-economic summary filters | 2,232 |
| Profitability summary filters | 2,226 |
| Duplicate items skipped before persistence | 6 |

Requested reason split:

| Reason | Count |
| --- | ---: |
| category | Not persisted separately |
| accessory | Not persisted separately |
| digital/service | Not persisted separately |
| incomplete product | Not persisted separately |
| platform mismatch | Not persisted separately |
| edition/version mismatch | Not persisted separately |
| sequel/year mismatch | Not persisted separately |
| region | Not persisted separately |
| seller rules | Not persisted separately |
| profitability | 2,226 |
| duplicate | 6 |
| other | Included in 2,232 non-economic summary filters |

Evidence that summary filtering is working:

- only `350` of `4,900` search results became stored candidates
- all stored candidates were category `139973 Video Games`
- no stored opportunity had category/accessory/digital/platform/edition/region
  hard-block diagnostics; only two retained rows still lacked item-specific Game
  Name evidence after detail

## 8. Detail Call Effectiveness

Classification rule: a detail call is useful when it changed shipping,
landed cost, profitability, matching recommendation, hard-block result,
persistence decision, or opportunity type.

| Classification | Count | Percent |
| --- | ---: | ---: |
| Useful | 329 | 75.3% |
| Unnecessary / no material effect | 108 | 24.7% |

Detail calls are much more targeted than before, but they remain the dominant
quota sink. The biggest remaining question is whether every candidate truly
needs Game Name confirmation, or whether high-confidence title/platform/category
matches can skip detail when shipping is already present.

## 9. Opportunity Quality

Opportunity type comparison by scored rows:

| Opportunity Type | Before Rows | After Rows | Delta |
| --- | ---: | ---: | ---: |
| Buy Now | 7 | 19 | +12 |
| Best Offer | 32 | 100 | +68 |
| Auction | 4 | 7 | +3 |
| Multi-unit | 0 | 3 | +3 |
| Watch | 11 | 3 | -8 |
| No profitable source found | 1,955 | 218 | -1,737 |

Workflow/status comparison:

| Status | Before Rows | After Rows | Delta |
| --- | ---: | ---: | ---: |
| Open | 0 | 47 | +47 |
| Watching | 17 | 3 | -14 |
| Purchased pending match | 3 | 1 | -2 |
| Dismissed | 86 | 1 | -85 |
| Rejected | 1,903 | 298 | -1,605 |

Actionable batch comparison:

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| Batch-qualifying opportunities | 1 | 47 | +46 |
| Batch-qualifying opportunities / searched ASIN | 0.004 | 0.329 | +0.325 |
| Batch-qualifying opportunities / 1,000 Browse calls | 0.67 | 81.31 | +80.64 |

Opportunity recall appears maintained or improved by volume. Precision also
appears improved because the optimized run stored only Video Games category
rows, but the sample is smaller and skewed toward final-cycle catalog ASINs.

## 10. Remaining Optimization Opportunities

| Rank | Opportunity | Expected Browse Savings | Complexity | Sourcing Risk |
| ---: | --- | --- | --- | --- |
| 1 | Reduce Game Name detail calls for high-confidence title/platform/category matches. | Up to part of `437` detail records; likely the largest remaining savings. | Medium | Medium |
| 2 | Skip shipping detail when a candidate is already economically impossible even with unknown/free shipping. | Could reduce the `297` shipping-missing detail reason overlap. | Medium | Low |
| 3 | Persist summary-filter reason counters. | No direct savings, but needed to target the `2,232` non-economic pre-detail rejects. | Low | Low |
| 4 | Improve upstream seed/title hygiene for non-game titles entering the queue. | Prevents weak queries like the Skinfix/Xbox 360 row. | Medium | Low |
| 5 | Add a confidence gate for detail: no detail if category, platform, title overlap, and price/shipping are already decisive. | Could remove some of the `108` no-effect detail records. | Medium | Medium |
| 6 | Keep the run-level detail cache and consider a short-lived persistent item-detail cache. | Small in this run (`1` duplicate detail prevented), but useful across runs. | Medium | Low |

## 11. Recommendation

**NEEDS ANOTHER OPTIMIZATION PASS**

The first optimization should stay deployed: it fixed the production search
path, category leakage, alias fan-out, and quota accounting gap. It also
completed the active coverage cycle with a reconciled quota delta.

However, Browse efficiency is not done. Detail calls are now `75.4%` of
app-counted Browse usage, and `24.7%` of detail records had no material effect.
The next pass should focus on reducing Game Name and shipping detail calls
without weakening platform-specific matching.

Sources used:

- Supabase `sourcing_runs`
- Supabase `sourcing_coverage_cycles`
- Supabase `sourcing_opportunity_batches`
- Supabase `sourcing_seed_asins`
- Supabase `sourcing_ebay_candidates`
- Supabase `sourcing_opportunities`
- CloudWatch log stream
  `scheduled/mbop-scheduler/97f3b7c91bfb48dbac82a439be6d41fc`
- ECS task description for
  `arn:aws:ecs:us-west-2:297464765814:task/mbop-cluster1/97f3b7c91bfb48dbac82a439be6d41fc`

No production behavior was changed.
