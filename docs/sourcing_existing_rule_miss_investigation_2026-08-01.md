# Sourcing Existing-Rule Miss Investigation

Date: 2026-08-01

Scope: identity/condition dismissal rows from the latest 1,000-dismissal audit where the current deterministic evaluator says an existing hard block should apply. This was a read-only production investigation plus local code/tests. No production rows were rescored, no statuses were updated, no marketplace APIs were called, and nothing was deployed.

## Dataset

The filtered current-rule-miss set was reproduced with:

```powershell
.\.venv\Scripts\python.exe integrations\analyze_recent_sourcing_dismissals.py --limit 1000 --rule-miss-class "current rule should already block" --csv tmp\sourcing-existing-rule-miss-current.csv --json tmp\sourcing-existing-rule-miss-current.json --report tmp\sourcing-existing-rule-miss-current.md
```

Result: 122 rows, from 2026-06-15T02:50:54.610133+00:00 through 2026-07-31T03:12:08.325513+00:00.

The prior report text said 109 rows. Re-running the committed analyzer against current production data and current local rules produced a stable count of 122.

## Root-Cause Distribution

| Root cause | Count | Finding |
| --- | ---: | --- |
| Opportunity persistence/default visibility ignored a hard block | 48 | Stored diagnostics already said `Blocked`, but the operator still dismissed the opportunity later. These rows were not found in a batch table, so the likely exposure path was non-batch/open visibility. |
| Opportunity was created before the rule existed | 37 | Opportunity `created_at` was before the 2026-07-11 deterministic rule sprint. Current rules block them now, but they were historical/pre-rule rows. |
| Audit classification was incorrect due to settings drift | 31 | Current hard block is `non-US item location`; all 32 non-US-location blocks are Canada (`CA`). These are current-setting blocks, not necessarily defects at original presentation time. One CA row was pre-rule, leaving 31 post-rule settings-drift rows. |
| Batch selection ignored a hard block | 6 | Stored diagnostics were already `Blocked` and the rows were inserted into `sourcing_opportunity_batch_items`. |

## Representative Examples

Batch selection ignored stored hard blocks:

| Action | Reason | Stored block | eBay title |
| --- | --- | --- | --- |
| d7bd8e59-804d-4a7e-a8c0-bf49a769a24c | wrong_platform | unsupported sourcing platform: DS | Bratz Fashion Boutique Nintendo DS 2012 New |
| 30689927-dcac-4aad-80f7-1f6c4cad11be | missing_shrink_wrap | excluded keyword/download/incomplete | Good NBA 2K14 (Sony PlayStation 3 PS3, 2013) |
| b64c3c16-af7b-4fa9-8519-1ece0dac76f3 | digital_item | digital/download listing: digital content | Madden NFL 25 Supercharge Packs Xbox One / Xbox Series |

Pre-rule/stale examples:

| Action | Created | Current block | eBay title |
| --- | --- | --- | --- |
| a84bde22-1b3a-49c1-8778-00dc578ffdd7 | 2026-06-13T05:41:10Z | numeric sequel/year mismatch | historical wrong-product row |
| e2cd0ee9-39de-4ff0-9585-e4afb6db469d | 2026-06-13T05:41:10Z | item-specific Game Name identifies a different game | historical wrong-product row |

Settings-drift examples:

| Action | Created | Current block | Item location |
| --- | --- | --- | --- |
| 41cf35a3-28af-4b65-966b-86d61a9e5e58 | 2026-07-30T07:24:01Z | non-US item location | CA |
| 767b24bb-81a6-49f5-9ce8-f8ed55657dfb | 2026-07-30T07:24:01Z | non-US item location | CA |

## Code-Path Findings

The production path is:

1. eBay search result received in `integrations/ebay_sourcing_search.py`.
2. Summary evidence normalized by `map_item` and `normalize_candidate_evidence`.
3. Pre-detail rules evaluated by `candidate_decision`.
4. Detail enrichment runs only for needed shipping/platform/Game Name evidence.
5. Post-detail rules are re-evaluated by `candidate_decision`.
6. Candidates that pass search-stage rejection are persisted.
7. `integrations/score_sourcing_opportunities.py` scores candidates and writes `matching_diagnostics_json`.
8. Scoring normally assigns `rejected` for hard-blocked rows.
9. `integrations/run_sourcing_workflow.py` calculates batch qualification.
10. `sourcing_opportunity_batch_items` is inserted for selected rows.
11. `/api/sourcing/opportunities` returns rows to Replenishment/Sourcing.

Confirmed defect: the final batch selector checked `status` and `opportunity_type`, but did not independently honor stored hard-block diagnostics. The API also had an `all_open` path that could return stale open rows without a final stored-diagnostic hard-block filter.

## Defects Fixed

- Added a final Python presentation gate in `run_sourcing_workflow.py`.
- Batch selection now rejects rows with `Blocked:` flags, top-level/stored `Blocked` recommendation, or stored hard-block diagnostics.
- `select_unbatched_open_opportunities` now fetches `status`, `ai_flags`, and `matching_diagnostics_json` so the gate has the needed evidence.
- Added an API-side stored-diagnostic guard in `web/app/api/sourcing/opportunities/route.ts` for stale open rows.
- Updated `analyze_recent_sourcing_dismissals.py` with read-only filters: `--rule-miss-class`, `--action-id`, `--opportunity-id`, and `--candidate-id`.
- Added batch, opportunity status, run, and item-location evidence to analyzer CSV output.

## Historical Validation

| Metric | Count |
| --- | ---: |
| Original/current reproduced miss set | 122 |
| Rows current rules would now prevent if re-created/rescored | 122 |
| Rows directly protected by the new stored-diagnostic presentation gate | 54 |
| Rows caused by stale/pre-rule history | 37 |
| Rows treated as audit misclassification/settings drift | 31 |
| Rows still unexplained | 0 |
| Current open opportunities newly hard-blocked in dry-run | 0 |

The current database has zero `open` sourcing opportunities, so there are no open opportunities newly hidden by the gate at validation time.

## Positive-Match Safety

Read-only validation of current non-open positive/review statuses found:

| Status | Current rules hard-blocked | Presentation impact from this sprint |
| --- | ---: | --- |
| watching | 11 | none, not batch-presentable |
| purchased_pending_match | 11 | none, not batch-presentable |
| matched_to_purchase | 23 | none, not batch-presentable |

These are existing current-rule false-positive candidates, not new behavior introduced by this sprint. Because accepted/purchased positives are blocked by the current evaluator in dry-run, do not deploy broader matching-rule changes without a separate positive-fixture review. The enforcement gate added here only affects `open` rows before presentation.

## Files Changed

- `integrations/analyze_recent_sourcing_dismissals.py`
- `integrations/run_sourcing_workflow.py`
- `tests/test_ebay_sourcing_search.py`
- `tests/test_sourcing_progressive_batches.py`
- `web/app/api/sourcing/opportunities/route.ts`
- `docs/matching_intelligence.md`
- `CURRENT_STATE.md`
- `DECISIONS.md`
- `KNOWN_ISSUES.md`

## Tests Run

```powershell
.\.venv\Scripts\python.exe -m py_compile integrations\analyze_recent_sourcing_dismissals.py integrations\run_sourcing_workflow.py integrations\score_sourcing_opportunities.py integrations\ebay_sourcing_search.py integrations\sourcing_match_rules.py
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_progressive_batches tests.test_sourcing_match_rules tests.test_ebay_sourcing_search
Set-Location C:\Dev\amazon-ebay-ops-system\web; npm.cmd run build
```

All passed.

## Deployment Recommendation

Do not deploy matching-rule expansions from this investigation, because positive-status dry-run rows need review first.

Deploying only the final presentation gate is reasonable after operator review because it does not add new matching rules; it honors hard-block diagnostics already produced by backend scoring and prevents stale hard-blocked `open` rows from entering batches or API presentation.

