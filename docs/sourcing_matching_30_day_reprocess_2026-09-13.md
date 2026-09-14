# Sourcing matching closeout and 30-day re-evaluation

Completed the operator-authorized closeout with the accepted Phase 3 parser. The earlier FIFA/Madden wording stop is superseded by the final work order. No additional parser whitelist, adjudication exercise, provider search or marketplace action was introduced.

## Deployment and validation

Implementation commit `a2247102a9e6aa4da62f78fc78c30dc4a87054f2` is pushed to origin/main. Sourcing scheduler revision **93** is active; web **151** is unchanged and healthy. Image digest: `sha256:78cd26f23c2e5cdf04c25147d507d9eb5ea8dd80ba18c5e69ba338310152d44b`. ECS smoke task `3e3a5ff4b91f4a9ab42ded4335ed7462` exited 0 with Phase 3 enabled and a successful database read. All 20 schedules were compared; only `mbop-sourcing-catalog` changed from scheduler92 to scheduler93. Cadence, state, command, network, roles and other settings were preserved.

Migration `20260914045624_mbop_guarded_sourcing_decision_refresh.sql` was applied through the documented CLI after reconciling the shared ledger; all 19 entries then matched. The nonfatal CLI catalog-cache warning did not affect application. No College Planner migration was changed.

Validation: 173 Python tests, 94 disposable database guard checks, the end-to-end guarded runner/idempotent-resume fixture, and 69 networking-disabled tests in the exact pushed image passed. The strict baseline remains 12/12 Tier A Match; three adjudicated negatives route as two nonmatch and one Review; 15/15 curated positives eligible and all 18 curated negatives excluded. Crystal Harbor scoped correction passes; genuine PS4/PS5 conflict stays blocked. All 1,609 legacy outputs are unchanged when Phase 3 is disabled. Seventeen scoped corrections remain effective; no saved Compatible relationship was invented. Minecraft condition exclusion is independent of identity.

## Frozen scope and exact results

Los Angeles calendar window: **2026-08-15T07:00:00+00:00 through 2026-09-14T06:22:13.607958+00:00**, inclusive at the original runtime start. This is September 13 and the preceding 29 calendar dates. Resuming preserves this frozen window and run ID `4e564247-26f7-4945-b143-106e1ad9d5a9`.

| Measure | Count |
|---|---:|
| Total found | 50239 |
| Excluded: explicit operator identity review | 9 |
| Excluded: protected lifecycle/history | 17437 |
| Excluded/skipped: insufficient evidence | 0 |
| Guarded rows processed | 32793 |
| Actually evaluated | 31455 |
| Successful atomic writes | 28013 |
| Protected skips during processing | 4667 |
| Stale skips | 113 |
| Unchanged identity/recommendation/status | 0 |
| Unresolved errors | 0 |

Explicit identity review is determined from normalized exact-pair human actions, including Not Sure; status alone is insufficient. Human dismissal and purchased/completed history remain protected. Known availability/duplicate automation does not count as human review. Business-only snoozes remain independent protections. Scoped corrections may apply to otherwise unreviewed pairs. The informational mixed lot is never used as ground truth.

Accounting: 50,239 found = 17,446 initially excluded + 32,793 processed. Of the processed rows, 1,338 were protected before evaluation; 3,329 further protected skips and all 113 stale skips occurred after evaluation. Thus 31,455 evaluated = 28,013 writes + 3,329 later protected skips + 113 stale skips.

Prior success means stored open status or an explicitly true prior presentation-eligibility decision. Other evaluable rows form the prior-failure group. Missing legacy identity fields are reported as unavailable, not invented. Evaluated counts include proposals later rejected by an atomic stale/protection check; routing counts below include successful writes only.

| Previous outcome | Evaluated | New Match | New Conflict | New Review/Unknown |
|---|---:|---:|---:|---:|
| Success/admitted | 2388 | 855 | 1360 | 173 |
| Failed/excluded | 29067 | 11136 | 15458 | 2473 |

| Written historical-row route | Count |
|---|---:|
| buy_list | 418 |
| business_excluded | 10342 |
| closest_excluded | 17253 |

These are historical opportunity-row routes, not unique live workspace listings. Conflict stays excluded; Review/Unknown uses existing Closest Excluded behavior. Identity Match still requires current business eligibility to enter Buy List.

## Important changed rows

These are exact matcher outputs, not new operator adjudications. Descriptive wording can still cause conservative false exclusions; the accepted parser was preserved.

