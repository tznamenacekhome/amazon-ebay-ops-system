# Phase 1 typed identity metadata: local implementation and failed release gate

**Release gate: FAIL. No commit, push, deployment or production reevaluation.**

The shared Phase1 correction is implemented locally, but individual review found an unsafe newly Open shadow outcome for Super Mario Advance. Following the explicit task stop condition, the production rollout and replay were not performed. All changes remain uncommitted for review, and the unrelated MF oversale documentation is preserved.

## Release-blocking finding

`920153081093 / B00005B8FZ`, Flipmine row238: the named game is corroborated, and reusable metadata parsing correctly changes `super mario advance boy advance usa` to `super mario advance`. However, the existing full scorer would promote the saved listing to Open at **$8.90 landed**, against a historical approximately **$226.49** New Amazon/Keepa reference, reporting **$163.76 / 1,840% ROI** in a multi-unit scenario.

All four public image URLs retained in the listing snapshot were inspected. They show a **loose cartridge**, including stock-style front views; none establishes original sealed retail packaging. The listing's Brand New flag, EAN and seller MPN do not prove that the offered physical product is the New retail package represented by that reference. The description also makes a questionable Super Game Boy compatibility claim. This is insufficient package/condition evidence, **not a finding that the cartridge is counterfeit**.

The existing text/condition/contents checks do not consume this visual packaging concern, so a successful core-game match would expose it as actionable. No exact-ASIN exception, new image classifier, blanket packaging requirement or unrelated condition-policy expansion was added to force the release gate through. This needs a separately reviewed, reusable package/condition evidence disposition before deployment. The gate artifact preserves image hashes and the unsafe full-scoring result.

## Architecture and code changes

- `integrations/system_detection.py`: extend the **existing canonical alias definitions**, rather than creating a competing taxonomy, for Game Boy Advance/Color/Game Boy, Dreamcast, Sega CD, Sony PSP and complete Super Nintendo/SUPER NES phrases. Existing sourcing eligibility remains separate.
- `integrations/sourcing_identity_metadata.py`: new narrow typed-span preparation for complete corroborated legacy-platform phrases, terminal region/media metadata and structured missing-value placeholders. It retains original source text, the extracted text, typed field, canonical platform value, source and reason. This module has a scope allowlist of existing canonical platform keys, not a second alias dictionary.
- `integrations/video_game_identity.py`: integrate typed spans before existing product parsing; preserve a meaningful bare Switch under independent non-Switch evidence; use raw exact-catalog platform observations when normalized labels are absent or contradictory. Unknown normalized platform values remain missing rather than becoming a literal competing None observation. Raw/normalized conflicts stay review.
- Newly extracted legacy spans cannot hide an additional explicit platform in the same title. The existing `detect_all_systems` is reused; lexical nesting of Game Boy/Advance/Color and NES/SNES is suppressed in `sourcing_match_rules.py`, consistently with the existing Xbox/PlayStation nesting pattern.
- Typed media evidence is retained independently. Contradictory CD-ROM/DVD-ROM/cartridge evidence associated with a removed media span yields review; catalog format is not treated as infallible. Raw region and physical/digital/condition/content evidence continues through the existing gates. No general title-word stripping, media inference from price, fuzzy matching, publisher normalization, spelling correction, stock-code rule or alias policy was introduced.
- No frontend, SQL, migration, fee, demand, quota, cache, provider or schedule changes. An eventual successful implementation would need a worker rollout; no unaffected web deployment is proposed by this patch.

## Missing-value correction and investigation attribution correction

`usable_game_names` now treats explicit structured Game Name N/A, None, Unknown, Does not apply and Not applicable as missing observations. It does not remove those words from titles or descriptions. Removed placeholders are retained in assignedMetadata with a missing-value explanation. A missing observation cannot create a positive product match, and actual competing names remain source conflict/review.

**The previous investigation misattributed the one missing-value example to source row346.** That row's retained Game Name is Tokyo Xtreme Racer3; its leading New remains a Phase2 issue. Actual N/A captures belong to three other Tokyo Xtreme Racer listings: **920147066337, 940074372452 and 800953016239**, all ASIN B0000E3D8T in the prior97 cohort. This was a report attribution error, not evidence changed to fit the implementation. The original investigation artifacts remain unedited; this correction must guide future cohort selection.

