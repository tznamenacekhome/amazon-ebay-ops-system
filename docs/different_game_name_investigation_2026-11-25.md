# Different Game Name exclusions: investigation and proposed correction

Evidence reviewed November 25, 2026 (Pacific). **Investigation only. No production candidate changes, replay, reimport, deployment or matcher changes.** The unrelated MF oversale document remains untouched.

## Executive findings

**108 of the original 265 pairs appear to be MBOP false named-game exclusions; 21 are strongly supported incompatible products. Another 135 have material uncertainty and one lacks usable exact-ASIN identity.** These are conservative retained-text/structured-evidence assessments, not purchasing recommendations or visually authenticated physical-item matches.

| Assessment | Pairs | Share |
|---|---:|---:|
| A: Confirmed / strongly supported incompatible product | 21 | 7.9% |
| B: Apparent MBOP false named-game exclusion | 108 | 40.8% |
| C: Likely named-game match; material uncertainty | 135 | 50.9% |
| D: Insufficient exact-ASIN identity | 1 | 0.4% |

**Potential yield:** 53 of the 108 apparent false exclusions, representing 52 ASINs, have historical diagnostics passing the configured $5 profit / 40% ROI gates. They comprise 27 buy-now, 25 best-offer and one multi-unit scenario. These are not 53 actionable purchases. Thirty-three of the 108 also have retained independent static blocks (including 17 unsupported-platform blocks); 43 have unknown shipping and incomplete economics. None has a linked opportunity. Do not add these ASIN counts to existing inventory demand or sum their theoretical profit as recoverable value.

The largest reusable problems are platform/media residue, seller descriptive wording, publisher attribution, and orthographic/duplicated-number variants. The matching engine commonly preserves the full listing title as the primary identity even after a structured Game Name is treated as a compatible subset; cross-market comparison then requires identical normalized values. This conservatism prevents real mistakes, but also makes harmless extra title text appear to be a different game. Replacing the title wholesale with Game Name would be unsafe: real examples have catalog-derived specifics that contradict the offered item.

## Scope, reconstruction and reconciliation

- Original source tab: `97fc964e-a4f2-43bb-a5ca-90381d1352b8`; 558 original pairs preserved. Current source outcomes are 434 excluded, 118 evaluated, 6 reused, 0 failed/pending.
- There are now **266** persisted primary `game_name_conflict` decisions. Row 238 (Super Mario Advance) was processed after the original analysis. Excluding it reconstructs the original **265 pairs / 265 distinct eBay listings / 236 ASINs**. This reconstruction uses the still-retained primary source decisions and the documented later row-238 retry; a separately versioned original 265-ID export was not found.
- All 265 remain source-ledger excluded for that headline reason; **zero** are linked to an opportunity and **zero** changed source outcomes in the prior targeted edition replay. The earlier stock-prefix examples are not part of this reconstructed cohort.
- Retained candidate, exact seed and source diagnostic records exist for every pair. **264** have sufficient evidence for an A/B/C assessment; **1** has insufficient exact-ASIN identity (D). Having a complete stored payload does not make its assertions reliable.
- The deployed unmodified identity implementation was run **locally on retained inputs only**. It produces 264 conflicts and 1 Review for the original 265. Row 207 (Nintendo Selects Pikmin 2) is the existing correction already improving parser output; the historical source exclusion was not rewritten. Mario is a separate conflict. No candidate economics were recalculated and no live scoring/replay worker was launched.
- Current baseline source matches worker `f82933aad115` for the four relevant identity/edition/package/static-rule files (`git diff` empty); the recent release receipt records worker179/web235. No AWS deployment verification was needed or attempted in this investigation.
- The previous 24 Buy List / 86 Closest Excluded figures are the November 25 rollout verification, **not freshly refreshed presentation counts in this task**. They concern the previously persisted opportunities, not these 265 pre-opportunity exclusions.

## Why the name label is misleading

`general_product_fields` in `integrations/video_game_identity.py` removes a limited set of platform and marketing patterns. Its `PHASE3_PLATFORM` vocabulary is narrower than the platform detector and does not represent several legacy systems. For example it removes Nintendo/Game rather than the full Game Boy Advance phrase, leaving `boy advance`. Other cases leave `game cube`, `sega dreamcast`, `sony psp`, media format words or model aliases. Conversely, unscoped platform substitution can remove a meaningful product word: Double Switch becomes `double`. A longer regex alone is therefore not an adequate design.

