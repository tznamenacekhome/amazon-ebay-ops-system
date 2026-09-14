# Phase 3 correction/admission candidate: curated gate failed

PHASE 3 NOT DEPLOYED — CORRECTION/ADMISSION SAFETY GATE FAILED

The scoped-correction candidate fixes the exact Crystal Harbor acceptance case, but introduces four curated positive admission losses. The operator's original work order requires stopping on a strict-gate regression. Work stopped before atomic-guard implementation, fresh production capture, deployment or refresh. This is an unapproved shadow candidate, not a production fix. The previous failure and report are preserved in commit `1aa82cb`.

## Root cause and implemented candidate

`evaluate_static_match_rules` applied scoped corrections once to canonical identity, then evaluated platform again from original titles/metadata. Valid PS4-to-PS5 correction therefore produced canonical Match but static Blocked and scorer rejected.

The audit also found raw-text digital/download, completeness and region checks after canonical corrections. Core/base, installment, edition, generation and package/theme already use canonical comparisons. Category/accessory, condition, location, delivery and configured excluded-keyword rules are independent safeguards; an identity-field correction does not authorize clearing them. Downstream scoring consumes static diagnostics and separate business/history signals; no additional raw reparse of these corrected identity fields was found there.

Candidate changes in `integrations/sourcing_match_rules.py` reuse the canonical effective fields for platform admission and retain the raw rule under `raw_rule`. Valid scoped eBay corrections feed digitalPhysical/completeness/region checks; raw hits and corrected-field provenance remain visible. Unsupported corrected values require Review; negative values still block. Amazon-only, wrong-scope and stale corrections cannot clear the eBay-specific restriction. Corrections are applied once by `apply_scoped_reviews`.

`integrations/video_game_identity.py` classifies supported unequal platforms as conflicts while retaining existing compatibility semantics. `integrations/matching_feedback.py` adds action time and optional actor to correction provenance. `tests/test_sourcing_effective_identity.py` adds ten focused tests with subcases covering the actual duplicate paths. No production policy activation/default, API, UI, scheduler or SQL change was made.

## Exact acceptance and regression results

- Crystal Harbor, raw PS4 vs Amazon PS5, valid current exact-pair PS5 correction, no pair verdict: before canonical Match/static Blocked/scorer rejected; candidate canonical Match/static Probable Match/no hard blocks/scorer open. Before/after full inputs and outputs are frozen locally.
- Genuine PS4/PS5 without correction: canonical platform Conflict, static Blocked, scorer rejected.
- Stale, wrong-scope or wrong-variation correction: correction not applied, conflict remains blocked/rejected.
- Supersession: latest correction wins; a stale newest correction never resurrects an older correction.
- Correction to Xbox Series X against PS5: remains blocked/rejected.
- Original PS4, effective PS5, action/snapshot/scope/time and optional actor are preserved. No source input is mutated.
- Strict adjudicated sample: 12/12 Tier A identity Match; three negatives excluded as two nonmatches and one Review; 17/17 corrections applied. Twelve Not Applicable variation qualifications remain intact. Zero saved Compatible examples; synthetic compatibility coverage is not operator evidence.
- Minecraft remains identity Match with its separate condition-related Blocked result. The BIGS remains Review and excluded.
- Curated identities: 15/15 Match, but **only 11/15 remain eligible**. All 18 curated negatives remain excluded. This fails the required gate.

## Exact new blocker

The new platform check requires canonical platform evidence even where that reference field is unknown. The old static check also used `resolve_seed_system` metadata fallbacks, which the canonical reference does not currently ingest. Replacing the old check discarded valid reference-platform evidence. In the exact Zelda fixture, raw static platform is Wii/Wii pass with `seed_system_source=keepa_category_tree`; canonical Amazon platform is unknown and eBay is Nintendo Wii. The candidate maps this unknown comparison to Review, yields Probable Non-Match, and rejects the row despite overall identity Match.

Four curated rows lose admission (all were eligible in the preceding Disney-policy replay):

| ASIN | Product | Candidate outcome |
| --- | --- | --- |
| B000FQBPCQ | The Legend of Zelda: Twilight Princess | Match identity; Probable Non-Match; ineligible |
| B004WL4LOY | White Knight Chronicles II | Match identity; Probable Non-Match; rejected |
| B081W4X9RW | Persona 5 Royal: Phantom Thieves | Match identity; Probable Non-Match; rejected |
| B0088MVPFQ | New Super Mario Bros. 2 | Match identity; Probable Non-Match; rejected |

Exact opportunity IDs, original reviewed outputs, and hashes are in the manifest and ignored evidence. The immediate commentary initially misnamed B000FQBPCQ as Rayman; the frozen fixture and this report correctly identify Zelda. Do not deploy this candidate. A subsequent authorized repair must preserve valid reference-platform resolution without letting raw sources override an applied correction; do not turn unknown into an automatic platform pass.

## Validation and operational closeout

167 Python tests pass, including ten new focused tests and existing Disney, correction, compatibility, variation and negative regressions. All 1,609 production-default static/full scorer outputs equal the previous baseline. The 1,000-row frozen and 600-row current-input replay identity counts remain 187 Match/746 nonmatch/67 Review and 114/378/108 respectively. These identity totals do not prove admission safety: the curated scorer gate failed. No further candidate implementation was attempted after this failure.

Original final operational work order did not advance past the prerequisite gate. Atomic write guard and mutation tests: not reached. Fresh production manifest and read-only production dry run: not reached. Final deploy-candidate packaged tests, deployment and pre-write recapture: not reached. Bounded refresh evaluated/written/stale/protected skips: all zero, not started. Buy List/Closest Excluded/Business Excluded were neither read nor changed. Protected rows touched and historical evidence rewrites: zero. Provider searches, marketplace writes, schema and scheduler changes: zero.

No new image was built or published. Last recorded runtime remains web151/scheduler92; no fresh AWS inspection was performed. Prior local-only Disney image digest remains `sha256:1090a7a354ed8407093fe240ae1a91ffb2540d9e5c60f0a6f2b35d0bed217fc0`, which does not contain this candidate. All twenty schedules are untouched; no new comparison was needed or claimed. No runtime/data rollback is required. Authenticated production UI was not accessed. Disposable local validation container `mbop-phase2-review-test` was inspected and is exited.

Evidence directory: `tmp/sourcing-effective-identity/`. Original frozen evidence was not overwritten. The current JSON manifest links candidate hashes, exact Crystal Harbor before/after, the Zelda missing-reference-platform proof, full replay and failing curated counts. Documentation-only closeout records implementation commit information separately to avoid self-reference. Phase 3 remains incomplete and shadow-only.

PHASE 3 NOT DEPLOYED — CORRECTION/ADMISSION SAFETY GATE FAILED