Removing N/A does not promote those three: two remain Review for insufficient edition corroboration; the third becomes non-match because the retained A++ suffix still conflicts. Phase1 does not strip that suffix or manufacture a structured name.

## Same-input shadow method

The deployed worker baseline **f82933aad115** was copied before editing. Five baseline identity/platform/static/edition/package files were byte-verified against that commit after LF normalization. The same captured inputs and scoring context were used in separate baseline/revised Python processes. HTTP was blocked during scoring.

Cohort: **379 distinct material-evidence snapshots / 376 distinct listing–ASIN pairs**: all original265, supplemental Mario, the exact prior97 edition/condition/package capture and16 regular catalog controls. Identical snapshots were deduplicated; three pairs retain materially different captures. The original265 explicitly includes all108 B,135 C,21 A and1 D assessments. The accepted20 controls from the prior97 are included.

The normal `score_candidate` pipeline ran locally with the frozen settings, historical matching/review context, price and owned-unit inputs. The prior97 retained its original context; new investigation rows use retained diagnostic price references where absent from that context. These are **historical same-input shadow results**, not fresh availability, eligibility, shipping, demand or current-profit validation. Review cutoffs/history/owned context are frozen and must be refreshed in any future authorized production pipeline.

| Cohort | Baseline Match / Review / Non-match | Revised Match / Review / Non-match | Baseline / revised Open |
|---|---:|---:|---:|
| Original265 + Mario (266) | 0 / 1 / 265 | 10 / 3 / 253 | 0 / 6 |
| Prior97 (97) | 53 / 36 / 8 | 54 / 34 / 9 | 29 / 30 |
| Regular controls (16) | 0 / 1 / 15 | 0 / 1 / 15 | 0 / 0 |

Across all379: Match53→64, Review38→38, Non-match288→277; provisional Open29→36. These row-level shadow counts are not distinct purchasing demand or production presentation totals. The six newly Open original-import rows and one newly Open prior97 row were individually inspected against retained title, description, specifics, condition, contents and economic diagnostics. Mario makes the release gate fail regardless of the other results.

The original265 assessments now yield: A21 all non-match; B108:8 Match,2 Review,98 Non-match; C135:1 Match,1 Review,133 Non-match; D1 remains non-match. Mario is supplemental Match but unsafe for automatic purchasing. Most unchanged conflicts still contain Phase2 wording/lexical/publisher residue or material package/source uncertainty; they were not forcibly cleared.

Initial requested30 (28 platform-group, attributed missing-value row346, Mario):9 Match,1 Review,20 Non-match. The goal is typed evidence correctness, not30 guaranteed opportunities. Original source row344 is an additional direct SNES-span case; row92 is a direct product-word/catalog-conflict review. The actual N/A captures are separately identified above. No additional replay selection was executed.

## Protected controls and unexpected changes

- **All21 independently supported mismatches remain non-match.** No wrong-game, poster, demo, wrong-year or materially incompatible-package case was promoted.
- **All20 previously accepted/control identities and lifecycle outcomes are unchanged.** Every baseline Open in the prior97 remains Open; no accepted match was lost in the final patch.
- Existing numeric/franchise controls, including 1942/1943, FFX/X-2, FIFA23/24, Resident Evil4/5,007 Legends,50 Cent,13 Sentinels,7 Days to Die, New Super Mario Bros. and Wii Play Motion, pass their regression tests.
- Spirit Camera/AR Book and Wii Fit exact-package ambiguity remain Review/Rejected. Tiger Woods seal/case damage, Legends of Wrestling missing seal, Dragon Ball Z/Samurai Warriors condition review and Shining Tears punched UPC remain Rejected, independently of named-game identity.
- **Double Switch:** core name preserved on both sides; exact catalog normalized Switch contradicts raw Sega CD, so platform remains Review and it stays Rejected. Retained description also discloses case cracks/separated seal; a near-miss indication is not condition clearance.
- **F-Zero row184:** title says PC plus Super Nintendo/SNES. PC may be seller shorthand, but Phase1 does not establish that alias. Typed extraction preserves the ambiguity as platform Review; it does not automatically choose the convenient structured platform.
- Outside the initial30, prior97 Gran Turismo2 (168847018534/B07FYS9TQC) becomes Match/Open because the exact raw catalog PS observation now resolves an unrecognized normalized label. Description lists both discs/manual/case, but original factory seal/physical condition is not independently established. It is a shadow finding, not approved regular-history replay.
- Another prior97 Tokyo N/A listing becomes non-match because removing the placeholder reveals A++ title residue; it stays Rejected. The16 regular catalog controls are entirely unchanged.
- **All379 material-evidence hashes remain unchanged.** Original spans, observations and scope are retained; no manual decision is widened, reset or persisted by the shadow. Dismissed, watching and inventory-snoozed status counts stay unchanged.