| ASIN / eBay item | Previous | New | Reason |
|---|---|---|---|
| B014XCWZA8 / v1 / 277454369889 / 0 | dismissed; identity unavailable; Probable Match | non-match; closest_excluded | coreProduct conflict: Amazon minecraft story mode season disc, eBay minecraft story mode season pass disc; coreGame conflict: Amazon minecraft story mode season disc, eBay minecraft story mode season pass disc |
| B00IQCRKP2 / v1 / 298385597971 / 0 | dismissed; identity unavailable; Probable Match | non-match; closest_excluded | coreProduct conflict: Amazon kinect sports rivals, eBay new kinect sports rivals ntsc; coreGame conflict: Amazon kinect sports rivals, eBay new kinect sports rivals ntsc |
| B00CH9253W / v1 / 377492075837 / 0 | open; unknown; Probable Match | non-match; closest_excluded | coreProduct conflict: Amazon mario party, eBay mario party island tour game party; coreGame conflict: Amazon mario party, eBay mario party island tour game party |
| B0088MVPFQ / v1 / 298628110851 / 0 | rejected; identity unavailable; Probable Match | match; buy_list | Identity matched or unknown; unknown fields are not positive evidence. |
| B01IPARXDS / v1 / 336715184189 / 0 | rejected; identity unavailable; Blocked | match; buy_list | Identity matched or unknown; unknown fields are not positive evidence. |
| B01E6239X2 / v1 / 137545111299 / 0 | rejected; identity unavailable; Review | match; buy_list | Identity matched or unknown; unknown fields are not positive evidence. |
| B097RB8JJB / v1 / 198614379112 / 0 | rejected; identity unavailable; Review | needs_review; closest_excluded | coreProduct review: Amazon farming simulator, eBay world of simulators farm drive and rescue complete games; coreGame review: Amazon farming simulator 22, eBay world of simulators farm drive and rescue 22 complete games |
| B004W4STO4 / v1 / 377150377955 / 0 | rejected; identity unavailable; Probable Match | needs_review; closest_excluded | coreProduct review: Amazon mystery case files the malgrave incident, eBay mystery case files the malgrave incident; coreGame review: Amazon mystery case files the malgrave incident, eBay mystery case files the malgrave incident |
| B00182QCXS / v1 / 335793385535 / 0 | rejected; identity unavailable; Probable Match | needs_review; closest_excluded | coreProduct review: Amazon deal or no deal, eBay deal or no deal; coreGame review: Amazon deal or no deal, eBay deal or no deal |

## Final verification and limitations

| Production API-equivalent view | Total | Returned |
|---|---:|---:|
| buy_list | 102 | 102 |
| closest_excluded | 122 | 50 |
| business_excluded | 19 | 19 |

All three actual API handlers returned 200. Verification used production reads and the checked-in TypeScript handler; authenticated browser verification was not performed. The supporting 5,000-row presented-listing query used only identifiers consumed by that helper, avoiding unused raw payload/diagnostic transfer. Primary view projections and decision logic were unchanged. Normal API limits/deduplication mean totals are not the sum of historical row routes. No duplicate listing identities appeared in the returned views.

Journal and database audit readback reconcile **28013 writes**. Every initially excluded opportunity is absent from the write set. Protected rows touched **0**; reviewed rows overwritten **0**; historical actions/reviews rewritten **0**; provider searches launched by closeout **0**; marketplace writes **0**. The applied function only updates its explicit decision/derived-financial allowlist and inserts its audit log. It does not mutate operator actions, corrections, holds or marketplace/lifecycle workflows. Capture, final recapture and atomic transaction checks protect activity occurring after cohort selection.

One transport interruption after 21,165 processed rows closed the connection without a response. There was no pending write; a tiny database read succeeded and the same durable journal resumed. This was recovered without changing guards or cohort. Unresolved errors at completion are zero. The same run was also resumed with the existing tested batch bound raised from 10 to 25 to reduce request overhead. Durable pending requests and stable UUIDs prevented duplicate writes. The disposable database container was stopped after tests. Production source evidence was reused; large snapshots were not duplicated into database audit records. Initial database size was about 6,175 MB, so capacity/IO risk was noted and compact logs/bounded batches used.

Known limitations: stored evidence can be incomplete or stale; normal ambiguous wording remains subject to operator feedback. No claim of perfect title interpretation is made, and no new audit or queue is required for this closeout. Existing schedules continue their normal work; none was manually launched for provider discovery. Future related-ASIN, wholesale and eBay-first discovery are documented as possible reuse, not implemented.

Feature/runbook: [SOURCING_MATCHING_CURRENT_STATE.md](SOURCING_MATCHING_CURRENT_STATE.md). Compact evidence manifest: [closeout manifest](sourcing_matching_closeout_manifest_2026-09-13.json). Private run artifacts remain ignored under `tmp/sourcing-closeout/`. The final documentation commit is reported externally to avoid self-referential commit metadata.

SOURCING MATCHING CLOSEOUT COMPLETE
