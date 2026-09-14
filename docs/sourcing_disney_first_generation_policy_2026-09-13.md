# Disney Infinity first-generation policy and strict gate

STRICT ADJUDICATED SAFETY GATE PASSED — READY FOR FINAL WRITE-GUARD/DEPLOYMENT PHASE

The operator explicitly authorized treating an absent version indicator as 1.0 in the ongoing Disney Infinity investigation. This changes the shadow policy; it does not fabricate a catalog observation or amend saved reviews. The convention applies to all Disney Infinity ASINs, with no ASIN/title-pair whitelist. It does not impose first-generation defaults on unrelated games.

## Implementation

`phase3_side` infers generation and installment 1.0 only after reconciling the side's title and supporting sources, when both fields are unknown and no parsed numeric indicator exists. The fields carry `state=inferred` and `identity_policy / disney_infinity_unnumbered_is_1.0` provenance. An abbreviated Game Name cannot manufacture a conflict against explicit 2.0/3.0. Explicit unknown later or multiple numeric indicators suppress the default. Typed Disney generation is kept out of coreGame, while the generation/installment comparisons still enforce version conflicts. No edition, package, platform, mixed-lot or business rule was relaxed. Original source text and the 17 saved corrections remain unchanged.

The exact Disney adjudicated fixture now returns Match using the existing scoped core corrections. Its reference generation is a policy inference, not new operator field evidence. Existing Not Applicable variation evidence remains solely selection-scope evidence. Additional listing contents remain in the source description; no general package-containment rule was introduced.

## Strict and regression results

- 15 reviewable: 12 qualified positives, 3 verified negatives; 0 unresolved/unqualified; 1 separate informational exclusion.
- Tier A: **12 Match, 0 Conflict, 0 Review, 0 Unknown admission**.
- Negatives: **2 Conflict, 1 Review, 0 Match**. The BIGS remains excluded through Review.
- All 17 corrections applied within scope; all 12 variation scopes remain Not Applicable.
- All 15 curated positives retained; all 18 curated negatives remain definite nonmatches.
- Zero saved Compatible examples: no observed false platform conflict, but this sample does not establish general relationship-based compatibility admission.
- Minecraft remains identity Match with its independent used-condition static block. No buying eligibility or hold was changed.

157 Python tests and 70 tests against the newly built scheduler runtime passed, including five new semantic tests and the exact full-source Disney fixture. The container had networking disabled. 150 Python-to-API-to-UI indicators and 15 panels pass; Python compilation and diff whitespace checks pass. No web/API code changed, so no Next.js build or new API/RPC transaction run was needed.

All 1,609 production-default static/full scorer outputs remain identical. All 1,600 business checks are unchanged. Nine non-adjudicated frozen shadow comparisons (five frozen, four current-input) change Review to Conflict: each pairs the now-inferred 1.0 reference with an explicitly 3.0 Star Wars listing. No Match is lost. New frozen shadow totals: Match 187 / Conflict 746 / Review 67; current-input totals: Match 114 / Conflict 378 / Review 108. These are offline outcomes, not production writes.

Tier B/C diagnostics were rerun: receiving B 186 Match / 200 Conflict / 5 Review; broader B 183 / 202 / 5; broader C 1024 / 573 / 88. Counts are unchanged, cohorts overlap, and these are diagnostic assertions rather than strict truth.

Local scheduler image `mbop-scheduler:disney-version-policy`: `sha256:1090a7a354ed8407093fe240ae1a91ffb2540d9e5c60f0a6f2b35d0bed217fc0`. Built and tested only; not pushed or deployed. No additional production evidence read was necessary: the stable 27-action capture was reused.

## Handoff

The [current manifest](sourcing_adjudicated_ground_truth_manifest_2026-09-13.json) records all rows, inferred fields, source/candidate hashes and test artifacts. The previous failed gate remains in Git at `af71589`; private artifacts are under `tmp/sourcing-disney-version-policy` and the preceding frozen capture directory. Reproduce the corpus with the existing validator's `--candidate` flag and a new output path.

This is a passed sampled identity gate under the newly authorized policy, not Phase 3 completion or deployment approval. The next phase still owns atomic stale-state/operator-activity write protection, fresh production capture, final validation and separately authorized activation/refresh. Production deployment, sourcing refresh, provider searches, marketplace/review writes, scheduler changes and business-hold/lifecycle mutations: all zero.

STRICT ADJUDICATED SAFETY GATE PASSED — READY FOR FINAL WRITE-GUARD/DEPLOYMENT PHASE