`phase3_side` reconciles structured Game Name as a subset of the title but normally retains the longer primary title. `phase3_comparison` then compares that value across Amazon/eBay as a conflict. The title can include NEW, READ DESCRIPTION, publisher suffixes, inventory codes, repeated Roman/Arabic numerals or condition disclosures. `IGNORED_GAME_NAMES` does not include N/A/None/Unknown. `split_game_names` splits commas but does not consistently resolve semicolon-separated competing releases. Structured publisher removal currently handles leading attribution and `by Publisher`, but misses many plain trailing attributions. Amazon-side publisher metadata is also not generally equivalent to eBay-side attribution evidence.

These are shared Python semantics used after Browse or Trading normalization. The cohort uses the saved normalized evidence; this was **not** a fresh live Browse/Trading parity experiment. No provider-specific workaround is proposed.

## Apparent false exclusions: non-overlapping primary causes

| Primary observed cause | Pairs | Representative source rows |
|---|---:|---|
| Seller descriptive wording retained as game identity | 42 | 109 Kingdom Hearts; 286 Elden Ring; 400 Mario Tennis Aces; 491 Destiny |
| Platform/region metadata and platform-word collisions | 28 | 28 Brunswick SNES; 149/180 PES PSP; 347/348 Double Dragon Advance; 508 Mario Kart DS |
| Publisher/brand attribution retained as identity | 20 | 19 Extreme Assault; 20 Hip Hop Dance; 88 FIFA 19; 513 MotoGP |
| Orthography, tokenization or repeated installment notation | 15 | 78 Metal Gear 3D order; 93 Hitman III 3; 175 Accalim typo; 470 Suikoden V 5; 544 Newbie's |
| Edition, package or named-release reconciliation | 2 | 207 Nintendo Selects Pikmin 2; 363 Witcher JC/Jewel Case |
| Source reconciliation or missing-value interpretation | 1 | 346 Tokyo Xtreme Racer 3, Game Name N/A |

Primary counts sum to 108. Secondary concerns overlap and are retained per pair in the appendix. Some C cases also contain obvious parsing residue, but remain C because material product/condition/source evidence has not been resolved. This is deliberately more conservative than counting every identical base-game phrase as a false exclusion.

### Representative distinctions

- **B — Extreme Assault (377670942318 / B0006J1DKG):** PC, Game Name and description support the same named game. `CD-Rom Computer Game Blue Byte` stays in core identity. Stored $368.61 / 1,527% is a best-offer diagnostic against an unusually high $508.66 reference; it needs full pricing/risk review, not automatic promotion.
- **B — Hitman III 3 (147691479318 / B08MG7QWN7):** title repeats the same installment in Roman and Arabic notation; Game Name is Hitman 3. Require equivalence of adjacent duplicate representation, not removal of arbitrary numbers.
- **B — Tokyo Xtreme Racer 3 (346):** N/A is a missing-value placeholder, not an alternate game. Leading New is another contributor. Removing the placeholder must still leave the title, platform and other sources to establish identity.
- **C — Final Fantasy VII Rebirth (147694709601 / B0CJ5XNP16):** named game agrees, but shipping/case damage is a real disclosure. Move disclosure to condition evidence; do not make it disappear from the purchase decision.
- **C — FFXIII-2 rows118/237:** Amazon requires the Limited novella package; a sealed game alone does not establish that book.
- **C — Rune Factory 4 / Special (481), Jewel Master / Cradle of Rome (488), Viva Pinata 2 alias (403):** plausible exact-release aliases or catalog abbreviations, but insufficient corroboration for blanket subtitle deletion.
- **C — sports years (69):** 2004 in an eBay release-format title may be release metadata, but Tiger Woods 2005 is a meaningful sports identity. Require identifier/release corroboration before resolving it.
- **A — GTA Double Pack (860152349717 / B0000DJX7H, row240):** description explicitly sells GTA III only and excludes Vice City, despite a double-pack Game Name.
- **A — Just Dance row505:** Game Name says 2018 while actual title sells 2014 plus Biggest Loser. Never let structured specifics override a contradictory offered product.
- **A — flags/posters rows128/308/386/528:** product-name overlap does not make artwork into software. Demo discs171/176, wrong games127/294/318/517 and NHL97/98 rows292/536 remain blocked.
- **D — B01GW3LR8M / 900115665914:** both catalog and Keepa say Video Game Title 8 while the listing says Dead Rising 4. A Flipmine proposal cannot repair deficient exact-ASIN identity.

