# Sourcing Video Game Identity Final Validation

Date: 2026-08-05

Scope: final production-read validation for the conservative video game
identity engine. This pass did not call eBay search, did not use AI/image
analysis, did not change matching rules, and did not write production data
until the validation gate passed.

## Repo And Deployment Baseline

Validated commit before the final diagnostics patch:
`995712a2b36dbee2b882c545e430dfb55eff6936`.

Production web baseline before deployment:

- ECS task definition: `mbop-web-task:111`
- Build SHA: `3e460026c064`
- Image digest:
  `sha256:f8c8a0ba2d9992eb89a91b57e0d78600d34ae9d741223f04bdc08535682f5e98`

Production scheduler baseline before deployment:

- Latest task definition: `mbop-scheduler-task:61`
- Scheduler image digest:
  `sha256:c7e79f487ac6d6ba36e2554e2cf53c5c7af4c687ec846f7ce7b0928f471ddb1a`
- EventBridge `mbop-sourcing-catalog` target was still pinned to
  `mbop-scheduler-task:60`.

Because the identity engine runs inside shared sourcing integration code used by
scheduled scoring/reprocessing, scheduler deployment and schedule target updates
are required in addition to web deployment.

## Positive Dataset Reconciliation

Final confirmed-positive safety audit:

| Metric | Count |
| --- | ---: |
| Raw positive evidence rows | 6,110 |
| Deduplicated positive rows | 2,436 |
| Authoritative confirmed positives | 2,353 |
| Review-only watching rows | 83 |
| Unique ASINs | 1,098 |
| Unique ASIN/eBay-or-title pairs | 2,427 |
| Current hard-blocked authoritative positives | 85 |
| Authoritative positives blocked by the new video identity conflict | 0 |

The earlier 2,280 count was the previous status/source snapshot. The current
2,353 count includes additional confirmed positive evidence now present in
production, especially matching-intelligence purchase-item examples and
receiving outcome examples. The 83 `watching` rows remain review-only and are
not treated as authoritative positives.

The 85 hard-blocked authoritative positives are existing rule-family conflicts,
not new video identity conflicts:

| Rule family | Count |
| --- | ---: |
| accessory | 24 |
| edition | 19 |
| location | 15 |
| platform | 8 |
| numeric | 6 |
| title_overlap | 6 |
| incomplete | 3 |
| other | 2 |
| game_name | 1 |
| digital | 1 |

Artifacts:

- `tmp/identity-final-positive-safety-2026-08-05.csv`
- `tmp/identity-final-positive-safety-2026-08-05.json`
- `tmp/identity-final-positive-safety-2026-08-05.md`

## Current Open Dry-Run

Artifact:
`tmp/sourcing_unreviewed_reprocess_dry_run_20260805012737.json`.

| Metric | Count |
| --- | ---: |
| Rows in scope | 3,441 |
| Rows processed | 3,441 |
| Unchanged | 2,890 |
| Newly hard-blocked | 62 |
| Downgraded from open to rejected | 440 |
| Rows leaving presentation | 449 |
| Rows entering presentation | 0 |
| Recommendation changes | 449 |
| Purchased/completed/dismissed rows touched | 0 |

Status transitions:

| Transition | Count |
| --- | ---: |
| open -> open | 2,992 |
| open -> rejected | 440 |
| open -> watching | 1 |
| open -> inventory_snoozed | 8 |

Rows leaving presentation by primary reason:

| Reason | Count |
| --- | ---: |
| edition_version_conflict | 336 |
| profitability | 85 |
| game_name_conflict | 23 |
| numeric_installment_mismatch | 4 |
| digital_or_service_listing | 1 |

All rows leaving presentation were current `open` rows. No purchased, completed,
dismissed, or accepted rows were in the write scope.

## Recent Dismissal Review

Latest 1,000 operator dismissals:

| Metric | Count |
| --- | ---: |
| Operator dismissals analyzed | 1,000 |
| Date range | 2026-07-11T14:35:18.776324+00:00 to 2026-08-04T14:57:12.841521+00:00 |
| Excluded system/availability actions | 164 |

Top dismiss reasons:

| Reason | Count |
| --- | ---: |
| wrong_edition_version | 397 |
| wrong_product | 194 |
| missing_shrink_wrap | 76 |
| sales_velocity_too_low | 74 |
| asin_blocked | 61 |
| digital_item | 38 |
| incomplete_product | 38 |
| wrong_platform | 30 |

Artifacts:

- `tmp/identity-final-dismissals-2026-08-05.csv`
- `tmp/identity-final-dismissals-2026-08-05.json`
- `tmp/identity-final-dismissals-2026-08-05.md`

## Rejected / Closest Excluded Diagnostics Dry-Run

Artifact:
`tmp/sourcing_rejected_decision_trace_dry_run_20260805012642.json`.

| Metric | Count |
| --- | ---: |
| Rows in scope | 459 |
| Diagnostic update count | 459 |
| Existing precise reason count | 459 |
| Existing missing/generic reason count | 0 |
| Primary reason changes | 50 |
| Final recommendation changes | 45 |
| Rows that would become presentation eligible | 0 |

New primary reason counts:

| Reason | Count |
| --- | ---: |
| profitability | 379 |
| edition_version_conflict | 43 |
| historical_exact_negative | 27 |
| game_name_conflict | 7 |
| numeric_installment_mismatch | 3 |

## Regression Fixtures

Manual fixture checks plus unit tests verified:

- Rock Band 3 vs Metal Track Pack: blocked by core product conflict.
- Rock Band 3 vs The Beatles Rock Band: blocked by core product conflict.
- Rock Band 3 vs Rock Band 3: remains a probable match.
- Just Dance 2014 vs Just Dance 2015: blocked by existing numeric identity
  mismatch.
- Final Fantasy XIV Complete Edition wording: remains a probable match.
- Platform-only agreement with different games: does not create positive
  identity evidence.

## Final Gate Decision

Gate result: pass.

Reasons:

- Zero authoritative confirmed positives were hard-blocked by the new video
  identity conflict.
- Current-open write scope is restricted to existing `open` rows.
- No purchased/completed/dismissed rows are touched by the current-open
  reprocess script.
- Recent rejected diagnostics remain rejected; no rows become presentation
  eligible.
- The diagnostics primary-reason mapper now treats
  `identity_comparison.result = conflict` as a failed identity check, so Rock
  Band, Disney Infinity, and similar conflicts no longer appear primarily as
  profitability rejects.

## Verification

Commands passed:

- `.venv\Scripts\python.exe -m unittest tests.test_video_game_identity_engine tests.test_sourcing_match_rules tests.test_ebay_sourcing_search tests.test_sourcing_decision_trace`
- `.venv\Scripts\python.exe -m py_compile integrations\video_game_identity.py integrations\sourcing_match_rules.py integrations\sourcing_decision_trace.py integrations\score_sourcing_opportunities.py integrations\reprocess_current_unreviewed_sourcing.py integrations\reprocess_recent_rejected_sourcing_decisions.py integrations\analyze_sourcing_positive_match_safety.py integrations\analyze_recent_sourcing_dismissals.py`
- `npm.cmd run build` from `web`

## Production Write And Deployment

To be filled after deployment:

- Final commit SHA:
- Web image digest:
- Web ECS task revision:
- Scheduler image digest:
- Scheduler ECS task revision:
- EventBridge schedules updated:
- Current-open rows written:
- Rejected/Closest Excluded diagnostics rows written:
- Production verification rows:
