# eBay Browse Call Optimization Implementation

Date: 2026-07-13

Baseline: `docs/ebay_browse_call_efficiency_audit_2026-07-12.md`

## Summary

Implemented the first quota-efficiency pass for Amazon-to-eBay replenishment sourcing. The search pipeline now uses one approved platform-aware query per ASIN, restricts Browse search to the EBAY_US Video Games software category `139973`, requests up to 200 first-page results, applies deterministic local filters before detail calls, and calls item detail only when a plausible candidate is missing information required for final matching or scoring.

No schema migration was added. Exact counters and compact per-detail-call records are stored under `sourcing_runs.raw_summary_json.ebay_search`.

## Search Behavior

- Query format is `<cleaned game title without platform> <approved platform suffix>`.
- DS, original Xbox, and GameCube seeds are skipped.
- Xbox Series X and Xbox Series S use the same Xbox Series suffix.
- eBay search sends `category_ids=139973`, `conditionIds:{1000}`, configured US/Canada location filters, delivery country, fixed-price/auction buying options, buyer ZIP context, `sort=price`, and `limit=200`.
- The search does not paginate beyond the first 200 results.

## Detail Eligibility

Detail calls are now lazy. A candidate must first survive summary-level matching filters and economic feasibility filters.

Detail reasons use this vocabulary:

- `shipping_missing`
- `platform_confirmation_needed`
- `region_confirmation_needed`
- `game_name_confirmation_needed`
- `edition_confirmation_needed`
- `type_or_format_confirmation_needed`
- `description_needed`
- `quantity_confirmation_needed`
- `combined_shipping_evaluation_needed`
- `other`

The implemented first pass currently emits the reasons that are actionable from existing summary scoring gaps: `shipping_missing`, `platform_confirmation_needed`, and `game_name_confirmation_needed`.

## Metrics

Per run/chunk metrics include:

- search/detail call counts
- retry and 429 attempt counts
- failed search/detail counts
- query variant count
- search result count
- summary matching/profitability filter counts
- detail eligibility and skip counts
- detail success/resolution/decision-change counts
- duplicate item and duplicate-detail-prevention counts
- detail reason counts
- compact detail-call records

The daily coverage runner aggregates chunk metrics into the completed run summary and preserves exact run-level call totals instead of relying on rounded cycle-item allocation.

## UI

Coverage Cycle -> Daily Runs now shows search calls, detail calls, retries, pre-detail filtered rows, detail missing-data resolutions, detail decision changes, and an expandable detail-reason breakdown.

## Validation

Targeted tests passed:

```powershell
.\.venv\Scripts\python.exe tests\test_ebay_sourcing_search.py
.\.venv\Scripts\python.exe tests\test_sourcing_match_rules.py
.\.venv\Scripts\python.exe tests\test_sourcing_progressive_batches.py
.\.venv\Scripts\python.exe tests\test_sourcing_coverage_cycle.py
.\.venv\Scripts\python.exe -m py_compile integrations\ebay_sourcing_search.py integrations\run_daily_catalog_sourcing.py integrations\run_daily_sourcing_discovery.py integrations\run_sourcing_workflow.py integrations\sourcing_match_rules.py integrations\score_sourcing_opportunities.py
Set-Location .\web; npm.cmd run build
```

Expected comparison target after the next controlled production sample:

- baseline total calls/ASIN: 6.04
- baseline search calls/ASIN: 2.69
- baseline detail calls/ASIN: 3.35

Success should be judged by both lower calls/ASIN and acceptable opportunity quality/recall, not call reduction alone.

## Boundaries Preserved

No AI calls, UPC/EPID discovery, eBay-to-Amazon sourcing, purchases, bids, Best Offers, or marketplace write behavior were added.