## Super Mario Advance, supplemental row238

`920153081093 / B00005B8FZ`: retained title is Super Mario Advance (Nintendo Game Boy Advance, 2001) USA Brand New. Structured Game Name is Super Mario Advance; platform is Nintendo Game Boy Advance; region NTSC-U/C; seller MPN AGB-AMAE-USA. eBay EAN `0045496731397` agrees with retained exact-ASIN Keepa UPC `045496731397` / EAN `0045496731397`. This is strong named-product corroboration.

The current parser produces Amazon `super mario advance` versus eBay `super mario advance boy advance usa`. The exact-ASIN catalog records raw platform Game Boy Advance but normalized_platform is null; the identity platform resolver likewise remains unresolved. This exposes both incomplete span removal and incomplete canonical platform support. The generic DVD-ROM catalog format also needs skepticism for a cartridge product.

The retained description makes a dubious claim about using Super Game Boy with Game Boy Advance to play on a TV. This does not establish a different named game, but lowers confidence in seller prose. Brand New condition1000 and four image references exist; images were not inspected. No factory-sealed/complete-original-package conclusion is made. The supplemental assessment remains **C**, with an identifiable normalization false conflict requiring independent product/condition checks. It is not included in the original265 statistics.

Historical Mario economics: price $8.9, shipping $0.0, landed $8.9; target $226.5; recorded profit 163.76 and ROI 1840.0%, scenario `multi_unit`. These are stored diagnostics, not recomputed profit. Keepa retained drops30/90: 2/14; seed monthly velocity 0.0, owned units 0. No fresh eligibility, physical condition or purchase clearance.

## Business relevance and limitations

| Retained evidence | B: apparent false exclusion | B+C: matching/review pool |
|---|---:|---:|
| Pairs | 108 | 243 |
| Distinct ASINs | 102 | 219 |
| Known stored profit/ROI | 65 | 157 |
| Stored profit+ROI pass | 53 | 137 |
| Distinct ASINs with stored pass | 52 | 128 |
| Missing shipping / incomplete economics | 43 | 86 |

All 43 B / 86 B+C rows lacking economics have an export price below their stored Amazon target: a **gross spread only**, before unknown shipping/fees and without proving profitability. Of the 65 B rows with stored economics, 12 fail one or both configured financial gates. The 53 passes are the first business-priority audit pool, not a promotion list.

Among B+C, 75 have other retained non-name static blocks, 28 specifically unsupported sourcing platforms. Two have positive recorded owned inventory; one C row has ASIN-wide inventory-snooze history (row280/B000HKGD4A), which is not proof that the hold is still active. There are no exact-pair manual action records found and no recorded restricted=true seed flags, but these old booleans do not substitute for current New-condition restriction checks. Historical actions, seller summaries and business reasons are attached per row.

Seed monthly_velocity is zero on 105/108 B rows, yet latest retained Keepa has positive rank drops30 for 53 B rows. These are different evidence sources/time bases; zero seed velocity is not proof of zero demand, and rank drops are not guaranteed sales. The full normal evaluator must resolve demand, stock, risk, eligibility and seller history after any future identity fix.

Every row was last recorded active, but **current availability is unknown for all265**: this investigation made zero eBay/Amazon/Keepa listing calls. Historical availability, pricing and identifier evidence can expire; no stale cache is approved for live purchasing. No total profit sum or inventory-demand sum is claimed.

## Bounded regular catalog history

Sample: latest500 retained candidate rows by last_seen_at, excluding232 import-linked/tagged records, leaving **268 regular candidates / 268 listings / 109 ASINs**. Indexed reads of their retained opportunities returned **6,334 historical opportunity records**, covering281 candidate–ASIN proposals. Of these,2,742 have a stored Different Game Name primary reason, representing **133 listings / 138 listing–ASIN pairs / 62 ASINs**. Repeated runs are records, not independent demand. No full-history scan, rescore or catalog replay was run.

| Overlapping exposure signature | Records | Listings | ASINs | Pairs | Financial-pass pairs | Protected lifecycle records |
|---|---:|---:|---:|---:|---:|---:|
| Edition/package residual signature | 228 | 13 | 11 | 15 | 5 | 182 |
| Orthography/spacing/possessive signature | 238 | 6 | 3 | 6 | 1 | 204 |
| Platform/media residual signature | 11 | 1 | 1 | 1 | 1 | 0 |
| Publisher attribution signature | 146 | 9 | 4 | 9 | 4 | 31 |
| Seller/condition wording signature | 52 | 3 | 3 | 3 | 0 | 50 |