## Potential presentation eligibility (offline only)

The existing actual API `isClosestExcludedCandidate` helper was applied to the shadow records locally, with no database calls. It uses the actual edition/condition/financial qualification logic, but presentation-history context was null, so these are **pre-suppression potential rows**, not final UI counts.

| Cohort | Potential Closest Excluded before / after |
|---|---:|
| Original265 + Mario | 1 / 6 |
| Prior97 | 41 / 39 |
| Regular controls | 0 / 0 |

Current listing/ASIN action suppression, previous presentations, current holds and duplicate actionable-listing guards would still have to run in production. Mario is among the six provisional Open import rows but is explicitly rejected by the release gate. No shadow count authorizes it for Buy List.

## Newly Open shadow records — not purchasing recommendations

| Title | ASIN | eBay ID | Captured landed cost | Stored-input profit / ROI | Disposition |
|---|---|---:|---:|---:|---|
| Pro Evolution Soccer 2012 - PlayStation Portable | B005GM7J4M | 377656806812 | $23.19 | $43.85 / 189.1% | Historical shadow only; current normal pipeline not run |
| Wave Race: Blue Storm | B00005Q8LV | 900097135752 | $85.96 | $51.02 / 59.4% | Historical shadow only; current normal pipeline not run |
| Monopoly - Game Boy Advance | B0002T7ZHA | 920149541277 | $44.94 | $36.69 / 81.6% | Historical shadow only; current normal pipeline not run |
| F-Zero | B00002SVFQ | 940087170614 | $99.99 | $109.40 / 109.4% | Historical shadow only; current normal pipeline not run |
| Tom Clancy's Splinter Cell Double Agent - Gamecube | B000CC58VM | 900081321133 | $40.85 | $11.66 / 28.5% | Historical shadow only; current normal pipeline not run |
| Super Mario Advance [video game] | B00005B8FZ | 920153081093 | $8.90 | $163.76 / 1840.0% | UNSAFE: loose-cartridge retail-package evidence insufficient; release blocked |
| Gran Turismo 2 Greatest Hits Playstation | B07FYS9TQC | 168847018534 | $71.86 | $37.97 / 52.8% | Historical shadow only; current normal pipeline not run |

Splinter Cell's displayed28.5% is an asking-cost ROI in a conditional best-offer scenario that the existing business checker marks passing. It is **not** a buy-now40% clearance. No economic algorithm was changed and no offer was submitted. All rows need normal current pricing/shipping/eligibility/history checks after a future successful gate.

## Remaining exclusions and proposed production cohort

Named-compatible original-import rows still rejected: Brunswick (row28), PES2012(row149) and Shenmue(row458) have unknown shipping/economics; row149 also has a recorded New-condition blocker. 7 Wonders(row178) remains below ROI threshold at32%. Double Switch and F-Zero/PC remain review for independent platform/condition concerns. Tokyo row346 still has leading New residue outside this phase. All per-row reasons are in the shadow JSON.