No missing-value Game Name signature was observed in this bounded regular sample. Signature counts overlap and are **not independently adjudicated false-exclusion counts**. Older opportunity evidence can differ from the current candidate payload; publisher/platform/package signatures especially include real mismatches. For example the publisher group includes Fallout4 versus Fallout76, and the platform/media signature is Kung Fu Panda versus Panda-monium Activity CD-ROM. Those must not be called recoverable matches.

Direct regular examples supporting shared defects: Cabelas versus Cabela s Big Game Hunter (236770297609/B000SFK0L6), Steelbook versus Steel Book for Dissidia (257626667356/B074ZQ9F4S), and New Overcooked2 (206136105028/B07DPKYRRL), New Just Dance2016 (158223650182/B00ZE360GG). All six orthography pairs have scoped action history; five of the six are Steelbook/Steel Book variants. Most matching historical records are already dismissed/held. Reuse them as **shadow-only controls**, never reset those decisions.

The sample is recent and retention-biased. It does not represent every search result or historical exclusion, and no population-wide false-negative rate is extrapolated. Raw provenance and every signature record are in the regular-history JSON.

## Proposed implementation phases — not implemented

### Phase1: typed metadata and missing evidence (high priority; medium complexity)

- Address28 B platform/media cases, plus supplemental Mario. Separate complete, corroborated platform/media/region spans into typed evidence; unify canonical legacy-platform vocabulary with backend system detection. Preserve unsupported-platform sourcing eligibility as an independent gate. Explicit region contradictions stay blockers.
- Treat N/A/None/Unknown/Does not apply as missing only in the structured Game Name field (one B observed). Never turn missing into a match; retain title/identifier/platform requirements. Keep competing real Game Name values as source conflict.
- Risks/negatives: Double Switch, Wii Play Motion, meaningful platform-like words, 1942, cross-platform ports and regional releases. Removing platform/region words globally is prohibited. Real conflicting identifiers, Game Name and title remain visible.
- Corroboration: complete known platform phrase plus consistent structured platform and exact catalog or identifier evidence; uncertain legacy mapping stays review. Missing-value change can be a separate small commit, but these rules share typed evidence regressions.

### Phase2: evidence-based lexical and title reconciliation (high priority; medium complexity)

- Fifteen B orthographic/token-order/duplicate-installment cases plus42 seller-wording cases are the primary groups;20 publisher cases have a related but separately auditable attribution policy. Counts are exclusive primary groups, not projected successes.
- Normalize harmless apostrophe/word-boundary equivalence and adjacent Roman/Arabic duplicate installment representations only when Game Name and title agree on the same number. Token reordering such as Metal Gear3D is a separate identifier-corroborated relation, not global word sorting. Preserve V3, X-2, sports years and all meaningful numbers.
- Assign tightly bounded descriptive spans (condition, media, publisher, inventory/seller metadata) with source references and reason; carry condition/contents disclosures to the independent gates. Require the remaining full named title to corroborate structured Game Name and platform, with no contradictory title/description/identifier evidence. Leading New only when a corroborated title proves it is a condition modifier; New Super Mario Bros. and New Carnival Games stay distinct.
- Extend trailing structured Publisher attribution only where the edge span demonstrably equals the publisher/brand, Game Name excludes it, and it is not part of a meaningful franchise. Disney Infinity and genuine subtitle/edition labels are negative controls. Do not expand the current seller stock-code allowlist or blindly strip arbitrary alphanumeric prefixes. Mario Tennis Aces E16003773 and stock-like suffixes must use evidence provenance and remain review when uncertain.
- Regular sample supports six orthography pairs and three simple seller-wording pairs; nine publisher-signature pairs require individual adjudication, not automatic inclusion. Expected business impact is bounded by the53 historical financially-passing B rows and their independent gates.

### Phase3: aliases, named editions, bundle/source reconciliation (separate; medium/high complexity)

- Two B primary cases and135 C cases require careful per-release resolution. Do not blend broad alias expansion with low-risk normalization. Existing Nintendo Selects improvement is already deployed; do not reimplement it. Retain all approved ordinary/re-release policy, condition and exact-ASIN package rules.
- Require exact-ASIN/release identifiers and explicit included contents for incomplete aliases, abbreviations, translations and named bundle configurations. Semicolon multi-values need a source-consistency model, not selection of the convenient value. Publisher attribution is not permission to remove Disney, subtitles, Deluxe, Collector, Day One or regional releases.
- The regular sample has15 package-signature pairs, many genuine incompatibilities and protected rows; zero safe automatic recovery estimate is offered. Review C rows such as FFXIII-2 book, Rune Factory Special, Viva Pinata2, Nintendo Labo kit, and regional releases separately.
- Confirmed mismatches A and deficient catalog D stay excluded. Repair deficient exact-ASIN evidence through the existing catalog workflow before considering D; no Flipmine-derived title override.

## Proposed shadow gate and fixtures

`different_game_name_proposed_fixtures_2026-11-25.json` contains **35 actual captured cases** with baseline inputs/output and **13 synthetic protected distinctions**, plus five mandatory identifier/condition/contents/numeric guard specifications. These are fixture specifications for the next implementation, not newly passing behavioral tests. Include all108 B, Mario, the135 uncertain cases, all21 real mismatches, and the deficient catalog control; combine with the original97 captured edition/condition/package opportunities and accepted controls. Add the six regular spelling pairs and three seller-wording pairs as immutable shadow controls; manually adjudicate attribution examples before adding positives. Deduplicate by exact evidence snapshot + listing + ASIN, retaining materially different captures.

Required negatives include Final Fantasy X/X-2, FIFA23/24, Guitar HeroIII/World Tour, Resident Evil4/5, 007 Legends, 50 Cent, 13 Sentinels, 7 Days to Die, 1942/1943, New Super Mario Bros., New Carnival Games, Disney Infinity and Double Switch. Actual cases include incorrect catalog-derived specifics (Just Dance/GTA), wrong platforms (Payday), demos/posters, condition failures, uncertain identifiers, required book/accessory contents and catalog placeholders. Reuse prior exact-ASIN/edition fixtures for identifier contradictions, AR book, board/package ambiguity, punched UPC and damaged/missing seals.

Gate: no unsafe promotion in any inspected new Match/Open result; accepted controls unchanged except documented safer outcomes; every true mismatch and physical-content/condition block retained; numeric/platform/region/edition distinctions intact; protected decisions/holds unchanged; evidence hashes stable for unchanged inputs; progress reconciles and no duplicate actionable listing or inventory demand. A local parser Match alone never passes the release gate. No production replay until reviewed implementation and successful shadow gate.

## Validation and deliverables

- Existing baseline regression suites: **66 tests passed** (`test_video_game_identity_engine`, `test_sourcing_edition_policy`, `test_edition_shadow_failures`, `test_exact_asin_packages`). No matcher changes and no new behavior was claimed tested.
- JSON/CSV reconciliation checks enforce265 unique original pairs,266 total with Mario, A/B/C/D totals,108B primary causes and53 historical financial passes. A final live read confirmed all558 source-row statuses, candidate/opportunity links and updated_at checkpoints were unchanged from the initial capture; no opportunity was created or modified.
- Detailed JSON appendix contains every investigated pair, normalized source evidence, extracted fields and per-field comparisons, original reasons, independent assessment, secondary concerns, historic scenario economics, identifiers, seller and scoped action history, and recommended handling. CSV is the compact review index.
- No production writes, source-sheet reads, live marketplace enrichment, purchases, offers, bids, migrations, deployments, scheduler changes, threshold/fee/demand changes, quota/provider/TTL changes, or code commits. Report/fixture artifacts only; unrelated MF document preserved.

Files:

- `different_game_name_appendix_2026-11-25.json` —265 original detailed records + separate Mario.
- `different_game_name_appendix_2026-11-25.csv` —265-row review index.
- `different_game_name_regular_history_2026-11-25.json` —bounded regular signature evidence and distinct counts.
- `different_game_name_proposed_fixtures_2026-11-25.json` —actual/synthetic regression and shadow plan.

Limitations: no comprehensive image review, physical authentication, fresh availability/eligibility/pricing refresh or full historical census. Recorded product specifics can be wrong. All economic values remain historical/conditional. A/B/C/D classifications are conservative technical triage on retained evidence and should be revisited when material new evidence arrives. No investigation result authorizes purchase.