The initial30 authorized identities and selection reasons are retained in the machine artifact, but **none were replayed**. Any future cohort should correct the missing-value attribution, add only directly affected original Flipmine pairs with an individually documented safe reason, recheck manual decisions/holds and reuse valid evidence under unchanged freshness protections. Do not include Gran Turismo or unrelated regular history in an automatic replay. Preserve all558 source pairs and immutable original evaluations, and use only existing guarded writers when a later release is approved.

## Validation, release and API usage

- **331 Python tests passed**, including12 new Phase1 methods, actual34 captured fixture records, legacy aliases, ambiguous/contradictory platforms, missing names, region/media contradictions, conflicting identifiers, unsupported DS eligibility and Phase2 non-normalization controls. Existing edition/condition/package suites remain green.
- **37 disposable PostgreSQL17 tests passed**:17 Flipmine persistence/progress and20 shared eBay quota tests. Isolated Docker databases, no published database ports and no production database used.
- **11 frontend/API test files passed**, including120 actual Python→API→UI indicator comparisons and existing Buy List/Closest Excluded, scope/history and Flipmine completion contracts. An initial UI-test invocation from web/ could not locate its root-relative Python executable; rerunning from the repository root passed.
- `git diff --check` passed. No frontend source changed, so no web build or deployment was needed to establish this blocked local gate. Unit/database/frontend success does not override the unsafe end-to-end shadow result.
- Marketplace API calls: **eBay0 / Amazon0 / Keepa0**. Four direct public CDN image GETs for Mario; all379 shadow scores blocked HTTP. No fresh provider enrichment, source-sheet reads, purchases, bids, offers or marketplace mutations. No production candidate/opportunity writes.
- Deployment: **not performed**. No commit hash for this uncommitted Phase1 patch; repository baseline is e7748d3, matching worker implementation f82933aad115. No schedule, command, timing, permission, quota, cache or provider setting changed. No AWS task was launched or service retargeted.
- Production reevaluation: **not performed**. Buy List/Closest Excluded before/after replay: **N/A—no replay**. The last prior rollout verification was24/86; those figures were not refreshed or represented as a new live count here. There are **zero newly persisted actionable opportunities** from this task.

## Required next step and Phase2 recommendation

Review a reusable distinction between named-game identity and the **offered New retail physical package** for cartridge/legacy listings whose images or other evidence show loose media. The disposition must retain visual/source provenance, require review when New retail packaging is not established, avoid treating a matching EAN or seller condition flag as proof, preserve manual decisions, and avoid one-game or price-based exceptions. The precise evidence-storage/adjudication path needs review before broadening policy. No automatic image/authenticity feature was built.

Then rerun the same379 snapshots plus explicit loose-cartridge/retail-box controls, verify there are no unsafe Open promotions, and only then revisit worker deployment and guarded targeted replay. Phase2 lexical/publisher/seller-wording changes should remain separate: leading New, publisher suffixes, inventory codes, spelling and token reordering were not implemented and must not be used to bypass this physical-product concern.

## Artifacts and limitations

- `docs/typed_metadata_phase1_shadow_2026-11-25.json`:379 before/after decisions, hashes, per-field comparisons, physical/economic blockers, potential presentation qualification, individual newly Open reviews, planned identities and gateFAIL.
- `tests/fixtures/typed_metadata_phase1_20261125.json`:34 actual Phase1 captures, including the three correctly attributed N/A cases.
- `tests/test_sourcing_typed_metadata.py`:12 new Phase1 regression methods.
- Exact frozen local evaluation inputs: `tmp/metadata-phase1-inputs.pickle` with SHA256 recorded in the machine artifact. Pure evaluators: `tmp/metadata_phase1_shadow.py`, `tmp/metadata_phase1_presentation.cjs`; baseline code copy:`tmp/metadata-phase1-baseline/`. These local temporary captures must be retained for continuation; they are not committed deployment artifacts.

No fresh listing availability, physical authentication, live New-condition eligibility, current profit, comprehensive photo review of every cohort member, production UI verification or live AWS health review is claimed. New shadow Open candidates were inspected individually from captured text/structured data; only Mario's four photos were fetched because they exposed the release-blocking physical-package issue. Stored seller/catalog specifics can be wrong. All evidence and progress/duplicate/manual protections must be checked again in a future normal authorized replay.
